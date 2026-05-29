# SOURCES.md — Real-World Format Research

For each source: what real-world format I researched, what I learned, what the sample data looks like and why, and what would break in a real deployment.

---

## Source 1: SAP — Fuel & Procurement

### What format I researched

SAP materials management data can be extracted through several paths. I researched:

- **SAP MSEG table** (Material Document Segment) — the transactional table for goods movements. Fields: MANDT (client), MBLNR (material document number), MJAHR (year), ZEILE (item), BWART (movement type), MATNR (material number), WERKS (plant), MENGE (quantity), MEINS (unit of measure), ERFMG/ERFME (entry quantity/unit), KOSTL (cost centre), DMBTR (amount in local currency).
- **SAP EKPO table** (Purchase Order Item) — for procurement-side data including vendor, material, and quantity ordered.
- **SE16N / SE16 transaction** — how sustainability leads typically extract data: navigate to the table, apply date filters, download as spreadsheet.
- **Movement type codes** — 261 = goods issue to cost centre (fuel used from stock), 101 = goods receipt from purchase order, 122 = return to vendor. Only 261 and 501 movements represent actual consumption.
- **SAP locale settings** — German locale (system language DE) produces column headers in German, number format with period as thousands separator and comma as decimal (`1.234,567`), and date format `DD.MM.YYYY`.

**Key sources:** SAP Help Portal (help.sap.com), SAP Community blog on MSEG field catalogue, ABAP Dictionary table documentation for MM module.

### What I learned

1. SAP plant codes are meaningless without a lookup table. `P001` means nothing. The mapping from plant code to facility name is stored in SAP's own master data (T001W table) but will not be in a flat file export.
2. German SAP installs export semicolon-delimited files with German number and date formats by default. Any parser that assumes comma-delimited or ISO dates will silently corrupt data.
3. Unit codes are internal SAP codes, not ISO standards. `L` = litre, `M3N` = normal cubic metre (for gas at standard pressure), `M3B` = standard cubic metre, `GL` = US gallon. These are not obvious and not documented in the export itself.
4. SAP sometimes exports a BOM (byte order mark, `\ufeff`) at the start of UTF-8 files. Parsers that don't strip this will corrupt the first column header.
5. The movement type determines whether a row represents consumption (261 = fuel drawn from stock) or procurement receipt (101 = goods received from supplier). A parser that ingests all rows without filtering by movement type will double-count — once when fuel is received into stock, once when it's issued.

### Sample data design rationale

```
BLDAT;BUDAT;WERKS;MATNR;MAKTX;MENGE;MEINS;KOSTL;BELNR;BWART
20240115;20240116;P001;DIESEL-HSD-001;High Speed Diesel;5000;L;CC-101;4900012345;261
20240120;20240121;P002;NAT-GAS-001;Natural Gas Supply;12000;M3N;CC-201;4900012347;261
20240125;20240126;P003;DIESEL-HSD-001;High Speed Diesel;8.000,500;L;CC-301;4900012348;261
```

- German headers (BLDAT, WERKS, MATNR, MENGE, MEINS) — reflects what a German-locale SAP system actually exports
- `M3N` unit for natural gas — the normal cubic metre is the correct unit for metered gas; `L` would be wrong
- `8.000,500` — German number format for 8000.5, testing that the parser handles comma-as-decimal
- Row with `00000000` date — SAP sometimes exports this for unposted documents; the parser should treat it as an error, not a date
- One deliberately invalid row (`INVALID` quantity) — tests error logging
- Mix of fuel (Scope 1) and procurement/materials rows (Scope 3) — tests category classification

### What would break in a real deployment

1. **Plant code lookup** — the `PlantCodeMapping` table would be empty until the client's onboarding team populates it. Every record would show `facility_name = "Unknown (P001)"`.
2. **Material classification** — real SAP material numbers (e.g., `ZEROFUEL-001-HSD`) don't contain readable keywords. A real deployment needs a client-provided material-to-fuel-type mapping table, not keyword matching.
3. **Movement type filtering** — my parser doesn't filter by `BWART`. A real deployment must only ingest movement type 261 (goods issue) to avoid double-counting.
4. **Large files** — a multinational client's SAP export for a full year could be 500,000+ rows. Synchronous processing would time out. Celery async task queue needed.
5. **Multi-company-code SAP landscapes** — large clients have multiple SAP company codes. A flat file export may contain data from multiple legal entities that should be reported separately.

