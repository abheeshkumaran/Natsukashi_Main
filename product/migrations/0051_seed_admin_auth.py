from django.contrib.auth.hashers import make_password
from django.db import migrations

# Values previously hardcoded in settings.py as SUPERADMIN_EMAIL /
# SUPERADMIN_PASSWORD. Seeded here once so existing logins keep working;
# change them afterwards from /admin-panel/profile/.
INITIAL_EMAIL = 'natsukashii.traditional@gmail.com'
INITIAL_USERNAME = 'Admin'
INITIAL_PASSWORD = 'Unlearn@123456'


def seed_admin_auth(apps, schema_editor):
    AdminAuth = apps.get_model('product', 'AdminAuth')
    if not AdminAuth.objects.exists():
        AdminAuth.objects.create(
            username=INITIAL_USERNAME,
            email=INITIAL_EMAIL,
            password=make_password(INITIAL_PASSWORD),
        )


def unseed_admin_auth(apps, schema_editor):
    AdminAuth = apps.get_model('product', 'AdminAuth')
    AdminAuth.objects.filter(email=INITIAL_EMAIL).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0050_adminauth'),
    ]

    operations = [
        migrations.RunPython(seed_admin_auth, unseed_admin_auth),
    ]
