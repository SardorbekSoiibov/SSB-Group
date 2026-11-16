"""Qurilmalar (faol sessiyalar) — Telegramdagi "Qurilmalar" bo'limi kabi.

Har bir kirish = bitta DeviceSession yozuvi. Qurilmadan chiqarish Django sessiyasini bazadan o'chiradi:
o'sha brauzer/ilova keyingi so'rovdayoq hisobsiz qoladi. Yozuvlar sessiya bilan doim moslashtirib turiladi
(kalit almashsa yangilanadi, sessiya tugasa ro'yxatdan tushadi), shuning uchun ro'yxat har doim haqiqiy holatni ko'rsatadi.
"""
import ipaddress
import re
from datetime import timedelta

from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.db import transaction
from django.dispatch import receiver
from django.utils import timezone

from .models import DeviceSession

SESSION_FLAG = "_device"
TOUCH_EVERY = timedelta(seconds=60)
REMEMBER_FOR = 60 * 60 * 24 * 30  # "Meni eslab qol" — 30 kun


# ------------------------------------------------------------------ aniqlash

def client_ip(request):
    """Cloudflare tunnel orqali kelganda haqiqiy IP sarlavhada bo'ladi; unga faqat so'rov mahalliy proksidan kelsa ishonamiz."""
    remote = request.META.get("REMOTE_ADDR", "")
    try:
        local = ipaddress.ip_address(remote).is_loopback
    except ValueError:
        local = False
    if local:
        forwarded = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    try:
        return str(ipaddress.ip_address(remote))
    except ValueError:
        return None


_BROWSERS = [
    (r"SSBDesktop/([\d.]+)", "SSB Boshqaruv ilovasi"),
    (r"Edg(?:e|A|iOS)?/([\d.]+)", "Microsoft Edge"),
    (r"YaBrowser/([\d.]+)", "Yandex Browser"),
    (r"OPR/([\d.]+)", "Opera"),
    (r"SamsungBrowser/([\d.]+)", "Samsung Internet"),
    (r"Telegram", "Telegram ichki brauzeri"),
    (r"Firefox/([\d.]+)|FxiOS/([\d.]+)", "Firefox"),
    (r"CriOS/([\d.]+)|Chrome/([\d.]+)", "Chrome"),
    (r"Version/([\d.]+).*Safari", "Safari"),
]


def describe(ua):
    """User-Agent → {'name': 'Chrome 131', 'os': 'Windows 10/11', 'kind': 'desktop|phone|tablet|app'}."""
    ua = ua or ""
    name = "Noma’lum brauzer"
    for pattern, label in _BROWSERS:
        m = re.search(pattern, ua)
        if m:
            version = next((g for g in m.groups() if g), "") if m.groups() else ""
            name = f"{label} {version.split('.')[0]}".strip() if version and label != "SSB Boshqaruv ilovasi" else (
                f"{label} {version}" if version else label)
            break
    if re.search(r"iPad|Tablet|SM-T|Tab\b", ua):
        kind = "tablet"
    elif re.search(r"Mobi|iPhone|Android.+Mobile", ua):
        kind = "phone"
    else:
        kind = "desktop"
    if "SSBDesktop/" in ua or "Electron/" in ua:
        kind = "app"
    if m := re.search(r"Android ([\d.]+)", ua):
        os_name = f"Android {m.group(1).split('.')[0]}"
    elif m := re.search(r"(?:iPhone|CPU) OS (\d+)", ua):
        os_name = f"iOS {m.group(1)}"
    elif re.search(r"iPad", ua):
        os_name = "iPadOS"
    elif re.search(r"Windows NT 10", ua):
        os_name = "Windows 10/11"
    elif m := re.search(r"Windows NT ([\d.]+)", ua):
        os_name = f"Windows {m.group(1)}"
    elif re.search(r"Mac OS X|Macintosh", ua):
        os_name = "macOS"
    elif re.search(r"CrOS", ua):
        os_name = "ChromeOS"
    elif re.search(r"Linux", ua):
        os_name = "Linux"
    else:
        os_name = "Noma’lum tizim"
    return {"name": name, "os": os_name, "kind": kind}


# ------------------------------------------------------------------ yozish

