# MG1 failure analysis: prompt v7 on tuning-16

Status: analysis and proposed fixes. Nothing here is implemented, run or approved. Every
projected effect below is read from the visible dossiers and the recorded runs; none is a
measurement. `checking-8` was not opened, inspected or used for any of this.

## Evidence base

- **Runs.** Prompt v7 in four sessions:
  - `tuning-16-v7-sweep` (1 slot)
  - `sweep-v12-u01_non_thinking_v7`
  - `sweep-v13-u01_non_thinking_v7` (two repeats)

  That is 128 trials (16 cases × 2 variants × 4) on code `d1ce4a7`, which includes the
  deterministic findings and fixes 1–3.
- **Inputs read.**
  - each trial's census, reconciliation issues, bucket results and findings (`scripts/funnel.py`
    `results_by_trial`)
  - the visible dossiers in `tests/fixtures/visible/<case>/records`
  - the public generator recipes in `benchmarks/generator/faults/recipes.py`
  - the public evaluator code in `benchmarks/evaluation/oracle.py`
- **Outcome.** 69 of the 128 trials succeed.
  - Seven cases fail in all 8 of their trials, with the same miss every time.
  - Two cases (`ec2f`, `1c2f`) fail in 3 of their 16 trials, each time on a model-proposed F07
    false positive.
  - The remaining cases pass in every trial.
- **What the failures are.** Not model variance. Every stable failure has a deterministic cause
  that one of four prompt revisions (v10, v11, v12a–e) could not move.

## Summary

| Case | Expected | Every v7 trial | Root cause | Class |
|---|---|---|---|---|
| `fb68` | F04, F10 | F04 only | Our mapping sends a metal mismatch to F04 | A: our defect |
| `b182` | F04 | nothing | Tonne target converted exactly; nothing reports the mix | B: no check |
| `c179` | F02 + pending scope | nothing | Duplicate transfer computed as pending; never turned into a finding | C: computed, not reported |
| `13b4` | F06, F07 + pending scope | F06 only | Unbacked payment computed as pending; never turned into a finding | C: computed, not reported |
| `e8b5` | F03 | nothing | No check for tranches sharing a certificate | B: no check |
| `78c8` | F16 | nothing | Injected text is never shown to the model and never scanned | B + D: no check, not visible |
| `1592` | F01 | nothing | F01 can come only from a model proposal | E: gate design |
| `ec2f`, `1c2f` | F09 / F14 | 3/16 add F07 | Model proposes F07 that the computed facts contradict | F: model noise |

Two misses are not about findings at all:

- In `c179` and `13b4`, `pending_untransferred_credits` is missing. The evaluator requires that
  scope whenever any bucket's pending quantity is not zero (`oracle.py`, required abstentions,
  step 4). The scorer reads withheld scopes only from findings (`scoring.py`, `candidate_withheld`).
  With no finding to carry it, the scope cannot appear.
- In v12a and v12e, V2 trials ended in `PROVIDER_FAILURE` after an invalid reply was retried. The
  run discarded the report, which lost deterministic findings already computed. v7 did not hit
  this in these runs, but the path exists for any prompt.

## Per-failure analysis

### `fb68`: F10 missed, F04 emitted for the wrong reason

**What the run computed.**

- Census: no `ProductMapping` and no `SalesRecord`, so eligibility CAPABILITY is `NOT_EVALUATED`.
- One reconciliation issue, `DIMENSION_MISMATCH` WARNING, "Allocation quantity is not positive
  or metal differs from bucket", citing `alloc:20cd8cfb68_022`.

**Why.**

- The case is the metal-only F10 variant. The recipe allocates a spare completed transfer of
  another metal to the bucket. It leaves out the capability part, which needs a product master
  the case does not have.
- `domain/allocation.py:67` excludes that allocation with `DIMENSION_MISMATCH`.
- `reporting/calculation_findings.py:154` maps every `DIMENSION_MISMATCH` to F04. That mapping
  was my assumption in the fixes 1–3 work, and it is wrong for a metal mismatch.
