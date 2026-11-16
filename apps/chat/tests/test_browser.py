import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import uuid
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from apps.accounts.models import Role, User
from apps.chat.models import Message


@skipUnless(os.environ.get('SSB_CHAT_BROWSER') == '1', 'Set SSB_CHAT_BROWSER=1 for two real browser sessions')
class ChatBrowserTests(StaticLiveServerTestCase):
    host = '127.0.0.1'

    def test_two_real_employees_chat_reconnect_and_mobile(self):
        password = secrets.token_urlsafe(24)
        role = Role.objects.create(name='Chat test staff', rank=60)
        users = [User.objects.create_user(username=name, password=password, role=role)
                 for name in ['chat_browser_one', 'chat_browser_two']]
        Message.objects.bulk_create([Message(sender=users[0], recipient=users[1], body=f'History {i}') for i in range(65)])
        ports = []
        for _ in users:
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0)); ports.append(listener.getsockname()[1])
        root = settings.BASE_DIR / '.setup' / ('chat-browser-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        node = os.environ.get('SSB_NODE') or shutil.which('node')
        self.assertTrue(node)
        payload = {'server': self.live_server_url, 'password': password, 'ports': ports,
                   'root': str(root), 'users': [{'id': user.pk, 'username': user.username} for user in users]}
        result = subprocess.run([node, str(settings.BASE_DIR/'tools/qa/chat-browser.cjs')],
                                input=json.dumps(payload), text=True, capture_output=True, timeout=140)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:] + result.stdout[-1000:])
        evidence = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(evidence['ok'])
        self.assertTrue(Message.objects.filter(body='Browser reply').exists())
        self.assertTrue(Message.objects.filter(body='After reconnect').exists())
        (settings.BASE_DIR/'.setup/chat-browser-result.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
