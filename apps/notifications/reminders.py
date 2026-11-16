"""Idempotent deadline reminders, shared by CLI and active dashboard polling."""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.core.models import WorkspaceSettings
from apps.crm.models import Project, Task
from .services import Kind, notify


def send_deadline_reminders():
    today = timezone.localdate()
    days = WorkspaceSettings.load().reminder_days_before
    closed = [Project.Status.COMPLETED, Project.Status.ARCHIVED, Project.Status.CANCELLED]
    tasks = Task.objects.filter(status__in=Task.OPEN, assignee__isnull=False).exclude(
        project__status__in=closed).select_related('assignee', 'project__manager')
    sent = 0
    for task in tasks.filter(deadline__range=(today, today + timedelta(days=days))):
        left = (task.deadline - today).days
        sent += len(notify([task.assignee], Kind.DEADLINE_SOON,
            f"Muddat {'bugun' if left == 0 else f'{left} kundan keyin'}: {task.title}",
            body=task.project.name, url=task.get_absolute_url(),
            dedupe_key=f'soon:{task.pk}:{task.deadline}:{today}'))
    for task in tasks.filter(deadline__lt=today):
        sent += len(notify([task.assignee, task.project.manager], Kind.OVERDUE,
            f"Muddati o‘tgan vazifa: {task.title}",
            body=f'{task.project.code} · muddat {task.deadline:%d.%m.%Y}',
            url=task.get_absolute_url(), dedupe_key=f'overdue:{task.pk}:{today}'))
    for project in Project.objects.filter(deadline__lt=today).exclude(status__in=closed).select_related('manager'):
        sent += len(notify([project.manager], Kind.OVERDUE,
            f"Loyiha muddati o‘tgan: {project.name}", url=project.get_absolute_url(),
            dedupe_key=f'project-overdue:{project.pk}:{today}'))
    return sent


def refresh_deadline_reminders():
    # DB uniqueness is the final duplicate guard across processes and CLI runs.
    key = 'ssb-deadline-reminders-v2'
    if not cache.add(key, True, timeout=60):
        return
    try:
        send_deadline_reminders()
    except Exception:
        cache.delete(key)
        raise