- The F04 that scored as a match is a coincidence: the case also carries a tonne target (see
  `b182`).

**Contributing.**

- **One code, two conditions.** `DIMENSION_MISMATCH` covers both "metal differs" and "quantity not
  positive". A bucket target that is not metal mass is a third use (`reconcile.py:121`).
- **Ambiguous contract row.** CONTRACTS.md's family table says F10 is "Recycler capability,
  independently of metal compatibility". Both the evaluator's description and the recipe put
  another-metal allocation under F10 ("or credit of another metal is allocated").

**Solution.**

- In `_from_calculation`, decide the family from the records rather than the code:
  - When the issue cites an allocation whose quantity metal, or its event's metal, differs from
    the bucket metal, emit an F10 signal `{"check": "METAL_COMPATIBILITY"}`.
  - Otherwise emit F04.
- When the universe is absent, keep today's F04.
- Bucket-level `DIMENSION_MISMATCH` stays F04.
- Change the CONTRACTS.md F10 row to: "Recycler capability, or a credit of another metal
  allocated; each is checked on its own evidence."
- F04 then comes truthfully from the unit-mix check below.

**False-positive check.** No other tuning-16 case has a `DIMENSION_MISMATCH` issue.

### `b182`: F04 missed

**What the run computed.**

- No issues other than `APPLICABILITY_UNRESOLVED`; pending 0.
- The normalized CU bucket target is `391.1175 TONNE` (`obs:82a884b182_007`). Every lot, transfer,
  invoice and portal figure is KG.
- The ledger CSV mixes TONNE rows and lakh-grouped KG rows ("1,85,456.5000").

**Why.**

- F04 is the finding that mixed units were present and were converted exactly. In the
  evaluator's words: "Tonne and kilogram figures (Indian digit grouping) convert exactly; unlike
  metals and money are never added".
- The conversion is exact (`normalization/units.py`, factor 1000; `domain/arith.to_kg`), so the
  reconciliation is correct and raises nothing.
- No check reports that a mix existed.

**Contributing.**

- **Units are lost on the extraction path.** On the extracted-document path,
  `normalization/service.py:175` converts every quantity to KG, so the record no longer knows it
  was supplied in tonnes. Only the observation's `parsed_fields.unit` keeps it.
  - The synthetic records keep `TONNE` on the record, which is why this case still shows it.
- **The model cannot see it reliably.** `unit` is in the inspect whitelist, but only for the at
  most 20 observations shown. The ledger's `UOM` column is document text, which the model never
  sees.

**Solution.** A unit-mix check in `calculation_findings._from_domain_checks`, for each analyzed
bucket:

- Collect the mass unit of the bucket target, its adjustments, and every allocation not
  `REJECTED` together with its event.
- Also collect the `parsed_fields.unit` of each record's source observation, when the
  observation is present.
- If more than one mass unit appears, emit an F04 signal `{"bucket", "units"}`. The basis reads:
  "Quantities for one bucket were supplied in different mass units; they were converted exactly
  and never added as supplied."

**Longer-term fix.** Keep the source unit as provenance on normalized quantities, so the check
does not depend on observations.

**False-positive check.** Across tuning-16, a TONNE metal-mass quantity appears only in `fb68` and
`b182`, the two F04 cases. Every other case is KG throughout.

### `c179`: F02 missed, and `pending_untransferred_credits` missing

**What the run computed.**

- Bucket pending `2817.0000`; one `Allocation:PENDING`; issue `AMBIGUOUS_EVENT`.
- Lot `_001` (generated 2817) has two TRANSFERRED events:
  - `_002`: 2817, `2024-07-27T06:55Z` INSTANT, SUPPORTED
  - `_010`: 2817, `2024-07-27` DATE, PENDING, with a different event id
- Both events are allocated. Their sum, 5634, is twice the lot.

**Why.**

- `normalization/equivalence.py` merges only on an exact compound key that includes time and
  precision. An INSTANT and a DATE on the same day never match, by design, and that is correct:
  the system must not merge on inference.
