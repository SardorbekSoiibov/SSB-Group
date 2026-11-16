"""Weekly rating: a week runs from one Sunday 00:00 to the next and is published at that moment.

SSB AI only reads what really happened (accepted tasks, projects, delays, corrections) and suggests an order.
The boss sets the places and the prize for 1st place; employees see nothing until the Sunday arrives.
"""
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record
from apps.crm.models import Task, TaskReview
from apps.notifications.services import Kind, notify
from .models import WeeklyPlace, WeeklyRating

MONTHS = ('yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr')
MANAGE = 'performance.manage'


def sunday_after(day):
    """The Sunday that closes the week containing this day. A Sunday itself opens a new week."""
    return day + timedelta(days=7 - (day.weekday() + 1) % 7)


def current_week(today=None):
    return sunday_after(today or timezone.localdate())


def moment(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def week_label(publish_on):
    start, end = publish_on - timedelta(days=7), publish_on - timedelta(days=1)
    if start.month == end.month:
        return f'{start.day}–{end.day} {MONTHS[end.month - 1]}'
    return f'{start.day} {MONTHS[start.month - 1]} – {end.day} {MONTHS[end.month - 1]}'


def rated_people():
    """Everyone who works here, except the Founder who gives the places."""
    return (User.objects.filter(is_active=True, status=User.Status.ACTIVE).exclude(role__is_owner=True).exclude(is_superuser=True)
            .select_related('role', 'department').order_by('first_name', 'last_name', 'username'))


def week_facts(publish_on):
    """What each person actually did this week, straight from the task records, best suggestion first."""
    begins, ends = moment(publish_on - timedelta(days=7)), moment(publish_on)
    last_day = publish_on - timedelta(days=1)
    people = list(rated_people())
    done = {}
    for task in (Task.objects.filter(assignee__in=people, status=Task.Status.APPROVED, approved_at__gte=begins, approved_at__lt=ends)
                 .select_related('project').annotate(corrections=Count('reviews', distinct=True, filter=_changes())).order_by('-approved_at')):
        done.setdefault(task.assignee_id, []).append(task)
    waiting = dict(Task.objects.filter(assignee__in=people, status=Task.Status.SUBMITTED, submitted_at__gte=begins, submitted_at__lt=ends)
                   .order_by().values_list('assignee').annotate(total=Count('pk')))
    overdue = dict(Task.objects.filter(assignee__in=people, status__in=Task.OPEN, deadline__lte=last_day)
                   .order_by().values_list('assignee').annotate(total=Count('pk')))
    corrections = dict(TaskReview.objects.filter(task__assignee__in=people, decision=TaskReview.Decision.CHANGES, created_at__gte=begins, created_at__lt=ends)
                       .order_by().values_list('task__assignee').annotate(total=Count('pk')))
    rows = []
    for person in people:
        tasks = done.get(person.pk, [])
        for task in tasks:
            task.on_time = not task.deadline or timezone.localtime(task.approved_at).date() <= task.deadline
        on_time = sum(task.on_time for task in tasks)
        row = {'person': person, 'tasks': tasks, 'done': len(tasks), 'on_time': on_time, 'late': len(tasks) - on_time,
               'projects': sorted({task.project.name for task in tasks}), 'waiting': waiting.get(person.pk, 0),
               'overdue': overdue.get(person.pk, 0), 'corrections': corrections.get(person.pk, 0)}
        row['score'] = row['done'] * 10 + on_time * 5 - row['corrections'] * 2 - row['overdue'] * 3
        rows.append(row)
    rows.sort(key=lambda row: (-row['score'], -row['done'], row['person'].display_name.lower()))
    for number, row in enumerate(rows, 1):
        row['suggested'] = number if row['done'] else 0
    return rows


def _changes():
    from django.db.models import Q
    return Q(reviews__decision=TaskReview.Decision.CHANGES)


def is_published(rating, today=None):
    return rating.publish_on <= (today or timezone.localdate()) and rating.places.exists()


def published(today=None):
    today = today or timezone.localdate()
    return WeeklyRating.objects.filter(publish_on__lte=today, places__isnull=False).distinct()


def editable_weeks(today=None):
    """This week, and the week just closed if the boss has not placed anyone yet (it then publishes on saving)."""
    today = today or timezone.localdate()
    week = current_week(today)
    closed = week - timedelta(days=7)
    weeks = [week]
    if not WeeklyPlace.objects.filter(rating__publish_on=closed).exists():
        weeks.append(closed)
    return weeks


def save_places(actor, publish_on, prize, places, today=None):
    """places maps employee id to place number. Checked here so that no screen can save a broken rating."""
    if not actor.has_cap(MANAGE):
        raise ValidationError('O‘rinlarni faqat boshliq belgilaydi.')
    if publish_on not in editable_weeks(today):
        raise ValidationError('Bu hafta e’lon qilingan, uni o‘zgartirib bo‘lmaydi.')
    prize = prize.strip()
    numbers = sorted(places.values())
    if not numbers:
        raise ValidationError('Kamida 1-o‘rinni belgilang.')
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValidationError('O‘rinlar 1 dan boshlab ketma-ket bo‘lsin va takrorlanmasin.')
    if not prize:
        raise ValidationError('1-o‘rin uchun sovg‘ani yozing.')
    allowed = set(rated_people().values_list('pk', flat=True))
    if not set(places) <= allowed:
        raise ValidationError('Ro‘yxatda yo‘q xodim tanlangan.')
    with transaction.atomic():
        rating, _ = WeeklyRating.objects.select_for_update().get_or_create(publish_on=publish_on)
        rating.prize, rating.updated_by = prize[:200], actor
        rating.save()
        rating.places.all().delete()
        WeeklyPlace.objects.bulk_create([WeeklyPlace(rating=rating, employee_id=pk, place=place) for pk, place in places.items()])
        record(actor, 'rating.saved', rating, {'week': str(publish_on), 'prize': rating.prize, 'places': {str(pk): place for pk, place in places.items()}})
    announce_due(today)
    return rating


def announce_due(today=None):
    """Runs from the notification poll, so the announcement goes out once the Sunday has come."""
    today = today or timezone.localdate()
    for pk in list(WeeklyRating.objects.filter(publish_on__lte=today, announced=False, places__isnull=False).values_list('pk', flat=True).distinct()):
        with transaction.atomic():
            rating = WeeklyRating.objects.select_for_update().filter(pk=pk, announced=False).first()
            if rating is None:
                continue
            rating.announced = True
            rating.save(update_fields=['announced'])
            winner = rating.places.select_related('employee').filter(place=1).first()
            url = f'/management/enterprise/reyting/?hafta={rating.publish_on}'
            label = week_label(rating.publish_on)
            if winner:
                notify([winner.employee], Kind.ANNOUNCEMENT, 'Tabriklaymiz, siz 1-o‘rindasiz!', f'{label} · Sovg‘a: {rating.prize}', url)
            everyone = User.objects.filter(is_active=True, status=User.Status.ACTIVE)
            notify(everyone, Kind.ANNOUNCEMENT, 'Haftalik reyting e’lon qilindi', label, url, exclude=winner.employee if winner else None)
