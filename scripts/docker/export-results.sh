#!/bin/sh
# Copy what may be committed for one session, or for a prompt sweep and each of its sessions.
# Bundles, attempts and data roots hold dossier data and stay in the volume.
# Usage: scripts/docker/export-results.sh <name> <destination>
set -eu
name=${1:?usage: export-results.sh <name> <destination>}
mkdir -p "${2:?usage: export-results.sh <name> <destination>}"
destination=$(cd "$2" && pwd)
docker compose run --rm --no-deps --entrypoint sh --volume "$destination:/export" trials -c "
    set -eu
    export_one() {
        cd /work
        if [ ! -d \$1 ]; then
            echo \"skipped \$1: not run yet\"
            return 0
        fi
        mkdir -p /export/\$1
        for item in ledger.jsonl results protocol.json backend.txt summary.json \
            sweep.json sessions configs.json compare.csv compare.json; do
            [ ! -e \$1/\$item ] || cp -R \$1/\$item /export/\$1/
        done
        find \$1 -maxdepth 1 -name '*.log' -exec cp {} /export/\$1/ \;
        for extra in scores tables; do
            [ ! -d \$1-\$extra ] || cp -R \$1-\$extra /export/
        done
        [ -d \$1/trials ] || return 0
        cd \$1
        find trials -name isolation-evidence-real.json -o -name isolation-inspect.json |
            while read -r path; do
                mkdir -p /export/\$1/isolation/\$(dirname \$path)
                cp \$path /export/\$1/isolation/\$path
            done
    }
    export_one $name
    if [ -f /work/$name/sessions ]; then
        for session in \$(cat /work/$name/sessions); do
            export_one \$session
        done
    fi
"
echo "Exported $name to $destination."