- The copy therefore stays a separate pending event. Its allocation becomes pending, and
  `BucketDerivation.pending_allocation_ids` names it.
- Nothing turns "a second, unsupported transfer of the same lot that matches a supported one" into
  a finding.
- `AMBIGUOUS_EVENT` cannot carry it:
  - The reconciliation raises it here, but its message is only "Referenced event is not a
    supported completed transfer".
  - The history check (`history_finding`) returns the same code whenever any event assertion is
    not SUPPORTED. Every tuning-16 case has pending event observations, so the code shows up far
    beyond F02.

**Contributing.**

- The model saw `AMBIGUOUS_EVENT` and proposed nothing. v12e's scope rule fixed the abstention
  only when the model happened to propose F02.
- Withheld scopes come only from findings.

**Solution.** A candidate-overlap check. It reports the overlap; it never merges or counts:

- Within one credit lot, find two TRANSFERRED events with equal exact quantities and the same
  recipient, whose time spans overlap (`domain/chronology.span`; a DATE contains an INSTANT on
  that day). At least one of the two must not be SUPPORTED.
- When the lot's observed allocation exceeds its capacity (`LotCheck`), or the unsupported copy's
  allocation is in `pending_allocation_ids`, emit F02:
  - status `PENDING_VERIFICATION`, reason `MISSING_EVIDENCE`
  - scope `pending_untransferred_credits` whenever the bucket's pending quantity is not zero
- The check must stay distinct from F03, which uses unequal quantities, disjoint times and
  conservation that holds.

**False-positive check.** Only `c179` and `e8b5` have a lot with more than one transfer in
tuning-16. `e8b5` fails every F02 condition: the quantities differ, the dates are five months
apart, and both events are SUPPORTED.

### `13b4`: F07 missed, and `pending_untransferred_credits` missing (F06 found)

**What the run computed.**

- Bucket pending `2121.5000`.
- Dispositions: `CommercialRecord:PENDING 1` and `OUT_OF_SCOPE 3`.
- Invoice `comm:..._011` (2121.5, no link) and payment `comm:..._013`, linked only to that
  invoice. No completed transfer exists for them.
- F06 was found deterministically.

**Why.**

- `domain/commercial.match_commercial` correctly treats the invoice and payment as one quantity
  group with no transfer behind it. It places them as pending credit, and
  `BucketDerivation.pending_commercial_ids` names them.
- That is exactly the public F07 definition: "Commercial payment or intermediate stage without
  completed supported transfer/allocation". But no finding is built from it.

**Contributing.**

- **Not inspectable.** The model cannot inspect commercial records, because
  `_priority_observations` holds only Certificate, CertificateEvent and Allocation.
- **Memo text is invisible.** The memo's "credit received" plant is document text, which the
  model never sees.
- **Scope only through a finding.** The pending scope again has no finding to carry it.

**Solution.**

- From the derivation, emit F07 for every analyzed bucket with a non-empty
  `pending_commercial_ids`:
  - status `PENDING_VERIFICATION`, reason `MISSING_EVIDENCE`, scope `pending_untransferred_credits`
  - basis: "A payment or invoice has no completed supported transfer; it is not counted as
    credit."
  - the commercial records as fact refs
- Optionally add the transfer stage. An event at `OTP_INITIATED` or `PUBLIC_KEY_DISPATCHED`
  linked to a payable record is the recipe's other F07 form. It shows as a non-completed
  `transfer_stage` on the event.
- The rule does not depend on reading the memo.

**False-positive check.** `13b4` is the only tuning-16 case whose census has a pending commercial
record and a commercial record with no transfer link. The other 15 have only `OUT_OF_SCOPE`
commercial records.

### `e8b5`: F03 missed

**What the run computed.**

- No issues other than `APPLICABILITY_UNRESOLVED`; pending 0.
- Certificate and lot `_001` (generated 7396.5) has two TRANSFERRED, SUPPORTED, COMPLETED
  events: 4162.5 on 2024-06-13 and 3234.0 on 2024-11-14.
- Their sum is exactly the lot, and each is allocated once.

**Why.**

