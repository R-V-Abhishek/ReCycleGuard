#!/bin/sh
# Every check, in order, without stopping at the first failure. Exit is non-zero if any failed.
status=0
run() {
    echo "=== $*"
    "$@" || status=1
}
run ruff check .
run ruff format --check .
run python scripts/export_schemas.py --check
run python scripts/export_openapi.py --check
run pytest
cd ui || exit 1
run npm run typecheck
run npm test
run npm run build
exit $status
