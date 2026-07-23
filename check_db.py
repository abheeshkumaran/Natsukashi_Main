import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'natsukashi_design.settings')
django.setup()

from django.db import connection, connections
from django.conf import settings
from product.models import OnamSaree, OnamSetMund, OnamSareeImage

print('='*70)
print('DATABASE CONFIGURATION')
print('='*70)
print(f'Configured in settings.py: {settings.DATABASES["default"]["ENGINE"]}')
print(f'Configured DB Name: {settings.DATABASES["default"]["NAME"]}')
print(f'Configured Host: {settings.DATABASES["default"]["HOST"]}')
print(f'Configured Port: {settings.DATABASES["default"]["PORT"]}')

print('\n' + '='*70)
print('ACTUAL DATABASE CONNECTION')
print('='*70)
db_engine = connection.settings_dict['ENGINE']
db_name = connection.settings_dict['NAME']
print(f'Actually Connected: {db_engine}')
print(f'Database File/Name: {db_name}')
print(f'Database Vendor: {connection.vendor}')

print('\n' + '='*70)
print('RECORD COUNT BY TABLE')
print('='*70)
print(f'OnamSaree: {OnamSaree.objects.count()} records')
print(f'OnamSareeImage: {OnamSareeImage.objects.count()} records')
print(f'OnamSetMund: {OnamSetMund.objects.count()} records')

print('\n' + '='*70)
print('DETAILED SAREE DATA')
print('='*70)
for saree in OnamSaree.objects.all().order_by('id'):
    print(f'\nID: {saree.id}')
    print(f'  Name: {saree.collection_name}')
    print(f'  Price: ${saree.price}')
    print(f'  Quantity: {saree.quantity}')
    print(f'  Stock Available: {saree.stock_available}')
    print(f'  Description: {saree.description}')

print('\n' + '='*70)
print('DETAILED MUND DATA')
print('='*70)
for mund in OnamSetMund.objects.all().order_by('id'):
    print(f'\nID: {mund.id}')
    print(f'  Name: {mund.collection_name}')
    print(f'  Price: ${mund.price}')
    print(f'  Quantity: {mund.quantity}')
    print(f'  Stock Available: {mund.stock_available}')
    print(f'  Description: {mund.description}')

print('\n' + '='*70)
print('SAREE IMAGES')
print('='*70)
if OnamSareeImage.objects.count() > 0:
    for img in OnamSareeImage.objects.all().order_by('id'):
        print(f'Image ID: {img.id} | Saree ID: {img.saree_id} | Saree: {img.saree.collection_name}')
else:
    print('No images found')
