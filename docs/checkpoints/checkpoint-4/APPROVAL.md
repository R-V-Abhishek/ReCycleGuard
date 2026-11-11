# CP4 approval

- **Status:** APPROVED.
- **Date:** 1 November 2026 (Asia/Kolkata).
- **Accepted implementation candidate:** `b5a9831` on `checkpoint-4`.
- **Decision recorded by:** Abhishek, team lead, through this project conversation.
- **Acknowledgment basis:** the agent asked whether all four members acknowledged
  this exact candidate. Abhishek replied: **“yes. APPROVE it”**.
- **Record type:** lead-reported all-four acknowledgment and explicit approval;
  separate individual signatures or external review links are not asserted.

Acceptance covers the scripted prototype demonstrated in [completion](COMPLETION.md):
actual restricted investigator execution, audited denied-access evidence,
independent original-visible reference validation and separate agent semantic
review, reviewed reports, recovery, export and standalone artifact replay.

Retained qualifications:

- Independent reference/semantic review is coding-agent review, not human legal
  or domain-expert certification.
- Sandbox evidence covers the explicit scripted investigator; ordinary API and
  real-model execution are not claimed to inherit the sandbox.
- Public export remains PARTIAL pending exact-object rights clearance.
- Full-suite history, skipped checks and local/CI distinctions remain in the
  verification record. No scientific model-quality result is created by approval.
- MG1, CP5 and subsequent experiment gates remain unapproved.

**Released to start:** A09 (Abhishek), H09 (Sampreeth), S08 (Sushanth), V10 (Vedantha).
READY means dependencies are satisfied; it does not mean these tasks are complete.

## Durable evidence copy (recorded 1 November 2026, after approval)

The answer-bearing evaluator outputs and the CP4 verification artifacts that were
under `/private/tmp` were copied to a private, owner-only location outside the
repository (`~/recycleguard-private/cp4/`, 1,830 files). Their `SHA256SUMS` file has
digest `94d09e411e746f23d1b7e09474290e3c9abab4e2404570e5cca6befb0bfc59ca`
(recomputed `shasum -a 256 -c` found no mismatch). Nothing from that directory is in Git.
Large rebuildable directories (wheels, Docker contexts, copied visible inputs) were not copied.
