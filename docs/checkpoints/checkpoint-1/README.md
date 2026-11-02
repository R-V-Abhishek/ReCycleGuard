# CP1 approved: qualified evidence foundation

Accepted by R V Abhishek on **26 October 2026**, following the agent's technical
review and his explicit instruction to accept the candidate and lock the checkpoint.
Approval mode: **LEAD_EXPLICIT_ACCEPTANCE**. Scope: **QUALIFIED_EVIDENCE_FOUNDATION**.
[Approval evidence and exact frozen references](approvals.json).
[Lock manifest](boundary-manifest.json) pins 169 files at the verified implementation
commit; [verification evidence](verification.md) includes the passing GitHub CI run.

The lead explicitly accepted this checkpoint after being told that four-person
acknowledgement would not be claimed. This is a recorded CP1-specific exception to
the original four-person gate, not fabricated teammate reviews or a general policy
change. Unresolved applicability, deadlines, rights and normalization qualifications
remain visible. Approval does not mean every underlying fact passed a compliance check.

Integration branch: **`checkpoint-1`**. Lock tag:
**`checkpoint-1-approved-2026-10-26`**. Start subsequent work from this accepted
boundary in the next checkpoint/workstream branch. V02, checkpoint-0 and main are
preserved. A main integration, if requested, uses a reviewed PR from checkpoint-1.

| Owner | Task | Evidence | State |
| --- | --- | --- | --- |
| Vedantha, with Abhishek's integration repairs | V02 | [Storage handoff](v02.md) | DONE |
| Abhishek | A03 | [Snapshot/profile service](a03.md) | DONE |
| Sampreeth, with Abhishek's integration repairs | H02 / H03 | [Acquisition/extraction handoff](h02_h04.md) | DONE for batch intake and CSV/JSON/text-PDF scope |
| Sampreeth's proposals, technically reviewed by the agent and accepted by Abhishek | H04 | [Corrected originals, profile and review boundary](a04.md) | DONE within the explicitly qualified scope |
| Sushanth, with Abhishek's integration repairs | S02 | [Normalization and integration repairs](a04.md) | DONE; unresolved mappings remain quarantined |
| Abhishek | A04 | [Integrated foundation and final publication](a04.md) | DONE; final case pins approved profile and corpus |
| Sushanth | S05 | Visible renderer | READY; no new completion is inferred from the old starter fixtures |

The source workstreams are PR #5 at `72979c8` and PR #6 at `325636c`, retained in
merge ancestry. The initial candidate was constructed on top of V02/A03 `8750265`.
The final acceptance creates new reviewed versions rather than rewriting drafts.

**Next dependency states:** H05 and S03 are READY after CP1. V03 still needs S03;
A05 still needs S03 and V03. Other checkpoint gates remain unchanged. Runtime
model selection, local OCR/VLM evaluation and benchmark execution were not added.
