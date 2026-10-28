# Runtime configuration

A01 reads `RECYCLEGUARD_DATA_ROOT`, `RECYCLEGUARD_INTAKE_ROOT`,
`RECYCLEGUARD_OUTPUT_ROOT`, `RECYCLEGUARD_MODE` and
`RECYCLEGUARD_ENABLE_TEST_ADAPTERS`. Default mode is `runtime`; test adapters
require both mode `test` and explicit enablement. Evaluation mode rejects them.
No provider/model is selected. Do not put credentials or benchmark truth roots
in this configuration. Root access enforcement and production handlers belong
to later tasks; `doctor` only resolves/displays roots and checks in-memory FTS5.


## Local review on Windows and POSIX

Reviewer enrollment and authentication work with POSIX owner/mode checks or native
Windows owner-only ACLs. Windows uses the installed Windows PowerShell executable
and static .NET security operations; paths are passed as data, not interpolated
commands. Credential creation is exclusive and ACL protection is applied atomically.
Authentication rejects widened/inherited permissions and link/reparse credentials.
No new Python inference or OCR dependency is introduced.

Windows CI runs the full functional suite and native ACL tests on Python 3.11 and
3.12. POSIX permission primitive tests have Windows ACL counterparts; the evidence
pipeline and baseline demonstration run on both platforms. Enrollment still creates
only a local application reviewer, with no external portal/signatory authority.
