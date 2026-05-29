# DECISIONS.md — Every Ambiguity Resolved

This document records every significant technical and design decision, what I chose, why, and what I would ask the PM if I had the chance.

---

## 1. SAP Ingestion Format: Why Flat File CSV (not IDoc, not OData)

**Options considered:**

| Option | Reality |
|--------|---------|
| SAP IDoc | Designed for system-to-system EDI. Requires SAP Basis access to configure outbound IDocs. Would never be what a sustainability team uploads manually. |
| SAP OData | Requires a live SAP system with Internet-facing OData service enabled. Security-restricted in most enterprises. Needs OAuth/SAML. Not a Day 1 option. |
| SAP BAPI | Programmatic interface, not a file format. Requires SAP RFC connectivity. |
| **Flat file CSV** | **What sustainability teams actually get.** A scheduled ABAP report or manual SE16N/SE16 table download produces a delimited flat file. This is the realistic path for an enterprise client who doesn't have IT standing up APIs. |

**What I chose:** Flat file CSV export, semicolon-delimited (SAP default in German locale), with auto-detection fallback to comma.

**Research basis:** SAP MM module documentation for material document (MSEG table), EKPO purchase order items. The field names MENGE (quantity), MEINS (unit of measure), WERKS (plant), BLDAT (document date), MATNR (material number) are standard across SAP ECC 6.0 and S/4HANA.

**What I would ask the PM:** "Do any of their SAP systems run in German locale? Do they have a Basis resource who can set up a scheduled ABAP report, or will a manual SE16N download be the process?"

---

## 2. Utility Ingestion Format: Why Portal CSV (not PDF, not Green Button API)

**Options considered:**

| Option | Reality |
|--------|---------|
| PDF bill parsing | Requires OCR. Unstructured. Every utility has a different layout. Brittle in production — any template change breaks the parser. |
| Green Button API (ESPI) | US standard only. Not available from most Indian/UK/European utilities. Requires OAuth enrollment with each utility. Takes weeks to set up per meter. |
| **Portal CSV export** | **What facilities teams actually do.** EcoStruxure, Siemens Navigator, and direct utility portals (TATA Power, CESC, PG&E) all export CSVs. Facilities managers know this flow. |

**What I chose:** Portal CSV export with flexible header mapping, billing period preservation, and unit normalisation to kWh.

**Key insight from research:** Billing periods are not calendar months. A bill from Nov 18 to Dec 19 is standard in UK utilities (quarterly billing converted to monthly). I store `period_start` and `period_end` verbatim rather than assuming month alignment.

**What I would ask the PM:** "Do any of the client's facilities have automated Green Button data export? Does the client track market-based Scope 2 (i.e., do they have PPAs or renewable energy certificates)?"

---

## 3. Travel Ingestion Format: Why CSV (not live Concur API)

**Options considered:**

| Option | Reality |
|--------|---------|
| Concur API (OAuth) | Requires IT-provisioned OAuth client credentials, admin consent for data export scope. SAP Concur's `/api/v3.0/expense/reportdigests` API works but needs tenant-level setup. Takes 2-4 weeks to provision. |
| Navan (TripActions) API | Similar OAuth requirement. Company-specific. |
| **CSV export from Concur** | **Realistic for a prototype.** Sustainability leads already export Concur data as CSV for manual analysis. The export includes all fields needed. |

**What I chose:** CSV export. The API integration is documented as a Phase 2 enhancement in TRADEOFFS.md.

**What I would ask the PM:** "Does the client's Concur admin have the permissions to enable data export APIs? Is there a preference for Concur vs Navan?"

---

## 4. Airport Distance Calculation: Why Great Circle + ICAO Uplift

When travel platforms export only IATA codes (e.g., `BOM → LHR`) without distance, we must calculate it.

**What I chose:** Haversine formula (Great Circle distance) + 9% ICAO uplift for indirect routing.

**Why 9% uplift?** ICAO's Carbon Emissions Calculator methodology applies a 9% uplift factor to account for the fact that aircraft don't fly perfectly straight-line routes. DEFRA 2023 guidance also recommends this approach.

**Limitation acknowledged:** IATA coordinate lookup covers ~40 major hubs in the embedded table. Production would use the OpenFlights database (7,000+ airports, freely available, updated regularly).

