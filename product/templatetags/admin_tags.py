from django import template
from product.models import UpdationTask

register = template.Library()

@register.simple_tag
def get_pending_updations_count():
    return UpdationTask.objects.filter(status='Pending').count()
