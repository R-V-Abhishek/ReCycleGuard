# MG2: a Retriever and a Classifier (design)

Status: built and tested with scripted ports and the loopback fixture server. No real model has run
on it, so nothing here is a quality result. The arms, metrics and selection rule are fixed in
[PREREGISTRATION.md](PREREGISTRATION.md); what was tried and why is in
[EXPERIMENT_LOG.md](EXPERIMENT_LOG.md). Branch `codex/multi-agent-mg2`.

## Why this shape

The MG1 results (`../mg1/FAILURE_ANALYSIS.md`) say the deterministic engine carries the success:
the model-free controls score what the model arms score, and with every rule off the single-agent
loop recovered 0 of 21 faults. The model never saw document text, and it did not propose a finding
even when an issue code was in front of it. Two things were missing, and each becomes a role:

- something that **retrieves**: decides which passages to read, reads them, grades what came back,
  and tries again or stops;
- something that **classifies**: takes verified facts and says which family of problem they show.

A first attempt (a chunked Reader and an Analyst, `EXPERIMENT_LOG.md` entry 9) did not survive its
own review. The Analyst only looked up a family for each claim kind, and neither role was told the
problem it solves. This design fixes both.

## The two roles

```
observations (prose) ──► Retriever ──► verified claims (kind + id, no text) ─┐
   list_passages · read_passages · search_rules          │                    │
   grade every result, re-query, or stop (≤ 5 turns)     ▼                    ▼
                                                  quote verifier        Classifier ──► findings
 computed facts · calculation ids · bucket and certificate ids ─────────►  (≤ 3 compute calls,
                                                                            no passage text)
                                                                                │
                                          finding gate (existing, deterministic) ┘──► report
```

**Retriever (agentic RAG).** Sees only text. It lists the passages (id, length, first words),
chooses up to three to read, reads them, and writes claims `{kind, observation_id, quote}` for the
kinds it recognises. After each result it grades the result `SUFFICIENT`, `WEAK` or `EMPTY`; after a
weak or empty result it must change something, because a repeated call is refused. `search_rules`
lets it pull the public rule text when a passage cites a period, notice or scheme. A second search
counts as a reformulation. It stops by choosing `FINISH`, or at the turn cap, and says which.

**Classifier.** Sees only numbers, codes and ids: the computed facts, the verified claims as kind,
family and observation id, and the results of its own tool calls. It may call `compute_reconciliation`
or `trace_certificate`, with ids copied from the facts, before it proposes findings. It cannot read
a passage, so an instruction hidden in a dossier cannot reach the model that runs compute tools.

**Not agents.** The quote verifier, the claim-support filter and `gate_finding_proposals`. A
proposal in a text-derived family needs a verified claim of its kind on a cited observation; every
proposal then passes the gate, which rejects one the swept deterministic universe contradicts. A
deterministic finding always wins its family.

## What each role is told

Both prompts are cut from one registry, `src/recycleguard/agents/registry.py`, and written to
`prompts/` by `scripts/write_mg2_prompts.py`. A test fails when a committed file differs from what
the registry produces.

| | Retriever | Classifier |
| --- | --- | --- |
| The problem | Code computed every number; you only mark which passages are about which kind | Code computed the facts and checked the claims; you decide which families they show |
| Tools | `list_passages`, `read_passages`, `search_rules` | `compute_reconciliation`, `trace_certificate` |
| Definitions | The nine claim kinds, each with a definition and one synthetic example | The family meanings (from `reporting.briefs.FAMILY_MEANING`) and the status rules |
| Rules | Quote verbatim, 3 to 160 characters; grade, then change something | Cite only a verified claim's observation or a calculation id; words only, no digits |
| Not told | Statuses, abstention reasons, other agent's rules | Quoting rules, the tool list of the Retriever, passage text |

The kinds, meanings and examples come from the public family definitions. The examples are written
from those definitions, never copied from a dossier or from `benchmarks/`.

Three prompt versions are registered before any run (`PREREGISTRATION.md`): v1 baseline, v2 drops
the Retriever's examples, v3 drops the Classifier's family meanings.

## Arms

| Arm | Runs | Why |
| --- | --- | --- |
| `RETRIEVER_LOOKUP` (M1) | Retriever, then a fixed kind-to-family lookup | The bounded-classifier reading: no second model call |
| `RETRIEVER_CLASSIFIER` (M2) | Retriever, then the Classifier | The full design |
| `CLASSIFIER_ONLY` (M2-nr) | The Classifier with no claims | Does the Retriever help at all? |
| single agent (S1) and the controls | As in MG1 | The comparison |

## Bounds

Five Retriever turns, three Classifier tool calls (a fourth reply must propose), one retry per
model call with the error note, and the run's existing model-call, action and token budgets. A
refused call uses the turn. An exhausted budget or an unusable reply ends that role with what it
had; the deterministic findings are never affected. A turn cap is stated in the coverage and is
not treated as a failure.

## Where it plugs in

- `agents/` holds the pure parts: `models.py` (boundary models), `passages.py` (text units and the
  quote check), `retriever.py` and `classifier.py` (the two loops), `registry.py` (what each role
  is told) and `pipeline.py`.
- `WorkflowRunner._investigate_agents` supplies the model call and the audited tool call for each
  turn, so retries, budgets, audit and resume are the single-agent loop's own.
- Phases `RETRIEVE` and `CLASSIFY` in `local_model.py`; the V1 and V2 prompt pins are unchanged.
- `list_passages` and `read_passages` join the runner's allowed operations. They are read-only,
  registered only for these arms, and return no evidence references, so reading a passage never
  makes it citable.
- `AgentFacts` carries the facts, the ids each compute tool accepts, and the case's reporting period.
  Under ablation the facts use the same ablated sweep the report is drafted from.

## Limits

- Scripted and fixture replies check plumbing, audit and the gate. They say nothing about whether a
  9B model retrieves or classifies well.
- n=16 with one or two cases per family: no per-family intervals.
- The deterministic checks were built from tuning-16 failures, so the engine's own generalization is
  measured only on the sealed held-out set, once, at the end.
- A 9B model picks passages from their first 100 characters. If that is not enough, coverage will
  show unread passages and a lower recall; that is a finding, not a bug to hide.