**What I would ask the PM:** "Does the travel platform export distances? Most modern platforms (Navan, Egencia) do. If yes, we skip the calculation entirely and use the provided value."

---

## 5. Travel Class and Emission Factors

Business class emissions are approximately **2.4× economy** for the same route (DEFRA 2023). First class is approximately **4× economy**. This is not cosmetic — it materially changes Scope 3 numbers.

**What I chose:** Parse `class` field and map to one of: economy / premium_economy / business / first. Apply the class-specific DEFRA factor. Default to economy if class is unknown (conservative, logs a warning).

**Why include Radiative Forcing (RF)?** DEFRA recommends including an RF multiplier of ~1.9× for aviation to account for the non-CO₂ warming effects at altitude (contrails, NOx). I apply this because it is the current best practice for voluntary and mandatory Scope 3 reporting in the UK. Some frameworks (GHG Protocol) leave RF optional — I flag this in the record's `emission_factor_source`.

---

## 6. Emission Factor Database: Why DEFRA 2023

**Options:**

| Source | Coverage |
|--------|----------|
| DEFRA 2023 (UK) | UK grid, fuel combustion, travel — comprehensive and widely accepted |
| EPA eGRID 2022 (US) | US grid factors, state-level |
| CEA India 2022 | India grid factors |
| IPCC AR5/AR6 | GWP values for GHGs — used by DEFRA to build conversion factors |

**What I chose:** DEFRA 2023 as primary global factor set, supplemented by EPA and CEA for US and India grids. These are the factors auditors are most likely to recognise and accept.

**Limitation:** Factors are seeded statically in the `seed_data` management command. A real deployment needs a process to update factors annually when DEFRA publishes new ones.

---

## 7. Anomaly Detection Thresholds

I flag records that exceed per-category plausibility thresholds:

| Category | Min | Max | Rationale |
|----------|-----|-----|-----------|
| fuel_combustion | 0.001 L | 1,000,000 L | A site burning >1M litres/day is a refinery, not an office. Flag for review. |
| electricity | 1 kWh | 10,000,000 kWh | 10 GWh/month per meter is a data centre — possible, but worth confirming. |
| flight | 100 km | 25,000 km | Minimum reasonable flight; 25,000 km exceeds any single flight route. |
| hotel | 1 night | 365 nights | >365 nights in one trip record is a data entry error. |

These are sanity checks, not business rules. All flagged records are still created and visible to analysts — the flag is a prompt to review, not a block.

---

## 8. Review → Lock Workflow

**What I chose:** Approving a record immediately locks it (`is_locked = True`). Locked records cannot be edited by analysts. An admin can unlock with a note, which creates an `AuditLog` entry with `action=UNLOCKED`.

**Why lock on approval (not on batch finalisation)?** Locking at the record level rather than the batch level gives analysts flexibility to approve records incrementally as they gain confidence, rather than having to approve an entire batch at once.

---

## 9. Market-Based vs Location-Based Scope 2

**What I chose:** Store both. If the utility portal provides a grid factor (market-based), we store it in `metadata.market_based_factor` and use it for `co2e_kg`. If not, we use the location-based grid factor from our `EmissionFactor` table.

The `emission_factor_source` field makes it clear which method was used: `"market_based_from_utility"` vs `"DEFRA 2023 (UK Grid)"`.

**What I would ask the PM:** "Does the client have any Renewable Energy Certificates (RECs) or Power Purchase Agreements (PPAs)? If yes, market-based Scope 2 may be zero and we should capture that."

---

## 10. What I Would Ask the PM (Consolidated)

1. Do any of the client's SAP systems run in German locale, or have they already configured English output?
2. Is market-based Scope 2 a Day 1 requirement (PPAs, RECs)?
3. Do they need multi-currency handling for travel spend, or is reporting in a single base currency acceptable?
4. What is the expected file size for the SAP export? (>100k rows would require async processing)
5. Do they have Concur admin access to enable API export, or will CSV download be the long-term process?
6. What emission factor framework does their auditor prefer — DEFRA, EPA, or GHG Protocol?
7. Is Scope 3 Category 1 (procurement) in scope for this engagement, or just Category 6 (travel)?
