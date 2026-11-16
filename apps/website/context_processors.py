from .cache import CSRF_SLOT, cached
from .models import SiteSettings


def site(request):
    context = {"site": cached("settings", SiteSettings.load)}
    if getattr(request, "csrf_slot", False):
        # Keshlanadigan sahifada token o'rniga belgi qoladi (cache.public_page).
        context["csrf_token"] = CSRF_SLOT
    return context
