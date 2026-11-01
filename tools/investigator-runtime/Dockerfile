# Build context is prepared by prepare_build_context: no repository/test/oracle tree.
FROM ghcr.io/astral-sh/uv:0.9.7 AS uv
FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --locked --no-dev --no-install-project
COPY wheels/ /wheels/
RUN uv pip install --python /opt/venv/bin/python --no-deps /wheels/*.whl

FROM python:3.12-slim-bookworm
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/runtime \
    RECYCLEGUARD_DATA_ROOT=/runtime RECYCLEGUARD_INTAKE_ROOT=/visible \
    RECYCLEGUARD_OUTPUT_ROOT=/runtime/output RECYCLEGUARD_MODE=test \
    RECYCLEGUARD_ENABLE_TEST_ADAPTERS=true
WORKDIR /runtime
USER 10001:10001
ENTRYPOINT ["/opt/venv/bin/python", "-m", "recycleguard.isolated_runtime"]
