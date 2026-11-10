#!/bin/sh
# Keep /work across notebook sessions. Runbook: docs/checkpoints/mg2/CLOUD_RUNBOOK.md.
#
#     sh scripts/cloud/persist.sh restore <folder>   # once, before bootstrap: <folder>/work -> /work
#     sh scripts/cloud/persist.sh save <folder>      # one copy: /work -> <folder>/work
#     sh scripts/cloud/persist.sh every <folder>     # a copy every 10 minutes, until killed
#
# Nothing is ever deleted at the destination. Ledgers are copied last, so every result and bundle
# a copied ledger names is already there, and a line torn by a copy during a write is dropped.
set -eu

WORK=${RECYCLEGUARD_WORK:-/work}
ACTION=${1:?usage: persist.sh restore|save|every <folder>}
FOLDER=${2:?usage: persist.sh restore|save|every <folder>}
command -v rsync >/dev/null 2>&1 || { apt-get -qq update && apt-get -qq install -y rsync; }

copy() {
    mkdir -p "$2"
    # The model server's log and binaries are per machine; only the records move. Exit 24 means a
    # file vanished mid-copy (a running trial's SQLite -wal/-shm); the next copy takes what remains.
    rsync -a --exclude ledger.jsonl --exclude _model/server.log "$1/" "$2/" || [ $? -eq 24 ]
    rsync -a --include '*/' --include ledger.jsonl --exclude '*' "$1/" "$2/" || [ $? -eq 24 ]
    find "$2" -name ledger.jsonl -exec python3 -c '
import sys
for name in sys.argv[1:]:
    raw = open(name, "rb").read()
    if raw and not raw.endswith(b"\n"):
        open(name, "wb").write(raw[: raw.rfind(b"\n") + 1])
        print(f"dropped a torn last line in {name}")
' {} +
}

case $ACTION in
restore) [ -d "$FOLDER/work" ] && copy "$FOLDER/work" "$WORK" || echo "nothing to restore in $FOLDER" ;;
save) copy "$WORK" "$FOLDER/work" ;;
every)
    while :; do
        copy "$WORK" "$FOLDER/work"
        date -u +"saved %Y-%m-%dT%H:%M:%SZ"
        sleep 600
    done
    ;;
*) echo "usage: persist.sh restore|save|every <folder>" >&2; exit 2 ;;
esac