---

## Source 2: Utility / Electricity

### What format I researched

- **Green Button Data (GBD)** — US standard based on the ESPI (Energy Service Provider Interface) specification. Utilities like PG&E, Con Edison, and Duke Energy support Green Button. Format: XML or CSV. The CSV variant exports: account number, meter serial, service date (start/end), net consumption (kWh), peak demand (kW).
- **EcoStruxure (Schneider Electric)** — enterprise energy management portal. CSV export fields: Site, Meter, Period From, Period To, Consumption, Unit, Cost, Currency.
- **Siemens Navigator** — similar enterprise portal, similar CSV structure.
- **UK utility portals** (EDF, British Gas Business, UK Power Networks) — billing period, meter point admin number (MPAN), consumption in kWh, half-hourly demand profile optional.
- **Indian utilities** (TATA Power, CESC, BSES Rajdhani) — consumption in kWh or units (1 unit = 1 kWh in Indian billing), bi-monthly billing cycles common.

**Key sources:** Green Button Alliance developer documentation (greenbuttondata.org), Schneider Electric EcoStruxure API reference, OFGEM meter data documentation (UK), Bureau of Energy Efficiency India guidance.

### What I learned

1. **Billing periods don't align with calendar months.** This is the most important and most commonly ignored fact about utility data. UK utilities typically read meters every 28-32 days. A bill from 18 January to 17 February spans parts of two calendar months. Any system that assumes period_start = month start will produce wrong monthly allocations.
2. **Multiple meters per facility is the norm, not the exception.** A manufacturing plant may have 10-20 meters — one per building, one per major piece of equipment. The CSV export has one row per meter per billing period. Aggregating to facility level requires grouping by facility_id, not meter_id.
3. **Units vary by energy type.** Electricity is kWh. Gas (if a utility exports gas consumption) may be in therms, CCF, MCF, or GJ. Some portals mix energy types in the same export.
4. **Demand vs consumption.** Many utility CSVs include both peak demand (kW, the rate of consumption) and total consumption (kWh, the actual energy used). Only kWh is relevant for Scope 2 emissions. Parsers that ingest kW as if it were kWh produce numbers that are off by a factor of ~730 (hours in a month).
5. **Market-based vs location-based Scope 2.** If a client has a PPA or buys RECs, their market-based Scope 2 may be zero even if they consume grid electricity. Some portal exports include a grid factor column.

### Sample data design rationale

```
account_number,meter_id,facility_id,facility_name,billing_start,billing_end,consumption,unit,tariff_code,country
ACC-001,MTR-1001,P001,London Manufacturing Plant,2024-01-18,2024-02-17,45230,kWh,TOU-D-4,GBR
ACC-003,MTR-3001,P003,Frankfurt Distribution Hub,2024-01-15,2024-02-14,22100,MWh,HT-2-A,DEU
```

- Billing periods starting on the 18th — real-world billing cycle, not artificially aligned to month boundaries
- Mix of kWh (UK) and MWh (Germany) — different regions use different default units
- Multiple meters for the same facility (MTR-1001, MTR-1002 both at P001) — tests facility-level aggregation
- One row with empty consumption — tests null handling
- Facilities in GBR, IND, DEU, USA, AUS — tests that different location-based factors are applied

### What would break in a real deployment

1. **Billing period pro-ration** — the current model stores `period_start` and `period_end` verbatim. Monthly or quarterly reporting requires splitting bills at period boundaries (e.g., a 30-day bill spanning two months needs to be split proportionally). Not implemented.
2. **Half-hourly data** — some UK I&C (Industrial & Commercial) customers have half-hourly metering. That's 48 rows per meter per day. A year of half-hourly data for a facility with 20 meters = 350,000 rows. The current parsing pipeline handles this but the review dashboard would need aggregation before display.
3. **PDFs** — many facilities teams have only PDF bills, not CSV exports. OCR would be required. See TRADEOFFS.md.
4. **Currency and cost data** — the CSV may include cost (£ per kWh) but we don't use it for Scope 2 calculation. A spend-based fallback would need this.

---

## Source 3: Corporate Travel

### What format I researched

