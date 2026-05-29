from django.db import models
import uuid


class Client(models.Model):
    """
    Top-level tenant. Every piece of data in the system is scoped to a Client.
    Multi-tenancy is enforced at the application layer: every queryset is
    filtered by client before any other filter is applied.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    industry = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=3, blank=True, help_text='ISO 3166-1 alpha-3')
    reporting_year = models.PositiveIntegerField(default=2024)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'clients'
        ordering = ['name']

    def __str__(self):
        return self.name


class PlantCodeMapping(models.Model):
    """
    SAP plant codes are internal identifiers that mean nothing
    without a lookup table. This table is populated during client
    onboarding and maps e.g. 'P001' -> 'Mumbai Refinery, India'.
    """
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='plant_mappings')
    plant_code = models.CharField(max_length=50)
    facility_name = models.CharField(max_length=255)
    facility_type = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=3, blank=True)
    city = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = 'plant_code_mappings'
        unique_together = ('client', 'plant_code')

    def __str__(self):
        return f"{self.plant_code} → {self.facility_name}"


class EmissionFactor(models.Model):
    """
    Lookup table for converting activity data to kg CO2e.
    Scoped to a client (custom factors) or null (global defaults).
    Source: DEFRA, EPA, IPCC AR5/AR6.
    """
    SCOPE_CHOICES = [(1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')]

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, null=True, blank=True,
        related_name='emission_factors',
        help_text='Null = global default factor available to all clients'
    )
    activity_type = models.CharField(max_length=100, db_index=True)
    subcategory = models.CharField(max_length=100, blank=True)
    scope = models.IntegerField(choices=SCOPE_CHOICES)
    factor_value = models.DecimalField(max_digits=14, decimal_places=6)
    input_unit = models.CharField(max_length=30, help_text='Unit the factor applies to, e.g. litre, kWh, km')
    output_unit = models.CharField(max_length=30, default='kg_co2e')
    source = models.CharField(max_length=100, help_text='DEFRA 2023, EPA 2023, IPCC AR6, etc.')
    valid_from = models.PositiveIntegerField(help_text='Year this factor is valid from')
    valid_to = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'emission_factors'

    def __str__(self):
        return f"{self.activity_type} ({self.input_unit}) = {self.factor_value} {self.output_unit}"


class UnitConversion(models.Model):
    """
    Normalises raw units to a canonical form before applying emission factors.
    e.g. US Gallon -> Litre, MMBtu -> kWh, m3 of natural gas -> kWh.
    """
    from_unit = models.CharField(max_length=50)
    to_unit = models.CharField(max_length=50)
    multiplier = models.DecimalField(max_digits=18, decimal_places=8)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'unit_conversions'
        unique_together = ('from_unit', 'to_unit')

    def __str__(self):
        return f"1 {self.from_unit} = {self.multiplier} {self.to_unit}"
