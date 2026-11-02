# Isolated local inference runtime

Apple Silicon development only. This uv project pins MLX separately from the base
application. The model weights and virtual environment are ignored by Git.

See the [U01 progress record](../../docs/checkpoints/model-gateway/README.md) for
setup, actual failures, source/weight/runtime pins and cleanup paths. The current
native server has **not** passed full investigator compatibility. Work is paused.
