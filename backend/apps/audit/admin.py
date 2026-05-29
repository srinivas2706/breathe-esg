from django.contrib import admin
from .models import AuditLog
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'record', 'changed_by', 'changed_at']
    list_filter = ['action']
