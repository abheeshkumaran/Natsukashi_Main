from django.conf import settings
from django.shortcuts import redirect

ADMIN_PANEL_PREFIX = '/admin-panel/'
ADMIN_LOGIN_PATH = '/admin-panel/login/'


class AdminPanelAuthMiddleware:
    """Dual-gate admin panel access.

    Gate 1: the visitor must be logged in as the site's SiteUser account whose
    email is settings.SUPERADMIN_EMAIL (checked via the session, same as the
    customer-facing login). Anyone else is bounced to the home page without
    ever seeing an admin login form.

    Gate 2: once Gate 1 passes, the existing django.contrib.auth staff login
    is still required to actually open the dashboard.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(ADMIN_PANEL_PREFIX):
            from product.models import SiteUser

            site_user_id = request.session.get('site_user_id')
            is_site_superadmin = False
            if site_user_id:
                is_site_superadmin = SiteUser.objects.filter(
                    id=site_user_id, email__iexact=settings.SUPERADMIN_EMAIL
                ).exists()

            if not is_site_superadmin:
                return redirect('home')

            if path == ADMIN_LOGIN_PATH:
                return self.get_response(request)

            if not (request.user.is_authenticated and request.user.is_staff):
                return redirect(f'{ADMIN_LOGIN_PATH}?next={path}')

        return self.get_response(request)
