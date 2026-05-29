# MODEL.md — Breathe ESG Data Model

## Overview

The data model solves one core problem: **taking messy, inconsistent emissions activity data from three very different source systems and turning it into a single, auditable, scope-classified emissions ledger that a regulator could inspect.**

Every design decision traces back to one of five requirements:
1. Multi-tenancy — data from one client must never leak to another
2. Scope 1/2/3 classification — every row belongs to a GHG Protocol category
3. Source-of-truth tracking — a regulator must be able to trace any CO₂e number back to its raw source byte
4. Unit normalisation — activity data arrives in dozens of units; we must store both the original and the canonical form
5. Audit trail — every state change is recorded permanently, including who did it

---

## Entity Map

```
Client
  ├── PlantCodeMapping          (SAP plant code → human facility name)
  ├── EmissionFactor            (client-specific or global factor table)
  ├── UnitConversion            (unit conversion lookup)
  ├── User                      (scoped to a client)
  └── IngestionBatch
        ├── RawRecord           (immutable — one per source row)
        │     └── EmissionRecord
        │           └── AuditLog  (append-only)
        └── (batch-level error summary)
```

---

## 1. Multi-Tenancy

**Approach:** Application-layer row-level tenancy. Every table that contains emissions data has a `client` foreign key. Every queryset in every viewset filters by `client` before any other filter.

```python
# Every query starts with this pattern — no exceptions
qs = EmissionRecord.objects.filter(client=request.user.client)
```

**Why not schema-per-tenant or database-per-tenant?**

Schema-per-tenant (Postgres schemas) adds deployment and migration complexity with no meaningful security benefit at this scale. Database-per-tenant makes cross-client analytics (which Breathe needs internally) structurally difficult. Row-level tenancy with disciplined queryset discipline is the pragmatic default for a prototype that needs to prove out the model before adding infrastructure.

**What I would add before production:** A middleware that sets a thread-local `current_client` and verifies every queryset against it — preventing any viewset from accidentally skipping the filter.

---

## 2. Immutable Raw Storage

`RawRecord` stores the **exact row as it came off the wire**, as a JSON dict with keys verbatim from the source file. This is non-negotiable for an auditable ESG system.

```json
{
  "BLDAT": "20240115",
  "WERKS": "P001",
  "MATNR": "DIESEL-HSD-001",
  "MENGE": "5.000",
  "MEINS": "L",
  "KOSTL": "CC-101"
}
```

**Why JSON and not a typed model?** Because the schema of each source file is unknown until it arrives. A SAP export from one client's landscape may have 8 columns; another may have 22. JSON lets us store all of them without schema changes per client. The downside — you can't query inside the JSON efficiently — is acceptable because we never need to query `raw_records.raw_data` directly; we query `emission_records` instead.

`RawRecord` records that failed to parse are stored with `parse_status=ERROR` and a human-readable `parse_error` message. The analyst can see exactly which rows failed and why.

---

## 3. EmissionRecord — The Normalised Layer

This is the core table. It exists separately from `RawRecord` to enforce the principle that **we never edit source data**.

```
EmissionRecord
  raw_record (FK, OneToOne)     → chain of custody back to source byte
  scope (1/2/3)                 → GHG Protocol classification
  category                      → fuel_combustion / electricity / flight / hotel / ground_transport / procurement
  subcategory                   → diesel / natural_gas / economy / business / etc.
  activity_value                → original numeric value from source
  activity_unit                 → original unit from source (L, M3N, kWh, km, nights)
  normalised_value              → after unit conversion
  normalised_unit               → canonical unit (litre, kWh, km, nights)
  emission_factor_value         → SNAPSHOT of factor at calculation time
  emission_factor_source        → "DEFRA 2023", "EPA eGRID 2022", etc.
  co2e_kg                       → final output, computed as normalised_value × factor
  period_start / period_end     → activity period (not billing date — different for utility)
  review_status                 → PENDING / APPROVED / FLAGGED / REJECTED
  flag                          → machine-generated flag code
  is_locked                     → true after analyst approves; prevents further edits
```

**Key design choice — why store `emission_factor_value` as a Decimal snapshot?**

