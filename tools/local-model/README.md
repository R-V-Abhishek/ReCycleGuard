# Isolated local inference runtime

Apple Silicon only, and now the backup route. Real-model runs use llama.cpp in Docker on the RTX PC: see
[DOCKER_RUNBOOK.md](../../docs/checkpoints/mg1/DOCKER_RUNBOOK.md).

This uv project pins MLX separately from the base application. The model weights and virtual environment
are ignored by Git.

See the [U01 progress record](../../docs/checkpoints/model-gateway/README.md) for
setup, actual failures, source/weight/runtime pins and cleanup paths.