- **SAP Concur expense report export** — the most common enterprise travel platform. Standard CSV export includes: Report Name, Report ID, Employee ID, Expense Type, Transaction Date, Amount, Currency, Merchant Name, City of Purchase. The travel-specific fields (origin/destination airports, cabin class) are in the Travel module, accessible via a separate travel report export or the Concur API (`/api/v3.0/travelrequest/requests`).
- **Navan (TripActions)** — newer platform, used by Stripe, Snowflake, etc. Export fields: Booking ID, Traveler ID, Trip Type (Air/Hotel/Car), Origin, Destination, Departure Date, Cabin, Estimated CO2 (tonnes) — Navan pre-computes CO₂e using its own methodology.
- **American Express GBT** — enterprise travel management. Export includes IATA codes, ticket class, fare basis code.
- **Manual travel spreadsheets** — many smaller companies maintain travel logs in Excel. These have no standard format.

**Key sources:** SAP Concur Developer Center (developer.concur.com), Navan data export documentation, ICAO Carbon Emissions Calculator methodology paper, DEFRA 2023 GHG Conversion Factors for Company Reporting (travel section).

### What I learned

1. **Distances are rarely provided.** Concur's basic expense report doesn't include flight distance. You have origin and destination cities or airport codes. You must calculate distance or use a lookup table.
2. **Travel class dramatically changes CO₂e.** DEFRA 2023 factors for a 7,000 km flight: economy = 1,785 kg CO₂e, business = 4,285 kg CO₂e (2.4× economy), first = 7,141 kg CO₂e (4× economy). A company with senior executives travelling business class can have 2-3× higher Scope 3 Category 6 emissions than a headcount-equivalent company with economy-only travel.
3. **Radiative Forcing (RF).** DEFRA recommends including RF for aviation because aircraft emissions at altitude cause warming effects (contrails, NOx) beyond the CO₂ itself. The RF multiplier effectively increases the CO₂e factor by ~1.9×. This is a significant methodological choice — I include it, but document it.
4. **Hotels need country, not city.** Emission factors for hotel stays are country-level in DEFRA. The UK factor (28.6 kg CO₂e/room-night) differs from the global average (34 kg CO₂e/room-night from Cornell Hotel Sustainability Benchmarking).
5. **Ground transport categories.** Car hire (employee driving), taxi/rideshare (employee passenger), and rail all have different emission factors. Conflating them produces wrong numbers.

### Sample data design rationale

```
TRP-001,EMP-101,flight,BOM,LHR,2024-01-10,business,,,,4500,GBP
TRP-002,EMP-102,flight,DEL,SFO,2024-01-15,economy,,,,1200,USD
TRP-008,EMP-108,flight,SIN,NRT,2024-02-01,first,,,,5600,SGD
TRP-007,EMP-107,flight,INVALID,XYZ,2024-01-30,business,,,,3200,USD
```

- No `distance_km` provided for most rows — tests Great Circle calculation fallback
- Mix of business, economy, and first class — tests class-specific factor lookup
- `INVALID` and `XYZ` IATA codes — tests graceful handling of unrecognised airports (flag, don't block)
- Hotel records paired with flights — tests that segment_type drives different calculation paths
- Employee IDs only, not names — privacy by design; we never store traveller names
- Multiple currencies (GBP, USD, AED, SGD) — tests that we store spend data as-is without attempting conversion

### What would break in a real deployment

1. **IATA lookup table completeness** — the embedded table has 40 airports. The first time an employee flies through a regional airport (e.g., Tiruchirappalli, India, `TRZ`) that isn't in the table, the record gets flagged with `FACTOR_MISSING`. Production needs the full OpenFlights database.
2. **Concur's travel data is separate from expense data** — the expense report CSV doesn't always contain IATA codes. You may get "London Heathrow" as text, not "LHR". Text-to-IATA mapping requires a geocoding step.
3. **Domestic vs international classification** — DEFRA has separate factors for domestic UK flights vs short-haul international vs long-haul international. The current model uses a single per-class factor. Production should classify by route distance into short/long-haul buckets.
4. **Multi-leg trips** — Concur may export a BOM→LHR→JFK trip as two rows (BOM→LHR, LHR→JFK) or as one row with the final destination. The current parser treats each row as one segment. If a client's Concur is configured to aggregate multi-leg trips into one row, distance calculation from airport codes would be wrong.
