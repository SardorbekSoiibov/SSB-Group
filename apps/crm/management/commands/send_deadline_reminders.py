from django.core.management.base import BaseCommand
from apps.notifications.reminders import send_deadline_reminders


class Command(BaseCommand):
    help = 'Send duplicate-safe deadline reminders; schedule daily for an unattended server.'

    def handle(self, *args, **opts):
        self.stdout.write(f'Yuborildi: {send_deadline_reminders()}')
