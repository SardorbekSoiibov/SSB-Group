"""Ommaviy sahifalar keshi.

Mehmonlar (tizimga kirmagan foydalanuvchilar) uchun ommaviy sahifalar bir marta render qilinadi va
tayyor HTML keshdan beriladi — har so'rovda na baza, na shablon ishlaydi. Faqat CSRF tokeni har
foydalanuvchiga alohida qo'yiladi. CMS orqali sayt kontentiga tegishli har qanday yozuv o'zgarsa,
kontent versiyasi oshadi va eski sahifalar o'z-o'zidan eskiradi (signals.py).

Bir nechta gunicorn jarayoni bo'lsa, CACHE_URL umumiy kesh (Redis) ko'rsatishi kerak — aks holda har
jarayon o'z nusxasini TTL tugaguncha saqlaydi.
"""

from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.middleware.csrf import get_token

VERSION_KEY = "website:content-version"
TTL = 300


def _version():
    version = cache.get(VERSION_KEY)
    if version is None:
        cache.add(VERSION_KEY, 1, None)
        version = cache.get(VERSION_KEY, 1)
    return version


def bump():
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 2, None)


def cached(name, build):
    """`build()` natijasini kontent versiyasi bilan keshlaydi. Natija pickle qilinadigan bo'lishi kerak."""
    return cache.get_or_set(f"website:{_version()}:{name}", build, TTL)


CSRF_SLOT = "__ssb_csrf_slot__"


def public_page(view):
    """Mehmonlar uchun GET so'rovlarini (query parametrlarsiz) to'liq HTML ko'rinishida keshlaydi.

    View `csrf_token` ni kontekstga qo'ymaydi; dekorator render vaqtida o'rniga belgi qo'yadi
    va har javobda uni joriy foydalanuvchining tokeni bilan almashtiradi.
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        # DEBUG rejimida shablon o'zgarishlari darhol ko'rinishi uchun kesh ishlatilmaydi.
        if (settings.DEBUG or request.method != "GET" or request.GET or request.headers.get("HX-Request")
                or request.user.is_authenticated):
            return view(request, *args, **kwargs)
        key = f"website:{_version()}:page:{request.scheme}://{request.get_host()}{request.path}"
        html = cache.get(key)
        if html is None:
            request.csrf_slot = True
            response = view(request, *args, **kwargs)
            if response.status_code != 200:
                return response
            html = response.content.decode()
            cache.set(key, html, TTL)
        page = HttpResponse(html.replace(CSRF_SLOT, get_token(request)))
        page["Vary"] = "Cookie"
        return page

    return wrapper
