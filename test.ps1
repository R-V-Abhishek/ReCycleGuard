uv python install 3.12
uv sync --locked --python 3.12
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pytest
uv run --no-sync scripts/export_schemas.py --check
uv run --no-sync recycleguard doctor