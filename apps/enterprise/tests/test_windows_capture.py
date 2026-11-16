import json
import os
import secrets
import shutil
import socket
import subprocess
import uuid
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from apps.accounts.models import Role, User


@skipUnless(os.environ.get('SSB_WINDOWS_JOURNEY') == '1', 'Set SSB_WINDOWS_JOURNEY=1 to launch the packaged Windows app')
class WindowsCaptureProtectionTests(StaticLiveServerTestCase):
    host = '127.0.0.1'

    def test_windows_excludes_the_window_only_for_restricted_accounts(self):
        role = Role.objects.create(name='Capture QA', rank=60)
        password = secrets.token_urlsafe(24)
        blocked = User.objects.create_user(username='capture_blocked', password=password, role=role, allow_screenshots=False)
        allowed = User.objects.create_user(username='capture_allowed', password=password, role=role)
        executable = Path(os.environ.get('SSB_DESKTOP_EXE', settings.BASE_DIR / 'desktop/release/win-unpacked/SSB Boshqaruv.exe'))
        self.assertTrue(executable.is_file())
        root = settings.BASE_DIR / '.setup' / ('capture-qa-' + uuid.uuid4().hex)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        payload = {'server': self.live_server_url, 'exe': str(executable), 'root': str(root), 'port': port, 'password': password,
                   'blockedUser': blocked.username, 'allowedUser': allowed.username}
        node = os.environ.get('SSB_NODE') or shutil.which('node')
        try:
            result = subprocess.run([node, str(settings.BASE_DIR / 'desktop/qa/capture.cjs')], input=json.dumps(payload),
                                    text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:] + result.stdout[-500:])
            evidence = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertIs(evidence['blocked']['protected'], True, evidence)
            self.assertIs(evidence['allowed']['protected'], False, evidence)
            (settings.BASE_DIR / '.setup/windows-capture-result.json').write_text(json.dumps(evidence), encoding='utf-8')
        finally:
            shutil.rmtree(root, ignore_errors=True)
