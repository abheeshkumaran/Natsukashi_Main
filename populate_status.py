import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'natsukashi_design.settings')
django.setup()

from product.models import OrderStatus

statuses = [
    'pending', 'confirmed', 'processing', 'packed', 'shiped', 
    'out of delivery', 'deliverd', 'order placed', 'cancelled', 
    'return requested', 'return rejected', 'return approved', 
    'returened', 'refund initiated', 'refund completed', 'faild'
]

for s in statuses:
    OrderStatus.objects.get_or_create(status_name=s)
    
print("Order statuses populated successfully.")
