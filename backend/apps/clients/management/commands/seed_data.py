"""
Management command: python manage.py seed_data

Seeds:
  1. Unit conversions
  2. Global emission factors (DEFRA 2023)
  3. A demo client with plant code mappings
  4. A demo analyst user

Run this after migrations on a fresh database.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from decimal import Decimal

from apps.clients.models import Client, PlantCodeMapping, EmissionFactor, UnitConversion

User = get_user_model()


EMISSION_FACTORS = [
    # DEFRA 2023 Greenhouse Gas Reporting: Conversion Factors
    # Scope 1 — Fuel combustion (kg CO2e per litre unless noted)
    {'activity_type': 'fuel_combustion', 'subcategory': 'diesel',
     'scope': 1, 'factor_value': '2.68630', 'input_unit': 'litre',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'fuel_combustion', 'subcategory': 'petrol',
     'scope': 1, 'factor_value': '2.31380', 'input_unit': 'litre',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'fuel_combustion', 'subcategory': 'gas_oil',
     'scope': 1, 'factor_value': '2.75630', 'input_unit': 'litre',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'fuel_combustion', 'subcategory': 'lpg',
     'scope': 1, 'factor_value': '1.55450', 'input_unit': 'litre',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'fuel_combustion', 'subcategory': 'natural_gas',
     'scope': 1, 'factor_value': '2.02230', 'input_unit': 'm3',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'fuel_combustion', 'subcategory': 'heavy_fuel_oil',
     'scope': 1, 'factor_value': '3.17880', 'input_unit': 'litre',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'fuel_combustion', 'subcategory': 'cng',
     'scope': 1, 'factor_value': '0.00203', 'input_unit': 'litre',
     'source': 'DEFRA 2023', 'valid_from': 2023},

    # Scope 2 — Purchased electricity (kg CO2e per kWh)
    # UK grid factor
    {'activity_type': 'electricity', 'subcategory': 'grid_electricity',
     'scope': 2, 'factor_value': '0.20707', 'input_unit': 'kWh',
     'source': 'DEFRA 2023 (UK Grid)', 'valid_from': 2023},
    # India grid factor (CEA 2022)
    {'activity_type': 'electricity', 'subcategory': 'grid_electricity_india',
     'scope': 2, 'factor_value': '0.71600', 'input_unit': 'kWh',
     'source': 'CEA India 2022', 'valid_from': 2022},
    # US average (EPA 2022 eGRID)
    {'activity_type': 'electricity', 'subcategory': 'grid_electricity_us',
     'scope': 2, 'factor_value': '0.38600', 'input_unit': 'kWh',
     'source': 'EPA eGRID 2022', 'valid_from': 2022},

    # Scope 3 — Business travel flights (kg CO2e per km, per passenger)
    # Includes radiative forcing (RF) multiplier of 1.9 per DEFRA 2023
    {'activity_type': 'flight_economy', 'subcategory': 'economy',
     'scope': 3, 'factor_value': '0.25504', 'input_unit': 'km',
     'source': 'DEFRA 2023 (incl. RF)', 'valid_from': 2023},
    {'activity_type': 'flight_premium_economy', 'subcategory': 'premium_economy',
     'scope': 3, 'factor_value': '0.40806', 'input_unit': 'km',
     'source': 'DEFRA 2023 (incl. RF)', 'valid_from': 2023},
    {'activity_type': 'flight_business', 'subcategory': 'business',
     'scope': 3, 'factor_value': '0.61209', 'input_unit': 'km',
     'source': 'DEFRA 2023 (incl. RF)', 'valid_from': 2023},
    {'activity_type': 'flight_first', 'subcategory': 'first',
     'scope': 3, 'factor_value': '1.02016', 'input_unit': 'km',
     'source': 'DEFRA 2023 (incl. RF)', 'valid_from': 2023},

    # Scope 3 — Hotel stays (kg CO2e per room-night)
    {'activity_type': 'hotel', 'subcategory': 'hotel_uk',
     'scope': 3, 'factor_value': '28.6000', 'input_unit': 'nights',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'hotel', 'subcategory': 'hotel_global',
     'scope': 3, 'factor_value': '34.0000', 'input_unit': 'nights',
     'source': 'Cornell Hotel Sustainability Benchmarking 2022', 'valid_from': 2022},

    # Scope 3 — Ground transport
    {'activity_type': 'car_hire', 'subcategory': 'average_car',
     'scope': 3, 'factor_value': '0.17100', 'input_unit': 'km',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'taxi', 'subcategory': 'taxi',
     'scope': 3, 'factor_value': '0.20890', 'input_unit': 'km',
     'source': 'DEFRA 2023', 'valid_from': 2023},
    {'activity_type': 'rail', 'subcategory': 'national_rail',
     'scope': 3, 'factor_value': '0.03549', 'input_unit': 'km',
     'source': 'DEFRA 2023', 'valid_from': 2023},
]

UNIT_CONVERSIONS = [
    # Volume
    ('us_gallon', 'litre', '3.78541'),
    ('uk_gallon', 'litre', '4.54609'),
    ('barrel', 'litre', '158.987'),
    ('cubic_ft', 'litre', '28.3168'),
    # Energy
    ('kwh', 'kwh', '1'),
    ('mwh', 'kwh', '1000'),
    ('gj', 'kwh', '277.778'),
    ('mmbtu', 'kwh', '293.071'),
    ('btu', 'kwh', '0.000293071'),
    ('therm', 'kwh', '29.3001'),
    # Mass
    ('tonne', 'kg', '1000'),
    ('lb', 'kg', '0.453592'),
    # Distance
    ('miles', 'km', '1.60934'),
    ('nautical_mile', 'km', '1.852'),
]


class Command(BaseCommand):
    help = 'Seeds initial data: unit conversions, emission factors, demo client and user'

    def handle(self, *args, **options):
        self.stdout.write('Seeding unit conversions...')
        for from_unit, to_unit, mult in UNIT_CONVERSIONS:
            UnitConversion.objects.update_or_create(
                from_unit=from_unit, to_unit=to_unit,
                defaults={'multiplier': Decimal(mult)}
            )

        self.stdout.write('Seeding emission factors...')
        for ef in EMISSION_FACTORS:
            EmissionFactor.objects.update_or_create(
                client=None,
                activity_type=ef['activity_type'],
                subcategory=ef['subcategory'],
                scope=ef['scope'],
                valid_from=ef['valid_from'],
                defaults={
                    'factor_value': Decimal(ef['factor_value']),
                    'input_unit': ef['input_unit'],
                    'output_unit': 'kg_co2e',
                    'source': ef['source'],
                }
            )

        self.stdout.write('Creating demo client...')
        client, _ = Client.objects.get_or_create(
            slug='acme-corp',
            defaults={
                'name': 'Acme Corporation',
                'industry': 'Manufacturing',
                'country': 'GBR',
                'reporting_year': 2024,
            }
        )

        PlantCodeMapping.objects.update_or_create(
            client=client, plant_code='P001',
            defaults={'facility_name': 'London Manufacturing Plant', 'country': 'GBR', 'city': 'London'}
        )
        PlantCodeMapping.objects.update_or_create(
            client=client, plant_code='P002',
            defaults={'facility_name': 'Mumbai Operations Centre', 'country': 'IND', 'city': 'Mumbai'}
        )
        PlantCodeMapping.objects.update_or_create(
            client=client, plant_code='P003',
            defaults={'facility_name': 'Frankfurt Distribution Hub', 'country': 'DEU', 'city': 'Frankfurt'}
        )

        self.stdout.write('Creating demo users...')
        if not User.objects.filter(username='analyst').exists():
            User.objects.create_user(
                username='analyst',
                email='analyst@acme.com',
                password='Breathe2024!',
                role='analyst',
                client=client,
                first_name='Sarah',
                last_name='Chen',
            )

        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@breatheesg.com',
                password='Breathe2024!',
            )

        self.stdout.write(self.style.SUCCESS(
            '\n✅ Seed complete.\n'
            '  Demo analyst: analyst / Breathe2024!\n'
            '  Admin: admin / Breathe2024!\n'
            f'  Client: {client.name} (id: {client.id})\n'
        ))
