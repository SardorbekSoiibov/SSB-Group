"""SSB AI for the work schedule: reads a plain Uzbek instruction and proposes shifts.

Rules only, no external model: nothing leaves the server. It never saves by itself. The manager sees the
proposed shifts first and apply() repeats every permission and overlap check through operations.save_shift().
"""
import re
from datetime import date, datetime, time, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.policies import visible_employees
from . import operations
from .models import WorkShift

WEEKDAYS = ('dushanba', 'seshanba', 'chorshanba', 'payshanba', 'juma', 'shanba', 'yakshanba')
DAY_NAMES = ('Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba')
MONTHS = ('yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr')
SUFFIXES = ('', 'ga', 'ka', 'qa', 'ni', 'ning', 'dan', 'gacha', 'da', 'lar', 'larga', 'kuni', 'si')
PLACES = (('Masofaviy', ('masofa', 'uydan', 'uyda', 'onlayn', 'remote')), ('Navbatchilik', ('navbatchi',)), ('Ofis', ('ofis',)))
EVERYONE = ('hamma', 'hammaga', 'hammani', 'barcha', 'barchaga', 'barchani')
MYSELF = ('menga', 'meni', "o'zimga", "o'zim")
MAX_SHIFTS = 100
EXAMPLE = 'Masalan: «Sardor dushanbadan jumagacha 9 dan 18 gacha ofisda».'
DATE_NAMED = re.compile('([0-9]{1,2})[- ]?(' + '|'.join(MONTHS) + ')[a-z]*')
DATE_DOTTED = re.compile('(?<![0-9:])([0-9]{1,2})[.]([0-9]{1,2})(?:[.]([0-9]{4}))?(?![0-9])')
TIME_RANGE = re.compile('(?<![0-9])([0-9]{1,2})(?::([0-9]{2}))?[ ]?(?:dan|-|–)[ ]?([0-9]{1,2})(?::([0-9]{2}))?')


def clean(text):
    text = str(text).lower().strip()
    for mark in ('’', '‘', 'ʻ', 'ʼ', '`'):
        text = text.replace(mark, "'")
    return text


def word_is(word, stem):
    return word.startswith(stem) and word[len(stem):] in SUFFIXES


def weekday_of(word):
    return next((index for index, stem in enumerate(WEEKDAYS) if word_is(word, stem)), None)


def words_of(text):
    return re.findall("[a-z0-9_']+", text)


def read_dates(text, today):
    """Takes calendar dates out of the text so that their numbers are not read as hours."""
    found = []

    def named(match):
        found.append((match.start(), int(match.group(1)), MONTHS.index(match.group(2)) + 1, today.year))
        return ' '

    def dotted(match):
        day, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            return match.group(0)
        found.append((match.start(), day, month, int(match.group(3) or today.year)))
        return ' '

    text = DATE_DOTTED.sub(dotted, DATE_NAMED.sub(named, text))
    dates, wrong = [], False
    for _, day, month, year in sorted(found):
        try:
            dates.append(date(year, month, day))
        except ValueError:
            wrong = True
    return text, dates, wrong


def read_hours(text):
    match = TIME_RANGE.search(text)
    if not match:
        return text, time(9), time(18), True
    try:
        start = time(int(match.group(1)), int(match.group(2) or 0))
        end = time(int(match.group(3)), int(match.group(4) or 0))
    except ValueError:
        return text, None, None, False
    return text[:match.start()] + ' ' + text[match.end():], start, end, False


def read_days(text, dates, week, today):
    words = words_of(text)
    if len(dates) == 2 and 'gacha' in text and dates[0] < dates[1]:
        return [dates[0] + timedelta(days=i) for i in range((dates[1] - dates[0]).days + 1)]
    days = list(dates)
    if 'keyingi hafta' in text or 'kelasi hafta' in text:
        week += timedelta(days=7)
    if 'bugun' in text:
        days.append(today)
    if 'ertaga' in text:
        days.append(today + timedelta(days=1))
    if 'indinga' in text:
        days.append(today + timedelta(days=2))
    if 'ish kun' in text:
        days += [week + timedelta(days=i) for i in range(5)]
    elif 'har kun' in text or 'butun hafta' in text or 'hafta davomida' in text or "hafta bo'yi" in text:
        days += [week + timedelta(days=i) for i in range(7)]
    named = [(weekday_of(word), word) for word in words if weekday_of(word) is not None]
    joined = re.search('([a-z]+)[ ]?[-–][ ]?([a-z]+)', text)
    if joined and weekday_of(joined.group(1)) is not None and weekday_of(joined.group(2)) is not None:
        first, last = weekday_of(joined.group(1)), weekday_of(joined.group(2))
        days += [week + timedelta(days=i) for i in range(first, last + 1)]
    elif len(named) == 2 and named[0][1].endswith('dan') and named[1][1].endswith('gacha') and named[0][0] <= named[1][0]:
        days += [week + timedelta(days=i) for i in range(named[0][0], named[1][0] + 1)]
    else:
        days += [week + timedelta(days=index) for index, _ in named]
    return sorted(set(days))


def name_parts(person):
    return [clean(part) for part in (person.first_name, person.last_name, person.username) if part]