The `EmissionFactor` table will be updated annually (DEFRA publishes new factors every year). If we store only a FK to the factor, and the factor changes, we can no longer reproduce the historic calculation. The snapshot ensures that the CO₂e number an auditor sees today is identical to what the analyst approved, even if the factor table has been updated since.

---

## 4. Scope 1/2/3 Classification

| Source | Scope | GHG Protocol Category |
|--------|-------|-----------------------|
| SAP fuel (diesel, petrol, gas) | **Scope 1** | Stationary combustion |
| SAP procurement (paper, steel) | **Scope 3** | Cat. 1 Purchased Goods & Services |
| Utility electricity | **Scope 2** | Purchased electricity |
| Corporate flights | **Scope 3** | Cat. 6 Business Travel |
| Corporate hotels | **Scope 3** | Cat. 6 Business Travel |
| Ground transport (car hire, taxi) | **Scope 3** | Cat. 6 Business Travel |

Classification is set during parsing based on material description keywords (SAP) or segment type (travel). Analysts can correct it during review — the change is logged in `AuditLog`.

---

## 5. Unit Normalisation Pipeline

```
Source row arrives
    │
    ▼
Parser maps raw unit → canonical unit (SAP: L/M3N/KG, Utility: kWh/MWh, Travel: km/nights)
    │
    ▼
UnitConversion table applies multiplier (e.g. 1 US gallon = 3.78541 L)
    │
    ▼
EmissionFactor applied to canonical value  →  co2e_kg
```

Both the original (`activity_value` + `activity_unit`) and the normalised form are stored. An analyst can inspect both and flag anomalies where the conversion looks wrong.

**Units we handle:**

| Domain | Raw units | Canonical unit |
|--------|-----------|---------------|
| Liquid fuel | L, GAL, GL, BBL, M3 | litre |
| Gas fuel | M3N, M3B, CF, FT3 | m³ |
| Electricity | kWh, MWh, GWh, GJ, therm | kWh |
| Distance | km, miles, nautical miles | km |
| Hotel | nights | nights |

---

## 6. Audit Trail

`AuditLog` is append-only. It records:
- `action`: CREATED / APPROVED / FLAGGED / REJECTED / LOCKED / UNLOCKED / FACTOR_UPDATED / BULK_APPROVED
- `before_state`: full JSON snapshot of record before change (null for CREATED)
- `after_state`: full JSON snapshot after change
- `changed_by`: user FK
- `changed_at`: timestamp (auto_now_add — cannot be edited)
- `ip_address`: for security

**Why full snapshots rather than just the changed field?** It costs more storage but allows complete reconstruction of any historical state without chasing a diff chain. For a regulatory audit, being able to say "here is exactly what this record looked like on 15 March when the analyst approved it" is more valuable than a compact diff.

There is no `DELETE` path for `AuditLog` rows anywhere in the codebase. Deleting audit records would require direct database access.

---

## 7. Lookup Tables

### PlantCodeMapping
SAP plant codes (`P001`, `P002`) are internal identifiers. Without a mapping table, a sustainability analyst looking at the review dashboard would see `P001` and have no idea if that's the London plant or the Mumbai office. The mapping is populated during client onboarding.

**What happens when a plant code has no mapping?** The parser stores the raw code in `facility_id` and sets `facility_name = "Unknown (P001)"`. The record is not blocked — but the analyst will see it in the review dashboard and can add a note.

### EmissionFactor
Stores factors from DEFRA 2023 (UK), EPA eGRID 2022 (US), CEA 2022 (India). Scoped to `client = null` for global defaults; client-specific factors can override by setting `client = <client>`.

Lookup priority: **client-specific factor → global default → null (flag as FACTOR_MISSING)**.

---

## What I Would Add Before Production

1. **Postgres row-level security** as a second line of defence against application-layer tenancy bugs
2. **Async ingestion** via Celery + Redis — large SAP files (100k rows) would block the web worker under the current synchronous design
3. **Factor versioning** — `valid_from` / `valid_to` on `EmissionFactor` allows retroactive recalculation when DEFRA updates its factors
4. **Billing period pro-ration** — utility records spanning two calendar months need to be split at the month boundary for monthly reporting