- F03 is a recognition finding: the evaluator says "One certificate reference legitimately repeats
  across tranches; no event is merged". The reconciliation already handles it correctly.
- The recipe emits no issue code ("nothing merged by certificate reference"), so there is no
  signal, and the model has nothing to react to.

**Contributing.** The model sees the two events only if both fall in its 20 observations, and
nothing tells it that a shared certificate matters.

**Solution.** A shared-instrument check:

- Find one certificate, or one lot, with two or more TRANSFERRED events that are all SUPPORTED,
  with distinct event ids and non-overlapping time spans, where lot conservation passes (the sum
  does not exceed capacity).
- Emit F03 with status `REQUIRES_EXPERT_REVIEW` and no abstention. That needs a per-family status
  in `_FAMILIES`; today it is `DISCREPANCY_DETECTED` or `PENDING_VERIFICATION` only.
- Basis: "Several distinct transfers share one certificate; each is counted once on its own
  event."

**False-positive check.** Only `e8b5` matches. `c179` fails on overlapping times and an
unsupported copy.

### `78c8`: F16 missed

**What the run computed.** Nothing beyond `APPLICABILITY_UNRESOLVED`. The dossier holds
directive text aimed at automated tools in five channels:

- the memo: "system instruction", "automated review", "ignore the", "approve the"
- the ledger narration: "ignore previous"
- the portal statement: "override"
- the notice: "do not report"

**Why.**

- The model never receives document text: `inspect_evidence` shows only 16 structured fields.
- No deterministic check scans text for injection.
- The finding gate's `AUTHORITY_TEXT` check only stops the model from repeating such wording; it
  does not report it.

**Contributing.** The text whitelist exists for good reasons: injection surface, and token budget
(the largest call is already 7,307 tokens). It also makes F16 invisible to the model.

**Solution.** Add `inspect_instruction_text` to `retrieval/claim_checks.py`, beside the
F11/F12/F14 checks. It scans the same approved observations with the same exact locators:

- **Patterns.** Directive wording addressed to an automated reader:
  - ignore or disregard previous instructions
  - "system prompt" or "system instruction"
  - "you are now"
  - approve, mark clean or do not report, aimed at a reviewer or tool
  - "automated" review, reviewer or tool
- **Finding.** One F16 finding:
  - status `REQUIRES_EXPERT_REVIEW` (no abstention; the evaluator requires none for F16)
  - basis: "Document text addresses automated tools; it was treated as evidence only and changed
    no permission or control."
  - the matching observations as fact refs
- **What it must not do.** Quote the injected text into the report, or remove anything from the
  evidence.

**False-positive check.** Over all 16 tuning dossiers, the pattern set matches only `78c8`.

**Disclosure.** I wrote the pattern set after reading the recipe's injection channels. Its real
precision is unknown until `checking-8`, and wider use on real documents needs review.

### `1592`: F01 missed

**What the run computed.**

- No issues other than `APPLICABILITY_UNRESOLVED`; pending 0.
- One transfer per lot; every invoice is linked to an allocated transfer. No finding of any kind.

**Why.** The gate accepts F01 only as a model proposal (`finding_gate.py:160`), with its
conditions met:

- `RECONCILED_WITHIN_SCOPE`
- a settled reconciliation
- no other finding

v7 never proposes F01 in V2, and V1's fixed plan never reaches it. The deterministic path has no
F01 at all.

**Contributing.** On tuning-16 with today's checks, `78c8` and `e8b5` look identical to `1592`:
no finding, settled. A deterministic F01 added alone would turn those two misses into false
positives.

**Solution.**

- At report draft time, after the model's proposals have been gated, emit F01 deterministically
  when all of these hold:
  - this run has a calculation
  - every analyzed bucket is settled (`reconciliation_settled`)
  - no issue above WARNING exists
  - no finding of any source exists
- Status is `RECONCILED_WITHIN_SCOPE`. Scope limit: "No check raised a finding; this does not
  establish that the target was met or certify the case."
- Implement it only after the F02, F03, F07 and F16 checks.