def read_people(text, actor):
    words = [word for word in words_of(text) if weekday_of(word) is None]
    people = list(visible_employees(actor).filter(is_active=True))
    if any(word in EVERYONE for word in words):
        return [person for person in people if person.pk != actor.pk], []
    chosen, unclear = {}, []
    if any(word in MYSELF for word in words):
        chosen[actor.pk] = actor
    for index, word in enumerate(words):
        matches = [person for person in people if any(word_is(word, part) for part in name_parts(person) if len(part) >= 3)]
        if len(matches) > 1:
            around = words[max(index - 1, 0):index + 2]
            narrowed = [person for person in matches if sum(any(word_is(item, part) for part in name_parts(person)) for item in around) > 1]
            matches = narrowed or matches
        if len(matches) == 1:
            chosen[matches[0].pk] = matches[0]
        elif matches:
            unclear.append(matches)
    unclear = [group for group in unclear if not any(person.pk in chosen for person in group)]
    return list(chosen.values()), unclear


def read_place(text):
    return next((place for place, stems in PLACES if any(stem in text for stem in stems)), 'Ofis')


def moment(day, value):
    return timezone.make_aware(datetime.combine(day, value))


def propose(actor, message, week=None, today=None):
    """Returns {'reply', 'need', 'shifts'}. need=True means the next message continues this one."""
    today = today or timezone.localdate()
    week = week or today - timedelta(days=today.weekday())
    text = clean(message)
    if not text:
        return {'reply': 'Kimga va qachon smena qo‘yay? ' + EXAMPLE, 'need': False, 'shifts': []}
    text, dates, wrong_date = read_dates(text, today)
    if wrong_date:
        return {'reply': 'Bunday sana yo‘q. Sanani tekshirib, qayta yozing.', 'need': False, 'shifts': []}
    text, start, end, default_hours = read_hours(text)
    if start is None:
        return {'reply': 'Vaqtni tushunmadim. «9 dan 18 gacha» yoki «09:00-18:00» deb yozing.', 'need': False, 'shifts': []}
    if start == end:
        return {'reply': 'Boshlanish va tugash vaqti bir xil. Vaqtni tekshirib, qayta yozing.', 'need': False, 'shifts': []}
    people, unclear = read_people(text, actor)
    if unclear:
        names = ', '.join(person.display_name for person in unclear[0])
        return {'reply': f'Bir nechta odam topildi: {names}. Familiyasini ham yozing.', 'need': True, 'shifts': []}
    if not people:
        return {'reply': 'Kimga qo‘yay? Xodim ismini yozing.', 'need': True, 'shifts': []}
    days = read_days(text, dates, week, today)
    if not days:
        return {'reply': 'Qaysi kunga? Masalan: «ertaga», «dushanbadan jumagacha» yoki «12-noyabr».', 'need': True, 'shifts': []}
    place = read_place(text)
    if len(people) * len(days) > MAX_SHIFTS:
        return {'reply': f'Bir xabarda {MAX_SHIFTS} tagacha smena qo‘yiladi. Davrni qisqartiring.', 'need': False, 'shifts': []}
    shifts = []
    for person in people:
        for day in days:
            begins = moment(day, start)
            ends = moment(day + timedelta(days=1) if end < start else day, end)
            busy = WorkShift.objects.filter(employee=person, cancelled=False, starts_at__lt=ends, ends_at__gt=begins).exists()
            shifts.append({'employee': person.pk, 'name': person.display_name, 'date': day.isoformat(),
                           'label': f'{DAY_NAMES[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}',
                           'start': start.strftime('%H:%M'), 'end': end.strftime('%H:%M'), 'location': place, 'busy': busy})
    free = sum(not shift['busy'] for shift in shifts)
    reply = f'{free} ta smena tayyor. Tekshiring va tasdiqlang.' if free else 'Bu vaqtda hammasi band, qo‘shadigan smena yo‘q.'
    if free and free < len(shifts):
        reply += f' {len(shifts) - free} tasi band, ular qo‘shilmaydi.'
    if default_hours:
        reply += ' Vaqt yozilmagani uchun 09:00–18:00 oldim.'
    return {'reply': reply, 'need': False, 'shifts': shifts}


def apply(actor, shifts):
    """Saves proposed shifts. Each one goes through the normal service, so nothing here widens anyone's rights."""
    if not isinstance(shifts, list) or not shifts or len(shifts) > MAX_SHIFTS:
        raise ValidationError('Qo‘shiladigan smena topilmadi.')
    people = {person.pk: person for person in visible_employees(actor).filter(is_active=True)}
    saved, skipped = [], 0
    for item in shifts:
        try:
            person = people[int(item['employee'])]
            day = date.fromisoformat(item['date'])
            start, end = time.fromisoformat(item['start']), time.fromisoformat(item['end'])
            location = str(item['location'])[:180] or 'Ofis'
        except (KeyError, TypeError, ValueError):
            raise PermissionDenied
        try:
            saved.append(operations.save_shift(actor, person, moment(day, start),
                                               moment(day + timedelta(days=1) if end < start else day, end), location))
        except ValidationError:
            skipped += 1
    return saved, skipped
