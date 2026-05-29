"""
Utility / Electricity CSV Parser
==================================
Handles CSV exports from utility portals such as:
  - EcoStruxure (Schneider Electric)
  - Siemens Navigator
  - Direct utility portal exports (TATA Power, CESC, BSES in India;
    PG&E, Con Edison in US; UK Power Networks in UK)
  - Green Button Data (GBD) CSV format — US standard (ESPI)

Key complexity:
  - Billing periods don't align with calendar months.
    A bill from Nov 18 to Dec 19 spans two reporting months.
    We store period_start/period_end and pro-rate at reporting time.
  - Multiple meters per facility in the same file.
  - Units: kWh, MWh, therms, CCF, GJ — all observed in real exports.
  - Demand (kW peak) vs Consumption (kWh) mixed in some files.
    We only care about consumption for Scope 2.
  - Market-based vs location-based Scope 2 — we store both where available.

Sources consulted:
  - Green Button Alliance: https://www.greenbuttondata.org
  - ESPI (Energy Service Provider Interface) standard
  - Schneider Electric EcoStruxure API field definitions
  - UK ESOS guidance on meter data formats
"""

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)


# ── Header normalisation ─────────────────────────────────────────────────────
UTILITY_HEADER_MAP = {
    # Account / meter identifiers
    'account number': 'account_number',
    'account_number': 'account_number',
    'account no': 'account_number',
    'account no.': 'account_number',
    'meter id': 'meter_id',
    'meter_id': 'meter_id',
    'meter number': 'meter_id',
    'meter no': 'meter_id',
    'meter serial': 'meter_id',
    # Facility
    'site': 'facility_id',
    'site id': 'facility_id',
    'facility': 'facility_id',
    'facility id': 'facility_id',
    'facility name': 'facility_name',
    'location': 'facility_name',
    'building': 'facility_name',
    # Billing period
    'billing start': 'billing_start',
    'billing_start': 'billing_start',
    'start date': 'billing_start',
    'from date': 'billing_start',
    'period start': 'billing_start',
    'service from': 'billing_start',
    'billing end': 'billing_end',
    'billing_end': 'billing_end',
    'end date': 'billing_end',
    'to date': 'billing_end',
    'period end': 'billing_end',
    'service to': 'billing_end',
    # Consumption
    'consumption': 'consumption',
    'usage': 'consumption',
    'kwh': 'consumption',
    'energy': 'consumption',
    'total kwh': 'consumption',
    'total usage': 'consumption',
    'billed consumption': 'consumption',
    # Unit
    'unit': 'unit',
    'unit of measure': 'unit',
    'uom': 'unit',
    'consumption unit': 'unit',
    # Tariff
    'tariff': 'tariff_code',
    'tariff code': 'tariff_code',
    'rate': 'tariff_code',
    'rate code': 'tariff_code',
    'tariff name': 'tariff_code',
    # Country
    'country': 'country',
    # Grid emissions factor (market-based, sometimes provided by portal)
    'grid factor': 'grid_factor',
    'emission factor': 'grid_factor',
    'carbon intensity': 'grid_factor',
}

# ── Unit normalisation ────────────────────────────────────────────────────────
# All converted to kWh for Scope 2 calculation.
UTILITY_UNIT_MAP = {
    'kwh': ('kwh', Decimal('1')),
    'kw·h': ('kwh', Decimal('1')),
    'mwh': ('kwh', Decimal('1000')),
    'gwh': ('kwh', Decimal('1000000')),
    'therm': ('kwh', Decimal('29.3001')),
    'therms': ('kwh', Decimal('29.3001')),
    'ccf': ('kwh', Decimal('29.3001')),   # 1 CCF natural gas ≈ 1 therm ≈ 29.3 kWh
    'mcf': ('kwh', Decimal('293.001')),   # 1 MCF = 10 CCF
    'gj': ('kwh', Decimal('277.778')),
    'mj': ('kwh', Decimal('0.277778')),
    'btu': ('kwh', Decimal('0.000293071')),
    'mmbtu': ('kwh', Decimal('293.071')),
    'kbtu': ('kwh', Decimal('0.293071')),
}

DATE_FORMATS = [
    '%Y-%m-%d',    # ISO 8601
    '%d/%m/%Y',    # UK/India
    '%m/%d/%Y',    # US
    '%d-%m-%Y',
    '%d.%m.%Y',    # German
    '%Y%m%d',      # SAP style (sometimes appears in utility exports too)
    '%b %d, %Y',   # Jan 15, 2024
    '%d %b %Y',    # 15 Jan 2024
]


