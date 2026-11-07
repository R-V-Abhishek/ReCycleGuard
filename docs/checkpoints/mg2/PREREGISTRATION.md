# MG2 pre-registration

Written and committed **before** any real-model run of the MG2 design. The commit time of this
file is the evidence that the arms, metrics and rules below were fixed before the data existed.
Changing anything here later is a deviation and goes in the table at the end, with the reason.

## Question

On the same pinned local model (Qwen3.5-9B Q8_0, non-thinking, greedy), does a two-role design,
one agent that retrieves and one that classifies, add measurable value over (a) the deterministic
engine alone and (b) the single-agent v7 loop?

A result of "no lift" is a valid result and is reported as such. Architecture and the information
each role is given are the variables; the model, its pins, the gate and the engine are not.

## What each role is

- **Retriever** (agentic RAG). A bounded loop. It decides what to fetch with `find_passages`,
  `search_rules`, `inspect_evidence` and `lookup_locator`; grades each result as sufficient, weak
  or empty; re-queries with new wording, switches source, or stops and abstains. It is the only
  model that reads dossier text. Its output is an evidence bundle of verified claim kinds with
  observation ids, tool-result ids, coverage and abstentions. A claim's quote must occur verbatim
  in the observation shown; quotes are never forwarded.
- **Classifier.** Sees the bundle (kinds and ids, no passage text), the computed facts and the
  family definitions it needs. May call the compute tools (`compute_reconciliation`,
  `trace_certificate`, `compare_return`) in at most three calls, then proposes findings.
- **Judge, not a model.** `gate_finding_proposals` and the claim-support filter. A model
  proposal is gated; it never reaches a report on the model's say-so.

The claim kinds and family meanings come only from `docs/design/CONTRACTS.md` and the public
family definitions. No file under `benchmarks/` is read to write them.

## Arms

| Arm | What runs |
| --- | --- |
| D0 / SC | The deterministic controls (`V0`, `SC`). No model finds anything. |
| S1 | The single-agent v7 loop (FIXED_RETRIEVAL and ADAPTIVE), as in MG1. |
| M1 | Retriever, then a deterministic claim-kind-to-family lookup, then the gate. |
| M2 | Retriever, then the LLM Classifier with compute tools, then the gate. |
| M2-nr | The Classifier alone, with no Retriever. Does the Retriever help? |

M1 is a legitimate result: it is the "bounded classifier" reading of the design. If M2 does not
beat M1, the Classifier call adds nothing and the report says so.

## Arenas

1. **Primary: ablated** (`tuning-16-ablated`). Every deterministic family's findings and
   contradiction rule are off, tool outputs are unchanged. The deterministic control scores 0 of
   21 expected families here, so any recovery is the agents'. Reported as signal families (a tool
   shows a matching issue code) and judgement families (none does), as in MG1 Improvement 2.
2. **Gate: rules on** (`tuning-16`). The no-regression and no-false-positive check. An arm that
   introduces a false positive or drops below 32 of 32 here is not selected.
3. **Held-out: once, at the end** (see below).

## Metrics

- Primary: `supported_case_success`, reported two ways: deterministic-only (SC) and full, with
  `t3_model_influence` beside it. A gain that SC also gets is not an agent gain.
- Co-primary: false positives per case and the invalid-output rate. For each agent the
  schema-valid, semantically-valid and wrong-but-valid rates are reported separately.
- Reported, not pass or fail: model calls, tokens, wall seconds, claims proposed, verified and
  dropped, reader coverage (units read and not read, and why).
- Uncertainty: per-family n is 1 to 2, so there are no per-family intervals. Aggregate success
  uses the existing paired bootstrap against SC. Every arm runs at least two repeats.

## Selection rule

- At most **four** prompt versions, each differing from the baseline `mg2_agents_v1` in one stated
  thing. They are declared in `agents/registry.py` before the first run: v2 drops the
  Retriever's examples, v3 drops the Classifier's family meanings, and v4 is left open for one
  change a result motivates (it is logged before it runs). All are queued from the start.
- A version is chosen by false positives first (fewest), then by recall on the ablated arena,
  then by calls. It must pass the rules-on gate.
- After the choice is made, a person creates the freeze manifest the repository already defines
  (`benchmarks/evaluation/freeze.py`: committed, approved and verified against the exact code and
  protocol). Nothing is tuned after that.

## Held-out policy

- `pilot-0.1` has 24 development dossiers (tuning-16 plus checking-8) and 24 sealed held-out
  dossiers. checking-8 has been looked at, and one change (page loss) was prompted by it; it is
  not a clean test and is reported as a secondary no-regression check only.
- The 24 held-out dossiers are run **once**, after the freeze manifest exists, for D0, SC, S1 (v7) and
  the single best new arm. The queue refuses the job without that file.
- Nobody opens the held-out dossiers before then. The only check beforehand is the seal check
  (`generate --check`).
- The result is reported whatever it is, including a drop of the deterministic engine, which was
  built from tuning-16 failures. No re-tuning follows.

## Run conditions

- One slot count for every arm of a comparison, recorded in each run's configuration name
  (`-s<slots>`). Greedy decoding under parallel slots can differ in the last digits; that is why
  repeats are required and why arms are not compared across slot counts.
- Prompts, configurations and the code revision are pinned by digest in each run. A sweep or
  queue refuses to mix runs after a pin changes.
- Hard limits: a bounded number of Retriever turns, at most three Classifier tool calls, one retry
  per call with the error note, and the existing wall and token budgets. Exhausted budgets are
  recorded as outcomes, never hidden.
- Scripted and recorded runs are plumbing tests. They are never reported as model quality.

## Deviations

| Date | What changed | Why | Effect on the data already collected |
| --- | --- | --- | --- |
| | | | |
