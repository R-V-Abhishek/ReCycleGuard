# Reproducing the results

Status: **draft, not yet executed on a clean clone.** Execute it end to end at CP7 and keep the
transcript. Python commands use `uv`. Native model inference needs an Apple Silicon Mac; everything
else is portable.

## 1. Without the model (any OS)
```sh
git clone <repository> && cd recycleguard && git checkout <submission tag>
uv sync --locked
uv run pytest -m "not slow and not model"      # fast suite; full suite: uv run pytest
uv run python -m benchmarks.generator.generate --visible-root tests/fixtures/visible \
  --hidden-root benchmarks/hidden --heldout-root benchmarks/heldout/visible --check
uv run python scripts/verify_freeze.py docs/checkpoints/checkpoint-5/freeze.json
```
`generate --check` must match `benchmarks/pilot/heldout_seal.json`. `verify_freeze.py` recomputes
every digest in the CP5 freeze and lists any difference.

## 2. Rebuild tables from saved outputs (no model, no weights)
```sh
PYTHONPATH=. uv run scripts/score_trials.py <trial-output> <oracle-root> tests/fixtures/visible <scores-dir>
PYTHONPATH=. uv run scripts/make_tables.py <trial-output> <scores-dir> <tables-dir>
```
The CSVs are byte-identical on every run. The report's tables are these files.
To get LaTeX tabulars for the report from these CSVs, run
`uv run scripts/tables_to_latex.py <tables-dir> <out-dir>` and `\input` the generated files; do not retype values.

## 3. Inspect a saved run
Each real-model trial's request and response blobs are retained in its exported bundle:
`recycleguard audit verify-package` checks it and `recycleguard replay-package` inspects it without a database or
model. `RecordedReplayModelPort` (`src/recycleguard/recorded_port.py`) serves saved responses only
for identical requests, in test mode; a replay is not a new trial.

## 4. A new real-model run (optional, Apple Silicon)
Follow `docs/checkpoints/mg1/MODEL_TEST_HANDOFF.md` setup: pinned weights
`mlx-community/Qwen3.5-9B-4bit` revision `8b2b98c00a6b4d291155e4890773ca8f769aee53`, MLX-LM 0.32.2,
`tools/local-model/serve.py`, then `scripts/run_trials.py` with a protocol file. A new run is a **new
trial**, not a reproduction: decoding is greedy but unseeded and outputs vary between identical runs
(measured in MG1). Weights are not included in the archive.

## 5. What is not reproducible here
- Model outputs from a fresh run.
- The R02/R08 source PDFs if they are omitted for rights reasons (see `docs/data/source_data_card.md`).
- The UI demo against a live model without the weights; use the recorded replay.

No API keys are needed: the model is local and the endpoint is loopback only.
