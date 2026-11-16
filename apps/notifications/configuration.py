"""Live, server-only credentials in the existing ignored .env file."""
import os
import re
import tempfile
from pathlib import Path
import environ
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction


def value(name, default=''):
    class LocalEnv(environ.Env):
        ENVIRON = {}
    path = Path(settings.BASE_DIR) / '.env'
    if path.exists():
        LocalEnv.read_env(path, overwrite=True)
    return LocalEnv.ENVIRON.get(name, default)


def telegram_token():
    return value('TELEGRAM_BOT_TOKEN', settings.TELEGRAM_BOT_TOKEN)


@transaction.atomic
def save_telegram(token, username):
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', token) or not re.fullmatch(r'[A-Za-z0-9_]+', username):
        raise ValidationError('Token noto‘g‘ri. BotFather yuborgan tokenni to‘liq nusxalang.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(73910248)')
    path = Path(settings.BASE_DIR) / '.env'
    original = path.read_text(encoding='utf-8') if path.exists() else ''
    lines = original.splitlines()
    for key, val in {'TELEGRAM_BOT_TOKEN': token, 'TELEGRAM_BOT_USERNAME': username}.items():
        pattern = re.compile(r'^\s*(?:export\s+)?'+key+r'\s*=')
        lines = [line for line in lines if not pattern.match(line)]
        lines.append(f'{key}={val}')
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.env-', delete=False) as temp:
            temp.write('\n'.join(lines)+'\n')
            temp_path = temp.name
        os.replace(temp_path, path)
    except OSError:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise ValidationError('Token saqlanmadi. Serverda sozlamalar fayliga yozish ruxsatini tekshiring.') from None