def _ensure_key(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def register(request, remembered=None, user=None):
    """Joriy sessiyani qurilma sifatida qayd etadi (yoki mavjudini yangilaydi)."""
    key = _ensure_key(request)
    now = timezone.now()
    defaults = {"user": user or request.user,"user_agent": request.META.get("HTTP_USER_AGENT", "")[:400],
                "ip": client_ip(request), "last_seen": now}
    if remembered is not None:
        defaults["remembered"] = remembered
    device, _ = DeviceSession.objects.update_or_create(session_key=key, defaults=defaults)
    request.session[SESSION_FLAG] = device.pk
    return device


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    if request is None or not hasattr(request, "session"):
        return
    # Kirishdan oldingi sessiyaga tegishli eski yozuv bo'lsa — u endi yaroqsiz.
    old = request.session.get(SESSION_FLAG)
    if old:
        DeviceSession.objects.filter(pk=old).exclude(session_key=request.session.session_key).delete()
    register(request, user=user,
             remembered=bool(request.POST.get("remember")) if request.method == "POST" else False)


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        key = request.session.session_key
        if key:
            DeviceSession.objects.filter(session_key=key).delete()


class DeviceSessionMiddleware:
    """Har bir so'rovda: qurilma yozuvi sessiya bilan mos ekanini tekshiradi va "oxirgi faollik"ni yangilaydi.

    Yozuv o'chirilgan bo'lsa (boshqa qurilmadan chiqarilgan) — shu yerning o'zida tizimdan chiqaradi.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and hasattr(request, "session"):
            self._sync(request)
        return self.get_response(request)

    def _sync(self, request):
        key = _ensure_key(request)
        pk = request.session.get(SESSION_FLAG)
        device = DeviceSession.objects.filter(pk=pk, user=request.user).first() if pk else None
        if pk and device is None:
            # Bu qurilma boshqa joydan chiqarib yuborilgan.
            logout(request)
            return
        if device is None:
            register(request, remembered=request.session.get_expire_at_browser_close() is False
                     and request.session.get_expiry_age() > 60 * 60 * 24)
            return
        now = timezone.now()
        changes = {}
        if device.session_key != key:  # parol almashganda yoki kirishda kalit yangilanadi
            changes["session_key"] = key
        ua = request.META.get("HTTP_USER_AGENT", "")[:400]
        if ua and ua != device.user_agent:  # brauzer yangilansa, ro'yxatda darhol to'g'ri nom chiqadi
            changes["user_agent"] = ua
        if now - device.last_seen > TOUCH_EVERY:
            changes.update(last_seen=now, ip=client_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", "")[:400])
        if changes:
            DeviceSession.objects.filter(pk=device.pk).update(**changes)


# ------------------------------------------------------------------ ro'yxat va chiqarish

def active_devices(user):
    """Faqat haqiqatan ham amal qilayotgan sessiyalar. Tugagan yoki o'chirilganlar shu yerning o'zida tozalanadi."""
    devices = list(DeviceSession.objects.filter(user=user))
    live = set(Session.objects.filter(session_key__in=[d.session_key for d in devices], expire_date__gt=timezone.now())
               .values_list("session_key", flat=True))
    stale = [d.pk for d in devices if d.session_key not in live]
    if stale:
        DeviceSession.objects.filter(pk__in=stale).delete()
    return [d for d in devices if d.session_key in live]


def _kill(devices):
    keys = [d.session_key for d in devices]
    with transaction.atomic():
        Session.objects.filter(session_key__in=keys).delete()
        DeviceSession.objects.filter(pk__in=[d.pk for d in devices]).delete()
    return len(keys)


def revoke(user, device_pk, current_key):
    device = DeviceSession.objects.filter(pk=device_pk, user=user).exclude(session_key=current_key).first()
    return _kill([device]) if device else 0


def revoke_others(user, current_key):
    return _kill(list(DeviceSession.objects.filter(user=user).exclude(session_key=current_key)))


def revoke_all(user, keep_key=None):
    """Parol almashganda/tiklanganda: boshqa barcha qurilmalar chiqariladi (Django ham ularni yaroqsiz qiladi)."""
    qs = DeviceSession.objects.filter(user=user)
    if keep_key:
        qs = qs.exclude(session_key=keep_key)
    return _kill(list(qs))
