"""Private per-user channels. Credentials remain in environment; requests never log them."""
import hashlib
import json
import re
import secrets
import ssl
from datetime import timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import get_connection, send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from .models import ChannelCheck, ExternalDelivery, TelegramConnection, TelegramCursor
from .configuration import telegram_token


def email_configured():
    return (settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'
            and bool(settings.EMAIL_HOST and settings.EMAIL_HOST != 'localhost')
            and not (settings.EMAIL_USE_SSL and settings.EMAIL_USE_TLS))


def telegram_configured():
    return bool(re.fullmatch(r'\d+:[A-Za-z0-9_-]+', telegram_token()))


def fingerprint(channel):
    data = [telegram_token()] if channel == 'telegram' else [settings.EMAIL_BACKEND, settings.EMAIL_HOST, settings.EMAIL_PORT, settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD, settings.EMAIL_USE_TLS, settings.EMAIL_USE_SSL, settings.DEFAULT_FROM_EMAIL]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def status(channel):
    configured = email_configured() if channel == 'email' else telegram_configured()
    checked = ChannelCheck.objects.filter(channel=channel, fingerprint=fingerprint(channel), successful=True).first()
    return {'configured': configured, 'connected': bool(configured and checked), 'checked_at': checked.checked_at if checked else None}


def telegram_api_error(code):
    messages = {
        401: 'Telegram tokenni qabul qilmadi. BotFather bergan haqiqiy tokenni qayta nusxalang.',
        404: 'Telegram bot topilmadi. Token to‘liq va to‘g‘ri kiritilganini tekshiring.',
        403: 'Bot sizga yoza olmayapti. Telegramda botni blokdan chiqaring va Start bosing.',
        409: 'Bot boshqa dastur yoki webhook bilan band. Botning boshqa ulanishini tekshirish kerak.',
        429: 'Telegram vaqtincha juda ko‘p so‘rov oldi. Birozdan keyin qayta urinib ko‘ring.',
    }
    return ValidationError(messages.get(code, 'Telegram serveri vaqtincha javob bermayapti. Keyinroq qayta urinib ko‘ring.'), code=f'telegram_http_{code}')


