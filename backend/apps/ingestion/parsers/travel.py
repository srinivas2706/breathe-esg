"""
Corporate Travel CSV Parser
============================
Handles CSV exports from corporate travel platforms:
  - SAP Concur (most common in enterprise — downloaded from Expense module)
  - Navan (formerly TripActions)
  - American Express GBT
  - Manually compiled travel reports

Key complexities handled:
  1. Airport codes (IATA) without distances — calculate via Great Circle formula
  2. Travel class matters: business = ~3x economy emission factor (DEFRA guidance)
  3. Multiple segment types: flight / hotel / car_hire / rail / taxi
  4. Employees may be identified by ID only (privacy — we store ID, not name)
  5. Hotel nights: need country for correct emission factor
  6. Distance units: some platforms give km, others give miles

GHG Protocol classification:
  - All business travel = Scope 3, Category 6 (Business Travel)

Sources consulted:
  - SAP Concur Expense Report standard export fields
  - Navan (TripActions) data export documentation
  - DEFRA 2023 GHG Conversion Factors: Business Travel section
  - ICAO Carbon Emissions Calculator methodology
  - OpenFlights airport database (IATA codes + coordinates)
"""

import csv
import io
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)


# ── IATA Airport Coordinates (subset — major hubs) ──────────────────────────
# In production: load from OpenFlights database (~7000 airports).
# Here: a representative set of 40 major hubs across regions.
IATA_COORDS: dict[str, tuple[float, float]] = {
    # India
    'BOM': (19.0896, 72.8656),   # Mumbai
    'DEL': (28.5562, 77.1000),   # Delhi
    'BLR': (13.1979, 77.7063),   # Bangalore
    'MAA': (12.9900, 80.1693),   # Chennai
    'HYD': (17.2313, 78.4298),   # Hyderabad
    'CCU': (22.6520, 88.4467),   # Kolkata
    # UK
    'LHR': (51.4775, -0.4614),   # London Heathrow
    'LGW': (51.1537, -0.1821),   # Gatwick
    'MAN': (53.3537, -2.2750),   # Manchester
    'EDI': (55.9500, -3.3725),   # Edinburgh
    # Europe
    'CDG': (49.0097, 2.5478),    # Paris CDG
    'FRA': (50.0333, 8.5706),    # Frankfurt
    'AMS': (52.3086, 4.7639),    # Amsterdam
    'MAD': (40.4936, -3.5668),   # Madrid
    'FCO': (41.8003, 12.2389),   # Rome Fiumicino
    'ZRH': (47.4647, 8.5492),    # Zurich
    'MUC': (48.3538, 11.7861),   # Munich
    'DXB': (25.2532, 55.3657),   # Dubai
    'DOH': (25.2609, 51.6138),   # Doha
    # Asia Pacific
    'SIN': (1.3644, 103.9915),   # Singapore
    'HKG': (22.3080, 113.9185),  # Hong Kong
    'NRT': (35.7647, 140.3864),  # Tokyo Narita
    'ICN': (37.4692, 126.4505),  # Seoul Incheon
    'PEK': (40.0799, 116.6031),  # Beijing Capital
    'PVG': (31.1443, 121.8083),  # Shanghai Pudong
    'SYD': (-33.9399, 151.1753), # Sydney
    'MEL': (-37.6690, 144.8410), # Melbourne
    # North America
    'JFK': (40.6413, -73.7781),  # New York JFK
    'EWR': (40.6895, -74.1745),  # Newark
    'LAX': (33.9425, -118.4081), # Los Angeles
    'ORD': (41.9742, -87.9073),  # Chicago O'Hare
    'SFO': (37.6213, -122.3790), # San Francisco
    'YYZ': (43.6777, -79.6248),  # Toronto Pearson
    # Africa / Middle East
    'JNB': (-26.1392, 28.2460),  # Johannesburg
    'NBO': (-1.3192, 36.9275),   # Nairobi
    'CPT': (-33.9648, 18.6017),  # Cape Town
    'CAI': (30.1219, 31.4056),   # Cairo
}

