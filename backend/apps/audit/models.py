from django.db import models
from django.conf import settings
import uuid


class AuditLog(models.Model):
    """
    Append-only audit trail. Records every state change to an EmissionRecord.

    Design:
    - Never deleted, never updated — only inserted.
    - before_state / after_state are JSON snapshots of the full record,
      not just the changed field, so we can reconstruct any historical state.
    - action describes what happened: CREATED, REVIEWED, FLAGGED, APPROVED,
      REJECTED, LOCKED, UNLOCKED (admin override), FACTOR_UPDATED.
    """
    ACTION_CREATED = 'CREATED'
    ACTION_REVIEWED = 'REVIEWED'
    ACTION_FLAGGED = 'FLAGGED'
    ACTION_APPROVED = 'APPROVED'
    ACTION_REJECTED = 'REJECTED'
    ACTION_LOCKED = 'LOCKED'
    ACTION_UNLOCKED = 'UNLOCKED'
    ACTION_FACTOR_UPDATED = 'FACTOR_UPDATED'
    ACTION_BULK_APPROVED = 'BULK_APPROVED'
    ACTION_CHOICES = [
        (ACTION_CREATED, 'Record Created'),
        (ACTION_REVIEWED, 'Record Reviewed'),
        (ACTION_FLAGGED, 'Record Flagged'),
        (ACTION_APPROVED, 'Record Approved'),
        (ACTION_REJECTED, 'Record Rejected'),
        (ACTION_LOCKED, 'Record Locked for Audit'),
        (ACTION_UNLOCKED, 'Admin Unlock Override'),
        (ACTION_FACTOR_UPDATED, 'Emission Factor Updated'),
        (ACTION_BULK_APPROVED, 'Bulk Approval'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(
        'emissions.EmissionRecord', on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE,
        related_name='audit_logs',
        help_text='Denormalised for fast tenant-scoped audit queries'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='audit_actions'
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    before_state = models.JSONField(
        null=True, blank=True,
        help_text='Full record state before this action. Null for CREATED.'
    )
    after_state = models.JSONField(
        help_text='Full record state after this action.'
    )
    note = models.TextField(blank=True, help_text='Free-text note from the user who made the change')
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['record', 'changed_at']),
            models.Index(fields=['client', 'changed_at']),
        ]

    def __str__(self):
        return f"{self.action} on {self.record_id} at {self.changed_at:%Y-%m-%d %H:%M}"
