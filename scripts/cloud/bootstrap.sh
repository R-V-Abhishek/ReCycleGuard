#!/bin/sh
# Prepare a Linux GPU notebook (Kaggle or Colab) without Docker for one MG2 queue, then check it.
# Runbook: docs/checkpoints/mg2/CLOUD_RUNBOOK.md. Run as root from anywhere:
#
#     sh scripts/cloud/bootstrap.sh docs/checkpoints/mg2/queue/t4/queue-t4-core.json
#
# Safe to run again in a new session: finished steps are skipped. It starts the model server with
# the queue's slot count and ends with `run_queue.py --check`; it never starts the queue itself.
# LLAMA_FROM=image (default: the pinned image's own binary) or source (build tag b12033).
set -eu

REPO=$(cd "$(dirname "$0")/../.." && pwd)
QUEUE=${1:?usage: bootstrap.sh <queue.json>}
MODEL=/work/_model
OPT=/opt/llama
CRANE_VERSION=v0.20.2
MIN_FREE_MIB=1536
mkdir -p "$MODEL" /models/weights /models/provenance
cd "$REPO"
set -a
. deploy/model.env
set +a
ROOT=/models/provenance/$MODEL_SLUG
# One GPU everywhere: Kaggle's T4 x2 would otherwise split the model across both.
export CUDA_VISIBLE_DEVICES=0
SLOTS=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1]))['slots'])" "$QUEUE")

step() { printf '\n== %s\n' "$*"; }
fail() { printf 'STOP: %s\n' "$*" >&2; exit 1; }

step "1/7 GPU"
nvidia-smi -L >/dev/null 2>&1 || fail "no NVIDIA GPU: choose a T4 runtime and run again"
nvidia-smi -i 0 --query-gpu=name,memory.total,driver_version --format=csv | tee "$MODEL/gpu.txt"
{ date -u +%Y-%m-%dT%H:%M:%SZ; cat "$MODEL/gpu.txt"; } >> "$MODEL/gpu-history.txt"
grep -q "T4" "$MODEL/gpu.txt" || fail "not a T4: the cloud shards must all run on one GPU type"

step "2/7 Python environment (uv sync --locked)"
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv sync --locked

step "3/7 llama-server $LLAMA_BUILD"
if [ ! -x "$OPT/llama-server" ]; then
    if [ "${LLAMA_FROM:-image}" = image ]; then
        mkdir -p "$OPT/root"
        if [ ! -x "$OPT/crane" ]; then
            curl -fsSL "https://github.com/google/go-containerregistry/releases/download/$CRANE_VERSION/go-containerregistry_Linux_x86_64.tar.gz" \
                | tar -xz -C "$OPT" crane
        fi
        "$OPT/crane" export "ghcr.io/ggml-org/llama.cpp@$LLAMA_IMAGE_DIGEST" - | tar -x -C "$OPT/root"
        # Absolute symlinks in the image (/lib64, /usr/local/cuda) would point at the host: use
        # the real directories under the extracted root.
        LOADER=$OPT/root/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2
        [ -f "$LOADER" ] || fail "the image has no ld-linux; rm -rf $OPT, rerun with LLAMA_FROM=source"
        CUDA_LIB=$(ls -d "$OPT"/root/usr/local/cuda-*/targets/x86_64-linux/lib 2>/dev/null | head -n 1)
        # The host driver's libcuda comes first; the image's own libraries (and glibc) after it.
        HOST_CUDA=$(ldconfig -p | awk '/libcuda.so.1 /{print $NF; exit}')
        for dir in /usr/lib64-nvidia /usr/local/nvidia/lib64 /usr/lib/x86_64-linux-gnu; do
            [ -n "$HOST_CUDA" ] || { [ -e "$dir/libcuda.so.1" ] && HOST_CUDA=$dir/libcuda.so.1; }
        done
        [ -n "$HOST_CUDA" ] || fail "no host libcuda.so.1 found"
        LIBS="$(dirname "$HOST_CUDA"):$OPT/root/app:$CUDA_LIB:$OPT/root/usr/lib/x86_64-linux-gnu"
        # ggml finds its backend libraries in the working directory, since the executable is ld-linux.
        cat > "$OPT/llama-server" <<EOF
#!/bin/sh
cd $OPT/root/app
exec $LOADER --library-path $LIBS $OPT/root/app/llama-server "\$@"
EOF
        echo "image $LLAMA_IMAGE_DIGEST" > "$MODEL/llama-provenance.txt"
    else
        git clone --depth 1 --branch "$LLAMA_BUILD" https://github.com/ggml-org/llama.cpp "$OPT/src"
        cmake -S "$OPT/src" -B "$OPT/src/build" -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75 \
            -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
        cmake --build "$OPT/src/build" --target llama-server -j "$(nproc)"
        ln -sf "$OPT/src/build/bin/llama-server" "$OPT/llama-server"
        echo "source $LLAMA_BUILD (not the pinned image binary)" > "$MODEL/llama-provenance.txt"
    fi
    chmod +x "$OPT/llama-server"
fi
"$OPT/llama-server" --version 2>&1 | tee "$MODEL/llama-version.txt"
grep -q "${LLAMA_BUILD#b}" "$MODEL/llama-version.txt" || fail "llama-server is not build $LLAMA_BUILD"
"$OPT/llama-server" --list-devices 2>&1 | tee "$MODEL/llama-devices.txt"
grep -qi "cuda" "$MODEL/llama-devices.txt" \
    || fail "llama-server sees no CUDA device; rerun with LLAMA_FROM=source after rm -rf $OPT"

step "4/7 pinned weights (about 10 GB, checked against the manifest)"
ln -sfn "$REPO/deploy" /deploy
[ -f "$ROOT/download-manifest.json" ] \
    || uv run --no-project --with "huggingface_hub>=0.34,<1" python deploy/download.py
CONFIG=$(uv run scripts/configure_local_model.py --llama-cpp "$ROOT" --slots "$SLOTS" | sed 's/.*: //')
echo "configuration: $CONFIG"

step "5/7 model server with $SLOTS slots"
cat > "$MODEL/start.sh" <<EOF
pkill -f "$OPT/root/app/llama-server|$OPT/src/build/bin/llama-server" || true
sleep 2
cd $REPO
set -a; . deploy/model.env; set +a
CUDA_VISIBLE_DEVICES=0 SLOTS=$SLOTS LLAMA_SERVER=$OPT/llama-server nohup python3 deploy/start_model.py >> $MODEL/server.log 2>&1 &
EOF
sh "$MODEL/start.sh"
i=0
until curl -fs http://127.0.0.1:8766/health >/dev/null 2>&1; do
    i=$((i + 1))
    [ "$i" -le 90 ] || fail "server not healthy after 15 minutes; read $MODEL/server.log"
    sleep 10
done
python3 -c "import json, sys; f = json.load(open(sys.argv[1]))['server_flags']; \
assert f[f.index('--parallel') + 1] == sys.argv[2]" "$ROOT/server-session.json" "$SLOTS" \
    || fail "server-session.json does not record --parallel $SLOTS"

step "6/7 probe and VRAM"
uv run recycleguard model probe --config "$CONFIG"
nvidia-smi -i 0 --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | tee "$MODEL/vram.txt"
FREE=$(awk -F', ' '{print $2 - $1}' "$MODEL/vram.txt")
[ "$FREE" -ge "$MIN_FREE_MIB" ] || fail "only $FREE MiB free with $SLOTS slots; see the runbook, step 'Slots'"

step "7/7 queue check"
uv run scripts/run_queue.py --check "$QUEUE"
printf '\nReady. Start the queue as the runbook says.\n'
