"""Xodim bedjigi: shaxsiy ID, QR orqali tasdiqlash va chop etishga tayyor PDF.

QR ichida imzolangan havola bor (SECRET_KEY bilan). Uni soxtalashtirib bo'lmaydi, tekshirish sahifasi esa
xodimning HOZIRGI holatini ko'rsatadi: ishdan ketgan yoki to'xtatilgan xodimning bedjigi darhol "amal qilmaydi" bo'ladi.

Dizayn barcha xodimlar uchun bitta va static/boshqaruv/badge.css bilan millimetrma-millimetr bir xil.
Old tomon: logo, rasm, ism, lavozim, bo'lim, ID/sana/holat, shtrix-kod va gologramma.
Orqa tomon: katta logo, QR, Asoschi qo'shgan hamkorlar logolari, imzo va muhr joyi.
"""
import math
import os
from io import BytesIO

from django.conf import settings
from django.core import signing
from django.urls import reverse

SALT = "ssb-employee-badge"
_signer = signing.Signer(salt=SALT)

# Bedjik o'lchami: CR80 (bank kartasi), vertikal — 54 x 85.6 mm.
CARD_W_MM, CARD_H_MM = 54.0, 85.6
MAX_BADGE_PARTNERS = 5


def badge_id(user):
    return f"SSB-{user.pk:04d}"


def badge_token(user):
    return _signer.sign(str(user.pk))


def badge_partners():
    from .models import Partner

    return list(Partner.objects.filter(show_on_badge=True).exclude(logo="")[:MAX_BADGE_PARTNERS])


def user_from_token(token):
    from apps.accounts.models import User

    try:
        pk = int(_signer.unsign(token))
    except (signing.BadSignature, ValueError):
        return None
    return User.objects.filter(pk=pk).select_related("department", "role").first()


def verify_url(request, user):
    base = settings.SITE_URL
    if not base or "localhost" in base or "127.0.0.1" in base:
        base = f"{request.scheme}://{request.get_host()}"
    return base.rstrip("/") + reverse("badge_verify", args=[badge_token(user)])


def _qr_matrix(text):
    from reportlab.graphics.barcode import qrencoder

    qr = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    qr.addData(text)
    qr.make()
    n = qr.getModuleCount()
    return [[qr.isDark(r, c) for c in range(n)] for r in range(n)]


def qr_svg(text, quiet=2):
    """Ixcham SVG: har bir qorong'i katak bitta yo'l bo'lagi (rang CSS'dan, currentColor)."""
    m = _qr_matrix(text)
    n = len(m)
    size = n + quiet * 2
    parts = []
    for r, row in enumerate(m):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                parts.append(f"M{start + quiet} {r + quiet}h{c - start}v1h-{c - start}z")
            else:
                c += 1
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" shape-rendering="crispEdges" '
            f'aria-hidden="true"><path fill="currentColor" d="{"".join(parts)}"/></svg>')


# ------------------------------------------------------------------ PDF

NAVY = "#0a1a33"
INK = "#111827"
MUTED = "#6b7280"


