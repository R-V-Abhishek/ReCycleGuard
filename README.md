# ReCycleGuard

An audited, human-reviewed agentic assistant for e-waste Extended Producer Responsibility (EPR)
reconciliation under India's E-Waste (Management) Rules, 2022. It helps a compliance officer
establish, for one producer and reporting period, which obligation balances are supported by
verified evidence, which discrepancies need follow-up, and what a reviewer must confirm. Outputs
are advisory working papers, not legal certification, portal filings, credit trades or fraud
verdicts.

Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), VII Semester, BMSCE. Team 06.

## Final deliverables

- **Report:** [`docs/report/report.tex`](docs/report/report.tex) (department template); build it
  with `latexmk -pdf report.tex` in `docs/report/`. Its tables come from committed run data via
  `uv run scripts/report_tables.py`.
- **Experiment record:** [`docs/checkpoints/mg2/EXPERIMENT_LOG.md`](docs/checkpoints/mg2/EXPERIMENT_LOG.md)
  (every step: hypothesis, change, result, decision),
  [pre-registration](docs/checkpoints/mg2/PREREGISTRATION.md) and
  [evaluation protocol](docs/evaluation/PROTOCOL.md).

## What it does

1. **Evidence pipeline (deterministic).** Original PDFs, CSVs and JSON are hashed and stored
   immutably, extracted into observations with page/row locators, normalised with exact decimal
   arithmetic, and frozen into case and corpus snapshots.
2. **Bounded investigation agent.** A LangGraph workflow (preflight, investigate, draft, verify)
   in which a locally served model plans one audited tool call at a time, assesses the result and
   resolves, continues or abstains, within 12 calls, 600 s and a token budget.
3. **Deterministic gate and human review.** A model's finding is accepted only if computed evidence
   supports it; the verified working paper goes to a reviewer whose decision binds the exact
   report revision.
4. **Evaluation harness.** 48 synthetic dossiers with sixteen fault families, hidden answers kept
   outside the runtime, model-free controls in every session, and an unattended trial queue for a
   GPU PC (Docker) or a free cloud T4 notebook.

## Results in brief

All real-model runs use Qwen3.5-9B Q8_0 on llama.cpp `b12033`. Full tables are in the report.

- **MG1 (single agent, RTX PC).** With the deterministic checks and contradiction gate, v7 reached
  32 of 32 on the tuning set, but model-free controls matched it and the model's share of findings
  was 0. With the checks off, no model variant recovered a judgement fault.
- **MG2 (Retriever + Classifier, Kaggle T4, pre-registered).** No multi-agent arm passed the
  rules-on gate; every arm using the Retriever accepted 25 to 38 false findings in 32 trials.
  Prompt iteration stopped after three versions (log entry 15).
- **Held-out run.** The 24 sealed dossiers ran once, as declared in log entry 15; the result is in
  the experiment log and the report.

The value of the system at this model size comes from the deterministic tools, the gate and human
review; the agent loop is bounded, traceable and safe to fail.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). The deterministic pipeline needs no
model and no secrets.

```sh
uv sync --locked
uv run recycleguard doctor
uv run pytest                              # about 4 min, runs in parallel
uv run scripts/export_schemas.py --check   # contract checks
uv run scripts/export_openapi.py --check
```

HTTP API and browser UI (see [API](docs/api/README.md) and [UI](ui/README.md)):

```sh
uv run recycleguard serve --host 0.0.0.0 --port 8000 --model-config .recycleguard/local-model.json
cd ui && npm ci && npm run dev
```

Use fresh data roots for verification runs. Fixture reviewer identities are synthetic test data,
not team approvals.

## Local model and experiments

- PC with Docker and an NVIDIA GPU: [MG1 Docker runbook](docs/checkpoints/mg1/DOCKER_RUNBOOK.md),
  [MG2 runbook](docs/checkpoints/mg2/RUNBOOK.md).
- Free Kaggle/Colab T4: [cloud runbook](docs/checkpoints/mg2/CLOUD_RUNBOOK.md) and
  [`deploy/cloud/mg2_t4.ipynb`](deploy/cloud/mg2_t4.ipynb). The evaluator's answers are never
  uploaded; scoring runs where `benchmarks/hidden` is.
- Model and server pins: [`deploy/model.env`](deploy/model.env). Weights are not in Git.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/recycleguard/` | intake, extraction, normalisation, snapshots, indexing, retrieval, domain tools, workflow, agents, model gateway, reporting, review, export, API, CLI |
| `ui/` | React interface (consumes the HTTP API only) |
| `benchmarks/` | synthetic dossier generator and evaluation code |
| `scripts/` | trial runner, queue, scoring and table scripts, cloud helpers |
| `deploy/` | Docker files, model pins, cloud notebook |
| `tests/` | unit, integration, contract and acceptance tests |
| `docs/` | [system design](docs/design/SYSTEM_DESIGN.md), [contracts](docs/design/CONTRACTS.md), [dataset card](docs/data/dataset_card.md), [checkpoints](docs/checkpoints/README.md), report |

## Project history

The application was built through checkpoints CP0 to CP4 and model gates MG1 and MG2; each has a
construction and acceptance record in [docs/checkpoints](docs/checkpoints/README.md). The task plan
and ownership are in [implementation plan](implementation%20plan.md); course requirements in
[PROJECT_GUIDELINES.md](PROJECT_GUIDELINES.md). Earlier review artifacts remain available: the
[charter](PROJECT_CHARTER.tex), the [Review 2 design](docs/design/REVIEW_2_DESIGN.tex) and
[presentation sources](docs/presentation/README.md), and the
[domain research](docs/research/DOMAIN_RESEARCH.md).

## Team

| Member | USN | Components |
| --- | --- | --- |
| R V Abhishek (Team Lead) | 1BM23CD047 | orchestration, integration, contracts, CLI, snapshots, model gateway, evaluation harness, experiments |
| H Sampreeth Bhat | 1BM23CD020 | intake, extraction, indexing and retrieval |
| Sushanth S | 1BM23CD063 | normalisation, deterministic domain tools, synthetic dossiers |
| Vedantha Vinay Vernekar | 1BM23CD069 | storage and audit, reports and review, export and replay, evaluator isolation |
