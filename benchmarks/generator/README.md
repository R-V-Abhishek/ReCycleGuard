# C15 synthetic generator

Owner: Sushanth S. `starter_world.py` + `cp0_sources.py` produced the frozen S01 `case_001`.
S05 adds a reusable pipeline: **clean world → invariants → visible rendering → hidden record**.

| Module | Role |
| --- | --- |
| `world.py` | Typed world model, fictional party catalogue, identity and exact-decimal helpers |
| `s05_cases.py` | The six seeded S05 templates (`Draft` builder is reusable for S07) |
| `invariants.py` | Clean-world checks: IDs, conservation, chronology, metals, prices, synthetic identity |
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

The first command rewrites only the six `case_<tag>` directories (never `case_001`) and writes the
hidden record. `--check` rebuilds in a scratch folder under the hidden root and fails if any
committed visible byte differs. `benchmarks/hidden/` is gitignored; every developer regenerates it.

## Hidden record (proposal, pending V04 agreement)

`benchmarks/hidden/<dataset_version>/`:

- `generation_manifest.json`: `dataset_version`, `generator_revision` (git head plus a module digest), `seed`, `profile_digest` (null, with a reason), `case_ids`, `world_blob`, `visible_asset_manifest_blob`, `corruption_manifest_blob` (null: no faults in S05), `oracle_blob` (null: V04 builds the `OracleCase`), `split_policy` = `DEV_ONLY_S05`, `rights_manifest_ref`, plus `reference_blob`, `visible_map_blob`, `timeline_groups`, `templates`. All blob values are SHA-256 digests of the files below.
- `world/<tag>.json`: the full world and the per-document style choices.
- `visible_map/<tag>.json`: visible file + locator (JSON pointer, CSV row, PDF page) → world object.
- `reference/<tag>.json`: generator arithmetic per bucket (required, supported, signed gap, shortfall, surplus, pending, portal, delta) and the allocation order. This is **not** an `OracleCase`.

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
