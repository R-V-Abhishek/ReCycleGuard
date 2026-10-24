# Developer-only CP0 reference examples

These files must not be included in runtime images, prompts, retrieval or model
tools. They describe the starter development case, not held-out experiments.

- `case_001_expected.json`: S01 generator-submitted arithmetic/findings example.
- `cp0_credit_lot.json`: explicit typed example of a derived C04 output; not a
  source table or privileged generator truth injected into the runtime case.
- `cp0_calculation.json`: qualified interface example, not the output of a C08
  calculator. Its reference blobs are schema-only placeholders, not archived
  calculation artifacts. It retains incomplete-history qualification and omits
  a verified portal comparison across incompatible cut-offs.
- `cp0_finding.json`: explicit missing-evidence abstention and advisory next action,
  without a legal compliance verdict or human approval.

`benchmarks/evaluation/cp0_reference.py` independently spells out the small
hand-calculated reference using Fraction, without importing the generator or a
production calculator. It was added during A02. The team acknowledged the integrated candidate through Abhishek's report. The original input PRs and current candidate hashes are retained in the
checkpoint construction history.