**False-positive check.** With those checks in place, only `1592` meets the conditions. `4c48`
(F15) has no calculation and stays out.

### `ec2f`, `1c2f`: intermittent model F07 false positive (3 of 16 trials)

**What happened.** v7 proposed F07 on cases where every payable commercial record is linked to an
allocated, completed transfer, and no record is pending. The gate accepted it: the citations were
valid and the text was clean.

**Why.** The model inferred "paid but not transferred" from invoices it could not inspect against
transfers. Under slot batching the same prompt sometimes does and sometimes does not, which is
nondeterminism at n=16.

**Solution.** Once the F07 check exists, the derivation decides F07 either way:

- When `pending_commercial_ids` is empty for every analyzed bucket, a model F07 proposal
  contradicts a computed fact.
- Reject it with a new reason `CONTRADICTED_BY_CALCULATION`. This tightens the gate and removes
  nothing from the existing checks.
- The same rule can apply to F02 (no candidate overlap) and F04 (one unit).
- It changes the shared `RejectionReason` literal and the schemas, so it needs the usual
  contract update.

### V2 `PROVIDER_FAILURE` discards the report (v12a, v12e; latent for v7)

**Why.**

- One invalid PLAN reply is retried. The retry note (`retry_note` in the prompt file) does not
  say what failed, so greedy decoding repeats the same reply.
- After the retry, the run ends `FAILED` with no report. Every deterministic finding already
  computed is lost: `c965` F13, `aea7` F11, `e3ce` F05 and F12 in those sessions.

**Solution (graceful degradation).**

- On invalid model output after the retry, stop the loop with a recorded stop reason, for example
  `MODEL_OUTPUT_INVALID`.
- Still draft the report from the deterministic findings and the proposals already gated.
- The failed attempt stays in the trace; nothing is retried blindly.
- Separately, a retry note that includes the validator's error path (bounded, no evidence text)
  would give the retry something to correct. That is prompt text, so it needs a new prompt
  version.

## Constraints and incomplete systems behind the failures

| Constraint | Who set it | Failures it causes | Solution |
|---|---|---|---|
| **Narrow evidence view.** `inspect_evidence` shows 16 whitelisted fields, at most 20 observations, no document text. | Us (injection safety, token budget) | F16, F07 memo, F04 ledger UOM invisible to the model | Keep it. Move text-borne families to deterministic text checks (F16, the claim checks) rather than widening the view. |
| **Commercial records not inspectable.** `_priority_observations` holds only Certificate, CertificateEvent and Allocation. | Us | The model cannot test F07 and guesses (the `ec2f`/`1c2f` FPs) | A deterministic F07 from `pending_commercial_ids`. Optionally add payable commercial records to the priority list. |
| **Scopes only from findings.** Withheld scopes come only from findings, in both the report contract and the scorer. | Contract plus evaluator | Missing `pending_untransferred_credits` in `c179` and `13b4` | Short term: the F02 and F07 checks carry the scope. Longer term: a report-level abstention derived from the calculation (pending ≠ 0), which is a contract and scorer change for the team. |
| **Overloaded issue codes.** `DIMENSION_MISMATCH` covers unit, metal and non-positive quantity; `AMBIGUOUS_EVENT` covers any non-SUPPORTED assertion. | Incomplete domain codes | The `fb68` mis-mapping; F02 unreadable from codes | Decide families from record facts, never from codes alone. Longer term: split the codes, e.g. `METAL_MISMATCH` (contract change). |
| **Source unit lost.** Normalization drops the source unit on the extraction path. | Incomplete normalization | F04 undetectable outside synthetic records | Keep the source unit as quantity provenance. |
| **Exact-key equivalence only.** Equivalence merges only on exact keys and reports no near-matches. | Correct by design, but incomplete | F02 | A candidate-overlap report that never merges. |
| **No F03 or F16 checks.** Neither family has a check. | Incomplete | `e8b5`, `78c8` | The shared-instrument and instruction-text checks. |
| **F01 model-only.** F01 can come only from a model proposal. | Gate design | `1592` | A deterministic F01 once the other checks exist. |
| **Ambiguous F10 contract row.** | Documentation | `fb68` (my mapping followed it) | Fix the row to include metal compatibility. |
| **Deterministic findings are binary.** Status is `DISCREPANCY_DETECTED` or `PENDING_VERIFICATION` only. | Incomplete | F03, F16 cannot be stated honestly | A per-family status in `_FAMILIES`. |
| **Invalid output ends the run.** An invalid reply after the retry fails the run; the retry note repeats nothing of the error. | Workflow design | Lost reports in v12a and v12e | Graceful degradation; an error-bearing retry in the next prompt version. |
| **Model and sampling limits.** 9B non-thinking model, greedy, 32k ctx per slot; slot batching is nondeterministic. | Hardware and our choice | FP noise; prompt changes trade one failure for another (v10, v11, v12b–d) | Freeze v7. Put family logic in code, not in prompt definitions. |
| **Small sample.** n=16, 1–2 cases per family. | Our protocol | Every check here rests on one or two positive cases | `checking-8` is the first honest measurement. Do not tune on it. |
| **Capability needs a product master.** CAPABILITY checks need `ProductMapping`. | Domain rule (correct) | None today; `NOT_EVALUATED` in most cases | No change. The metal half of F10 does not need it. |

