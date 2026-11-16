import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import uuid
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from apps.accounts.models import Role, User
from apps.enterprise.models import ProjectArchive


@skipUnless(os.environ.get('SSB_ARCHIVE_BROWSER') == '1', 'Set SSB_ARCHIVE_BROWSER=1 for the real archive code/upload/download flow')
@override_settings(REQUIRE_MALWARE_SCAN=False, MALWARE_SCANNER='')
class ArchiveBrowserTests(StaticLiveServerTestCase):
    host = '127.0.0.1'

    def test_founder_code_shared_upload_employee_unlock_and_mobile(self):
        password = secrets.token_urlsafe(24)
        founder = User.objects.create_user(username='archive_qa_founder', password=password,
                                           role=Role.objects.create(name='Archive QA founder', rank=0, is_owner=True))
        employee = User.objects.create_user(username='archive_qa_employee', password=password,
                                            role=Role.objects.create(name='Archive QA staff', rank=60))
        root = settings.BASE_DIR / '.setup' / ('archive-browser-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        media = tempfile.mkdtemp(prefix='ssb-archive-browser-')
        from apps.enterprise.tests.test_archive_access import zip_bytes
        upload_bytes = zip_bytes('Archive browser verification')
        (root / 'archive-qa.zip').write_bytes(upload_bytes)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        payload = {'server': self.live_server_url, 'founder': founder.username, 'employee': employee.username,
                   'password': password, 'port': port, 'root': str(root), 'code': 'browser-archive-' + secrets.token_hex(4),
                   'projectName': 'Brauzer sinov loyihasi', 'uploadFile': str(root / 'archive-qa.zip')}
        node = os.environ.get('SSB_NODE') or shutil.which('node')
        self.assertTrue(node)
        try:
            with override_settings(PRIVATE_MEDIA_ROOT=media):
                result = subprocess.run([node, str(settings.BASE_DIR / 'tools/qa/archive-browser.cjs')], input=json.dumps(payload),
                                        text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:] + result.stdout[-1000:])
            self.assertEqual((root / 'downloads' / 'archive-qa.zip').read_bytes(), upload_bytes)
            self.assertEqual(ProjectArchive.objects.count(), 0)
            evidence = json.loads(result.stdout.strip().splitlines()[-1])
            (settings.BASE_DIR / '.setup/archive-browser-result.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        finally:
            shutil.rmtree(media, ignore_errors=True)
            shutil.rmtree(root / 'profile', ignore_errors=True)
            shutil.rmtree(root / 'downloads', ignore_errors=True)
