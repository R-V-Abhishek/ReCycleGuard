# C15 synthetic generator

Owner: Sushanth S. `starter_world.py` + `cp0_sources.py` produced the frozen S01 `case_001`.
S05 adds a reusable pipeline: **clean world → invariants → visible rendering → hidden record**.

| Module | Role |
| --- | --- |
| `world.py` | Typed world model, fictional party catalogue, identity and exact-decimal helpers |
| `s05_cases.py` | The six seeded S05 templates (`Draft` builder is reusable for S07) |
| `s04_cases.py` | Six S04 variants (own dataset version `s04-dev-0.1`): expired credit, cancelled credit, invoice plus payment, capability mismatch, weight-basis conflict, earlier liability proven by allocation dates |
| `s06_cases.py` | 21 S06 fault dossiers (`s06-dev-0.1`): F01–F16 singly (F15 in two forms) plus four combinations |
| `faults/` | S06 fault recipes (`recipes.py`), hidden record models (`records.py`), visible-effect validation (`validate.py`) |
| `pilot_cases.py` | S07 pilot (`pilot-0.1`): 48 dossiers split 24 development / 24 held-out before rendering |
| `pilot.py` | S07 split independence, leakage and near-duplicate checks; the held-out digest seal |
| `invariants.py` | World checks with stable rule ids: IDs, conservation, chronology, metals, prices, synthetic identity; a recipe may relax only the ids it declares |
| `render.py` | Projects a world into a visible dossier validated by the contract models |
| `documents.py` | Indian inter-office memorandum + Indian number/money/date formatting |
| `pdf_style.py` | Seeded paper/ink/type styles, vector watermark, deterministic PDF writer |
| `invoice_builder.py` | Tax invoice; `style=None` keeps the frozen S01 bytes |
| `hidden.py` | Hidden generation record (CONTRACTS §5.3 field names) |
| `generate.py` | CLI |

## Regenerate

```
python -m benchmarks.generator.generate --visible-root tests/fixtures/visible --hidden-root benchmarks/hidden
python -m benchmarks.generator.generate --visible-root tests/fixtures/visible --hidden-root benchmarks/hidden --check
```

The first command rewrites only the 33 generated `case_<tag>` directories (never `case_001`) and
writes one hidden record per dataset version (`s05-dev-0.1`, `s04-dev-0.1`, `s06-dev-0.1`).
`--check` rebuilds in a scratch folder under the hidden root and fails if any committed visible
byte differs. For S06 it also refuses to write a dossier whose recorded corruption is not visible
in the rendered bytes. `benchmarks/hidden/` is gitignored; every developer regenerates it.

## Hidden record (base format agreed by V04, 2026-10-28)

`benchmarks/hidden/<dataset_version>/`:

- `generation_manifest.json`: `dataset_version`, `generator_revision` (git head plus a module digest), `seed`, `profile_digest` (null, with a reason), `case_ids`, `world_blob`, `visible_asset_manifest_blob`, `corruption_manifest_blob` (null in S04/S05; per-case digests in S06), `oracle_blob` (null: V04 builds the `OracleCase`), `split_policy` = `DEV_ONLY_<set>`, `rights_manifest_ref`, plus `reference_blob`, `visible_map_blob`, `timeline_groups`, `templates`. S06 adds `expected_effects_blob`, `clean_world_blob`, `clean_counterpart_root` and `fault_families`. All blob values are SHA-256 digests of the files below.
- S06 only (proposed additions, pending V04 agreement): `corruption/<tag>.json` (list of `CorruptionRecord`), `expected/<tag>.json` (`ExpectedEffects`: clean and visible reference buckets, expected codes, abstentions, forbidden actions; a draft input for the `OracleCase`, not an oracle), `clean_world/<tag>.json`, and `clean/case_<tag>/` (the clean counterpart rendered for paired review). `world/<tag>.json` is the corrupted world, i.e. what the visible evidence says.
- `world/<tag>.json`: the full world and the per-document style choices.
- `visible_map/<tag>.json`: visible file + locator (JSON pointer, CSV row, PDF page) → world object.
- `reference/<tag>.json`: generator arithmetic per bucket (required, supported, signed gap, shortfall, surplus, pending, portal, delta) and the allocation order. This is **not** an `OracleCase`.
  Since S04 it also lists `allocation_checks` per allocation (lifecycle, capability and
  earlier-liability outcome with the excluding code) and, for worlds with a product master,
  `product_checks` (weight-basis conflict per SKU, sales total). These are computed in `hidden.py`
  from dates and EEE codes without calling C08, so the integration tests compare two separate
  implementations of the same stated rules.

## S04 worlds (hand-built effects, not S06 faults)

