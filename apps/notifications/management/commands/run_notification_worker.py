import time
from django.conf import settings
from django.core.management.base import BaseCommand
from apps.notifications.channels import deliver_pending, poll_telegram, telegram_configured


class Command(BaseCommand):
    help = 'Deliver queued personal email/Telegram notifications; poll private bot linking commands.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            if telegram_configured() and settings.TELEGRAM_NOTIFICATIONS_ENABLED:
                try:
                    poll_telegram()
                except Exception:
                    self.stderr.write('Telegram poll failed. Check bot configuration, webhook conflicts and connectivity.')
            sent = deliver_pending()
            if sent or options['once']:
                self.stdout.write(f'Delivered: {sent}')
            if options['once']:
                return
            time.sleep(10)