# ── Header normalisation ──────────────────────────────────────────────────────
TRAVEL_HEADER_MAP = {
    # Trip identifier
    'trip id': 'trip_id',
    'trip_id': 'trip_id',
    'booking id': 'trip_id',
    'booking reference': 'trip_id',
    'report id': 'trip_id',
    'expense report id': 'trip_id',
    # Employee
    'employee id': 'employee_id',
    'employee_id': 'employee_id',
    'traveler id': 'employee_id',
    'traveller id': 'employee_id',
    'user id': 'employee_id',
    # Segment type
    'segment type': 'segment_type',
    'segment_type': 'segment_type',
    'type': 'segment_type',
    'travel type': 'segment_type',
    'expense type': 'segment_type',
    # Origin / destination
    'origin': 'origin',
    'from': 'origin',
    'departure': 'origin',
    'origin airport': 'origin',
    'departure airport': 'origin',
    'destination': 'destination',
    'to': 'destination',
    'arrival': 'destination',
    'destination airport': 'destination',
    'arrival airport': 'destination',
    # Date
    'travel date': 'travel_date',
    'departure date': 'travel_date',
    'date': 'travel_date',
    'check-in date': 'travel_date',
    'checkin date': 'travel_date',
    # Class
    'class': 'travel_class',
    'cabin class': 'travel_class',
    'class of service': 'travel_class',
    'fare class': 'travel_class',
    # Distance
    'distance': 'distance_km',
    'distance (km)': 'distance_km',
    'distance km': 'distance_km',
    'distance (miles)': 'distance_miles',
    'distance miles': 'distance_miles',
    # Hotel
    'nights': 'hotel_nights',
    'hotel nights': 'hotel_nights',
    'number of nights': 'hotel_nights',
    'hotel country': 'hotel_country',
    'country': 'hotel_country',
    # Spend (for spend-based calculation fallback)
    'amount': 'spend',
    'total amount': 'spend',
    'spend': 'spend',
    'currency': 'currency',
}

# ── Segment type normalisation ────────────────────────────────────────────────
SEGMENT_TYPE_MAP = {
    'flight': 'flight',
    'air': 'flight',
    'airline': 'flight',
    'airplane': 'flight',
    'plane': 'flight',
    'hotel': 'hotel',
    'accommodation': 'hotel',
    'lodging': 'hotel',
    'car': 'car_hire',
    'car hire': 'car_hire',
    'car rental': 'car_hire',
    'rental car': 'car_hire',
    'taxi': 'taxi',
    'cab': 'taxi',
    'rideshare': 'taxi',
    'uber': 'taxi',
    'lyft': 'taxi',
    'rail': 'rail',
    'train': 'rail',
    'eurostar': 'rail',
    'bus': 'bus',
    'coach': 'bus',
    'ferry': 'ferry',
    'ship': 'ferry',
}

# ── Travel class normalisation ────────────────────────────────────────────────
CLASS_MAP = {
    'economy': 'economy',
    'eco': 'economy',
    'coach': 'economy',
    'y': 'economy',
    'premium economy': 'premium_economy',
    'premium': 'premium_economy',
    'w': 'premium_economy',
    'business': 'business',
    'business class': 'business',
    'biz': 'business',
    'j': 'business',
    'c': 'business',
    'first': 'first',
    'first class': 'first',
    'f': 'first',
    'a': 'first',
}

DATE_FORMATS = [
    '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
    '%d.%m.%Y', '%Y%m%d', '%b %d, %Y', '%d %b %Y',
]


@dataclass
class ParsedTravelRow:
    row_number: int
    trip_id: str
    employee_id: str
    segment_type: str           # flight / hotel / car_hire / rail / taxi
    travel_date: date
    # Flight-specific
    origin_iata: str
    destination_iata: str
    travel_class: str           # economy / premium_economy / business / first
    distance_km: Optional[Decimal]
    distance_source: str        # 'provided', 'calculated_great_circle', 'unknown'
    # Hotel-specific
    hotel_nights: Optional[int]
    hotel_country: str
    # Common
    spend: Optional[Decimal]
    currency: str
    raw: dict
    warnings: list = field(default_factory=list)


@dataclass
class ParseError:
    row_number: int
    field: str
    message: str
    raw: dict