Each S04 world plants one effect with ordinary, contract-valid, dated evidence: an expiry date or
a `CANCELLED` event before the credit is used, an `INVOICE` and the `PAYMENT` that references it,
a recycler registered for another EEE category, one SKU mapped with two weight bases, and
allocations carrying `allocation_time` with no explicit order. The portal balance still reports
every allocation, so the delta against the supported quantity is visible. `invariants.py` rejects
a lifecycle date on the same calendar day as the transfer or allocation (it cannot be ordered at
day resolution) and an allocation dated before its transfer. S06 will add fault recipes on top.

## S06 fault recipes (`s06-dev-0.1`)

Each dossier is a clean world (which passes every invariant) followed by one or more recipes
from `faults/recipes.py`. A recipe returns the corrupted world and a `Change`: transformation,
before/after world refs, visible assets, effect, expected issue codes and abstentions, forbidden
actions, permitted alternatives, and the invariant ids it breaks on purpose. The world records
those ids in `World.relaxed`; `check_world` rejects unknown ids, and the tests prove every
declared break is real. `faults/validate.py` then reads the rendered bytes, PDFs through the
runtime extractor, and fails generation if an effect is not visible.

| Family | Visible effect |
| --- | --- |
| F01 | Full S06 surface, no fault (a GENERATED event per certificate repeats its ref legitimately) |
| F02 | A portal row copy with no transaction id and a date-only time, allocated a second time |
| F03 | Two lots merged into one certificate: one ref, three or more lifecycle events |
| F04 | Ledger mixes KG and TONNE rows in Indian grouping (`1,23,456.5`); tonne bucket target |
| F05 | Credit sent to a sister "Trading LLP" (own SYNTH GSTIN); invoices use a dated former name |
| F06 | Portal statement downloaded mid-year (cut-off between allocated transfers); memo states the date |
| F07 | Payment against a transfer stuck at OTP_INITIATED or PUBLIC_KEY_DISPATCHED |
| F08 | Later year drains a shared lot first (dated), or the same with no allocation dates |
| F09 | Certificate status CANCELLED with no dated cancellation event |
| F10 | Recycler registered for one EEE category only, and/or a lot of another metal allocated |
| F11 | Memo cites the 2016 Rules and an FY 2022-23 cut-off |
| F12 | Note for file says the CPCB has extended the filing date; no order in the dossier |
| F13 | One SKU mapped with two weight bases in the same period |
| F14 | An AU bucket plus a "gold offset" claim in the memo |
| F15 | Memo page with no text layer, or a memo whose footers say "of N" with a page missing (intake flags both as `INCOMPLETE_COVERAGE`) |
| F16 | Hostile instructions in the memo, an invoice remark, a ledger narration, a portal remark and the note for file |

Combinations: F02+F06, F08 (undated)+F09, F04+F10 (metal), F15 (textless)+F16.

Every S06 dossier carries the same surface (ledger `Quantity`/`UOM`/`Narration` columns, portal
`remarks`, a GENERATED event per certificate, a "Note for file", Annexure A/B on their own memo
pages), so the presence of a field never reveals which case is faulty. S04/S05 bytes are
unchanged (`surface="s05"`). The reference in `hidden.py` follows the C08 rules without calling
C08: a credit of another metal is excluded (`DIMENSION_MISMATCH`), a recipient other than the
producer is excluded (`AMBIGUOUS_IDENTITY`), a duplicate export is pending (`AMBIGUOUS_EVENT`), an
undated raw status CANCELLED/EXPIRED is UNKNOWN, and the portal reports only completed transfers
to the producer up to the statement cut-off. F11, F12 and F14 have no runtime check yet
(H06/H07, A07); S06 supplies the evidence and the expected abstentions only.

## S07 pilot (`pilot-0.1`): 24 development + 24 held-out

`pilot_cases.py` builds 48 dossiers and assigns each to a split **before rendering**. Each split
has one dossier per family F01–F16 and eight combinations. The split is grouped by entity,
template and timeline group. It is never a row-level random split.

- **Entities:** development uses the S05/S06 catalogue. Held-out uses twelve producers (serials
  13–24) and six recyclers (`recycler_i`–`n`) that no development dossier uses, including the 33
  earlier dossiers.
- **Templates:** a template is a shape plus its parameters (`tranches.CU.2.mid.portal`). The
  splits share no template and no multi-recipe combination. Single fault definitions are shared
  on purpose.
- **Variants:** F08 is dated in dev and undated in held-out. F10 is capability in dev and metal in
  held-out. F15 is textless in dev and truncated in held-out. The combinations use the other
  form.

| # | Development combination | Held-out combination |
| --- | --- | --- |
| 1 | F02+F06 | F02+F07 |
| 2 | F08 (undated)+F09 | F08 (dated)+F10 (capability) |
| 3 | F04+F10 (metal) | F04+F06 |
| 4 | F15 (textless)+F16 | F15 (truncated)+F11 |
| 5 | F03+F13 | F03+F09 |
| 6 | F05+F12 | F05+F16 |
| 7 | F11+F14 | F12+F13 |
| 8 | F06+F07 | F10 (metal)+F13 |

