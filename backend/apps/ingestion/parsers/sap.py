"""
SAP Fuel & Procurement CSV Parser
==================================
Handles SAP MM / SAP ECC flat-file exports as downloaded by a sustainability
lead from SAP's Material Ledger or via a scheduled ABAP report.

Real SAP quirks handled here:
  - German column headers (MENGE, MEINS, WERKS, BLDAT, MATNR, etc.)
  - Mixed date formats: YYYYMMDD and DD.MM.YYYY both observed in exports
  - Unit codes from SAP's internal unit table (L, M3, KG, GL, GAL, M3N)
  - Plant codes that are internal identifiers needing a lookup table
  - Material numbers that need mapping to fuel/procurement category
  - BOM character at start of file (UTF-8 BOM common in SAP exports)
  - Semicolon-delimited files (SAP default) vs comma-delimited

Sources consulted:
  - SAP Help: Materials Management (MM) module, document types RE/WE
  - SAP field catalogue: EKPO (purchase order item), MSEG (material doc seg)
  - Internal field MEINS: Unit of Measure for Purchase Order
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


# ── SAP Header Normalisation Map ─────────────────────────────────────────────
# Maps both German SAP field names and common English variants to our internal names.
SAP_HEADER_MAP = {
    # Date fields
    'bldat': 'document_date',
    'budat': 'posting_date',
    'cpudt': 'entry_date',
    'document date': 'document_date',
    'posting date': 'posting_date',
    # Quantity / unit
    'menge': 'quantity',
    'meins': 'unit',
    'quantity': 'quantity',
    'unit of measure': 'unit',
    'uom': 'unit',
    # Material
    'matnr': 'material_number',
    'material': 'material_number',
    'material number': 'material_number',
    'material_number': 'material_number',
    # Plant / facility
    'werks': 'plant_code',
    'plant': 'plant_code',
    'plant_code': 'plant_code',
    # Cost centre
    'kostl': 'cost_centre',
    'cost centre': 'cost_centre',
    'cost center': 'cost_centre',
    # Document number (SAP reference)
    'belnr': 'document_number',
    'document number': 'document_number',
    'doc. no.': 'document_number',
    # Material description
    'maktx': 'material_description',
    'material description': 'material_description',
    'description': 'material_description',
    # Amount
    'dmbtr': 'amount_lc',
    'amount': 'amount_lc',
    # Movement type
    'bwart': 'movement_type',
    'movement type': 'movement_type',
}

# ── SAP Unit Code → Canonical Unit ──────────────────────────────────────────
# SAP uses internal unit codes. Maps to our normalised unit strings.
SAP_UNIT_MAP = {
    'L':   'litre',
    'LTR': 'litre',
    'LT':  'litre',
    'M3':  'm3',
    'M3N': 'm3',       # Normal cubic metre (natural gas)
    'M3B': 'm3',       # Standard cubic metre
    'KG':  'kg',
    'TO':  'tonne',    # Metric tonne
    'T':   'tonne',
    'KWH': 'kwh',
    'MWH': 'mwh',
    'GL':  'us_gallon',
    'GAL': 'us_gallon',
    'GLL': 'us_gallon',
    'G':   'us_gallon',  # SAP sometimes uses G for gallon in legacy configs
    'BBL': 'barrel',
    'FT3': 'cubic_ft',
    'CF':  'cubic_ft',
    'BTU': 'btu',
    'MMBTU': 'mmbtu',
    'GJ':  'gj',
    'TJ':  'tj',
}

# ── Material Number → (Category, Subcategory, Scope) ────────────────────────
# In reality this is a client-specific lookup. These are common patterns.
# Pattern matching on material description is a fallback.
MATERIAL_CATEGORY_MAP = {
    # Diesel variants
    'diesel': ('fuel_combustion', 'diesel', 1),
    'gasoil': ('fuel_combustion', 'gas_oil', 1),
    'gas oil': ('fuel_combustion', 'gas_oil', 1),
    'hsd': ('fuel_combustion', 'diesel', 1),       # High speed diesel (India)
    # Petrol / gasoline
    'petrol': ('fuel_combustion', 'petrol', 1),
    'gasoline': ('fuel_combustion', 'petrol', 1),
    'unleaded': ('fuel_combustion', 'petrol', 1),
    # Natural gas
    'natural gas': ('fuel_combustion', 'natural_gas', 1),
    'lng': ('fuel_combustion', 'lng', 1),
    'cng': ('fuel_combustion', 'cng', 1),
    # Fuel oil
    'fuel oil': ('fuel_combustion', 'fuel_oil', 1),
    'hfo': ('fuel_combustion', 'heavy_fuel_oil', 1),
    'lfo': ('fuel_combustion', 'light_fuel_oil', 1),
    # LPG
    'lpg': ('fuel_combustion', 'lpg', 1),
    'propane': ('fuel_combustion', 'lpg', 1),
    # Procurement (Scope 3)
    'paper': ('procurement', 'paper', 3),
    'packaging': ('procurement', 'packaging', 3),
    'steel': ('procurement', 'steel', 3),
    'aluminium': ('procurement', 'aluminium', 3),
    'aluminum': ('procurement', 'aluminium', 3),
}


@dataclass
class ParsedSAPRow:
    """Structured output from the SAP parser, before EmissionRecord creation."""
    row_number: int
    document_date: Optional[date]
    plant_code: str
    material_number: str
    material_description: str
    quantity: Decimal
    unit: str                # SAP unit code, mapped to canonical
    canonical_unit: str
    cost_centre: str
    document_number: str
    category: str
    subcategory: str
    scope: int
    raw: dict                # Original row dict, keys verbatim from file
    warnings: list = field(default_factory=list)


@dataclass
class ParseError:
    row_number: int
    field: str
    message: str
    raw: dict


def _normalise_header(header: str) -> str:
    """Strip whitespace, lowercase, map SAP name to internal name."""
    cleaned = header.strip().lower().replace('\ufeff', '')  # Strip BOM
    return SAP_HEADER_MAP.get(cleaned, cleaned)


def _parse_sap_date(value: str) -> Optional[date]:
    """
    SAP exports dates in at least three formats depending on locale settings:
      YYYYMMDD  — most common in system exports
      DD.MM.YYYY — German locale output
      MM/DD/YYYY — US locale output
    """
    value = value.strip()
    if not value or value == '00000000':
        return None
    # YYYYMMDD
    if re.match(r'^\d{8}$', value):
        try:
            return datetime.strptime(value, '%Y%m%d').date()
        except ValueError:
            pass
    # DD.MM.YYYY
    if re.match(r'^\d{2}\.\d{2}\.\d{4}$', value):
        try:
            return datetime.strptime(value, '%d.%m.%Y').date()
        except ValueError:
            pass
    # MM/DD/YYYY
    if re.match(r'^\d{2}/\d{2}/\d{4}$', value):
        try:
            return datetime.strptime(value, '%m/%d/%Y').date()
        except ValueError:
            pass
    return None


def _parse_sap_quantity(value: str) -> Optional[Decimal]:
    """
    SAP quantities use comma as decimal separator in German locale:
    1.234,567 → 1234.567
    Also handles plain 1234.567.
    """
    value = value.strip()
    if not value:
        return None
    # German format: periods as thousands sep, comma as decimal
    if re.match(r'^[\d.]+,\d+$', value):
        value = value.replace('.', '').replace(',', '.')
    else:
        value = value.replace(',', '')  # remove any thousands comma
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _classify_material(material_number: str, description: str):
    """
    Maps material to ESG category. Checks description keywords.
    Returns (category, subcategory, scope).
    """
    text = (material_number + ' ' + description).lower()
    for keyword, classification in MATERIAL_CATEGORY_MAP.items():
        if keyword in text:
            return classification
    # Default: unclassified procurement (Scope 3 catch-all)
    return ('procurement', 'unclassified', 3)


def _detect_delimiter(sample: str) -> str:
    """Auto-detect whether SAP file uses ; or , as delimiter."""
    semicolons = sample.count(';')
    commas = sample.count(',')
    return ';' if semicolons > commas else ','


def parse_sap_csv(file_bytes: bytes) -> tuple[list[ParsedSAPRow], list[ParseError]]:
    """
    Main entry point for SAP CSV parsing.

    Args:
        file_bytes: Raw bytes of the uploaded SAP export file.

    Returns:
        (parsed_rows, errors) — errors are rows that could not be parsed,
        parsed_rows may include rows with warnings.
    """
    # Decode — try UTF-8 with BOM first, fall back to latin-1 (common in
    # older SAP systems, especially German installs)
    try:
        text = file_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = file_bytes.decode('latin-1')

    # Auto-detect delimiter
    first_line = text.split('\n')[0]
    delimiter = _detect_delimiter(first_line)

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    # Normalise headers
    original_fieldnames = reader.fieldnames or []
    header_map = {h: _normalise_header(h) for h in original_fieldnames}

    parsed_rows: list[ParsedSAPRow] = []
    errors: list[ParseError] = []

    for i, raw_row in enumerate(reader, start=2):  # start=2 because row 1 is header
        # Remap keys
        row = {header_map.get(k, k): v for k, v in raw_row.items()}

        # ── Date ─────────────────────────────────────────────────────────
        doc_date = _parse_sap_date(row.get('document_date', ''))
        if doc_date is None:
            errors.append(ParseError(
                row_number=i,
                field='document_date',
                message=f"Cannot parse date: '{row.get('document_date', '')}'",
                raw=raw_row
            ))
            continue

        # ── Quantity ─────────────────────────────────────────────────────
        qty = _parse_sap_quantity(row.get('quantity', ''))
        if qty is None or qty < 0:
            errors.append(ParseError(
                row_number=i,
                field='quantity',
                message=f"Invalid quantity: '{row.get('quantity', '')}'",
                raw=raw_row
            ))
            continue

        # ── Unit ─────────────────────────────────────────────────────────
        raw_unit = row.get('unit', '').strip().upper()
        canonical_unit = SAP_UNIT_MAP.get(raw_unit)
        warnings = []
        if canonical_unit is None:
            canonical_unit = raw_unit.lower()
            warnings.append(f"Unknown SAP unit '{raw_unit}' — stored as-is, manual review needed")

        # ── Plant code ───────────────────────────────────────────────────
        plant_code = row.get('plant_code', '').strip()
        if not plant_code:
            warnings.append("No plant code — facility will be unknown")

        # ── Material / classification ────────────────────────────────────
        mat_num = row.get('material_number', '').strip()
        mat_desc = row.get('material_description', '').strip()
        category, subcategory, scope = _classify_material(mat_num, mat_desc)

        parsed_rows.append(ParsedSAPRow(
            row_number=i,
            document_date=doc_date,
            plant_code=plant_code,
            material_number=mat_num,
            material_description=mat_desc,
            quantity=qty,
            unit=raw_unit,
            canonical_unit=canonical_unit,
            cost_centre=row.get('cost_centre', '').strip(),
            document_number=row.get('document_number', '').strip(),
            category=category,
            subcategory=subcategory,
            scope=scope,
            raw=raw_row,
            warnings=warnings,
        ))

    logger.info(
        "SAP parse complete: %d parsed, %d errors",
        len(parsed_rows), len(errors)
    )
    return parsed_rows, errors
