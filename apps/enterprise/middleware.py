from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect


class RoleStatusMiddleware:
    def __init__(self, get_response):
        self.get_response=get_response

    def __call__(self, request):
        user=request.user
        if user.is_authenticated and user.role_id and not user.role.is_active:
            logout(request)
            if '/api/' in request.path:
                return JsonResponse({'error':'Role disabled'},status=401)
            return redirect('accounts:login')
        return self.get_response(request)


class ArchiveVisitMiddleware:
    """The company archive asks for its code on every visit: navigating to any other page relocks it.

    Only real page navigations count. Background requests made while the archive is open
    (notification polling, API calls, modal fetches, static files) keep the current visit.
    """
    PREFIX = '/management/enterprise/archives/'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'GET' and not request.path.startswith(self.PREFIX) and self.is_navigation(request):
            from .archive_access import GRANT_KEY, CHALLENGE_KEY
            session = getattr(request, 'session', None)
            if session is not None and (GRANT_KEY in session or CHALLENGE_KEY in session):
                session.pop(GRANT_KEY, None)
                session.pop(CHALLENGE_KEY, None)
        return self.get_response(request)

    @staticmethod
    def is_navigation(request):
        mode = request.headers.get('Sec-Fetch-Mode')
        if mode:
            return mode == 'navigate' and request.headers.get('Sec-Fetch-Dest', 'document') in ('document', 'iframe')
        from django.conf import settings
        path = request.path
        return (request.headers.get('X-Requested-With') != 'XMLHttpRequest' and '/api/' not in path
                and not path.startswith((settings.STATIC_URL or '/static/', '/media/', '/favicon')))