def _great_circle_km(iata_a: str, iata_b: str) -> Optional[float]:
    """
    Calculate Great Circle distance between two IATA airport codes.
    Uses the Haversine formula.
    ICAO applies a 9% uplift for indirect routing — we apply that here.
    """
    coords_a = IATA_COORDS.get(iata_a.upper())
    coords_b = IATA_COORDS.get(iata_b.upper())
    if coords_a is None or coords_b is None:
        return None

    lat1, lon1 = math.radians(coords_a[0]), math.radians(coords_a[1])
    lat2, lon2 = math.radians(coords_b[0]), math.radians(coords_b[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    R = 6371  # Earth radius in km
    direct_km = R * c

    # ICAO 9% uplift for indirect routing
    return direct_km * 1.09


def _normalise_header(h: str) -> str:
    return TRAVEL_HEADER_MAP.get(h.strip().lower().replace('\ufeff', ''), h.strip().lower())


def _parse_date(value: str) -> Optional[date]:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Optional[Decimal]:
    value = value.strip().replace(',', '')
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_travel_csv(file_bytes: bytes) -> tuple[list[ParsedTravelRow], list[ParseError]]:
    """Main entry point for corporate travel CSV parsing."""
    try:
        text = file_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = file_bytes.decode('latin-1')

    reader = csv.DictReader(io.StringIO(text))
    header_map = {h: _normalise_header(h) for h in (reader.fieldnames or [])}

    parsed_rows: list[ParsedTravelRow] = []
    errors: list[ParseError] = []

    for i, raw_row in enumerate(reader, start=2):
        row = {header_map.get(k, k): v for k, v in raw_row.items() if k}
        warnings = []

        # ── Travel date ─────────────────────────────────────────────────
        travel_date = _parse_date(row.get('travel_date', ''))
        if travel_date is None:
            errors.append(ParseError(i, 'travel_date',
                f"Cannot parse date: '{row.get('travel_date', '')}'", raw_row))
            continue

        # ── Segment type ────────────────────────────────────────────────
        raw_type = row.get('segment_type', '').strip().lower()
        segment_type = SEGMENT_TYPE_MAP.get(raw_type)
        if segment_type is None:
            warnings.append(f"Unknown segment type '{raw_type}' — defaulted to 'flight'")
            segment_type = 'flight'

        # ── Travel class ────────────────────────────────────────────────
        raw_class = row.get('travel_class', 'economy').strip().lower()
        travel_class = CLASS_MAP.get(raw_class, 'economy')
        if travel_class == 'economy' and raw_class not in CLASS_MAP:
            warnings.append(f"Unknown class '{raw_class}' — defaulted to economy")

        # ── Distance (flight) ───────────────────────────────────────────
        origin = row.get('origin', '').strip().upper()
        destination = row.get('destination', '').strip().upper()
        distance_km = None
        distance_source = 'unknown'

        # Try provided distance first
        dist_raw = row.get('distance_km') or row.get('distance_miles')
        if dist_raw:
            d = _parse_decimal(dist_raw)
            if d is not None:
                if 'miles' in (row.get('distance_miles', '')):
                    distance_km = d * Decimal('1.60934')
                    distance_source = 'provided_converted_from_miles'
                else:
                    distance_km = d
                    distance_source = 'provided'

        # Fall back to Great Circle calculation
        if distance_km is None and segment_type == 'flight' and origin and destination:
            gc = _great_circle_km(origin, destination)
            if gc is not None:
                distance_km = Decimal(str(round(gc, 1)))
                distance_source = 'calculated_great_circle'
                warnings.append(
                    f"Distance not provided for {origin}→{destination}: "
                    f"calculated {distance_km} km using Great Circle + 9% ICAO uplift"
                )
            else:
                warnings.append(
                    f"IATA codes {origin}/{destination} not in lookup table — "
                    f"distance unknown, manual entry required"
                )

        # ── Hotel nights ────────────────────────────────────────────────
        hotel_nights = None
        if segment_type == 'hotel':
            nights_raw = row.get('hotel_nights', '').strip()
            if nights_raw:
                try:
                    hotel_nights = int(nights_raw)
                except ValueError:
                    warnings.append(f"Cannot parse hotel nights: '{nights_raw}'")

        # ── Country ─────────────────────────────────────────────────────
        hotel_country = row.get('hotel_country', '').strip().upper()

        parsed_rows.append(ParsedTravelRow(
            row_number=i,
            trip_id=row.get('trip_id', '').strip(),
            employee_id=row.get('employee_id', '').strip(),
            segment_type=segment_type,
            travel_date=travel_date,
            origin_iata=origin,
            destination_iata=destination,
            travel_class=travel_class,
            distance_km=distance_km,
            distance_source=distance_source,
            hotel_nights=hotel_nights,
            hotel_country=hotel_country,
            spend=_parse_decimal(row.get('spend', '')),
            currency=row.get('currency', '').strip().upper(),
            raw=raw_row,
            warnings=warnings,
        ))

    logger.info("Travel parse: %d rows, %d errors", len(parsed_rows), len(errors))
    return parsed_rows, errors
