from django.contrib import admin
from .models import Client, PlantCodeMapping, EmissionFactor, UnitConversion

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'industry', 'country', 'reporting_year', 'is_active']
    search_fields = ['name', 'slug']

@admin.register(PlantCodeMapping)
class PlantCodeMappingAdmin(admin.ModelAdmin):
    list_display = ['client', 'plant_code', 'facility_name', 'country']
    list_filter = ['client']

@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ['activity_type', 'subcategory', 'scope', 'factor_value', 'input_unit', 'source', 'valid_from']
    list_filter = ['scope', 'source']

admin.site.register(UnitConversion)
