# ReCycleGuard domain research: Indian e-waste EPR reconciliation

**Research cut-off:** 16 October 2026 (India).

**Perspective:** A compliance officer working for a producer of electrical and electronic equipment (EEE).

**Companion:** [Officer-task-to-agent mapping and data feasibility](AGENTIC_IMPLEMENTATION_OVERVIEW.md).

## 1. Purpose, evidence and limits

ReCycleGuard should help an officer determine **which reconciliation discrepancy requires investigation, what evidence is missing, and what action should be reviewed next**. It should produce a defensible working paper, not certify a company's legal compliance.

This document distinguishes three kinds of statements:

- **Regulatory basis:** Requirements or explanations supported by linked government publications. Read each publication with applicable amendments and later orders.
- **Documented portal procedure:** Behavior described in CPCB's published instructions. Historical screenshots are evidence of that documented version, not a live test of today's authenticated portal.
- **Recommended operating practice:** Our reconstruction of a sensible company workflow. No producer interview, private ERP, authenticated portal account, or actual company dossier was accessed. The detailed controls below are proposed research inputs, not a claim that every firm follows an identical SOP.

Public primary sources were prioritized. Commercial compliance blogs were used only as discovery leads, not as authority for requirements. The research is not a certified consolidation of all applicable law, company-specific directions or court orders. Unresolved sources are identified rather than silently filled in.

### Reading guide

| Section | Question answered |
| --- | --- |
| 2–3 | Who makes the rules, who administers them, and which evidence should prevail? |
| 4–5 | What exactly is being reconciled, and what records support it? |
| 6 | What work would the company officer perform? |
| 7–8 | What does an investigation and its audit trail look like? |
| 9–10 | What should the mini-project support, and what remains uncertain? |
| 11 | Where can the original sources be verified? |

## 2. Sources of truth and deciding authorities

### 2.1 Different questions have different authorities

There is no single spreadsheet that is the source of truth for everything. Separate **legal requirements**, **official account state**, **business events**, and **internal judgments**.

| Question | Primary evidence / authority | What it does not establish |
| --- | --- | --- |
| What has legal force? | Applicable enacted law, Gazette notifications and valid orders; use official publication and commencement details. | A search result, FAQ or consultant summary cannot independently amend a rule. |
| Who establishes the national framework? | Central Government through MoEFCC; the parent statute is the Environment (Protection) Act, 1986. | The firm's officer cannot rewrite an obligation because its ERP disagrees. |
| Who administers the EPR mechanism? | CPCB, including portal administration and EPR monitoring; SPCBs/PCCs have specified state-level verification/monitoring responsibilities. | A state's facility listing is not the full producer account ledger. |
| What is recorded for this producer? | Dated CPCB registration, obligation statement, account transactions and submitted-return acknowledgments. | Official account state may itself require correction; an export is not infallible proof of underlying business facts. |
| What actually happened commercially? | Source sales/import records, approved product weights, contracts, invoices and finance records, reconciled against each other. | A payment alone does not prove usable EPR credit. |
| Who approves the company's position? | Authorized company signatory and designated compliance reviewers under the firm's governance. | Internal approval does not bind CPCB or adjudicate a dispute. |

