"""Windows ilovasi (SSB Boshqaruv) faqat boshqaruv tizimini ko'rsatadi.

Ilova so'rovlarida User-Agent oxirida "SSBDesktop/<versiya>" bo'ladi. Shunday so'rov ommaviy sayt
sahifalariga (bosh sahifa, portfolio, xizmatlar...) kelsa, boshqaruv tizimiga qaytariladi:
kirilgan bo'lsa — bosh panelga, kirilmagan bo'lsa — kirish sahifasiga. Brauzerdagi sayt o'zgarmaydi.
"""
from django.shortcuts import redirect

DESKTOP_MARK = "SSBDesktop/"
# Ilova ichida ochilishi mumkin bo'lgan manzillar: boshqaruv tizimi va uning fayllari.
ALLOWED_PREFIXES = ("/management/", "/static/", "/media/", "/favicon.ico")


def is_desktop(request):
    return DESKTOP_MARK in request.META.get("HTTP_USER_AGENT", "")


class DesktopManagementOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_desktop(request) and not request.path.startswith(ALLOWED_PREFIXES):
            # /management/ kirgan foydalanuvchini bosh panelga, kirmaganini kirish sahifasiga o'zi olib boradi.
            return redirect("/management/")
        return self.get_response(request)
