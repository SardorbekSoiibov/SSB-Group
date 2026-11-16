from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.static import serve
from django.views.generic import RedirectView

from apps.crm.views import people as crm_people
from apps.website.sitemaps import SITEMAPS
from apps.website.views import robots_txt

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("management/hisob/", include("apps.accounts.urls")),
    path("management/", RedirectView.as_view(pattern_name="enterprise:overview", permanent=True)),
    path("management/enterprise/", include("apps.enterprise.urls")),
    path("management/chat/", include("apps.chat.urls")),
    path("management/", include("apps.crm.urls")),
    path("favicon.ico", RedirectView.as_view(url=f"{settings.STATIC_URL}img/favicon.svg", permanent=True)),
    path("robots.txt", robots_txt),
    # Bedjikdagi QR: xodim ekanligini ochiq tasdiqlash (imzolangan token).
    path("xodim/<str:token>/", crm_people.badge_verify, name="badge_verify"),
    path("xodim/<str:token>/rasm/", crm_people.badge_photo, name="badge_photo"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("", include("apps.website.urls")),
]

if settings.DEBUG or settings.SERVE_PUBLIC_MEDIA:
    # Public media only (portfolio, team photos). Private files are always streamed by permission-checked views.
    urlpatterns += [path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT})]

handler404 = "apps.website.views.not_found"
handler500 = "apps.website.views.server_error"