def telegram_call(method, payload=None, *, token=None, timeout=10):
    token = token if token is not None else telegram_token()
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', token):
        raise ValidationError('Telegram bot tokeni sozlanmagan.')
    request = Request(f'https://api.telegram.org/bot{token}/{method}',
                      data=json.dumps(payload or {}).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(2000001)
        if len(raw) > 2000000:
            raise ValueError
    except HTTPError as error:
        # Never expose the URL or provider response: the URL contains the token.
        raise telegram_api_error(error.code) from None
    except (TimeoutError, URLError, ssl.SSLError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        if isinstance(reason, ssl.SSLError):
            raise ValidationError('Server Telegramning xavfsizlik sertifikatini tekshira olmadi. Server vaqti va sertifikatlarini tekshirish kerak.', code='telegram_tls') from None
        if isinstance(reason, TimeoutError):
            raise ValidationError('Telegramdan javob kelishi cho‘zildi. Internet aloqasini tekshirib, qayta urinib ko‘ring.', code='telegram_timeout') from None
        raise ValidationError('Server Telegramga internet orqali chiqa olmayapti. Serverning internet yoki proksi ulanishini tekshirish kerak. Bu token tekshiruvidan oldingi ulanish xatosi.', code='telegram_network') from None
    except Exception:
        raise ValidationError('Telegram javobini o‘qib bo‘lmadi. Keyinroq qayta urinib ko‘ring.', code='telegram_response') from None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
        if not data.get('ok'):
            raise telegram_api_error(data.get('error_code', 500))
        return data['result']
    except ValidationError:
        raise
    except (ValueError, TypeError, KeyError):
        raise ValidationError('Telegramdan noto‘g‘ri javob keldi. Keyinroq qayta urinib ko‘ring.', code='telegram_response') from None


def telegram_upload(method, fields, file_field, filename, content, *, timeout=60):
    """Fayl (masalan, rasm) bilan Telegram so'rovi — multipart/form-data. Xatolar telegram_call bilan bir xil."""
    token = telegram_token()
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', token):
        raise ValidationError('Telegram bot tokeni sozlanmagan.')
    boundary = 'ssb' + secrets.token_hex(16)
    parts = []
    for name, val in fields.items():
        if val is None:
            continue
        val = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{val}\r\n'.encode())
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', filename)[:80] or 'file'
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{safe_name}"\r\n'
                 f'Content-Type: application/octet-stream\r\n\r\n'.encode() + content + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    request = Request(f'https://api.telegram.org/bot{token}/{method}', data=b''.join(parts),
                      headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read(2000001))
    except HTTPError as error:
        raise telegram_api_error(error.code) from None
    except Exception:
        raise ValidationError('Telegramga fayl yuborib bo‘lmadi. Internet aloqasini tekshiring.', code='telegram_network') from None
    if not isinstance(data, dict) or not data.get('ok'):
        raise telegram_api_error((data or {}).get('error_code', 500) if isinstance(data, dict) else 500)
    return data['result']


def check_channel(channel):
    successful = False
    try:
        if channel == 'email':
            if not email_configured():
                raise ValidationError('SMTP serveri va xavfsiz ulanish sozlamalarini kiriting.')
            with get_connection(timeout=10):
                pass
        else:
            bot = telegram_call('getMe')
            if not bot.get('is_bot'):
                raise ValidationError('Bot tasdiqlanmadi.')
        successful = True
    except ValidationError:
        raise
    except Exception:
        raise ValidationError('Pochta serveriga ulanib bo‘lmadi. Server, port va kirish ma’lumotlarini tekshiring.') from None
    finally:
        ChannelCheck.objects.update_or_create(channel=channel, defaults={'fingerprint': fingerprint(channel), 'successful': successful})


def message_url(notification):
    base = settings.SITE_URL.rstrip('/')
    return base + notification.safe_url if urlsplit(base).scheme in ['http', 'https'] else ''


def send_email(user, title, body):
    if not email_configured() or not user.email:
        raise ValidationError('SMTP sozlamalari yoki profilingizdagi email manzili yetishmayapti.')
    validate_email(user.email)
    if send_mail(title.replace('\r', ' ').replace('\n', ' ')[:200], body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False) != 1:
        raise ValidationError('Email yuborilmadi.')


KIND_ICONS = {'task_assigned': '📌', 'deadline_soon': '⏰', 'overdue': '🔴', 'comment': '💬', 'submitted': '📤',
              'reviewed': '✅', 'approval': '🟡', 'project_status': '📁', 'inquiry': '📨', 'announcement': '📣', 'equipment': '💻'}


def telegram_notification(note):
    """Zamonaviy ko'rinish: belgi + qalin sarlavha, matn, pastda «Ochish» tugmasi (havola matn emas, tugma)."""
    import html
    from .bot import public_site
    title = html.escape(note.title, quote=False)
    body = html.escape(note.body or '', quote=False)
    text = f'{KIND_ICONS.get(note.kind, "🔔")} <b>{title}</b>' + (f'\n\n{body}' if body else '') + f'\n\n<i>{html.escape(note.get_kind_display(), quote=False)} · SSB Boshqaruv</i>'
    site = public_site()
    rows = [[{'text': '🔗 Ochish', 'url': site + note.safe_url}]] if site else None
    return text, rows


def send_telegram(user, text, rows=None):
    connection = TelegramConnection.objects.filter(user=user, enabled=True, chat_id__isnull=False, bot_fingerprint=fingerprint('telegram')).first()
    if not connection:
        raise ValidationError('Avval shaxsiy Telegram hisobingizni botga bog‘lang.')
    payload = {'chat_id': connection.chat_id, 'text': text[:4096], 'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': True}}
    if rows:
        payload['reply_markup'] = {'inline_keyboard': rows}
    try:
        telegram_call('sendMessage', payload)
    except ValidationError as error:
        if not rows or error.code != 'telegram_http_400':
            raise
        payload.pop('reply_markup')  # Tugma havolasi rad etilsa ham xabar yetib borsin.
        telegram_call('sendMessage', payload)


def create_link(user):
    if not telegram_configured():
        raise ValidationError('Avval bot tokenini sozlang.')
    bot = telegram_call('getMe')
    username = bot.get('username', '')
    if not re.fullmatch(r'[A-Za-z0-9_]+', username):
        raise ValidationError('Bot nomi aniqlanmadi.')
    token = secrets.token_urlsafe(24)
    TelegramConnection.objects.update_or_create(user=user, defaults={'link_hash': hashlib.sha256(token.encode()).hexdigest(), 'expires_at': timezone.now()+timedelta(minutes=10), 'enabled': False, 'chat_id': None, 'bot_fingerprint': fingerprint('telegram')})
    return f'https://t.me/{username}?start={token}'


POLL_LOCK = 73910249  # Bitta bot — bitta getUpdates o'quvchi (aks holda Telegram 409 qaytaradi).


def poll_once(timeout=0):
    """Telegram yangiliklarini o'qib, har birini bot.handle_update orqali qayta ishlaydi.

    Har bir yangilanishdan keyin offset saqlanadi: bitta xato xabar botni to'xtatib qo'ymaydi.
    """
    from . import bot
    cursor, _ = TelegramCursor.objects.get_or_create(pk=1)
    if cursor.bot_fingerprint != fingerprint('telegram'):
        cursor.offset, cursor.bot_fingerprint = 0, fingerprint('telegram')
        cursor.save(update_fields=['offset', 'bot_fingerprint'])
    updates = telegram_call('getUpdates', {'offset': cursor.offset, 'timeout': timeout, 'limit': 100,
                                           'allowed_updates': bot.ALLOWED_UPDATES}, timeout=timeout + 15)
    for update in updates:
        try:
            with transaction.atomic():
                bot.handle_update(update)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Telegram yangilanishini qayta ishlashda xato')
        cursor.offset = max(cursor.offset, update['update_id'] + 1)
        cursor.save(update_fields=['offset'])
    return len(updates)


def poll_telegram():
    """Bir martalik tekshiruv. Fonda doimiy o'quvchi ishlayotgan bo'lsa, u bilan to'qnashmaslik uchun hech narsa qilmaydi."""
    from django.db import connection
    with connection.cursor() as c:
        c.execute('SELECT pg_try_advisory_lock(%s)', [POLL_LOCK])
        if not c.fetchone()[0]:
            return 0
    try:
        return poll_once(0)
    finally:
        with connection.cursor() as c:
            c.execute('SELECT pg_advisory_unlock(%s)', [POLL_LOCK])


def enqueue(notification):
    user = notification.recipient
    # Chat messages stay inside the app; their confidential text is not copied to external channels.
    if notification.kind == 'chat_message':
        return
    channels = []
    if email_configured() and settings.EMAIL_NOTIFICATIONS_ENABLED and user.email:
        channels.append('email')
    if telegram_configured() and settings.TELEGRAM_NOTIFICATIONS_ENABLED and TelegramConnection.objects.filter(user=user, enabled=True, bot_fingerprint=fingerprint('telegram')).exists():
        channels.append('telegram')
    for channel in channels:
        ExternalDelivery.objects.get_or_create(notification=notification, channel=channel, defaults={'next_attempt_at': timezone.now()})
    if channels:
        from .runtime import start_after_commit
        start_after_commit()


def deliver_pending(limit=50):
    sent = 0
    for _ in range(limit):
        with transaction.atomic():
            job = (ExternalDelivery.objects.select_for_update(skip_locked=True).filter(status='pending', next_attempt_at__lte=timezone.now())
                   .select_related('notification__recipient').order_by('pk').first())
            if not job:
                break
            note, user = job.notification, job.notification.recipient
            enabled = settings.EMAIL_NOTIFICATIONS_ENABLED if job.channel == 'email' else settings.TELEGRAM_NOTIFICATIONS_ENABLED
            if not enabled or not user.is_active or note.kind in user.muted_notifications:
                job.status = 'cancelled'
                job.save()
                continue
            job.attempts += 1
            try:
                if job.channel == 'email':
                    send_email(user, note.title, f'{note.title}\n\n{note.body}\n\n{message_url(note)}')
                else:
                    send_telegram(user, *telegram_notification(note))
                job.status, job.sent_at, job.error_code = 'sent', timezone.now(), ''
                sent += 1
            except Exception as error:
                job.error_code = type(error).__name__[:100]
                job.status = 'failed' if job.attempts >= 5 else 'pending'
                job.next_attempt_at = timezone.now()+timedelta(minutes=2**job.attempts)
            job.save()
    return sent
