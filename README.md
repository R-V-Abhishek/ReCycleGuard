# ReCycleGuard

Agentic AI for e-waste Extended Producer Responsibility (EPR) compliance reconciliation.

This mini-project supports a compliance officer in investigating discrepancies between a producer's obligations and supporting records. The planned scope covers one producer, one reporting period, limited equipment categories, structured records, and a curated regulatory corpus. Outputs are advisory and subject to human review.

## Current artifacts

- [Project guidelines](PROJECT_GUIDELINES.md): course requirements, schedule, rubrics, and deliverables.
- [Project charter source](PROJECT_CHARTER.tex): editable one-page LaTeX charter.
- [Project charter PDF](output/pdf/PROJECT_CHARTER.pdf): compiled charter.
- [Additional project PDF](output/pdf/ReCycleGuard.pdf).

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
