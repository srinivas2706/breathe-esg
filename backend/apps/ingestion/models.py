from django.db import models
from django.conf import settings
import uuid


class IngestionBatch(models.Model):
    """
    Tracks one ingestion event: a single file upload or API pull
    for a specific client and source type.

    Raw files are kept — we never delete source material.
    status transitions: PENDING -> PROCESSING -> COMPLETE | FAILED
    """
    SOURCE_SAP = 'SAP'
    SOURCE_UTILITY = 'UTILITY'
    SOURCE_TRAVEL = 'TRAVEL'
    SOURCE_CHOICES = [
        (SOURCE_SAP, 'SAP Fuel & Procurement'),
        (SOURCE_UTILITY, 'Utility / Electricity'),
        (SOURCE_TRAVEL, 'Corporate Travel'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETE = 'COMPLETE'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE, related_name='batches'
    )
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    original_filename = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='ingestion/%Y/%m/', null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='uploaded_batches'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    row_count = models.IntegerField(default=0)
    parsed_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    error_summary = models.TextField(blank=True, help_text='Human-readable summary of parse errors')
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'ingestion_batches'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.client.name} / {self.source_type} / {self.uploaded_at:%Y-%m-%d %H:%M}"

    @property
    def success_rate(self):
        if self.row_count == 0:
            return 0
        return round((self.parsed_count / self.row_count) * 100, 1)


class RawRecord(models.Model):
    """
    Immutable record of exactly what came in from the source.
    Never edited after creation. EmissionRecord links back here
    to provide a chain of custody from CO2e number back to source bytes.

    raw_data stores the original row as a dict (JSON) — preserving
    German SAP headers, original units, and any quirks of the source file.
    """
    PARSE_STATUS_OK = 'OK'
    PARSE_STATUS_ERROR = 'ERROR'
    PARSE_STATUS_WARNING = 'WARNING'
    PARSE_STATUS_CHOICES = [
        (PARSE_STATUS_OK, 'Parsed OK'),
        (PARSE_STATUS_ERROR, 'Parse Error'),
        (PARSE_STATUS_WARNING, 'Parsed with Warnings'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='raw_records')
    row_number = models.IntegerField(help_text='1-indexed row number in the source file')
    raw_data = models.JSONField(help_text='Original row as parsed from source, keys preserved verbatim')
    parse_status = models.CharField(max_length=10, choices=PARSE_STATUS_CHOICES)
    parse_error = models.TextField(blank=True, help_text='Error message if parse failed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'raw_records'
        ordering = ['batch', 'row_number']
        # Composite index for the most common query: all raw records for a batch
        indexes = [
            models.Index(fields=['batch', 'parse_status']),
        ]

    def __str__(self):
        return f"Row {self.row_number} of batch {self.batch_id}"
