from django.contrib import admin
from .models import EmissionRecord

@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = ['client', 'scope', 'category', 'period_start', 'co2e_kg', 'review_status', 'flag']
    list_filter = ['scope', 'review_status', 'flag', 'source_type', 'client']
    search_fields = ['source_ref', 'facility_name']
