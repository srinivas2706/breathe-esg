from django.contrib import admin
from .models import IngestionBatch, RawRecord

@admin.register(IngestionBatch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ['client', 'source_type', 'status', 'row_count', 'error_count', 'uploaded_at']
    list_filter = ['source_type', 'status', 'client']

@admin.register(RawRecord)
class RawRecordAdmin(admin.ModelAdmin):
    list_display = ['batch', 'row_number', 'parse_status']
    list_filter = ['parse_status']
