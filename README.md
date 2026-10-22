# ReCycleGuard

Agentic AI for e-waste Extended Producer Responsibility (EPR) compliance reconciliation.

This mini-project supports a compliance officer in investigating discrepancies between a producer's obligations and supporting records. The planned scope covers one producer, one reporting period, limited equipment categories, structured records, and a curated regulatory corpus. Outputs are advisory and subject to human review.

## Current artifacts

- [Project guidelines](PROJECT_GUIDELINES.md): course requirements, schedule, rubrics, and deliverables.
- [Project charter source](PROJECT_CHARTER.tex): editable one-page LaTeX charter.
- [Project charter PDF](output/pdf/PROJECT_CHARTER.pdf): compiled charter.
- [Additional project PDF](output/pdf/ReCycleGuard.pdf).

## Research inputs

- [Domain research](docs/research/DOMAIN_RESEARCH.md): regulatory authorities, source hierarchy, compliance-officer workflow, evidence trails, and research gaps.
- [Agentic implementation overview](docs/research/AGENTIC_IMPLEMENTATION_OVERVIEW.md): task mapping, ingestion/retrieval/tools, data licensing, synthetic-data precedents, and evaluation recommendations.
- [CPCB EPR data and RAG research](docs/research/CPCB%20EPR%20Data%20and%20RAG.md): additional source inventory, candidate fields, and synthetic-data proposals.

The initial research notes are dated 16 October 2026; the additional CPCB data/RAG document is a further design input. Proposed behavior and synthetic-data plans are not implemented or measured results.

## System specification

- [System design](docs/design/SYSTEM_DESIGN.md): component architecture, online-source storage, synthetic dossier formats, reconciliation, retrieval, complete audit trails, recovery, and evaluation.
- [Component contracts](docs/design/CONTRACTS.md): versioned input/output types, permissions, component interfaces, data/control flow, and integration acceptance criteria.

The specifications were drafted on 18 October and corrected against the research review on 22 October 2026. They qualify tentative research assumptions and describe planned implementation.

The repository currently contains planning documents; the agent implementation is forthcoming.

## Build the charter

With a LaTeX distribution providing `pdflatex` installed, run from the repository root:

```sh
mkdir -p tmp/pdfs output/pdf
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=tmp/pdfs PROJECT_CHARTER.tex
cp tmp/pdfs/PROJECT_CHARTER.pdf output/pdf/PROJECT_CHARTER.pdf
```

## Team

| Member | Student ID |
| --- | --- |
| R V Abhishek (Team Lead) | 1BM23CD047 |
| H Sampreeth Bhat | 1BM23CD020 |
| Sushanth S | 1BM23CD063 |
| Vedantha Vinay Vernekar | 1BM23CD069 |

Agentic AI (26CD7PEAAI), B.E. CSE (Data Science), VII Semester, BMSCE.
