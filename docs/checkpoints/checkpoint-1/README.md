# CP1 work in progress

CP0 remains accepted at its historical candidate. CP1 is **WAITING**.
Integration branch: **`checkpoint-1`**, as requested by Abhishek on 25 October 2026.
It starts from `8750265`, retaining the complete V02 foundation, its repairs and
both A03 commits. `V02` is preserved at that same commit; its history is not rewritten.
No checkpoint-0 or main merge is performed here.

Create remaining CP1 workstream branches from `checkpoint-1` and target their PRs
at `checkpoint-1`. Existing workstream branches can also target this branch;
review their diffs and reconcile interface drift before merging. Integrate and
verify the required handoffs here, then merge the accepted checkpoint into `main`
after CP1 approval. Branch creation alone does not approve the checkpoint.

| Owner | Task | Evidence | State |
| --- | --- | --- | --- |
| Vedantha + Abhishek repair/review | V02 | [Storage handoff and repairs](v02.md) | DONE after local verification; remote CI tracked separately |
| Abhishek | A03 | [Snapshot/profile persistence, structured service and trusted CLI](a03.md) | DONE; 214 tests and CI passed on Python 3.11/3.12 at `8750265` |
| Sampreeth | H02 | Audited batch intake | READY after V02 |
| Sushanth | S02 / S05 | Normalization / visible renderer | READY from CP0; no new completion is inferred |

A03 supplies the persistence/review handoff; H02 can use the repaired shared write coordinator. H03/H04 and S02
remain prerequisites for A04, so this update does not approve CP1.
