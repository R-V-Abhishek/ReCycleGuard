# Document 6: Viva and Q&A preparation

Every member must be able to explain the whole system, not only their own component. Answers below come
from the repository and from the development runs (prompt v9, 24 development dossiers). Held-out results do not
exist yet; do not quote any. If asked for a number that is not here, say it has not been measured.

## The five-minute explanation

1. **Problem.** A compliance officer at an electronics producer must show that the EPR obligation for each
   metal is met by usable credits. Records are in PDFs, ledgers and a portal export and disagree in specific
   ways (double-counted transfers, unit mixes, cancelled certificates, payment without a portal transfer).
2. **Decision supported.** Which discrepancy to investigate next, and what verification or action the evidence
   supports. The output is an advisory working paper, never a filing, a legal verdict or a fraud finding.
3. **Why an agent.** What to check next depends on what the last check showed, and the number of useful steps
   varies. A script cannot choose; a single prompt cannot calculate or cite reliably.
4. **How it works.** Deterministic preflight, then a bounded loop: the model PLANs one check from six read-only
   tools, a tool runs it (exact decimal arithmetic or retrieval), the model ASSESSes the result, and the loop
   continues, resolves or abstains. A gate and a verifier decide what is allowed into the report. A human
   reviewer decides the report.
5. **Evidence it works, and where it does not.** Reliability on the development set is complete (48 of 48
   runs, 100% schema-valid replies, all sandbox probes denied, correct recovery from killed processes). Quality is
   weak: reconciliation is exact because it is deterministic, but few fault families were found and the model's
   one accepted finding was wrong. The held-out A/B result is pending.

## System and design

**Q: What is the division of labour between the model and the code?**
Code owns every quantity, date check, citation check and the arithmetic. The model only chooses the next check
and reads the result, and it may attach one finding proposal that passes a gate. It cannot approve evidence,
write to the database, run code or change quantities.

**Q: Why not let the model do the reconciliation directly?**
A small quantised model cannot be trusted to add decimals or to cite exactly. The reconciler uses exact decimal
arithmetic per bucket (producer, liability year, metal, unit): `gap = required - supported`.

**Q: What are the agent's tools?**
Six, all read-only: `inspect_evidence`, `lookup_locator`, `trace_certificate`, `compute_reconciliation`,
`compare_return`, `search_rules`. The runner holds the whitelist; any other operation ends the run.

**Q: Where is planning visible?**
The PLAN call returns a plan (objective, hypotheses, proposed checks, expected evidence, stopping criteria) and
an action or a stop. The ASSESS call returns a verdict (supports, refutes, weak, no progress, unknown) and a
disposition. A plan record is stored before each action, an assessment after it, and each turn manifest says
whether the plan changed.

**Q: What is the rule linking verdict and disposition?**
`RESOLVE` requires `SUPPORTS`. Any other verdict forces `CONTINUE` or `ABSTAIN`.

**Q: What stops the loop?**
Budgets (12 model calls, 600 s, token reservations checked before dispatch), per-finding limits (8 tool calls,
2 reformulations, 1 retry, 1 report repair), a fingerprint of finding, tool and arguments that stops an exact
repeat, and the stop reasons the model can give.

**Q: Why LangGraph, and why does every node end the graph?**
LangGraph gives a checkpointed state graph. Each call to the runner executes one turn and commits it with a
compare-and-swap version, so a killed process resumes from the last committed turn without repeating a tool.

**Q: How do you handle a model call whose outcome is unknown?**
The intent is written first and every attempt is retained. An uncertain outcome is never retried blindly,
because a repeat could duplicate a side effect. In the server-kill test the trial ended failed with a single
attempt.

**Q: What is agentic about the RAG?**
Retrieval is a tool the agent chooses. Results are graded for authority, temporal applicability and direct
support. Weak results allow at most two reformulations; unresolved applicability escalates instead of guessing.
Passages that are only leads cannot support a definitive statement.

**Q: Why BM25 and not embeddings?**
The corpus has two sources and the evaluated system uses SQLite FTS5 with BM25. Dense retrieval is optional in
the design and is not part of the evaluated system. No claim is made about retrieval quality on a larger corpus.

**Q: What is the finding gate?**
A model finding proposal is accepted only if every citation is evidence this run's tools returned, its text
has no digits, prohibited claims or authority wording, and a "clean" finding is backed by a reconciliation
from this run with nothing pending. Rejections are kept with reasons.

**Q: What is the difference between V0, SC, V1 and V2?**
V0: deterministic, no model. SC: scripted control, never reported as model performance. V1: fixed retrieval
with the real model (a pre-declared sequence of checks; the model assesses). V2: adaptive (the model chooses
each check). The primary comparison is V2 against V1, same tools, corpus and budget.

## Data, safety and evidence

**Q: What data did you use?**
48 synthetic dossiers (24 development, 24 held-out) built from a typed world model, 16 fault families, 8
combinations per split. Firms and documents are fictional and watermarked. Real producer data was not used.

