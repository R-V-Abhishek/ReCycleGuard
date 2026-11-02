#!/bin/sh
# Copy the git-ignored evaluator data into its volume. Usage: scripts/docker/import-hidden.sh <dir>
set -eu
source_dir=$(cd "${1:?usage: import-hidden.sh <path to benchmarks/hidden>}" && pwd)
for required in s06-dev-0.1/clean pilot-0.1/oracle; do
    [ -d "$source_dir/$required" ] || { echo "missing $required in $source_dir" >&2; exit 1; }
done
docker compose run --rm --no-deps --entrypoint sh \
    --volume "$source_dir:/import:ro" trials -c 'cp -a /import/. /repo/benchmarks/hidden/'
echo "Imported $source_dir into the evaluator volume."
