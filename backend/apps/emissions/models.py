from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
import uuid
import decimal


class EmissionRecord(models.Model):
    """
    THE central model. Represents one normalised emission activity row.

    Design principles:
    1. Immutable lineage: raw_record FK points back to the exact source row.
    2. Scope 1/2/3 is set during parsing and can be corrected by analyst.
    3. All activity values stored in a canonical normalised unit alongside
       the original value+unit — never discard the original.
    4. co2e_kg is the computed output; the factor used is recorded.
    5. review_status drives the analyst workflow; is_locked is set after
       approval and prevents further edits (audit gate).
    """

    # ── Scope / GHG Protocol classification ──────────────────────────────
    SCOPE_1 = 1
    SCOPE_2 = 2
    SCOPE_3 = 3
    SCOPE_CHOICES = [
        (SCOPE_1, 'Scope 1 — Direct emissions (fuel combustion, company vehicles)'),
        (SCOPE_2, 'Scope 2 — Purchased electricity/heat'),
        (SCOPE_3, 'Scope 3 — Value chain (business travel, procurement)'),
    ]

    CATEGORY_FUEL = 'fuel_combustion'
    CATEGORY_ELECTRICITY = 'electricity'
    CATEGORY_FLIGHT = 'flight'
    CATEGORY_HOTEL = 'hotel'
    CATEGORY_GROUND_TRANSPORT = 'ground_transport'
    CATEGORY_PROCUREMENT = 'procurement'
    CATEGORY_CHOICES = [
        (CATEGORY_FUEL, 'Fuel Combustion'),
        (CATEGORY_ELECTRICITY, 'Purchased Electricity'),
        (CATEGORY_FLIGHT, 'Business Flight'),
        (CATEGORY_HOTEL, 'Hotel Stay'),
        (CATEGORY_GROUND_TRANSPORT, 'Ground Transport'),
        (CATEGORY_PROCUREMENT, 'Procurement / Materials'),
    ]

    # ── Review workflow ──────────────────────────────────────────────────
    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_FLAGGED = 'FLAGGED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_FLAGGED, 'Flagged — Needs Attention'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    FLAG_OUTLIER = 'OUTLIER'
    FLAG_UNIT_AMBIGUOUS = 'UNIT_AMBIGUOUS'
    FLAG_FACTOR_MISSING = 'FACTOR_MISSING'
    FLAG_DATE_INVALID = 'DATE_INVALID'
    FLAG_OVERLAP = 'BILLING_OVERLAP'
    FLAG_NONE = ''
    FLAG_CHOICES = [
        (FLAG_OUTLIER, 'Statistical outlier — value >3σ from category mean'),
        (FLAG_UNIT_AMBIGUOUS, 'Unit could not be confidently normalised'),
        (FLAG_FACTOR_MISSING, 'Emission factor is missing or estimated'),
        (FLAG_DATE_INVALID, 'Date is in future or >2 years old'),
        (FLAG_OVERLAP, 'Billing period overlaps with another record'),
        (FLAG_NONE, 'No flag'),
    ]

    # ── Primary key ──────────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Tenancy ──────────────────────────────────────────────────────────
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='emission_records',
        help_text='All queries MUST filter by client first.'
    )

    # ── Source of truth ──────────────────────────────────────────────────
    batch = models.ForeignKey(
        'ingestion.IngestionBatch', on_delete=models.CASCADE,
        related_name='emission_records'
    )
    raw_record = models.OneToOneField(
        'ingestion.RawRecord', on_delete=models.CASCADE,
        related_name='emission_record',
        null=True, blank=True
    )
    source_type = models.CharField(max_length=20)   # SAP / UTILITY / TRAVEL
    source_ref = models.CharField(
        max_length=255, blank=True,
        help_text='Original identifier from source: SAP doc number, meter ID, trip ID, etc.'
    )

    # ── GHG classification ───────────────────────────────────────────────
    scope = models.IntegerField(choices=SCOPE_CHOICES)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    subcategory = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. diesel, natural_gas, long_haul_flight, economy_class'
    )

    # ── Activity data (original, preserved verbatim from source) ─────────
    activity_value = models.DecimalField(
        max_digits=18, decimal_places=4,
        validators=[MinValueValidator(decimal.Decimal('0'))]
    )
    activity_unit = models.CharField(max_length=30, help_text='Original unit from source file')

    # ── Normalised activity (after unit conversion) ──────────────────────
    normalised_value = models.DecimalField(
        max_digits=18, decimal_places=4,
        null=True, blank=True
    )
    normalised_unit = models.CharField(
        max_length=30, blank=True,
        help_text='Canonical unit after conversion: litre, kWh, km, kg'
    )

    # ── Emission calculation ─────────────────────────────────────────────
    emission_factor = models.ForeignKey(
        'clients.EmissionFactor', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='emission_records'
    )
    emission_factor_value = models.DecimalField(
        max_digits=14, decimal_places=6, null=True, blank=True,
        help_text='Snapshot of factor at time of calculation (factor table may change)'
    )
    emission_factor_source = models.CharField(max_length=100, blank=True)
    co2e_kg = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True,
        help_text='Final output in kg CO2-equivalent'
    )

    # ── Time ─────────────────────────────────────────────────────────────
    period_start = models.DateField()
    period_end = models.DateField()
    reporting_year = models.PositiveIntegerField(db_index=True)

    # ── Location ─────────────────────────────────────────────────────────
    facility_id = models.CharField(max_length=100, blank=True)
    facility_name = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=3, blank=True, help_text='ISO 3166-1 alpha-3')
    city = models.CharField(max_length=100, blank=True)

    # ── Source-specific metadata (flexible storage) ───────────────────────
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text=(
            'Source-specific fields that do not fit the normalised schema. '
            'SAP: cost_centre, material_code. '
            'Utility: meter_id, tariff_code, account_number. '
            'Travel: origin_iata, dest_iata, travel_class, employee_id.'
        )
    )

    # ── Review workflow ──────────────────────────────────────────────────
    review_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    flag = models.CharField(max_length=30, choices=FLAG_CHOICES, default=FLAG_NONE, blank=True)
    flag_detail = models.TextField(blank=True, help_text='Machine-generated explanation of why this was flagged')
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_records'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_note = models.TextField(blank=True)

    # ── Audit lock ───────────────────────────────────────────────────────
    is_locked = models.BooleanField(
        default=False,
        help_text='True after analyst approves. Locked records cannot be edited — only an admin override creates a new AuditLog entry.'
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'emission_records'
        ordering = ['-period_start', 'client', 'scope']
        indexes = [
            models.Index(fields=['client', 'reporting_year']),
            models.Index(fields=['client', 'scope', 'review_status']),
            models.Index(fields=['client', 'category']),
            models.Index(fields=['review_status', 'flag']),
        ]

    def __str__(self):
        return (
            f"{self.client.name} | Scope {self.scope} | {self.category} | "
            f"{self.period_start} | {self.co2e_kg} kg CO2e"
        )

    def save(self, *args, **kwargs):
        # Auto-compute co2e_kg if we have all inputs
        if (
            self.normalised_value is not None
            and self.emission_factor_value is not None
        ):
            self.co2e_kg = self.normalised_value * self.emission_factor_value
        super().save(*args, **kwargs)
