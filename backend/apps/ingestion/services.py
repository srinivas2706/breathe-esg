"""
Ingestion Service — fixed version
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.ingestion.models import IngestionBatch, RawRecord
from apps.emissions.models import EmissionRecord
from apps.audit.models import AuditLog
from apps.clients.models import PlantCodeMapping, EmissionFactor, Client
from apps.ingestion.parsers.sap import parse_sap_csv
from apps.ingestion.parsers.utility import parse_utility_csv
from apps.ingestion.parsers.travel import parse_travel_csv

logger = logging.getLogger(__name__)

ANOMALY_THRESHOLDS = {
    'fuel_combustion': {'min': Decimal('0.001'), 'max': Decimal('1000000')},
    'electricity':     {'min': Decimal('1'),     'max': Decimal('10000000')},
    'flight':          {'min': Decimal('100'),   'max': Decimal('25000')},
    'hotel':           {'min': 1,                'max': 365},
}


def _lookup_plant(client, plant_code):
    if not plant_code:
        return ('', 'Unknown Facility', '')
    try:
        mapping = PlantCodeMapping.objects.get(client=client, plant_code=plant_code)
        return (plant_code, mapping.facility_name, mapping.country)
    except PlantCodeMapping.DoesNotExist:
        return (plant_code, f'Unknown ({plant_code})', '')


def _get_emission_factor(client, activity_type, subcategory='', scope=1):
    """
    Lookup emission factor: client-specific first, then global defaults.
    FIXED: removed invalid models_valid_to_gte_or_null filter.
    """
    year = datetime.now().year
    try:
        # Client-specific factor first
        factor = EmissionFactor.objects.filter(
            client=client,
            activity_type=activity_type,
            scope=scope,
            valid_from__lte=year,
        ).order_by('-valid_from').first()
        if factor:
            return factor

        # Fall back to global default (client=None)
        factor = EmissionFactor.objects.filter(
            client__isnull=True,
            activity_type=activity_type,
            scope=scope,
            valid_from__lte=year,
        ).order_by('-valid_from').first()
        return factor
    except Exception as e:
        logger.warning("Factor lookup failed for %s: %s", activity_type, e)
        return None


def _detect_anomaly(category, value, unit):
    thresholds = ANOMALY_THRESHOLDS.get(category)
    if thresholds is None:
        return ('', '')
    try:
        v = int(value) if isinstance(thresholds['max'], int) else value
        if v > thresholds['max']:
            return (EmissionRecord.FLAG_OUTLIER,
                    f"Value {value} {unit} exceeds max ({thresholds['max']}) for {category}.")
        if v < thresholds['min']:
            return (EmissionRecord.FLAG_OUTLIER,
                    f"Value {value} {unit} below min ({thresholds['min']}) for {category}.")
    except Exception:
        pass
    return ('', '')


@transaction.atomic
def process_sap_batch(batch, file_bytes, user):
    batch.status = IngestionBatch.STATUS_PROCESSING
    batch.save(update_fields=['status'])

    parsed_rows, errors = parse_sap_csv(file_bytes)
    batch.row_count = len(parsed_rows) + len(errors)
    batch.error_count = len(errors)
    batch.parsed_count = len(parsed_rows)

    for err in errors:
        RawRecord.objects.create(
            batch=batch, row_number=err.row_number,
            raw_data=err.raw,
            parse_status=RawRecord.PARSE_STATUS_ERROR,
            parse_error=f"[{err.field}] {err.message}",
        )

    for row in parsed_rows:
        facility_id, facility_name, country = _lookup_plant(batch.client, row.plant_code)
        factor = _get_emission_factor(batch.client, row.category, row.subcategory, row.scope)

        raw_record = RawRecord.objects.create(
            batch=batch, row_number=row.row_number,
            raw_data=row.raw,
            parse_status=RawRecord.PARSE_STATUS_WARNING if row.warnings else RawRecord.PARSE_STATUS_OK,
            parse_error='\n'.join(row.warnings),
        )

        flag, flag_detail = _detect_anomaly(row.category, row.quantity, row.canonical_unit)
        if not flag and row.warnings:
            flag = EmissionRecord.FLAG_UNIT_AMBIGUOUS

        factor_value = factor.factor_value if factor else None

        record = EmissionRecord.objects.create(
            client=batch.client,
            batch=batch,
            raw_record=raw_record,
            source_type='SAP',
            source_ref=row.document_number,
            scope=row.scope,
            category=row.category,
            subcategory=row.subcategory,
            activity_value=row.quantity,
            activity_unit=row.canonical_unit,
            normalised_value=row.quantity,
            normalised_unit=row.canonical_unit,
            emission_factor=factor,
            emission_factor_value=factor_value,
            emission_factor_source=factor.source if factor else '',
            period_start=row.document_date,
            period_end=row.document_date,
            reporting_year=row.document_date.year if row.document_date else datetime.now().year,
            facility_id=facility_id,
            facility_name=facility_name,
            country=country,
            review_status=EmissionRecord.STATUS_FLAGGED if flag else EmissionRecord.STATUS_PENDING,
            flag=flag,
            flag_detail=flag_detail,
            metadata={
                'plant_code': row.plant_code,
                'material_number': row.material_number,
                'material_description': row.material_description,
                'cost_centre': row.cost_centre,
            }
        )

        AuditLog.objects.create(
            record=record, client=batch.client,
            action=AuditLog.ACTION_CREATED, changed_by=user,
            before_state=None,
            after_state={'review_status': record.review_status, 'co2e_kg': str(record.co2e_kg)},
            note='Created via SAP ingestion',
        )

    batch.status = IngestionBatch.STATUS_COMPLETE
    batch.processed_at = timezone.now()
    batch.error_summary = (
        f"{len(errors)} rows failed parsing." if errors else ''
    )
    batch.save()
    return batch


@transaction.atomic
def process_utility_batch(batch, file_bytes, user):
    batch.status = IngestionBatch.STATUS_PROCESSING
    batch.save(update_fields=['status'])

    parsed_rows, errors = parse_utility_csv(file_bytes)
    batch.row_count = len(parsed_rows) + len(errors)
    batch.error_count = len(errors)
    batch.parsed_count = len(parsed_rows)

    for err in errors:
        RawRecord.objects.create(
            batch=batch, row_number=err.row_number,
            raw_data=err.raw,
            parse_status=RawRecord.PARSE_STATUS_ERROR,
            parse_error=f"[{err.field}] {err.message}",
        )

    for row in parsed_rows:
        factor = _get_emission_factor(batch.client, 'electricity', '', 2)

        raw_record = RawRecord.objects.create(
            batch=batch, row_number=row.row_number,
            raw_data=row.raw,
            parse_status=RawRecord.PARSE_STATUS_WARNING if row.warnings else RawRecord.PARSE_STATUS_OK,
            parse_error='\n'.join(row.warnings),
        )

        flag, flag_detail = _detect_anomaly('electricity', row.normalised_kwh, 'kWh')
        factor_value = row.grid_factor or (factor.factor_value if factor else None)

        record = EmissionRecord.objects.create(
            client=batch.client,
            batch=batch,
            raw_record=raw_record,
            source_type='UTILITY',
            source_ref=row.meter_id or row.account_number,
            scope=2,
            category='electricity',
            subcategory='grid_electricity',
            activity_value=row.consumption,
            activity_unit=row.raw_unit,
            normalised_value=row.normalised_kwh,
            normalised_unit='kWh',
            emission_factor=factor,
            emission_factor_value=factor_value,
            emission_factor_source='market_based_from_utility' if row.grid_factor else (factor.source if factor else ''),
            period_start=row.billing_start,
            period_end=row.billing_end,
            reporting_year=row.billing_start.year,
            facility_id=row.facility_id,
            facility_name=row.facility_name,
            country=row.country,
            review_status=EmissionRecord.STATUS_FLAGGED if flag else EmissionRecord.STATUS_PENDING,
            flag=flag,
            flag_detail=flag_detail,
            metadata={
                'account_number': row.account_number,
                'meter_id': row.meter_id,
                'tariff_code': row.tariff_code,
                'billing_days': row.billing_days,
                'market_based_factor': str(row.grid_factor) if row.grid_factor else None,
            }
        )

        AuditLog.objects.create(
            record=record, client=batch.client,
            action=AuditLog.ACTION_CREATED, changed_by=user,
            before_state=None,
            after_state={'review_status': record.review_status, 'co2e_kg': str(record.co2e_kg)},
            note='Created via utility ingestion',
        )

    batch.status = IngestionBatch.STATUS_COMPLETE
    batch.processed_at = timezone.now()
    batch.save()
    return batch


@transaction.atomic
def process_travel_batch(batch, file_bytes, user):
    batch.status = IngestionBatch.STATUS_PROCESSING
    batch.save(update_fields=['status'])

    parsed_rows, errors = parse_travel_csv(file_bytes)
    batch.row_count = len(parsed_rows) + len(errors)
    batch.error_count = len(errors)
    batch.parsed_count = len(parsed_rows)

    for err in errors:
        RawRecord.objects.create(
            batch=batch, row_number=err.row_number,
            raw_data=err.raw,
            parse_status=RawRecord.PARSE_STATUS_ERROR,
            parse_error=f"[{err.field}] {err.message}",
        )

    for row in parsed_rows:
        activity_type = f"flight_{row.travel_class}" if row.segment_type == 'flight' else row.segment_type
        factor = _get_emission_factor(batch.client, activity_type, row.segment_type, 3)

        raw_record = RawRecord.objects.create(
            batch=batch, row_number=row.row_number,
            raw_data=row.raw,
            parse_status=RawRecord.PARSE_STATUS_WARNING if row.warnings else RawRecord.PARSE_STATUS_OK,
            parse_error='\n'.join(row.warnings),
        )

        # Activity value by segment type
        if row.segment_type == 'flight' and row.distance_km:
            activity_value = row.distance_km
            activity_unit = 'km'
        elif row.segment_type == 'hotel' and row.hotel_nights:
            activity_value = Decimal(str(row.hotel_nights))
            activity_unit = 'nights'
        else:
            activity_value = row.spend or Decimal('0')
            activity_unit = row.currency or 'USD'

        # Category mapping
        if row.segment_type == 'flight':
            category = 'flight'
        elif row.segment_type == 'hotel':
            category = 'hotel'
        else:
            category = 'ground_transport'

        flag_code = ''
        flag_detail = ''
        if row.segment_type == 'flight' and row.distance_km is None:
            flag_code = EmissionRecord.FLAG_UNIT_AMBIGUOUS
            flag_detail = "Distance could not be calculated — IATA codes missing or not in lookup table"
        if not factor:
            flag_code = EmissionRecord.FLAG_FACTOR_MISSING
            flag_detail = f"No emission factor found for {activity_type}"

        record = EmissionRecord.objects.create(
            client=batch.client,
            batch=batch,
            raw_record=raw_record,
            source_type='TRAVEL',
            source_ref=row.trip_id,
            scope=3,
            category=category,
            subcategory=f"{row.segment_type}_{row.travel_class}" if row.segment_type == 'flight' else row.segment_type,
            activity_value=activity_value,
            activity_unit=activity_unit,
            normalised_value=activity_value,
            normalised_unit=activity_unit,
            emission_factor=factor,
            emission_factor_value=factor.factor_value if factor else None,
            emission_factor_source=factor.source if factor else '',
            period_start=row.travel_date,
            period_end=row.travel_date,
            reporting_year=row.travel_date.year,
            facility_id='',
            facility_name='',
            country=row.hotel_country,
            review_status=EmissionRecord.STATUS_FLAGGED if flag_code else EmissionRecord.STATUS_PENDING,
            flag=flag_code,
            flag_detail=flag_detail,
            metadata={
                'employee_id': row.employee_id,
                'origin_iata': row.origin_iata,
                'destination_iata': row.destination_iata,
                'travel_class': row.travel_class,
                'distance_source': row.distance_source,
                'hotel_nights': row.hotel_nights,
                'spend': str(row.spend) if row.spend else None,
                'currency': row.currency,
            }
        )

        AuditLog.objects.create(
            record=record, client=batch.client,
            action=AuditLog.ACTION_CREATED, changed_by=user,
            before_state=None,
            after_state={'review_status': record.review_status, 'co2e_kg': str(record.co2e_kg)},
            note='Created via travel ingestion',
        )

    batch.status = IngestionBatch.STATUS_COMPLETE
    batch.processed_at = timezone.now()
    batch.save()
    return batch
