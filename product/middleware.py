from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

ADMIN_PANEL_PREFIX = '/admin-panel/'


class AdminPanelAuthMiddleware:
    """The SiteUser account whose email matches settings.SUPERADMIN_EMAIL is
    the site's one admin - logging in as that account IS logging into the
    admin panel, and there is nothing else to authenticate against.

    Two rules, both driven off that same session flag:
    1. Anyone who is NOT that account gets bounced out of /admin-panel/ to
       the home page.
    2. The superadmin, while logged in, never sees the customer-facing site
       at all - any non-admin-panel page redirects them straight back to the
       dashboard. The one exception is logging out, which has to be reachable
       or they could never leave the admin panel.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        site_user_id = request.session.get('site_user_id')
        is_site_superadmin = False
        if site_user_id:
            from product.models import SiteUser
            is_site_superadmin = SiteUser.objects.filter(
                id=site_user_id, email__iexact=settings.SUPERADMIN_EMAIL
            ).exists()

        if path.startswith(ADMIN_PANEL_PREFIX):
            if not is_site_superadmin:
                return redirect('home')
            return self.get_response(request)

        if is_site_superadmin and path != reverse('logout'):
            return redirect('admin_dashboard')

        return self.get_response(request)
