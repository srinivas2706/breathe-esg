# TRADEOFFS.md — Three Things Deliberately Not Built

---

## 1. Live SAP OData / RFC Connector

**What it would be:** A real-time connection to the client's SAP system using either OData services (SAP Gateway) or RFC/BAPI calls (via `pyrfc`) to pull material documents and purchase orders directly, without any manual export step.

**Why I chose not to build it:**

The realistic SAP integration timeline looks like this:

1. Client IT security review of external API access — 2–4 weeks minimum
2. SAP Basis team enablement of OData services or RFC gateway — 1–2 weeks
3. OAuth/SAML configuration for external authentication — 1 week
4. Schema discovery — SAP OData schemas are client-specific; field names and structures depend on which version of SAP, which add-ons are installed, and how the client's Basis team has configured the system

That is 4–7 weeks of work that doesn't involve writing code. For a 4-day prototype, it is the wrong bet.

**What I built instead:** A flat-file CSV parser that handles the formats sustainability teams actually work with today — including SAP's German headers, multiple date formats, and unit codes.

**What real deployment would need:** A configurable SAP connector that accepts the client's specific OData endpoint, authenticates via OAuth 2.0, and maps their specific field names to our internal schema through a configuration UI.

**The honest tradeoff:** The file-upload path requires a human step (exporting from SAP, uploading the file). The API path removes that step. But the API path has hard dependencies on SAP IT infrastructure that a 4-day prototype cannot satisfy. File upload is slower operationally but it works, it's testable, and it demonstrates the full parsing and normalisation pipeline — which is the same logic the API connector would use.

---

## 2. PDF Bill Parsing (OCR-based Utility Ingestion)

**What it would be:** A pipeline that accepts PDF utility bills, extracts the relevant fields (account number, meter ID, billing period, consumption, unit) using OCR and layout analysis, and ingests them without requiring the facilities team to manually export a CSV.

**Why I chose not to build it:**

PDF parsing for utility bills is deceptively hard:

- Every utility has a different bill layout. UK Power Networks, TATA Power, PG&E, EDF, E.ON — none of them use the same template.
- OCR errors on numbers (1 vs l, 0 vs O) can silently introduce incorrect activity values. A 45,230 kWh reading parsed as 45,230,000 kWh would compute to a wildly wrong CO₂e figure — and if the analyst doesn't notice the anomaly flag, that number goes to auditors.
- Bill templates change. Utilities redesign their PDF layouts. Any hardcoded template-based parser breaks silently.
- The GHG Protocol requires that emissions be traceable to source data. A system where the "source" is a PDF parsed by a fragile OCR pipeline is harder to defend to an auditor than one where the source is an unmodified CSV export.

**What I built instead:** CSV portal export ingestion. Every major utility portal — EcoStruxure, Siemens Navigator, PG&E Energystar, UK Power Networks — offers a CSV download. The facilities team can export it in under a minute. The CSV is structured, machine-readable, and unambiguous.

**What real deployment would need:** If clients genuinely cannot export CSVs and only have PDFs, a reasonable approach is document AI (e.g., AWS Textract, Google Document AI) with a human-in-the-loop verification step before ingestion. The verification step is important — OCR results should always be confirmed by a human before being used for regulatory reporting.

**The honest tradeoff:** CSV requires a deliberate export step from the facilities team. PDF would accept the bill as-is. But PDF parsing introduces a failure mode — silent data errors — that is more dangerous than an extra click. For regulatory data, correctness beats convenience.

---

## 3. Automated Emission Factor Updates

**What it would be:** An automated pipeline that checks DEFRA, EPA, and CEA factor databases annually (or when new versions are published) and updates the `EmissionFactor` table, then optionally recalculates affected `EmissionRecord` rows.

**Why I chose not to build it:**

Automated factor updates touch approved, locked records — which is the most sensitive operation in the system. The consequences of getting this wrong are serious:

- If a factor is updated silently and recalculates CO₂e on records that have already been submitted to auditors, the numbers change retroactively. This is not acceptable.
- DEFRA, EPA, and CEA don't provide machine-readable APIs for their factor tables. Updates would require scraping PDFs or Excel files — a fragile, maintenance-heavy pipeline that is likely to break once a year exactly when you need it.
- Different clients may be contractually required to use the factor version they were using when they filed their previous report. Automatic updates could push them onto a different version without their knowledge.

**What I built instead:** A `seed_data` management command that populates factors with explicit `valid_from` and `valid_to` fields and a clear `source` label ("DEFRA 2023"). When new factors are published, an admin runs a migration or a new seed that adds the new factor version alongside the old one. Old records keep their snapshot (`emission_factor_value` is stored on the record, not computed from the live table).

**What real deployment would need:** An admin UI for factor management where an authorised user can: upload a new DEFRA conversion factors spreadsheet, preview which records would be affected by the change, choose whether to recalculate historical records or only apply the new factors to future ingestions, and generate an audit entry documenting the factor update decision.

**The honest tradeoff:** Manual factor updates require human attention once a year. But that human attention is appropriate — changing the conversion factors that underpin your regulatory filings should be a deliberate, documented decision, not an automated background task.
