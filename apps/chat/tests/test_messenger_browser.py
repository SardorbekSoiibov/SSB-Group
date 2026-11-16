import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import uuid
from datetime import timedelta
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Role, User
from apps.chat.models import Message, Presence


@skipUnless(os.environ.get('SSB_MESSENGER_BROWSER') == '1', 'Set SSB_MESSENGER_BROWSER=1 to click every messenger control in Edge')
class MessengerBrowserTests(StaticLiveServerTestCase):
    host = '127.0.0.1'

    def test_every_control_in_a_real_browser(self):
        role = Role.objects.create(name='Messenger QA', rank=60)
        password = secrets.token_urlsafe(24)
        user = User.objects.create_user(username='messenger_qa', password=password, role=role, first_name='Aziz', last_name='Karimov')
        peer = User.objects.create_user(username='messenger_peer', role=role, first_name='Dilnoza', last_name='Rahimova', is_verified=True)
        other = User.objects.create_user(username='messenger_other', role=role, first_name='Jasur', last_name='Tursunov', job_title='Bosh muhandis',
                                         last_login=timezone.now() - timedelta(hours=2))
        old = Message.objects.create(sender=peer, recipient=user, body='Qadimgi shartnoma haqida', read_at=timezone.now())
        Message.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))
        for number in range(60):
            mine = number % 3
            row = Message.objects.create(sender=user if mine else peer, recipient=peer if mine else user,
                                         body=f'Oraliq xabar {number}', read_at=timezone.now())
            if number < 15:
                Message.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=2))
        newest = Message.objects.create(sender=peer, recipient=user, body='Yangi o‘qilmagan xabar')
        Presence.objects.create(user=peer, last_seen=timezone.now() + timedelta(minutes=10))
        root = settings.BASE_DIR / '.setup' / ('messenger-browser-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        Image.new('RGB', (640, 360), '#2f7fd6').save(root / 'rasm.png')
        media = tempfile.mkdtemp(prefix='ssb-messenger-browser-')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        payload = {'server': self.live_server_url, 'username': user.username, 'password': password, 'peer': peer.pk,
                   'other': other.pk, 'port': port, 'root': str(root), 'image': str(root / 'rasm.png'), 'expectedId': newest.pk,
                   'expectedTime': timezone.localtime(newest.created_at).strftime('%H:%M')}
        node = os.environ.get('SSB_NODE') or shutil.which('node')
        self.assertTrue(node)
        try:
            with override_settings(PRIVATE_MEDIA_ROOT=media):
                result = subprocess.run([node, str(settings.BASE_DIR / 'tools/qa/messenger-browser.cjs')], input=json.dumps(payload),
                                        text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=150)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:] + result.stdout[-1000:])
            evidence = json.loads(result.stdout.strip().splitlines()[-1])
            (settings.BASE_DIR / '.setup/messenger-browser-result.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        finally:
            shutil.rmtree(media, ignore_errors=True)
            shutil.rmtree(root / 'profile', ignore_errors=True)