The statutory foundation is documented by [India Code's Environment (Protection) Act record](https://www.indiacode.nic.in/indiacode/handle/123456789/1876?col=123456789%2F1362&view_type=search). CPCB/SPCB duties are specified in Schedule V of the [2022 Rules](https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf). Company controls in this table are our recommended separation of responsibilities.

**Practical implication:** ReCycleGuard should say “the supplied portal snapshot reports X; company records support Y; the discrepancy is Z,” rather than choosing one silently. Where interpretation or official rectification is needed, the officer escalates through the appropriate authorized channel. The software is not the deciding authority.

### 2.2 Recommended hierarchy for interpreting a question

1. Identify the entity, business role, product, event date and reporting period.
2. Find the governing provision and all relevant amendments/commencement clauses.
3. Check applicable orders, including deadline changes and entity-specific communications.
4. Consult CPCB's technical framework, SOP and relevant portal instructions.
5. Use the FAQ to clarify administration; flag any apparent inconsistency with higher authority.
6. Compare the resulting requirement with the dated company/account evidence.
7. Record unresolved conflicts for human interpretation; do not let retrieval ranking decide legal precedence.

This is a proposed interpretation workflow, not an assertion that every class of order has a universally fixed rank. An order's jurisdiction, scope and legal basis matter. A later website upload date does not automatically supersede an earlier legal instrument.

## 3. Regulatory inventory and temporal applicability

### 3.1 Verified core instruments

| Instrument | Verified identification | Why to include it |
| --- | --- | --- |
| E-Waste (Management) Rules, 2022 | G.S.R. 801(E), 2 November 2022; commenced 1 April 2023. | Base definitions, roles, EPR mechanism and schedules. |
| E-Waste (Management) Amendment Rules, 2023 | G.S.R. 61(E), 30 January 2023; commencement 1 April 2023. | Changes RoHS declaration wording and adds Schedule II exemptions. |
| E-Waste (Management) Second Amendment Rules, 2023 | G.S.R. 534(E), notification dated 24 July 2023; Gazette issue dated 25 July. | Adds end-product conversion-factor provisions and other changes, including refrigerants/RoHS. |
| E-Waste (Management) Amendment Rules, 2024 | G.S.R. 164(E), 8 March 2024. | Adds return-timeline relaxation and exchange-platform/price provisions; changes dismantler definition. |
| E-Waste (Management) Second Amendment Rules, 2024 | G.S.R. 699(E), 12 November 2024. | Replaces Rule 23 with a reference to the penalty provisions of section 15 of the parent Act. |

Primary texts: [2022 Rules](https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf), [January 2023 amendment](https://mpcb.gov.in/sites/default/files/Establishment%20of%20MPCB/Seniority%20list/2014/E-waste-ammendment-Rules-2023.pdf), [July 2023 amendment](https://mpcb.gov.in/sites/default/files/Establishment%20of%20MPCB/Seniority%20list/2014/E-Waste-Second-Amendment-Rules-2023.pdf), [March 2024 amendment](https://eprewaste.cpcb.gov.in/assets/PDF/Amendment-Rules-2024.pdf), [November 2024 Gazette](https://egazette.gov.in/WriteReadData/2024/258591.pdf).

**Naming trap:** The [MPCB index](https://mpcb.gov.in/en/waste-management/electronic-waste) calls the March 2024 item “Third Amendment,” while its Gazette title is “Amendment Rules, 2024.” Identify a source using its G.S.R. number and publication details, not only the menu label. Likewise, separate notification date, publication date, commencement date and website upload date.

The November 2024 official Gazette PDF was retrieved and its English amendment text inspected after the browser fetch failed. Its existence is also corroborated in [Lok Sabha proceedings of 13 February 2025](https://eparlib.sansad.in/bitstream/123456789/2989669/1/lsd_18_IV_13-02-2025.pdf). The inventory above lists instruments verified in this research; it does not assert that no later instrument exists.

### 3.2 Operational publications to collect alongside the rules

| Publication | Role in an investigation |
| --- | --- |
| Producer registration SOP | Establishes the documented registration inputs and review process. |
| CPCB FAQ, 23 January 2024 | Explains stakeholder registration, recycler capability and metal-based obligation questions. |
| Certificate-generation framework | Connects EEE categories, recoverable metals and obligation interpretation. |
| Generation/transfer guidance | Explains the documented lifecycle and fields of certificates. |
| Producer quarterly/annual return instruction sheet | Explains the documented filing screens and sequencing. |
| Environmental-compensation guidelines | Explains the enforcement framework; not a substitute for reconciliation evidence. |
| Current notices/directions and account correspondence | May change a deadline or process for a particular period or stakeholder. |

The source links and inspection status are in Section 11.

### 3.3 Deadline and version handling

Rule 6(4)'s baseline is the end of the month following the relevant quarter or year. For an April–March financial year, the corresponding baseline dates are:

| Return period | Baseline filing date before any applicable relaxation |
| --- | --- |
| April–June | 31 July |
| July–September | 31 October |
| October–December | 31 January |
| January–March | 30 April |
| Financial year ending 31 March | 30 April |

These dates express the rule's baseline, not an assurance about the operational filing window for a particular year. [2022 Rules, Rule 6(4)](https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf).

The March 2024 amendment permits the Central Government to relax specified return/report timelines by order for a further period up to nine months. Therefore a filing calendar must store the baseline and the applicable order, not just a recurring hard-coded date. [G.S.R. 164(E), inserted Rule 9A](https://eprewaste.cpcb.gov.in/assets/PDF/Amendment-Rules-2024.pdf).

The public [CPCB portal](https://eprewaste.cpcb.gov.in/) currently advertises an annual-return extension for FY 2025–26 to **30 September 2026**, and notices concerning GST-linked recycler invoices. These were visible in indexed official portal content; the full extension order and GST direction were not obtained here. Treat them as **notice-discovery leads**, obtain the signed documents before relying on their detailed applicability, and do not infer that a return extension extends the EPR achievement or trading deadline.

Recommended source-register fields: title, issuer, document ID, official URL, publication date, effective dates, affected roles/periods, amendment relation, page/clause, retrieval timestamp, file hash, inspection status and reproduction rights. Re-querying a website must not silently alter an already-issued report's evidence bundle.

## 4. Domain concepts that materially affect reconciliation

### 4.1 Producer is a business role, not a synonym for factory

A business selling under its brand or importing covered EEE may be a producer even without manufacturing locally. A company may have multiple roles. ReCycleGuard's main view is the **producer's EPR position**; factory-generated waste, recycler operations and other waste streams require separate treatment. The [official portal's producer explanation](https://eprewaste.cpcb.gov.in/) is the starting point for role screening, with the applicable legal definition controlling.

### 4.2 Targets are period- and product-dependent

Historical sales and product life matter; applying a percentage to current-year sales is not a safe general formula. The government explains the headline phased targets as 60%, then 70%, then 80% across the relevant years. These headlines do not select the correct sales cohort or determine a particular producer's position. [MoEFCC's PIB explanation](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1881761&lang=2&reg=48).

For the project, begin with a supplied, reviewed **portal obligation snapshot** and reconcile against it. Independently deriving statutory targets from historical sales should be a separately validated extension. Where the snapshot and an independent calculation differ, retain both and investigate instead of overwriting the assigned target.

### 4.3 EEE mass and recovered-metal credits are different quantities

CPCB's framework describes certificates associated with gold, copper, aluminium and iron, and provides EEE-wise material composition. It also contains special gold-obligation arrangements and adjustment examples. Therefore equipment mass, metal mass, financial amount and certificate denomination must be separate fields. [Certificate-generation framework, main provisions and Annexure I](https://eprewaste.cpcb.gov.in/assets/PDF/Framework.pdf).

The FAQ distinguishes metal obligation from the EEE-code capability of the recycler: it says metal obligations are independent of EEE code while requiring the recycler's capability for the producer's obligated code. A blanket “certificate EEE code must equal producer EEE code” rule would be unsafe. [CPCB FAQ, Section C](https://eprewaste.cpcb.gov.in/assets/PDF/faqewaste.pdf).

**Recommended analytical buckets:** producer, obligation year, obligation component/metal, unit, and approved rule profile; preserve EEE category and capability evidence separately. Never combine unlike metals into one balance or invent a conversion when its basis is unavailable. Gold offsets, refurbishing, historical liabilities and other adjustments should enter only through an explicitly supported profile.

### 4.4 Evidence of purchase, ownership and use are distinct

The documented certificate screen includes certificate number, generation date, expiry, value in kilograms and end product; transferred records include transfer date and recipient. The guidance describes staged recycler/producer authentication, including OTP/key steps. A commercial agreement or payment is therefore not sufficient evidence of a completed portal transfer. [Generation/transfer guidance, Sections 4–4.1 and transfer steps](https://ewaste2023.eprewastecpcb.in/assets/Guidance%20document%20for%20E-Waste%20-%20generation%20and%20transfer%20of%20EPR%20Certificate_Final%20(1).pdf).

The base rules describe adjustment against liability with priority for earlier liability, extinguishment of adjusted credits, and refurbishing-based deferral rather than final discharge. Consequently, repeated appearances of one identifier in inventory, transfer and return records need not be duplicate credit. [2022 Rules, Rules 14–15](https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf).

Model **events and states**. A unique certificate can legitimately appear in several snapshots; an invalid double count occurs when the same eligible quantity is attributed more than once without an authorized basis. Verify the relevant dates and event history before assigning a finding.

## 5. What the officer needs on the desk

### 5.1 Registration evidence versus ongoing reconciliation evidence

The producer SOP lists corporate/contact details, authorized person, EEE information, historical sales and supporting registration documents such as GST, IEC, incorporation/CIN and PAN as applicable, along with declarations. It describes CPCB review and approval through the portal. These establish identity and the registration dossier; they are not substitutes for a period's credit ledger. [Producer registration SOP, Sections 2 and application guidance](https://eprewaste.cpcb.gov.in/assets/landingpage%20PDF/SOP_for_grant_of_Registration_to_Producer_on_under_Ewaste_Rules_2022.pdf).

The following inventory is **recommended company working-paper organization**, informed by these source types. It is not a claim that each artifact is a mandatory attachment to every return.

| Evidence bundle | Likely custodian | Question it helps answer | Important limitation |
| --- | --- | --- | --- |
| Registration and amendments | Compliance/legal | Which entity, role and EEE coverage are recorded? | A historical certificate may not show later changes. |
| Product master and approved weights | Engineering/product operations | Which SKU maps to which EEE category and mass basis? | Packaging/product/component weights must not be assumed interchangeable. |
| Historical sales/import records and adjustments | Finance/sales/import team | What supports the declared business volumes? | The treatment of returns/exports/adjustments needs an approved basis. |
| Obligation statement and prior-period balances | Compliance/portal operator | What liability is being reconciled? | A screenshot can omit balances, filters or later corrections. |
| Recycler registration/capability evidence | Procurement/compliance | Is the selected counterparty appropriate for the intended transaction? | A public listing may be stale or incomplete. |
| Contract, purchase order, invoice and payment reference | Procurement/finance | What was agreed and paid for? | Does not by itself prove certificate transfer or adjustment. |
| Certificate inventory and transfer history | Authorized portal operator | What moved, to whom, when, in what quantity/state? | Extract timestamp and full coverage must be known. |
| Quarterly/annual drafts and acknowledgments | Compliance/signatory | What was reviewed and what was actually submitted? | A draft is not a submission receipt. |
| Notices, clarification tickets and responses | Compliance/legal | What issue remains open or was officially resolved? | Informal correspondence may not alter an official record. |
| Awareness activity evidence | Compliance/communications | What supports awareness-related return content? | Evidence quality and applicable instructions must be checked. |
| Physical waste movement records, if relevant | EHS/logistics | What physical waste was moved? | Physical movement is distinct from a producer's certificate acquisition. |

### 5.2 What a producer should not be assumed to possess

Recycler procurement, production, recovered-product sales and GST-linked invoices form a separate upstream evidence chain in CPCB's generation guidance. Some information may be supplied contractually, but the project has not established that a producer can download the entire recycler ledger. [Generation/transfer guidance, Sections 2–4](https://ewaste2023.eprewastecpcb.in/assets/Guidance%20document%20for%20E-Waste%20-%20generation%20and%20transfer%20of%20EPR%20Certificate_Final%20(1).pdf).

ReCycleGuard should distinguish **record absent**, **record outside the user's access**, **record not applicable**, and **record contradicted**. A company officer can request clarification; the system must not impersonate a regulator or infer that an inaccessible upstream invoice is fraudulent.

## 6. Reconstructed officer workflow and stable task IDs

These **16 tasks define the process covered by the companion mapping**. They are a proposed operational reconstruction. Their order is typical rather than rigid: investigations loop back when evidence changes.

### T01 — Establish mandate, entity and reporting boundary

- Confirm the legal entity, applicable business role, reporting year/quarter, cut-off date and supported EEE categories.
- Identify the person authorized to review the working paper and submit returns.
- Write a scope note including unavailable evidence and explicit exclusions.
- **Output:** Signed-off case scope and evidence access boundary. Do not mix subsidiaries or GST registrations simply because a trade name is shared.

### T02 — Establish the applicable rules and deadline register

- Assemble the official document inventory, amendments, relevant notices and company-specific communications.
- Determine which version applies to each event/period; preserve unresolved conflicts.
- Maintain separate dates for obligation achievement, credit events and return filing.
- **Output:** A dated applicability matrix and calendar, with each interpretation traceable to its source.

### T03 — Reconcile identity and registration coverage

- Compare the producer's registration dossier, current certificate and amendments with entity records.
- Check aliases, address changes, category additions and the validity interval shown by supplied evidence.
- Separate a historical identity change from a genuinely different counterparty.
- **Output:** Entity/registration exceptions and a reviewed identity mapping.

### T04 — Assemble and normalize the evidence pack

- Obtain approved company exports and dated portal captures; record who supplied them and their filters.
- Preserve originals. Create working copies for extraction and normalization.
- Check dates, units, required identifiers, missing pages, duplicate exports and extraction uncertainty.
- **Output:** A document register, normalized working tables and a completeness checklist. A parse failure is a data-quality issue, not an absent transaction.

### T05 — Review product classification and weight basis

- Join SKUs to the approved EEE mapping and engineering weight record.
- Investigate ambiguous descriptions, obsolete mappings and conflicting measurements.
- Ask for an authorized determination where the category or weight basis cannot be established.
- **Output:** A versioned category/weight crosswalk and unresolved mapping cases. HSN or a product name alone should not be treated as a complete EEE classification decision.

### T06 — Reconstruct the sales history supporting the obligation

- Reconcile reporting extracts to the relevant sales/import records and documented adjustments.
- Investigate missing history or cut-off differences rather than filling gaps with a guess.
- Keep original figures, proposed corrections and approved figures separate.
- **Output:** A historical-volume working paper. In the first project version, this supports investigation rather than automatic statutory target derivation.

### T07 — Establish the obligation ledger

- Capture the supplied official account target and its dimensions/date.
- Identify opening liabilities and any supported adjustments; distinguish components instead of netting unlike quantities.
- Compare against an independently approved calculation only where the calculation profile is supported.
- **Output:** The obligation baseline, adjustment trail and any disagreement requiring review. Missing opening balances limit the conclusion that can be drawn.

### T08 — Check recycler identity and capability

- Inspect the registration/capability evidence supplied for the intended counterparty.
- Match legal identity and relevant category capability, retaining the evidence date.
- Escalate uncertainty about suspension, coverage or historical validity to the responsible officer.
- **Output:** Counterparty verification note. Do not turn a stale or missing public search result into a definitive adverse finding.

### T09 — Match the commercial transaction to the credit event

- Link contract/PO, invoice and finance references to the corresponding certificate transfer evidence.
- Identify “paid but not transferred,” wrong recipient and conflicting quantities.
- Treat partial/failed transfers as unresolved states until the supplied account record establishes their outcome.
- **Output:** A transaction-to-certificate cross-reference and an open-items list.

### T10 — Reconstruct certificate history and usable quantities

- Preserve generation, transfer, expiry and adjustment evidence as distinct events.
- Compare repeated records by provenance and event context before deduplicating.
- Account for recorded cancellation, prior use and missing lifecycle evidence according to the reviewed rule profile.
- **Output:** A certificate-event ledger and a reason for each included, excluded or pending quantity.

### T11 — Reconcile balances and investigate discrepancies

- Compare like-for-like obligation and supported adjustment totals.
- Trace a gap back through quantity, unit, event date, recipient, opening balance and evidence filters.
- Test the smallest plausible explanations first; recompute after an approved correction.
- **Output:** A discrepancy register linking each finding to amounts, sources, alternative explanations and its next check. An arithmetic gap alone is not proof of misconduct.

### T12 — Prepare return-supporting working papers

- Tie draft-return figures to the reviewed obligation and certificate working papers.
- Check period sequencing, completeness and applicable supporting sections.
- Separate record reconciliation from awareness, solar or other sections outside the project's supported scope.
- **Output:** A draft comparison and a filing-readiness checklist; unresolved sections remain visible.

The published return instructions describe sequential quarterly filing, checking obligations, awareness attachments and final confirmation. Awareness is compulsory in the annual workflow described, while the quarterly treatment differs; a solar-related screen is conditional. These are documented portal instructions, not proof of the current authenticated interface. [Producer return instruction sheet](https://eprewaste.cpcb.gov.in/assets/PDF/Instruction_Sheet_for_Producer_Annual_Return_Filing.pdf).

### T13 — Obtain review and sign-off

- Route factual corrections to the data owner and ambiguous interpretations to the compliance/legal reviewer.
- Present the exact revised numbers and unresolved items to the authorized signatory.
- Capture reviewer, timestamp, report version and approved action.
- **Output:** A review record; approval of a draft does not establish successful portal submission.

### T14 — Submit or rectify through authorized channels

- The authorized human uses the official procedure to submit, amend where permitted, or raise a clarification ticket.
- Retain the submitted artifact, acknowledgment and subsequent correspondence.
- Do not assume a locked portal entry can be silently edited or deleted.
- **Output:** Submission/rectification evidence. ReCycleGuard's project scope stops at preparing and recording human-reviewed actions; it does not perform live filing or trading.

### T15 — Archive an auditable case and support queries

- Freeze the evidence bundle, calculations, interpretations, reviewer decisions and final report.
- Answer a query by reproducing the specific version and record lineage behind a figure.
- Keep a written unresolved-items handover. Choose retention with the company's applicable obligations; do not invent a universal statutory retention term here.
- **Output:** A reproducible case package and audit response index.

### T16 — Reopen after changes and improve the process

- Reassess affected findings when a new notice, corrected invoice, completed transfer or official response arrives.
- Issue a new report version with a change summary and retained prior version.
- Track recurring causes such as export filters or category-mapping errors.
- **Output:** A versioned case update. Previous human decisions remain attributable, rather than being overwritten by the agent's latest answer.

## 7. Evidence trails an investigation should follow

The following trails are **proposed working-paper structures**. They are not invented statutory forms.

### 7.1 Obligation trail

```text
Legal entity and reporting scope
  -> product/category mapping + approved weight basis
  -> relevant historical business records
  -> reviewed target interpretation or supplied portal target
  -> opening liabilities and supported adjustments
  -> obligation ledger bucket
```

For every arrow, record the join key, source record, effective date and approval basis. An unresolved join is a visible gap, not an invitation to fuzzy-match silently.

### 7.2 Credit trail

```text
Recycler identity/capability evidence
  -> commercial agreement + invoice/payment reference
  -> certificate identity and documented transfer event
  -> producer account state / adjustment evidence
  -> reconciliation working paper
  -> submitted-return reference, if available
```

This trail does not assert that the producer physically handed the exact equipment represented by each purchased credit to that recycler. Keep physical waste-chain evidence separate from credit-accounting evidence.

### 7.3 Rule and decision trail

```text
Finding -> supporting source facts -> tool calculation
        -> applicable provision/version -> remaining uncertainty
        -> proposed next action -> reviewer decision
```

Include the exact page/clause or table row, not merely a homepage link. Distinguish “this clause was retrieved” from “this clause supports this claim.”

### 7.4 Commercial and regulatory reporting are separate

Finance may reconcile rupees paid; the compliance officer reconciles appropriately denominated obligations and credit events. A recycling acknowledgment, physical weight ticket, destruction certificate and portal EPR certificate should not be collapsed into one generic “certificate” record. Label document type and what it can actually establish.

## 8. Worked investigation and report contents

### 8.1 Illustrative case, not a legal calculation

Assume a **synthetic, reviewed obligation bucket** of 100 kg of one metal for one producer/year. The dataset defines the following facts; these are not real CPCB records or prescribed denominations:

| Evidence | Observation | Treatment in the working paper |
| --- | --- | --- |
| Earlier official account snapshot | 55 kg recorded as adjusted | Preserve as the starting supported figure. |
| Internal purchase ledger | Three rows: 55 kg, 55 kg, 25 kg | Do not add to 135 kg and declare the target met. |
| Two 55 kg rows | Same source transaction repeated by an overlapping export | One business event; retain both source references. |
| 25 kg purchase | Invoice/payment present; transfer not established | Pending evidence, not recognized completion. |
| Later authenticated export supplied by officer | Adds evidence of the 25 kg event, dated after the earlier snapshot | Recompute only when the scenario's eligibility/period profile permits it. |

Initial supported position: 55 kg; apparent unresolved gap: 45 kg. If the later 25 kg is supported for this bucket, the revised position becomes 80 kg with a 20 kg gap. If historical allocation or cut-off is unresolved, keep the 25 kg pending. A correct investigation explains **why the figure changed** and what remains unverified.

### 8.2 Recommended report structure

1. Case identity, period, cut-off and supported scope.
2. Evidence inventory and known coverage gaps.
3. Obligation and supported-credit/adjustment summary by compatible bucket.
4. Finding register: type, quantity, records, source citations and confidence basis.
5. Investigations attempted, evidence obtained and unresolved hypotheses.
6. Proposed correction or next verification, named owner and review priority.
7. Human decisions and filing/rectification references, where supplied.
8. Limitations, rule snapshot, calculation version and reproducibility manifest.

Use system statuses such as **Reconciled within supplied scope**, **Discrepancy detected**, **Pending verification** and **Requires expert review**. None should imply an official CPCB classification or a full audit opinion.

### 8.3 Enforcement is a separate decision

The inspected CPCB EC document distinguishes end-product target shortfall from other non-compliances and states that paying compensation does not remove EPR responsibility. The downloaded file's URL includes “25.08.25,” but its opening notice is dated 9 September 2024; a filename is insufficient proof of a revised effective date. [Official EC document](https://eprewaste.cpcb.gov.in/assets/PDF/EC-Guidelines-under-E-Waste-Management-Rules-2022-25.08.25.pdf.pdf).

ReCycleGuard should identify review-worthy issues and cite relevant material, not impose compensation, choose an enforcement outcome or infer deliberate concealment from a mismatch. A monetary estimate would require a separate validated profile and clear authority; it is outside the proposed first version.

## 9. Recommended boundary for the mini-project

Start with a closed historical year, one synthetic producer, one or two approved EEE categories, and supplied metal-wise obligations. Retain enough history to expose prior-period allocation errors; a one-year reporting view does not guarantee that one year's records are sufficient.

**Core supported work:** T01–T04 and T07–T11, with draft support for T12–T13 and full provenance for T15–T16. T05–T06 initially use reviewed inputs. T08 uses supplied dated counterparty evidence. T14 remains human-operated.

Keep gold offsets, refurbishing deferrals, compensation calculations, complete RoHS verification, solar-specific duties, live credit trading and live filing outside the initial calculation profile. If encountered, report the unsupported feature and escalate. This is a proposed feasibility decision, not a statement that those duties are unimportant.

## 10. Research gaps to resolve before detailed system design

| Gap | What this research established | Required next evidence |
| --- | --- | --- |
| Current portal behavior | Public instructions and indexed notices exist. | Human-authorized sample exports/screens, exact filters and current field definitions. |
| Deadline exception | FY 2025–26 extension advertised on official portal. | Signed notice/order and its exact scope. |
| GST-linked invoice direction | Official portal advertises a direction. | Signed direction, date, applicability and amendments; no date hard-coded from blogs. |
| Current consolidated rule profile | Several Gazette amendments verified. | Controlled completeness review of Gazette/official notices and applicable entity orders. |
| Actual officer practice | Source-based reconstructed workflow. | Review by a producer compliance officer or qualified domain expert. |
| Historical account state | No private producer account accessed. | Authorized, de-identified representative samples or explicit synthetic adapters. |
| Record publication rights | Public access differs from reuse rights. | Asset-level license/permission register, discussed in the companion. |
| Special adjustments | Framework identifies material complexity. | Expert-approved formulas and fixtures before implementation. |

## 11. Primary source register

All sources were checked during this research on 16 October 2026. “Inspected” describes content actually read, not a guarantee of legal completeness or permission to redistribute.

| ID | Source and direct link | Inspection / locator |
| --- | --- | --- |
| R01 | [India Code: Environment (Protection) Act, 1986](https://www.indiacode.nic.in/indiacode/handle/123456789/1876?col=123456789%2F1362&view_type=search) | Official statute record inspected; use current text for specific enforcement questions. |
| R02 | [2022 Rules, G.S.R. 801(E)](https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf) | English Rules 6, 13–15, schedules and authority provisions inspected; original, unconsolidated PDF. |
| R03 | [January 2023 amendment](https://mpcb.gov.in/sites/default/files/Establishment%20of%20MPCB/Seniority%20list/2014/E-waste-ammendment-Rules-2023.pdf) | Gazette English text inspected on official state-board host. |
| R04 | [July 2023 second amendment](https://mpcb.gov.in/sites/default/files/Establishment%20of%20MPCB/Seniority%20list/2014/E-Waste-Second-Amendment-Rules-2023.pdf) | Amendment clauses inspected, including conversion factors. |
| R05 | [March 2024 amendment](https://eprewaste.cpcb.gov.in/assets/PDF/Amendment-Rules-2024.pdf) | English notification inspected, especially Rule 9A and Rule 15 additions. |
| R06 | [November 2024 second amendment](https://egazette.gov.in/WriteReadData/2024/258591.pdf) | Official PDF downloaded and English text inspected; browser fetch failed. |
| R07 | [Producer registration SOP](https://eprewaste.cpcb.gov.in/assets/landingpage%20PDF/SOP_for_grant_of_Registration_to_Producer_on_under_Ewaste_Rules_2022.pdf) | Sections 2 and application/document guidance inspected. |
| R08 | [CPCB FAQ, 23 January 2024](https://eprewaste.cpcb.gov.in/assets/PDF/faqewaste.pdf) | Sections B–C inspected; not a current consolidated legal text. |
| R09 | [Certificate-generation framework](https://eprewaste.cpcb.gov.in/assets/PDF/Framework.pdf) | Main provisions, gold examples and Annexure I inspected. |
| R10 | [Certificate generation/transfer guidance](https://ewaste2023.eprewastecpcb.in/assets/Guidance%20document%20for%20E-Waste%20-%20generation%20and%20transfer%20of%20EPR%20Certificate_Final%20(1).pdf) | Published 12-page document inspected; legacy official portal host, historical screen workflow. |
| R11 | [Producer return instruction sheet](https://eprewaste.cpcb.gov.in/assets/PDF/Instruction_Sheet_for_Producer_Annual_Return_Filing.pdf) | Seven-page instruction text inspected; authenticated behavior not tested. |
| R12 | [CPCB environmental-compensation document](https://eprewaste.cpcb.gov.in/assets/PDF/EC-Guidelines-under-E-Waste-Management-Rules-2022-25.08.25.pdf.pdf) | Official 20-page PDF retrieved; opening notice and selected regime sections inspected; revision date unresolved. |
| R13 | [CPCB e-waste portal](https://eprewaste.cpcb.gov.in/) | Official indexed public content inspected; live HTML is an application shell. |
| R14 | [MPCB e-waste index](https://mpcb.gov.in/en/waste-management/electronic-waste) | Official index inspected; source for amendment PDFs, not proof of consolidated currency. |
| R15 | [MoEFCC/PIB explanation of the 2022 Rules](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1881761&lang=2&reg=48) | Official explanation, used for context and headline target phases. |
| R16 | [Lok Sabha proceedings, 13 February 2025](https://eparlib.sansad.in/bitstream/123456789/2989669/1/lsd_18_IV_13-02-2025.pdf) | Indexed laying-of-papers passage corroborates G.S.R. 699(E). |

**Document status:** Research input to design. No officer interviews, operational access, deployed system, or measured reconciliation results are implied.