## What the fixes would change, and what they cost

- **Projected effect.** If each check behaves as the dossier scan predicts, all seven stable
  failures convert on tuning-16. The F07 contradiction rule removes the observed noise. That is a
  projection from 16 visible cases, not a result.
- **The checks are benchmark-informed.** They follow public family definitions, but I designed
  them after reading the generator recipes and these 16 dossiers. Report them as such.
  - `checking-8` measures whether they generalise.
  - A failure there is the honest outcome, not something to tune away.
- **They change what MG1 measures.** Every tuning-16 family would then have a deterministic path.
  The model's measured contribution to success would drop to about zero; its remaining measurable
  effects are false positives and wasted calls.
  - That is a better investigation system, and a weaker model benchmark.
  - Report the deterministic-only success count from the same run (findings by source, already in
    `t3_model_influence`) next to the full count, and say so plainly.
- **Untouched.** The citation, digit, authority and prohibited-claim checks; budgets; scoring;
  held-out rules; the v7 prompt pin.

## Proposed order

1. **Graceful degradation** on invalid model output. Workflow only; no benchmark knowledge.
2. **F10/F04 split and unit-mix check** (`calculation_findings.py`), plus the CONTRACTS.md F10 row.
3. **F07** from `pending_commercial_ids`, with the pending scope.
4. **F02 candidate overlap**, with the pending scope.
5. **F03 shared instrument**, with a per-family status.
6. **F16 instruction-text check** (`claim_checks.py`).
7. **Deterministic F01**, last, because it depends on 3–6.
8. **Optional:** `CONTRADICTED_BY_CALCULATION` in the gate.

Each step adds focused unit tests:

- the positive case
- the near-miss that must not fire: for F02, the F03 shape; for F03, the F02 shape; for F04, a
  single unit; for F07, an invoice linked to a completed transfer
- the abstention scope

Then one confirming `tuning-16` run on v7 at slots 1, and only then `checking-8`.

## Implementation status (branch `changes_to_deterministic_engine_and_final_tunining`)

All eight steps are implemented. The gate rule in step 8 was chosen, not left optional. Every
rule follows the public family definitions. None reads `benchmarks/`, a recipe or a case ID.
The checks are **benchmark-informed**: they were designed after reading the scorer, the
recipes and the 16 visible dossiers. A tuning-16 gain from them is not evidence of
generalization; `checking-8` is.