@dataclass
class ParsedUtilityRow:
    row_number: int
    account_number: str
    meter_id: str
    facility_id: str
    facility_name: str
    billing_start: date
    billing_end: date
    billing_days: int
    consumption: Decimal
    raw_unit: str
    canonical_unit: str           # always 'kwh' after normalisation
    normalised_kwh: Decimal
    tariff_code: str
    country: str
    grid_factor: Optional[Decimal]   # market-based factor if provided
    raw: dict
    warnings: list = field(default_factory=list)


@dataclass
class ParseError:
    row_number: int
    field: str
    message: str
    raw: dict


def _normalise_header(h: str) -> str:
    return UTILITY_HEADER_MAP.get(h.strip().lower().replace('\ufeff', ''), h.strip().lower())


def _parse_date(value: str) -> Optional[date]:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_quantity(value: str) -> Optional[Decimal]:
    value = value.strip().replace(',', '')   # strip thousands separator
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _normalise_unit(raw_unit: str, quantity: Decimal) -> tuple[str, Decimal, list[str]]:
    """
    Converts quantity from raw_unit to kWh.
    Returns (canonical_unit, normalised_value, warnings).
    """
    warnings = []
    unit_lower = raw_unit.strip().lower()
    mapping = UTILITY_UNIT_MAP.get(unit_lower)
    if mapping is None:
        warnings.append(f"Unknown utility unit '{raw_unit}' — stored unconverted, manual review needed")
        return raw_unit, quantity, warnings
    canonical, multiplier = mapping
    return canonical, quantity * multiplier, warnings


def parse_utility_csv(file_bytes: bytes) -> tuple[list[ParsedUtilityRow], list[ParseError]]:
    """
    Main entry point for utility CSV parsing.
    """
    try:
        text = file_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = file_bytes.decode('latin-1')

    # Skip comment/header lines (some utility exports prepend metadata rows)
    lines = text.splitlines()
    data_start = 0
    for idx, line in enumerate(lines):
        # Find the row that looks like a header (contains common field names)
        if any(kw in line.lower() for kw in ['meter', 'account', 'consumption', 'billing', 'kwh']):
            data_start = idx
            break

    clean_text = '\n'.join(lines[data_start:])
    reader = csv.DictReader(io.StringIO(clean_text))

    original_fieldnames = reader.fieldnames or []
    header_map = {h: _normalise_header(h) for h in original_fieldnames}

    parsed_rows: list[ParsedUtilityRow] = []
    errors: list[ParseError] = []

    for i, raw_row in enumerate(reader, start=data_start + 2):
        row = {header_map.get(k, k): v for k, v in raw_row.items() if k}

        # ── Billing period ──────────────────────────────────────────────
        billing_start = _parse_date(row.get('billing_start', ''))
        billing_end = _parse_date(row.get('billing_end', ''))
        if billing_start is None:
            errors.append(ParseError(i, 'billing_start',
                f"Cannot parse date: '{row.get('billing_start', '')}'", raw_row))
            continue
        if billing_end is None:
            errors.append(ParseError(i, 'billing_end',
                f"Cannot parse date: '{row.get('billing_end', '')}'", raw_row))
            continue
        if billing_end < billing_start:
            errors.append(ParseError(i, 'billing_end',
                'billing_end is before billing_start', raw_row))
            continue

        billing_days = (billing_end - billing_start).days

        # ── Consumption ─────────────────────────────────────────────────
        consumption = _parse_quantity(row.get('consumption', ''))
        if consumption is None or consumption < 0:
            errors.append(ParseError(i, 'consumption',
                f"Invalid consumption: '{row.get('consumption', '')}'", raw_row))
            continue

        # ── Unit ────────────────────────────────────────────────────────
        raw_unit = row.get('unit', 'kWh').strip()
        canonical_unit, normalised_kwh, warnings = _normalise_unit(raw_unit, consumption)

        # ── Grid factor (market-based, optional) ────────────────────────
        grid_factor = None
        gf_raw = row.get('grid_factor', '').strip()
        if gf_raw:
            try:
                grid_factor = Decimal(gf_raw)
            except InvalidOperation:
                warnings.append(f"Could not parse grid_factor '{gf_raw}'")

        parsed_rows.append(ParsedUtilityRow(
            row_number=i,
            account_number=row.get('account_number', '').strip(),
            meter_id=row.get('meter_id', '').strip(),
            facility_id=row.get('facility_id', '').strip(),
            facility_name=row.get('facility_name', '').strip(),
            billing_start=billing_start,
            billing_end=billing_end,
            billing_days=billing_days,
            consumption=consumption,
            raw_unit=raw_unit,
            canonical_unit=canonical_unit,
            normalised_kwh=normalised_kwh,
            tariff_code=row.get('tariff_code', '').strip(),
            country=row.get('country', '').strip().upper(),
            grid_factor=grid_factor,
            raw=raw_row,
            warnings=warnings,
        ))

    logger.info("Utility parse: %d rows, %d errors", len(parsed_rows), len(errors))
    return parsed_rows, errors
