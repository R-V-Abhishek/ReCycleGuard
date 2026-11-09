#!/bin/sh
# Copy what may be committed for one session, or for a prompt sweep and each of its sessions.
# Bundles, attempts and data roots hold dossier data and stay in the volume.
# Usage: scripts/docker/export-results.sh <name> <destination>
# With RECYCLEGUARD_WORK=<folder> it copies from that folder instead of the Docker volume, for a
# work folder brought back from a notebook (docs/checkpoints/mg2/CLOUD_RUNBOOK.md).
set -eu
name=${1:?usage: export-results.sh <name> <destination>}
mkdir -p "${2:?usage: export-results.sh <name> <destination>}"
destination=$(cd "$2" && pwd)
if [ -n "${RECYCLEGUARD_WORK:-}" ]; then
    work=$(cd "$RECYCLEGUARD_WORK" && pwd)
    run() { sh -c "$1"; }
    export_root=$destination
else
    work=/work
    run() { docker compose run --rm --no-deps --entrypoint sh --volume "$destination:/export" trials -c "$1"; }
    export_root=/export
fi
run "
    set -eu
    export_one() {
        cd '$work'
        if [ ! -d \$1 ]; then
            echo \"skipped \$1: not run yet\"
            return 0
        fi
        mkdir -p '$export_root'/\$1
        for item in ledger.jsonl results protocol.json backend.txt summary.json \
            sweep.json sessions configs.json compare.csv compare.json; do
            [ ! -e \$1/\$item ] || cp -R \$1/\$item '$export_root'/\$1/
        done
        find \$1 -maxdepth 1 -name '*.log' -exec cp {} '$export_root'/\$1/ \;
        for extra in scores tables reasoning; do
            [ ! -d \$1-\$extra ] || cp -R \$1-\$extra '$export_root'/
        done
        [ -d \$1/trials ] || return 0
        cd \$1
        find trials -name isolation-evidence-real.json -o -name isolation-inspect.json |
            while read -r path; do
                mkdir -p '$export_root'/\$1/isolation/\$(dirname \$path)
                cp \$path '$export_root'/\$1/isolation/\$path
            done
    }
    export_one $name
    if [ -f '$work'/$name/sessions ]; then
        for session in \$(cat '$work'/$name/sessions); do
            export_one \$session
        done
    fi
"
echo "Exported $name to $destination."
