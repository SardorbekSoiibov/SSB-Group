"""Shared helpers for management views."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


def require_cap(*caps, any_of=False):
    """Login + capability check. With any_of=True one capability is enough."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            check = any if any_of else all
            if not check(request.user.has_cap(c) for c in caps):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def deny_unless(condition):
    if not condition:
        raise PermissionDenied


def paginate(request, qs, per_page=25):
    page = Paginator(qs, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    page.querystring = params.urlencode()
    return page


def back(request, fallback):
    """Redirect to ?next= when it is a safe local URL, otherwise to fallback."""
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(fallback)


def htmx_or_redirect(request, fallback, message=None, level=messages.SUCCESS):
    if message:
        messages.add_message(request, level, message)
    if request.headers.get("HX-Request"):
        resp = HttpResponse(status=204)
        resp["HX-Refresh"] = "true"
        return resp
    return back(request, fallback)


def int_param(request, name):
    """Integer GET parameter or None (bad input is ignored instead of erroring)."""
    try:
        return int(request.GET.get(name, ""))
    except ValueError:
        return None
