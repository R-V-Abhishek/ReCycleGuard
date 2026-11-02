#!/bin/sh
# Copy what may be committed for one session. Bundles, attempts and data roots hold dossier data
# and stay in the volume. Usage: scripts/docker/export-results.sh <name> <destination>
set -eu
name=${1:?usage: export-results.sh <name> <destination>}
mkdir -p "${2:?usage: export-results.sh <name> <destination>}"
destination=$(cd "$2" && pwd)
docker compose run --rm --no-deps --entrypoint sh --volume "$destination:/export" trials -c "
    set -eu
    cd /work
    mkdir -p /export/$name
    for item in ledger.jsonl results protocol.json backend.txt summary.json; do
        [ ! -e $name/\$item ] || cp -R $name/\$item /export/$name/
    done
    for extra in scores tables; do
        [ ! -d $name-\$extra ] || cp -R $name-\$extra /export/
    done
    cd $name
    find trials -name isolation-evidence-real.json -o -name isolation-inspect.json |
        while read -r path; do
            mkdir -p /export/$name/isolation/\$(dirname \$path)
            cp \$path /export/$name/isolation/\$path
        done
"
echo "Exported $name to $destination."
