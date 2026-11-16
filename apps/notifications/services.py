"""Single entry point for notifications. External channels (e.g. Telegram) plug in inside notify()."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import ClearedReminder, Notification

Kind = Notification.Kind


def notify(recipients, kind, title, body="", url="", dedupe_key="", exclude=None):
    created = []
    seen = set()
    for user in recipients:
        if user is None or user.pk in seen or (exclude is not None and user.pk == exclude.pk):
            continue
        seen.add(user.pk)
        if not user.is_active or kind in user.muted_notifications:
            continue
        if dedupe_key and ClearedReminder.objects.filter(recipient=user, dedupe_key=dedupe_key).exists():
            continue
        try:
            with transaction.atomic():
                notification = Notification.objects.create(
                    recipient=user, kind=kind, title=title[:200], body=body, url=url, dedupe_key=dedupe_key,
                )
                from .channels import enqueue
                enqueue(notification)
                created.append(notification)
        except IntegrityError:
            if dedupe_key and Notification.objects.filter(recipient=user, dedupe_key=dedupe_key).exists():
                continue
            raise
    return created


def clear_notifications(user):
    """Deletes all of a person's notifications. Reminders are keyed by day, so only today's need remembering."""
    today = timezone.localdate()
    with transaction.atomic():
        own = user.notifications.all()
        keys = [key for key in own.exclude(dedupe_key="").values_list("dedupe_key", flat=True) if key.endswith(f":{today}")]
        ClearedReminder.objects.filter(cleared_on__lt=today).delete()
        ClearedReminder.objects.bulk_create(
            [ClearedReminder(recipient=user, dedupe_key=key, cleared_on=today) for key in keys], ignore_conflicts=True)
        return own.delete()[0]