**Layout.**
- Development dossiers go to `tests/fixtures/visible/case_<tag>/` (committed).
- Held-out dossiers go to `benchmarks/heldout/visible/case_<tag>/` (gitignored, `--heldout-root`).
- Git keeps only `benchmarks/pilot/heldout_seal.json`: opaque held-out case ids and a SHA-256 of
  each visible file tree. It carries no labels, families, seeds or templates.
- `generate --check` compares development bytes with the fixtures and held-out digests with the
  seal.
- The hidden record `benchmarks/hidden/pilot-0.1/` adds `split_policy = GROUPED_DEV_HELDOUT_V1`,
  `split_assignments` and `split_groups`. It also adds `oracle/` (V04's `write_oracle_records`)
  with `oracle_blob` filled.

**Checks** (`pilot.py`). Generation fails if any of these is true:
- the splits share an entity, template, combination, timeline group or hidden world id;
- a visible file or name carries a family, recipe, template, group, seed or split word;
- two dossiers are exact duplicates;
- a development dossier and a held-out dossier reach a word 5-shingle Jaccard of 0.85 or more.
  The current maximum is about 0.31.

**Limits.**
- The separation is internal only. Templates and seeds are in this code, so anyone with the
  repository can regenerate the held-out dossiers. This is disclosed as limited internal
  separation (plan §7.3), not as an external or double-blind test.
- The held-out access log and the digest freeze belong to V09.

## Indian digit grouping

`normalization/units.py` accepts plain, Western (`1,234,567.5`) and Indian lakh/crore grouping
(`12,34,567.5`, `1,00,00,000`) exactly; malformed groupings (`1,2,3`, `12,3456`) still raise. The
canonical `Quantity.decimal` never carries commas. F04 dossiers depend on this.

## Realism choices (India) and their sources

- **Memo layout:** Indian inter-office memoranda carry a reference/file number, the sender organisation, the addressee, the subject, a reference to earlier correspondence and the date, then numbered paragraphs, a "Sd/-" signature block with designation, and Encl./Copy-to lists. The exact form varies by organisation. Sources: government office-procedure training material (AP and Tripura state portals), the Qatar Digital Library archive of India Office memoranda, and the Lumen/LibreTexts business-communication memo chapters.
- **Letterhead:** Companies Act 2013 s.12(3)(c) requires the company name, registered office, CIN, telephone, e-mail and website on letterheads (summaries on TaxGuru, iPleaders and StudyCafe). LLPs show an LLPIN instead.
- **Tax invoice:** titled "Tax Invoice" and marked "Original for Recipient" (CGST Rules 46/48 practice), with GSTIN, place of supply, IGST or CGST+SGST by state, amount in words in lakh/crore, NEFT UTR, a masked bank account, the standard "Declaration ... true and correct" text and "Subject to <district> jurisdiction".
- **EPR certificate prices:** CPCB's 2024 price band sets the floor at 30% and the ceiling at 100% of the environmental-compensation rate. The reported per-kg bands are roughly ₹22–74 for consumer electronics (CEEW) and ₹34–112 for IT equipment (ITEW) (Newslaundry, April 2025). Market bids below the floor have also been reported (Newslaundry, June 2025). Rates are drawn inside the band (`PRICE_BAND_INR_PER_KG`).
- **GST:** no reviewed source fixes the GST treatment of traded EPR certificates. `GST_RATE_ASSUMED = 18` is a labelled generator assumption for realistic totals, not a statement of tax law.
- **Places:** real industrial localities and pincodes (KIADB Jigani/Sompura, SIPCOT Oragadam, MIDC Chakan/Taloja, Noida Sector 63, IMT Manesar, IDA Cherlapally, GIDC Vapi, SIDCUL Haridwar), GST state codes and STD codes. Recycler clusters follow the state pollution control board lists (e.g. TNPCB authorised e-waste recyclers 2023, https://tnpcb.gov.in/pdf_2023/ListEwasteRecyclers2023.pdf).

## Identity policy (SYSTEM_DESIGN §5.5)

Firms are fictional and carry a "Synth" marker. Identifiers are unmistakable project strings (`SYNTH-GSTIN-29-R0001`, `SYNTH-CIN-U26400-KA-2014-PTC-0001`) that never match real GSTIN/PAN/CIN patterns (this is tested). E-mail and web domains use the reserved `.example` TLD, and phone numbers use an unassigned `0000` exchange. No document carries an official seal, and every page shows the diagonal "SYNTHETIC - NOT A CPCB RECORD" watermark plus the same text in an extractable footer.

## Watermark

The watermark is drawn as stroke-glyph vector paths on a rotated, translucent layer, tagged
`/Artifact << /Subtype /Watermark >>`. A text watermark was rejected: pdfplumber interleaves its
letters into content lines (e.g. `25.0000 KG CUN`).