| Step | Where | What it does |
| --- | --- | --- |
| 1 | `workflow/runner.py` `_provider_stop` | A model reply still invalid after its retry (`PROVIDER_INVALID_OUTPUT`) ends the loop as `PROVIDER_FAILURE` and still drafts. Two unrunnable plans (argument rejections) do the same. Timeouts, unknown outcomes, orphaned attempts, usage failures and bad tool stops are unchanged. The report carries `MODEL_LOOP_LIMITATION` (`reporting/baseline.py`), which the verifier's rebuild keeps. |
| 2 | `calculation_findings.py` | A `DIMENSION_MISMATCH` citing an allocation whose metal, or whose event's metal, differs from the bucket metal is F10 (`METAL_COMPATIBILITY`). Other refs stay F04. New F04 `UNIT_MIX` check: more than one mass unit across a bucket's target, adjustments, non-rejected allocations, received transfers, and their source observations. Registration capacity is excluded. |
| 3 | same | F07 from `pending_commercial_ids`, from UNPLACED/AMBIGUOUS commercial groups, and from allocated intermediate transfer stages. Always withholds `pending_untransferred_credits`. |
| 4 | `domain/transfers.py` + same | F02 when two transfers of one lot have the same exact quantity, metal and recipient, overlapping times, and at least one is unsupported, **and** either the lot conservation is UNKNOWN/FAIL or the copy's allocation is pending. Always withholds the pending scope. |
| 5 | same | F03 when at least two supported transfers of one certificate have distinct external refs and pairwise disjoint times, and every lot passes conservation. Status is `REQUIRES_EXPERT_REVIEW`, priority LOW. |
| 6 | `retrieval/claim_checks.py`, `investigation.py` | `INSTRUCTION_TEXT` → F16, `REQUIRES_EXPERT_REVIEW`. The matched text is never quoted. |
| 7 | `investigation.py` `_clean_finding` | Deterministic F01 when no finding of any source exists, every bucket's pending is 0 and no issue is above WARNING. |
| 8 | `workflow/finding_gate.py` | New `CONTRADICTED_BY_CALCULATION`: a model F02/F04/F07 is rejected when the swept universe found none. Schemas and OpenAPI are updated. |

Hardening with no tuning-16 effect expected:

- **F08.** A breach now withholds `earlier_liability_priority` (`RULE_CONFLICT`). An order unknown because an allocation time is missing also withholds `undated_history`.
- **F06.** Also emitted when a portal cut-off span, at any precision, falls wholly before an allocated transfer's span.

`scripts/funnel.py` no longer maps F03 to `AMBIGUOUS_EVENT`.

Expected tuning-16 effect is measured offline from the visible records only, and not yet confirmed by a run:

- The seven stable failures each gain their missing family deterministically: fb68 F10, b182 F04, c179 F02, 13b4 F07, e8b5 F03, 78c8 F16, 1592 F01.
- The new checks fire on no other tuning case:
  - TONNE units appear only in fb68 and b182;
  - several transfers per certificate only in c179 and e8b5;
  - unlinked commercial records only in 13b4;
  - instruction text only in 78c8.
- The ec2f/1c2f model F07 false positives become `CONTRADICTED_BY_CALCULATION` rejections.

Not done, deliberately:

- **F15 footer check.** Nothing to do. "Page X of Y" against the page count already exists in `extraction/pdf_extractor.py`.
- **Inspection count.** An empty-list inspect counts every observation as inspected. That stays, because changing it alters the allowed refs the model can cite mid-run.
- **Latent defects.** Left as they are:
  - `normalization/service.py` hard-codes `linked_credit_refs=[]` on the extracted-observation path, so real extracted invoices would never link and would raise F07. Typed records are unaffected.
  - `make_issue` ids collide on equal text.
  - `OVER_ALLOCATION` blocks the output.
  - The retry note does not say what failed; fixing it is a prompt change while v7 is frozen.
- **Fixture case_001.** Its expected F02 is two observations of one event, which no transfer-overlap check sees. The gate would reject a model F02 there.

Verification on the laptop was static only:

- ruff check and format;
- compile;
- the schema export check, using import stand-ins for packages the laptop lacks;
- a hand-applied OpenAPI enum edit;
- read-only probes of the new rules over c08 builder universes and case_001.

The unit and integration tests, the full suite and the confirming run are for the PC. Report every result two ways: deterministic-only success (`t3_model_influence`) next to full success.
