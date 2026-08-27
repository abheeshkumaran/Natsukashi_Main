from django.shortcuts import redirect
from django.urls import reverse

ADMIN_PANEL_PREFIX = '/admin-panel/'


class AdminPanelAuthMiddleware:
    """The admin login lives in its own admin_auth table (product.AdminAuth),
    separate from the SiteUser/users table - logging in as that account sets
    the 'is_superadmin' session flag, which is what gates the admin panel
    below.

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

        is_site_superadmin = bool(request.session.get('is_superadmin'))

        if path.startswith(ADMIN_PANEL_PREFIX):
            if not is_site_superadmin:
                return redirect('home')
            return self.get_response(request)

        if is_site_superadmin and path != reverse('logout'):
            return redirect('admin_dashboard')

        return self.get_response(request)
