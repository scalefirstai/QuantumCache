# `data/sources/` — vendored public artifacts

Day 1-2 of `docs/DATA-PLAN.md` §8. Each artifact below is downloaded from a public source and SHA-256-hashed. Hashes are recorded inline and in sidecar `<file>.sha256` files. Re-running `fetch_sources.py` is idempotent: identical sources → identical hashes.

Large binaries (`.docx`, `.xlsx`, `.pdf`, `.zip`) are git-ignored and tracked by hash + URL only. Small machine-readable JSON/OSCAL files are committed in-repo for fast inspection.

## User-Agent

```
QuantumCache-DDQ-Bootstrap/0.1 (selwyn.theo@gmail.com)
```

## Sources

| ID | Format | License | SHA-256 | Bytes | Status |
|---|---|---|---|---|---|
| `afme.ddq.custodian.docx` | docx | free for all; AFME encourages widest usage | `be927248135e15bb…` | 365,828 | ok |
| `afme.ddq.custodian.xlsx` | xlsx | free for all; AFME encourages widest usage | `02c52d4bf375e558…` | 215,772 | ok |
| `afme.ddq.csd.docx` | docx | free for all; AFME encourages widest usage | `3c08d25fabdd7aa3…` | 282,519 | ok |
| `afme.ddq.prime_broker.docx` | docx | free for all; AFME encourages widest usage | `6cb509802e17096e…` | 250,964 | ok |
| `afme.esg.hy_disclosure.pdf` | pdf | free for all; AFME encourages widest usage | `3eff4c80384c094d…` | 1,821,944 | ok |
| `nist.csf.v2_0.oscal.json` | oscal-json | Public domain (US government work) | `e3edb5ef6b059f42…` | 317,504 | ok |
| `nist.sp800_53.rev5.oscal.json` | oscal-json | Public domain (US government work) | `1645df6a370dcb93…` | 10,441,264 | ok |
| `csa.ccm.machine_readable.bundle` | zip | CSA license — free, redistribution permitted with attribution | `c0e8d2b61ea43470…` | 1,184,926 | ok |
| `csa.ccm.v4_1.bundle` | zip | CSA license — free, redistribution permitted with attribution | `669a9210d981460f…` | 21,052,449 | ok |

## Per-source detail

### `afme.ddq.custodian.docx`

- **Title:** AFME Post Trade Due Diligence Questionnaire (custodian) 2026
- **URL:** <https://www.afme.eu/media/xfmhzoef/afme-due-diligence-questionnaire-for-use-in-2026-final-version-clean-3.docx>
- **License:** free for all; AFME encourages widest usage
- **Out:** `data/sources/afme/afme-ddq-custodian-2026.docx`
- **Version note:** DATA-PLAN §1 lists 2024 version; AFME has refreshed to 2026 (current as of 2026-05). Drift recorded in README.
- **SHA-256:** `be927248135e15bb6f525707cb0fd30005c1c0b140d488b40bf607dad8e3d0f6`
- **Bytes:** 365,828
- **Content-Type:** `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

### `afme.ddq.custodian.xlsx`

- **Title:** AFME Post Trade Due Diligence Questionnaire (custodian) 2026 — Excel template
- **URL:** <https://www.afme.eu/media/kx0j5a43/ddq-2026-excel-template-2.xlsx>
- **License:** free for all; AFME encourages widest usage
- **Out:** `data/sources/afme/afme-ddq-custodian-2026.xlsx`
- **SHA-256:** `02c52d4bf375e5587d3496f0659e5db0a24113444339519d451aed59491a8ac0`
- **Bytes:** 215,772
- **Content-Type:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

### `afme.ddq.csd.docx`

- **Title:** AFME Post Trade CSD Due Diligence Questionnaire 2026
- **URL:** <https://www.afme.eu/media/nfelwk3h/afme-ddq-csd-version-for-use-in-2026-2.docx>
- **License:** free for all; AFME encourages widest usage
- **Out:** `data/sources/afme/afme-ddq-csd-2026.docx`
- **SHA-256:** `3c08d25fabdd7aa32c764a3f29fb37abac1fe99b34bb156d0ec7e8e05279973b`
- **Bytes:** 282,519
- **Content-Type:** `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

### `afme.ddq.prime_broker.docx`