def _fonts():
    """O'zbekcha belgilar (‘ ’ ʻ) uchun TTF shrift. Topilmasa — Helvetica, belgilar oddiy apostrofga almashtiriladi."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        ("SSBRegular", ["C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]),
        ("SSBBold", ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]),
    ]
    names = []
    for name, paths in candidates:
        if name in pdfmetrics.getRegisteredFontNames():
            names.append(name)
            continue
        path = next((p for p in paths if os.path.exists(p)), None)
        if path:
            pdfmetrics.registerFont(TTFont(name, path))
            names.append(name)
    if len(names) == 2:
        return names[0], names[1], False
    return "Helvetica", "Helvetica-Bold", True


def _clean(text, ascii_only):
    text = text or ""
    if ascii_only:
        for ch in "‘’ʻʼ`":
            text = text.replace(ch, "'")
    return text


def _fit(c, text, font, size, max_w, min_size=6):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    while size > min_size and stringWidth(text, font, size) > max_w:
        size -= 0.25
    return size


def _ellipsize(text, font, size, max_w):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    if stringWidth(text, font, size) <= max_w:
        return text
    while text and stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _photo_reader(user, ratio=1.0):
    """Rasmni markazdan ratio (eni/bo'yi) nisbatida kesadi: 1.0 — kvadrat, 0.75 — pasport (3×4)."""
    if not user.photo:
        return None
    try:
        from PIL import Image
        from reportlab.lib.utils import ImageReader

        with user.photo.open("rb") as fh:
            img = Image.open(fh)
            img = img.convert("RGB")
            if img.width / img.height > ratio:
                cw, ch = int(img.height * ratio), img.height
            else:
                cw, ch = img.width, int(img.width / ratio)
            left = (img.width - cw) // 2
            top = max(0, (img.height - ch) // 4)  # yuz odatda tepada — biroz yuqoriroqdan kesamiz
            img = img.crop((left, top, left + cw, top + ch)).resize((int(800 * ratio), 800))
        buf = BytesIO()
        img.save(buf, "JPEG", quality=90)
        buf.seek(0)
        return ImageReader(buf)
    except Exception:  # noqa: BLE001 — rasm buzilgan bo'lsa, bosh harflar chiziladi
        return None


_BADGE_LOGO_CACHE = {}


def badge_logo_png(partner):
    """Bedjik uchun logo: to'q ko'k fonda aniq ko'rinishi uchun oq siluetga aylantiriladi.

    Logoning o'z foni (oq/rangli to'rtburchak) bo'lsa — burchak rangiga yaqin piksellar shaffof qilinadi.
    Bo'sh qirralar kesiladi, shunda barcha logolar bir xil o'lchamda ko'rinadi. Natija PNG baytlari.
    """
    key = (partner.pk, partner.logo.name, getattr(partner, "logo_version", None))
    if key in _BADGE_LOGO_CACHE:
        return _BADGE_LOGO_CACHE[key]
    from PIL import Image, ImageChops

    with partner.logo.open("rb") as fh:
        img = Image.open(fh)
        img.load()
    img = img.convert("RGBA")
    img.thumbnail((600, 600))
    w, h = img.size
    alpha = img.getchannel("A")
    rgb = img.convert("RGB")
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    if min(alpha.getpixel(p) for p in corners) > 200:  # shaffof emas — fonni olib tashlaymiz
        cols = sorted(rgb.getpixel(p) for p in corners)
        bg = cols[len(cols) // 2]
        diff = ImageChops.difference(rgb, Image.new("RGB", (w, h), bg))
        r, g, b = diff.split()
        dist = ImageChops.lighter(ImageChops.lighter(r, g), b)
        alpha = ImageChops.multiply(alpha, dist.point(lambda v: 0 if v < 24 else min(255, (v - 24) * 5)))
    box = alpha.point(lambda v: 255 if v > 20 else 0).getbbox()
    if box:
        alpha = alpha.crop(box)
    out = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    out.putalpha(alpha)
    buf = BytesIO()
    out.save(buf, "PNG", optimize=True)
    data = buf.getvalue()
    if len(_BADGE_LOGO_CACHE) > 64:
        _BADGE_LOGO_CACHE.clear()
    _BADGE_LOGO_CACHE[key] = data
    return data


def _logo_reader(partner):
    """Hamkor logosi bedjik orqa tomoni uchun (oq silueti)."""
    try:
        from PIL import Image
        from reportlab.lib.utils import ImageReader

        data = badge_logo_png(partner)
        with Image.open(BytesIO(data)) as im:
            ratio = im.width / im.height
        return ImageReader(BytesIO(data)), ratio
    except Exception:  # noqa: BLE001 — buzilgan logo bedjikni to'xtatmasin
        return None, 1


def _mix(a, b, t):
    """a va b ranglar orasidagi t nisbatdagi rang (CSS color-mix kabi)."""
    from reportlab.lib.colors import Color

    return Color(a.red + (b.red - a.red) * t, a.green + (b.green - a.green) * t, a.blue + (b.blue - a.blue) * t)


def _spaced(c, text, font, size, x, y, spacing, align="left"):
    """Harflar orasi kengaytirilgan matn."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    width = sum(stringWidth(ch, font, size) for ch in text) + spacing * (len(text) - 1)
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    t = c.beginText(x, y)
    t.setFont(font, size)
    t.setCharSpace(spacing)
    t.textOut(text)
    t.setCharSpace(0)
    c.drawText(t)
    return width


def _spaced_width(text, font, size, spacing):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return sum(stringWidth(ch, font, size) for ch in text) + spacing * (len(text) - 1)


def _split_name(c, name, font, size, max_w):
    """Uzun ism ikki qatorga bo'linadi (familiya/ism), kerak bo'lsa shrift kichrayadi."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    if stringWidth(name, font, size) <= max_w or " " not in name:
        return [name], _fit(c, name, font, size, max_w)
    words = name.split()
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    lines = [" ".join(words[:best]), " ".join(words[best:])]
    return lines, min(_fit(c, ln, font, size, max_w) for ln in lines)


class _Card:
    """Karta koordinatalari: (mm, yuqoridan mm) -> PDF nuqtalari. CSS bilan bir xil hisoblash uchun."""

    def __init__(self, c, x, y):
        from reportlab.lib.units import mm

        self.c, self.x, self.y, self.mm = c, x, y, mm
        self.w, self.h = CARD_W_MM * mm, CARD_H_MM * mm

    def X(self, v):
        return self.x + v * self.mm

    def Y(self, top):
        return self.y + self.h - top * self.mm

    def pt(self, v):
        return v * self.mm


def _card_clip(k):
    p = k.c.beginPath()
    p.roundRect(k.x, k.y, k.w, k.h, k.pt(3))
    k.c.clipPath(p, stroke=0, fill=0)


ROLE_INK = "#5b6474"
STATUS_COLORS = {"active": "#16a34a", "invited": "#f59e0b"}


def status_color(user):
    return STATUS_COLORS.get(user.status, "#ef4444")


def name_layout(name):
    """Ism o'lchami (mm) — ekranda ham shu qoida: <=20 belgi 3.7 mm, uzunroq 3.0 mm, 26 dan oshsa ikki qator."""
    n = len(name or "")
    if n <= 20:
        return 3.7, False
    return 3.0, n > 26


def _hero(k, navy, accent, height_mm=None, orbs=((50, 2, 14, 0.35),)):
    """Navy → aksent gradienti, nozik to'r va yorug' doira. height_mm berilsa — pastki cheti egri."""
    from reportlab.lib.colors import white

    c = k.c
    full = height_mm is None
    hh = CARD_H_MM if full else height_mm
    c.saveState()
    if not full:
        rx, ry = CARD_W_MM * 0.85, hh  # CSS: clip-path: ellipse(85% 100% at 50% 0)
        p = c.beginPath()
        p.ellipse(k.X(27 - rx), k.Y(ry), k.pt(2 * rx), k.pt(2 * ry))
        c.clipPath(p, stroke=0, fill=0)
    a = math.radians(155)  # CSS: linear-gradient(155deg, navy 0%, mix 58%, accent 135%)
    dx, dy = math.sin(a), math.cos(a)
    length = abs(CARD_W_MM * dx) + abs(hh * dy)
    sx, st = 27 - dx * length / 2, hh / 2 + dy * length / 2
    ex, et = 27 + dx * length / 2, hh / 2 - dy * length / 2
    mid = _mix(navy, accent, 0.30)
    end = _mix(mid, accent, (1 - 0.58) / (1.35 - 0.58))
    c.linearGradient(k.X(sx), k.Y(st), k.X(ex), k.Y(et), (navy, mid, end), (0, 0.58, 1), extend=True)
    for ox, ot, r, alpha in orbs:
        c.setFillColor(accent if alpha > 0.1 else white)
        c.setFillAlpha(alpha)
        c.circle(k.X(ox), k.Y(ot), k.pt(r), stroke=0, fill=1)
    # to'r: har 3 mm
    c.setStrokeColor(white)
    c.setStrokeAlpha(0.07)
    c.setLineWidth(k.pt(0.12))
    v = 3.0
    while v < CARD_W_MM:
        c.line(k.X(v), k.Y(0), k.X(v), k.Y(hh))
        v += 3
    v = 3.0
    while v < hh:
        c.line(k.X(0), k.Y(v), k.X(CARD_W_MM), k.Y(v))
        v += 3
    c.restoreState()


def _slot(k):
    """Lenta (lanyard) uchun teshik joyi."""
    from reportlab.lib.colors import HexColor, white

    c = k.c
    c.saveState()
    c.setFillColor(HexColor("#061022"))
    c.setFillAlpha(0.55)
    c.setStrokeColor(white)
    c.setStrokeAlpha(0.18)
    c.setLineWidth(k.pt(0.15))
    c.roundRect(k.X(21.5), k.Y(4.4), k.pt(11), k.pt(2), k.pt(1), stroke=1, fill=1)
    c.restoreState()


def _draw_front(c, x, y, user, company, accent_hex, fonts, partners=(), host=""):
    from reportlab.lib.colors import Color, HexColor, white
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from . import brand

    reg, bold, ascii_only = fonts
    k = _Card(c, x, y)
    navy, accent = HexColor(NAVY), HexColor(accent_hex)
    c.saveState()
    _card_clip(k)
    c.setFillColor(white)
    c.rect(k.x, k.y, k.w, k.h, stroke=0, fill=1)
    _hero(k, navy, accent, height_mm=36)
    # suv belgisi: katta "S"
    brand.draw(c, k.X(30), k.Y(6), k.pt(30), Color(1, 1, 1, alpha=0.07), white, mark_only=True)
    _slot(k)
    brand.draw(c, k.X(5.5), k.Y(6.2), k.pt(3.4), white, _mix(navy, accent, 0.2))
    c.saveState()
    c.setFillColor(white)
    c.setFillAlpha(0.7)
    _spaced(c, "XODIM GUVOHNOMASI · STAFF ID", bold, k.pt(1.25), k.X(5.5), k.Y(10.9 + 1.25 * 0.9), k.pt(1.25) * 0.18)
    c.restoreState()

    # Rasm: gradient halqa + oq halqa
    cx, ct = 27, 33
    c.saveState()
    c.setFillColor(navy)
    for spread, alpha in ((1.4, 0.05), (0.8, 0.07), (0.35, 0.09)):
        c.setFillAlpha(alpha)
        c.circle(k.X(cx), k.Y(ct + 1.3), k.pt(13.4 + spread), stroke=0, fill=1)
    c.restoreState()
    c.saveState()
    p = c.beginPath()
    p.circle(k.X(cx), k.Y(ct), k.pt(13.4))
    c.clipPath(p, stroke=0, fill=0)
    c.linearGradient(k.X(cx - 13.4), k.Y(ct - 13.4), k.X(cx + 13.4), k.Y(ct + 13.4), (accent, HexColor("#8b5cf6")), extend=True)
    c.restoreState()
    c.setFillColor(white)
    c.circle(k.X(cx), k.Y(ct), k.pt(12.7), stroke=0, fill=1)
    inner = 12.0
    c.saveState()
    p = c.beginPath()
    p.circle(k.X(cx), k.Y(ct), k.pt(inner))
    c.clipPath(p, stroke=0, fill=0)
    photo = _photo_reader(user, ratio=1.0)
    if photo:
        c.drawImage(photo, k.X(cx - inner), k.Y(ct + inner), k.pt(2 * inner), k.pt(2 * inner))
    else:
        c.linearGradient(k.X(cx - inner), k.Y(ct - inner), k.X(cx + inner), k.Y(ct + inner), (_mix(navy, accent, .55), accent), extend=True)
        c.setFillColor(white)
        c.setFont(bold, k.pt(8.5))
        c.drawCentredString(k.X(cx), k.Y(ct) - k.pt(8.5) * 0.36, user.initials)
    c.restoreState()

    # Ism
    name = _clean(user.display_name, ascii_only)
    size_mm, two = name_layout(name)
    size = k.pt(size_mm)
    c.setFillColor(navy)
    c.setFont(bold, size)
    if two:
        lines, size = _split_name(c, name, bold, size, k.pt(46))
        c.setFont(bold, size)
    else:
        lines = [name]
        size = _fit(c, name, bold, size, k.pt(46))
        c.setFont(bold, size)
    lh = k.pt(size_mm) * 1.12
    base = k.Y(48.3) - (lh - k.pt(size_mm)) / 2 - k.pt(size_mm) * 0.8
    for i, line in enumerate(lines):
        c.drawCentredString(k.X(27), base - i * lh, line)
    extra = 3.4 if two else 0

    # Lavozim
    rs = k.pt(2.1)
    c.setFillColor(HexColor(ROLE_INK))
    c.setFont(reg, rs)
    c.drawCentredString(k.X(27), k.Y(53.0 + extra + 2.1 * 0.85), _ellipsize(_clean(user.job_title or "Xodim", ascii_only), reg, rs, k.pt(46)))

    # Bo'lim — "pill"
    if user.department_id:
        ds, sp = k.pt(1.6), k.pt(1.6) * 0.08
        dept = _clean(str(user.department), ascii_only).upper()
        tw = min(_spaced_width(dept, bold, ds, sp) / k.mm, 40)
        pw, ph, pt_ = tw + 4.8, 3.8, 56.6 + extra
        c.setFillColor(_mix(white, accent, 0.11))
        c.roundRect(k.X(27 - pw / 2), k.Y(pt_ + ph), k.pt(pw), k.pt(ph), k.pt(ph / 2), stroke=0, fill=1)
        c.setFillColor(accent)
        _spaced(c, dept, bold, ds, k.X(27), k.Y(pt_ + ph / 2) - ds * 0.36, sp, align="center")

    # Uch ustun: ID · Ish boshlagan · Holat
    ft = 62.4 + extra
    joined = user.joined_on.strftime("%d.%m.%Y") if user.joined_on else "—"
    cols = (("ID", badge_id(user), None), ("Ish boshlagan", joined, None),
            ("Holat", user.get_status_display(), status_color(user)))
    for i, (label, value, dot) in enumerate(cols):
        colx = 11 + i * 16
        c.setFillColor(HexColor("#8a94a6"))
        _spaced(c, _clean(label, ascii_only).upper(), bold, k.pt(1.2), k.X(colx), k.Y(ft + 1.2 * 0.9), k.pt(1.2) * 0.12, align="center")
        vs = k.pt(2.05)
        value = _ellipsize(_clean(value, ascii_only), bold, vs, k.pt(15 - (2.2 if dot else 0)))
        vw = stringWidth(value, bold, vs) / k.mm + (1.8 if dot else 0)
        vx = colx - vw / 2
        vb = k.Y(ft + 1.9 + 2.05 * 0.88)
        if dot:
            c.setFillColor(HexColor(dot))
            c.circle(k.X(vx + 0.6), vb + k.pt(0.62), k.pt(0.6), stroke=0, fill=1)
            vx += 1.8
        c.setFillColor(navy)
        c.setFont(bold, vs)
        c.drawString(k.X(vx), vb, value)

    # Pastki satr
    c.setFillColor(HexColor("#9aa3b2"))
    c.setFont(reg, k.pt(1.3))
    c.drawString(k.X(5), k.Y(82.3), host)
    c.drawRightString(k.X(49), k.Y(82.3), badge_id(user))

    c.restoreState()
    c.setStrokeColor(HexColor("#c4cad4"))
    c.setLineWidth(0.4)
    c.roundRect(x, y, k.w, k.h, k.pt(3), stroke=1, fill=0)


def _draw_back(c, x, y, user, company, url, accent_hex, fonts, partners=(), host=""):
    from reportlab.lib.colors import HexColor, white

    from . import brand

    reg, bold, ascii_only = fonts
    k = _Card(c, x, y)
    navy, accent = HexColor(NAVY), HexColor(accent_hex)
    c.saveState()
    _card_clip(k)
    _hero(k, navy, accent, orbs=((52, 4, 18, 0.3), (2, 60, 12, 0.05)))
    _slot(k)
    logo_h = 7.4
    brand.draw(c, k.X(27 - 1100 / 240 * logo_h / 2), k.Y(10), k.pt(logo_h), white, _mix(navy, accent, 0.25))
    c.saveState()
    c.setFillColor(white)
    c.setFillAlpha(0.7)
    _spaced(c, "XODIM GUVOHNOMASI", bold, k.pt(1.45), k.X(27), k.Y(20.6 + 1.45 * 0.9), k.pt(1.45) * 0.3, align="center")
    c.restoreState()

    # QR
    qx, qt, qw, pad = 14.5, 24.5, 25.0, 1.8
    c.saveState()
    c.setFillColor(HexColor("#000000"))
    c.setFillAlpha(0.2)
    c.roundRect(k.X(qx), k.Y(qt + qw + 1.1), k.pt(qw), k.pt(qw), k.pt(2.6), stroke=0, fill=1)
    c.restoreState()
    c.setFillColor(white)
    c.roundRect(k.X(qx), k.Y(qt + qw), k.pt(qw), k.pt(qw), k.pt(2.6), stroke=0, fill=1)
    m = _qr_matrix(url)
    n = len(m)
    cell = (qw - 2 * pad) / (n + 4)
    c.setFillColor(navy)
    for ri, row in enumerate(m):
        for ci, dark in enumerate(row):
            if dark:
                c.rect(k.X(qx + pad + (ci + 2) * cell), k.Y(qt + pad + (ri + 3) * cell),
                       k.pt(cell) + 0.05, k.pt(cell) + 0.05, stroke=0, fill=1)

    c.setFillColor(white)
    _spaced(c, badge_id(user), bold, k.pt(2.6), k.X(27), k.Y(52.0 + 2.6 * 0.9), k.pt(2.6) * 0.1, align="center")

    # Hamkorlar
    logos = [(p, *_logo_reader(p)) for p in partners]
    logos = [(p, img, ratio) for p, img, ratio in logos if img]
    rules_top = 60.5
    if logos:
        rules_top = 71.2
        # Yozuvsiz va ramkasiz: logo o'z ko'rinishida, burchaklari biroz yumaloq (CSS bilan bir xil).
        count = len(logos)
        slot_h, gap = 8.0, 2.0
        slot_w = min(22.0, (46 - gap * (count - 1)) / count)
        start = 27 - (count * slot_w + (count - 1) * gap) / 2
        top = 58.6
        for i, (partner, img, ratio) in enumerate(logos):
            lx = start + i * (slot_w + gap)
            iw, ih = (slot_w, slot_w / ratio) if ratio > slot_w / slot_h else (slot_h * ratio, slot_h)
            ix, it = lx + (slot_w - iw) / 2, top + (slot_h - ih) / 2
            c.saveState()
            p = c.beginPath()
            p.roundRect(k.X(ix), k.Y(it + ih), k.pt(iw), k.pt(ih), k.pt(0.8))
            c.clipPath(p, stroke=0, fill=0)
            c.drawImage(img, k.X(ix), k.Y(it + ih), k.pt(iw), k.pt(ih), mask="auto")
            c.restoreState()

    c.saveState()
    c.setFillColor(white)
    c.setFillAlpha(0.62)
    rs = k.pt(1.45)
    c.setFont(reg, rs)
    for i, line in enumerate((f"Ushbu guvohnoma {company} xodimiga tegishli.",
                              f"Topib olsangiz: {host}" if host else "Topib olsangiz, kompaniyaga qaytaring.")):
        c.drawCentredString(k.X(27), k.Y(rules_top + 1.45 * 1.5 * i + 1.45 * 0.95), _clean(line, ascii_only))
    c.restoreState()

    # Imzo va muhr
    c.saveState()
    c.setStrokeColor(white)
    c.setStrokeAlpha(0.35)
    c.setLineWidth(k.pt(0.16))
    c.line(k.X(5), k.Y(80.2), k.X(25), k.Y(80.2))
    c.setDash(k.pt(0.8), k.pt(0.6))
    c.circle(k.X(45.5), k.Y(78.6), k.pt(3.4), stroke=1, fill=0)
    c.setDash()
    c.setFillColor(white)
    c.setFillAlpha(0.55)
    c.setFont(reg, k.pt(1.2))
    c.drawString(k.X(5), k.Y(81.9), _clean("Rahbar imzosi", ascii_only))
    c.setFont(bold, k.pt(1.2))
    c.drawCentredString(k.X(45.5), k.Y(78.6) - k.pt(1.2) * 0.36, _clean("M.O‘.", ascii_only))
    c.restoreState()

    c.restoreState()
    c.setStrokeColor(HexColor("#c4cad4"))
    c.setLineWidth(0.4)
    c.roundRect(x, y, k.w, k.h, k.pt(3), stroke=1, fill=0)


def _crop_marks(c, x, y, w, h):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm

    c.setStrokeColor(HexColor("#9ca3af"))
    c.setLineWidth(0.3)
    gap, ln = 2 * mm, 5 * mm
    for cx, cy, dx, dy in ((x, y, -1, -1), (x + w, y, 1, -1), (x, y + h, -1, 1), (x + w, y + h, 1, 1)):
        c.line(cx + dx * gap, cy, cx + dx * (gap + ln), cy)
        c.line(cx, cy + dy * gap, cx, cy + dy * (gap + ln))


def badge_pdf(user, url, company="SSB Group", accent="#007aff", partners=None):
    """A4 sahifa: old va orqa tomon haqiqiy o'lchamda (54 x 85.6 mm), kesish belgilari bilan."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    if partners is None:
        partners = badge_partners()
    fonts = _fonts()
    reg, bold, ascii_only = fonts
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Bedjik — {_clean(user.display_name, ascii_only)} ({badge_id(user)})")
    c.setAuthor(company)
    pw, ph = A4
    w, h = CARD_W_MM * mm, CARD_H_MM * mm
    gap = 18 * mm
    x1 = (pw - (2 * w + gap)) / 2
    x2 = x1 + w + gap
    y = ph - 60 * mm - h
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    c.setFillColor(HexColor(NAVY))
    c.rect(20 * mm, ph - 19 * mm, 1.2 * mm, 9 * mm, stroke=0, fill=1)
    c.setFillColor(HexColor(INK))
    c.setFont(bold, 14)
    c.drawString(24 * mm, ph - 15 * mm, _clean(f"{company} — xodim guvohnomasi", ascii_only))
    c.setFont(reg, 9)
    c.setFillColor(HexColor(MUTED))
    c.drawString(24 * mm, ph - 19.5 * mm, _clean(f"{user.display_name} · {badge_id(user)}", ascii_only))
    c.setFont(reg, 8.5)
    c.drawString(20 * mm, ph - 31 * mm, _clean("O‘lcham: 54 × 85,6 mm (CR80, bank kartasi). Chop etishda masshtab 100% bo‘lsin.", ascii_only))
    c.drawString(20 * mm, ph - 36 * mm, _clean("Kesish belgilari bo‘yicha kesing, ikki tomonini yopishtiring va laminatsiya qiling. Orqa tomoni rahbar imzosi va muhr bilan tasdiqlanadi.", ascii_only))
    _draw_front(c, x1, y, user, company, accent, fonts, partners=partners, host=host)
    _draw_back(c, x2, y, user, company, url, accent, fonts, partners=partners, host=host)
    _crop_marks(c, x1, y, w, h)
    _crop_marks(c, x2, y, w, h)
    c.setFont(bold, 9)
    c.setFillColor(HexColor("#374151"))
    c.drawCentredString(x1 + w / 2, y - 12 * mm, _clean("Old tomoni", ascii_only))
    c.drawCentredString(x2 + w / 2, y - 12 * mm, _clean("Orqa tomoni", ascii_only))
    c.showPage()
    c.save()
    return buf.getvalue()
