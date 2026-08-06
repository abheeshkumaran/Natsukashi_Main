from django.shortcuts import redirect

ADMIN_PANEL_PREFIX = '/admin-panel/'
ADMIN_LOGIN_PATH = '/admin-panel/login/'


class AdminPanelAuthMiddleware:
    """Requires a logged-in staff user for every /admin-panel/ URL except the login page itself."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith(ADMIN_PANEL_PREFIX) and path != ADMIN_LOGIN_PATH:
            if not (request.user.is_authenticated and request.user.is_staff):
                return redirect(f'{ADMIN_LOGIN_PATH}?next={path}')
        return self.get_response(request)
