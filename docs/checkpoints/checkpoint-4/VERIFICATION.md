# CP4 integration verification

Executed locally on macOS, 1 November 2026. These results do not approve CP4.

| Check | Observed result |
| --- | --- |
| Mapped G01–G12 regression battery | 413 passed, 24 skipped; [actual JUnit-derived ledger](gate-regressions.json) preserves missing/skipped evidence and review requirements |
| Final export/review/recovery/oracle/isolation-policy/CLI/storage battery | 48 passed |
| Runtime packaging pin regressions | 2 passed |
| Frontend | 78 passed; type check and production build passed |
| Runtime wheel | Built; installed source hash agrees with source checkout; exact build lock included; evaluator/tests excluded |
| Contracts | 159 boundary schemas and OpenAPI checked |
| Static checks | Ruff, formatting and diff checks passed |
| Fresh source API and CLI demonstrations | Real services, scripted model; qualified report and synthetic review; no model-quality claim |
| Standalone A07 export | 368 objects, durable export event, integrity PASS, offline artifact inspection SUCCESS |
| Independent evaluator world arithmetic | All 48 pilot records validated; zero reviewed visible references |

An earlier whole-repository sweep started before the export fixture repair:
**1008 passed, 30 skipped, one failed**. Its failure was the submitted legacy
`test_g10_review_and_export_lifecycle` constructing `ReviewService` without the
required arguments. It was replaced with a real authenticated integration path;
the final focused battery and mapped gate battery pass that replacement. The
entire repository suite was not rerun after every final repair. Do not describe
this as a clean final full-suite run. No Windows/Linux CI result is asserted here.

The final packaging fix removes checkout-only assumptions from source hashing
and dependency-lock lookup. Installed wheels previously searched a nonexistent
`src/recycleguard` tree and repository `uv.lock`. Wheels now hash their actual
package sources and carry exact build-lock bytes; checkouts still require the
working lock. A fresh API flow was rerun after this fix.

Raw local test outputs and JUnit were written under `/private/tmp/cp4-*`.
Answer-bearing evaluator artifacts remain private and outside investigator roots.
Refer to [A08 integration](A08_INTEGRATION.md) for mandatory G11/V09 acceptance
gaps and the exact scope of artifact replay and withheld public packages.
