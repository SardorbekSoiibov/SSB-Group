"""SSB Group logotipi (static/img/ssb-group.svg) — bedjikda ekranda (SVG) va PDF'da (reportlab) bir xil chiziladi.

Logo 1100 × 240 birlikda: "SSB" shakllari to'ldirilgan, pastki tasmada "GROUP" harflari kesib chiqilgan
(chiziq rangi = fon rangi).
"""
import math
import re

VIEW_W, VIEW_H = 1100, 240
_S = "M142 8H385L337 51H148C116 51 105 77 135 77H291C398 77 379 200 270 200H0L64 147H277C311 147 321 119 287 119H119C18 119 30 8 142 8Z"
FILLS = [
    (_S, (0, 0), False),
    (_S, (344, 0), False),
    ("M747 8H973C1064 8 1082 65 1027 91C1087 117 1056 174 994 182H738L743 78H958C992 78 999 51 964 51H745Z"
     "M805 119L802 140Q800 151 816 151H962C991 151 999 119 967 119Z", (0, 0), True),
    ("M744 163H1080Q1112 163 1091 191L1068 218Q1057 234 1039 234H690Q679 234 687 223Z", (0, 0), False),
]
# "GROUP" — translate(740 179) skewX(-16), stroke 8
STROKES = [
    "M48 5H15Q5 5 5 15V35Q5 45 15 45H48V27H27",
    "M68 45V5H100Q111 5 111 15V19Q111 29 100 29H68M90 29L111 45",
    "M141 5H167Q176 5 176 14V36Q176 45 167 45H141Q132 45 132 36V14Q132 5 141 5Z",  # rect rx=9
    "M198 5V35Q198 45 208 45H231Q241 45 241 35V5",
    "M263 45V5H295Q307 5 307 16V20Q307 30 295 30H263",
]
STROKE_ORIGIN, STROKE_SKEW, STROKE_W = (740, 179), -16, 8


def svg(cut="#0a1a33", fill="currentColor", mark_only=False):
    """Inline SVG. mark_only=True — faqat birinchi "S" (suv belgisi uchun)."""
    if mark_only:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 390 210" aria-hidden="true">'
                f'<path fill="{fill}" d="{_S}"/></svg>')
    parts = []
    for d, (dx, _), odd in FILLS:
        rule = ' fill-rule="evenodd"' if odd else ""
        move = f' transform="translate({dx})"' if dx else ""
        parts.append(f'<path fill="{fill}"{rule} d="{d}"{move}/>')
    strokes = "".join(f'<path d="{d}"/>' for d in STROKES)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {VIEW_H}" fill="none" role="img" aria-label="SSB Group">'
            f'{"".join(parts)}<g transform="translate({STROKE_ORIGIN[0]} {STROKE_ORIGIN[1]}) skewX({STROKE_SKEW})" '
            f'stroke="{cut}" stroke-width="{STROKE_W}" stroke-linejoin="round" stroke-linecap="square">{strokes}</g></svg>')


_TOKEN = re.compile(r"[MLHVCQZ]|-?\d*\.?\d+")


def _segments(d):
    """SVG yo'lidan (faqat absolyut M L H V C Q Z) buyruqlar ro'yxati: ('M',(x,y)), ('C',p1,p2,p3), ('Z',)."""
    tokens = _TOKEN.findall(d)
    out, i, cur, start, cmd = [], 0, (0.0, 0.0), (0.0, 0.0), None
    nums = lambda k: [float(tokens[i + j]) for j in range(k)]  # noqa: E731
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd == "Z":
                out.append(("Z",))
                cur = start
                continue
        if cmd == "M":
            x, y = nums(2); i += 2
            out.append(("M", (x, y))); cur = start = (x, y); cmd = "L"
        elif cmd == "L":
            x, y = nums(2); i += 2
            out.append(("L", (x, y))); cur = (x, y)
        elif cmd == "H":
            x, = nums(1); i += 1
            cur = (x, cur[1]); out.append(("L", cur))
        elif cmd == "V":
            y, = nums(1); i += 1
            cur = (cur[0], y); out.append(("L", cur))
        elif cmd == "C":
            a, b, c2, d2, e, f = nums(6); i += 6
            out.append(("C", (a, b), (c2, d2), (e, f))); cur = (e, f)
        elif cmd == "Q":
            qx, qy, x, y = nums(4); i += 4
            p0 = cur
            c1 = (p0[0] + 2 / 3 * (qx - p0[0]), p0[1] + 2 / 3 * (qy - p0[1]))
            c2_ = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
            out.append(("C", c1, c2_, (x, y))); cur = (x, y)
        else:
            i += 1
    return out


def _path(canvas, d, tf):
    p = canvas.beginPath()
    for seg in _segments(d):
        if seg[0] == "M":
            p.moveTo(*tf(*seg[1]))
        elif seg[0] == "L":
            p.lineTo(*tf(*seg[1]))
        elif seg[0] == "C":
            p.curveTo(*tf(*seg[1]), *tf(*seg[2]), *tf(*seg[3]))
        else:
            p.close()
    return p


def draw(canvas, x, top, height, fill, cut, mark_only=False):
    """Logoni PDF'ga chizadi: (x, top) — chap-yuqori burchak (PDF nuqtalarida), height — balandlik."""
    from reportlab.pdfgen.canvas import FILL_EVEN_ODD, FILL_NON_ZERO

    vh = 210 if mark_only else VIEW_H
    s = height / vh

    def at(dx=0, dy=0, skew=0.0):
        k = math.tan(math.radians(skew))
        return lambda px, py: (x + (dx + px + k * py) * s, top - (dy + py) * s)

    canvas.saveState()
    canvas.setFillColor(fill)
    for d, (dx, dy), odd in (FILLS[:1] if mark_only else FILLS):
        canvas.drawPath(_path(canvas, d, at(dx, dy)), stroke=0, fill=1, fillMode=FILL_EVEN_ODD if odd else FILL_NON_ZERO)
    if not mark_only:
        canvas.setStrokeColor(cut)
        canvas.setLineWidth(STROKE_W * s)
        canvas.setLineJoin(1)
        canvas.setLineCap(2)
        tf = at(*STROKE_ORIGIN, skew=STROKE_SKEW)
        for d in STROKES:
            canvas.drawPath(_path(canvas, d, tf), stroke=1, fill=0)
    canvas.restoreState()
    return VIEW_W * s if not mark_only else 390 * s