**Q: How do you know the held-out set was not used for tuning?**
It is outside the repository, sealed with a SHA-256 manifest, and the prompt was tuned only on a 16-case tuning
split. An 8-case checking split was run once at the end. The held-out run requires a freeze record that
verifies against the code.

**Q: Who produced the reference answers, and how independent are they?**
The generator's world model, recomputed from visible bytes and reviewed by a coding agent. No person
hand-reviewed them. The same person built the system, ran the trials and wrote the evaluator; blind teammate
scoring and a separate scorer process reduce this and do not remove it. Say this unprompted.

**Q: How do you handle prompt injection?**
Dossier and retrieved text are data. They enter the prompt as escaped JSON, the system prompt says to treat
the user message as data, the tool list is fixed and read-only, and a benchmark family (F16) puts an override
instruction in an invoice remark. On the development set no proposal acted on injected text.

**Q: What does the sandbox do, and what does it not do?**
Real-model trials run the investigator from an installed wheel under a macOS `sandbox-exec` profile with
loopback-only network and no evaluator paths. Before the investigator starts, probes of forbidden reads,
writes, network, imports and environment must all be denied. It is a host-level restriction on one laptop and
not a security proof; the mechanism is deprecated.

**Q: A probe was changed during testing. What happened?**
A list probe on a regular file always fails with ENOTDIR whatever the profile says, so it could not be
"denied". List probes now run on directories only; every path still gets a read probe. No probe was removed
and the profile was not weakened.

**Q: What is the audit trail?**
An append-only, hash-linked event store: the exact request and response of every model call, tool intents and
results, plan and assessment records, turn manifests. The review decision is bound to the report and input
digests. Exports can be replayed without the model.

## Results and honesty

**Q: What did the development runs show?**
Reliability (prompt v9, 48 trials): 48 of 48 not failed; schema-valid 132 of 132 (V1) and 43 of 43 (V2) per
call; no timeouts; no forbidden actions; all 1,630 probes denied. V1 mean wall time 134 s (target 120 s); V2
62 s. Success on the strict primary metric was low: 2 of 24 per variant, of which one was a correct preflight
stop. Reconciliation was exact in every reviewed trial.

**Q: Did the model help?**
Not yet. 16 proposals in V1, 14 rejected for authority wording, 1 for an unknown reference, and the one
accepted finding was a false positive. The findings that were found came from deterministic checks. V2 made no
proposals.

**Q: Why did the prompt go through nine versions?**
Each version fixed the failure seen on development cases: invented observation ids (v5, v6), a model that never
proposed because it was shown a refutation example and had no definition of a problem (v7), a flat example
that made the model put its proposal at the top level (v8, 40 invalid attempts), and nesting the example (v9).
The failure moved to the next layer each time; the success rate did not change.

**Q: Is V2 better than V1?**
Unknown for held-out data. On the development set V2 used about a third of the model calls and was not more
successful. The hypothesis H1 (V2 higher success at comparable cost) is stated as a hypothesis, and a negative
result will be reported as such.

**Q: Why is the success rate so low if reconciliation is exact?**
The primary metric requires every bucket exact and the emitted fault families to equal the expected families
with no miss or extra. Reconciliation passes; most trials fail on missed findings, which come from the model
rarely proposing and the gate refusing wording that contains authority words.

**Q: Which MG1 criteria were not met?**
V1 mean wall time (134 s against 120 s, a speed issue on this laptop) and "at least one correct model
finding". The gate has been approved only conditionally by the lead; no teammate acknowledgement is recorded.

**Q: What would you do with more time?**
Teach the prompt the substitutes for the authority-list words, tune on a faster machine, run the frozen
held-out experiment with repeats and the blind rubric, use independently written dossiers, widen the corpus,
and measure cost.

**Q: Which concepts are not demonstrated?**
Multi-agent collaboration (a collector and auditor is only a design option) and memory across runs. Within a
run, state and the previous rejection reason are passed back.

**Q: What would you say a regulator or auditor can rely on?**
The arithmetic and the audit trail. Not the model's reading of rules without human review.

## Component questions by owner

- **Intake, extraction, index, retrieval (Sampreeth):** how a PDF page becomes observations with locators; what
  incomplete coverage means; how FTS5 and the grader work; how temporal filtering is applied; why the corpus is
  two sources and what rights state they have (review required, manifest-only release).
- **Reconciler, tools, generator (Sushanth):** bucket arithmetic; why pending is not subtracted; why portal
  balance is comparison-only; the 16 fault families and how recipes inject them; how the splits are made disjoint.
- **Orchestration and model gateway (Abhishek):** graph nodes and states; budgets; PLAN and ASSESS prompts;
  the refused-action repair; the trial coordinator, freeze record and sandbox.
- **Audit, reports, review, evaluation (Vedantha):** blob store and audit kernel; report verifier and repair;
  how a decision binds to digests; export and replay; scorer isolation and the human rubric.

## Things not to say

- Do not claim held-out results, or that the model "found" faults the deterministic code found.
- Do not call the references hand-reviewed, the benchmark independent, or the sandbox secure.
- Do not say the system certifies compliance or detects fraud.
