"""Process-local delivery and the Telegram bot listener. No scheduled task or persistent OS service is installed.

Ikki fon oqimi:
- ssb-channel-delivery: navbatdagi email/Telegram bildirishnomalarni yuboradi (har 10 soniya);
- ssb-telegram-bot: botga kelgan xabar va tugmalarni darhol qayta ishlaydi (long polling).
Bot o'quvchisi Postgres advisory lock bilan himoyalangan: bir nechta server jarayoni bo'lsa ham, faqat bittasi o'qiydi.
"""
import logging
import threading

from django.db import close_old_connections, connection, transaction

_lock = threading.Lock()
_worker = None
_bot = None
logger = logging.getLogger(__name__)


def _run():
    from .channels import deliver_pending
    while True:
        close_old_connections()
        try:
            deliver_pending()
        except Exception:
            logger.warning('External notification worker: connection attempt failed.')
        finally:
            close_old_connections()
        threading.Event().wait(10)


def _bot_loop():
    from django.conf import settings
    from .channels import POLL_LOCK, poll_once, telegram_configured
    from . import bot
    wait = threading.Event().wait
    while True:
        close_old_connections()
        if not (telegram_configured() and settings.TELEGRAM_NOTIFICATIONS_ENABLED):
            wait(30)
            continue
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_try_advisory_lock(%s)', [POLL_LOCK])
                holder = cursor.fetchone()[0]
            if not holder:
                connection.close()
                wait(30)  # Boshqa server jarayoni botni o'qiyapti.
                continue
            try:
                bot.set_commands()
                failures = 0
                while telegram_configured():
                    try:
                        poll_once(timeout=25)
                        failures = 0
                    except Exception:
                        failures += 1
                        logger.warning('Telegram bot: getUpdates failed (%s).', failures)
                        wait(min(60, 3 * failures))
                        if failures >= 10:
                            break
            finally:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_advisory_unlock(%s)', [POLL_LOCK])
                except Exception:
                    pass
                connection.close()
        except Exception:
            logger.warning('Telegram bot listener restarted after an error.')
            wait(10)


def start_worker():
    global _worker, _bot
    from .channels import email_configured, telegram_configured
    from django.conf import settings
    with _lock:
        if (email_configured() and settings.EMAIL_NOTIFICATIONS_ENABLED) or (telegram_configured() and settings.TELEGRAM_NOTIFICATIONS_ENABLED):
            if not (_worker and _worker.is_alive()):
                _worker = threading.Thread(target=_run, name='ssb-channel-delivery', daemon=True)
                _worker.start()
        if telegram_configured() and settings.TELEGRAM_NOTIFICATIONS_ENABLED and not (_bot and _bot.is_alive()):
            _bot = threading.Thread(target=_bot_loop, name='ssb-telegram-bot', daemon=True)
            _bot.start()


def start_after_commit():
    transaction.on_commit(start_worker)