- **Title:** AFME-Irish Funds Prime Brokerage Due Diligence Questionnaire 2026
- **URL:** <https://www.afme.eu/media/h5cpngzj/afme-irish-funds-pb-ddq.docx>
- **License:** free for all; AFME encourages widest usage
- **Out:** `data/sources/afme/afme-ddq-prime-broker-2026.docx`
- **Note:** Beyond DATA-PLAN §1 scope; included because plan calls out custodian-adjacent products and prime brokerage is one. Optional.
- **SHA-256:** `6cb509802e17096e7a5ddde65a9beed0e5d1d3112af2ef881299b0309389230f`
- **Bytes:** 250,964
- **Content-Type:** `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

### `afme.esg.hy_disclosure.pdf`

- **Title:** AFME Recommended ESG Disclosure and Diligence Practices for the European High Yield Market — Jan 2026
- **URL:** <https://www.afme.eu/media/qr0l1ove/afme-hy-esg-disclosure-and-diligence-guidelines-jan-2026.pdf>
- **License:** free for all; AFME encourages widest usage
- **Out:** `data/sources/afme/afme-hy-esg-2026.pdf`
- **Version note:** DATA-PLAN §1 expects a standalone 'AFME ESG DDQ'. AFME has consolidated ESG content under HY Disclosure Guidelines as of 2026; closest substitute. SME review needed before using as canon.esg.* seed.
- **SHA-256:** `3eff4c80384c094d635e68b5ea2f586efa59c5379b525b01150a75f1a4c8d2f3`
- **Bytes:** 1,821,944
- **Content-Type:** `application/pdf`

### `nist.csf.v2_0.oscal.json`

- **Title:** NIST Cybersecurity Framework 2.0 — OSCAL JSON catalog
- **URL:** <https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/CSF/v2.0/json/NIST_CSF_v2.0_catalog.json>
- **License:** Public domain (US government work)
- **Out:** `data/sources/nist/NIST_CSF_v2.0_catalog.json`
- **SHA-256:** `e3edb5ef6b059f42becd446ddead36ce5189cd9f8631e3ee1789dc613b6ae936`
- **Bytes:** 317,504
- **Content-Type:** `text/plain; charset=utf-8`

### `nist.sp800_53.rev5.oscal.json`

- **Title:** NIST SP 800-53 rev5 — OSCAL JSON catalog
- **URL:** <https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json>
- **License:** Public domain (US government work)
- **Out:** `data/sources/nist/NIST_SP-800-53_rev5_catalog.json`
- **SHA-256:** `1645df6a370dcb931db2e2d5d70c2f77bc89c38499a416c23a70eb2c0e595bcc`
- **Bytes:** 10,441,264
- **Content-Type:** `text/plain; charset=utf-8`

### `csa.ccm.machine_readable.bundle`

- **Title:** CSA CCM v4 — machine-readable bundle (JSON / YAML / OSCAL)
- **URL:** <https://cloudsecurityalliance.org/download/artifacts/ccm-machine-readable-bundle-json-yaml-oscal>
- **License:** CSA license — free, redistribution permitted with attribution
- **Out:** `data/sources/caiq/ccm-machine-readable-bundle.zip`
- **Note:** This bundle is the gift per DATA-PLAN §1 — contains CAIQ JSON + CCM JSON/OSCAL. Verified via verify_sources.py.
- **SHA-256:** `c0e8d2b61ea43470786ca67af7a49cc276e01942ad86fc907fb527436b46b7ab`
- **Bytes:** 1,184,926
- **Content-Type:** `application/zip`

### `csa.ccm.v4_1.bundle`

- **Title:** CSA Cloud Controls Matrix v4.1 — main bundle (xlsx + companions)
- **URL:** <https://cloudsecurityalliance.org/download/artifacts/cloud-controls-matrix-v4-1>
- **License:** CSA license — free, redistribution permitted with attribution
- **Out:** `data/sources/caiq/ccm-v4.1-bundle.zip`
- **Note:** Contains CCM v4.1 xlsx, CAIQ v4.1 xlsx, and mapping spreadsheets to NIST/ISO/PCI/SOC2/CCPA/GDPR/AICPA TSC.
- **SHA-256:** `669a9210d981460f7413a9adbbc920dbd94f1c2d41ea267ced2764ae13636f14`
- **Bytes:** 21,052,449
- **Content-Type:** `application/zip`

## Deferred sources

- **`sec.formadv.bulk`** — SEC Form ADV bulk CSVs (all advisers). Multi-GB; Day 8 (05_parse_adv.py) per DATA-PLAN §8. Defer until Day 8.
- **`sig.lite_core`** — SIG Lite / SIG Core. Licensed ($6,500-$7,200/yr). Not redistributable. Stub canonical IDs from NIST/ISO until license procured. DATA-PLAN §1 + §4.4.
- **`bny.edgar.filings`** — BNY Mellon Corp 10-K, 10-Q, 8-K, DEF 14A via SEC EDGAR (CIK 1390777). Day 3-4 ingest via 01_fetch_edgar.py. Day 1-2 vendors framework sources only.
- **`bny.ir.pillar3_sustainability`** — BNY Pillar 3 + Sustainability disclosures. Day 3-4 ingest via 02_fetch_bny_ir.py.
