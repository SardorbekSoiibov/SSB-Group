import json
import os
import shutil
import socket
import subprocess
import uuid
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.test import Client, override_settings

from apps.accounts.models import User, Role
from apps.crm.models import Project, Task
from apps.enterprise import performance_system as ps


@skipUnless(os.environ.get('SSB_PERFORMANCE_BROWSER') == '1', 'Opt-in headless performance browser test')
@override_settings(PERFORMANCE_AI_ENDPOINT='', PERFORMANCE_AI_KEY='')
class PerformanceBrowserTests(StaticLiveServerTestCase):
    host = '127.0.0.1'

    def test_director_to_published_podium_and_mobile(self):
        os.environ['SSB_FOUNDER_PASSWORD'] = 'Browser-Test-Only-2026!'
        call_command('bootstrap_company', username='performance_qa', no_input=True, stdout=StringIO())
        owner = User.objects.get(username='performance_qa')
        staff = [User.objects.create(username=name, first_name=name.title(), role=Role.objects.get(name='Xodim')) for name in ['dev', 'designer', 'tester']]
        project = Project.objects.create(name='Browser test evidence', manager=owner, created_by=owner)
        start = ps.last_week()
        Task.objects.create(title='Haqiqiy QA vazifasi', project=project, assignee=staff[0], status='approved', deadline=start+timedelta(days=4),
                            approved_at=datetime.combine(start+timedelta(days=3), datetime.min.time(), ps.TZ))
        week = ps.prepare(owner, start)
        client = Client()
        client.force_login(owner)
        root = settings.BASE_DIR / '.setup' / ('performance-browser-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        data = {'server': self.live_server_url, 'session': client.cookies['sessionid'].value, 'root': str(root), 'port': port,
                'evaluations': list(week.evaluations.values_list('pk', flat=True))}
        result = subprocess.run([shutil.which('node'), str(settings.BASE_DIR/'tools/qa/performance-browser.cjs')], input=json.dumps(data),
                                capture_output=True, text=True, encoding='utf-8', timeout=100)
        self.assertEqual(result.returncode, 0, result.stderr[-2500:])
        week.refresh_from_db()
        self.assertTrue(week.published_at)
        self.assertEqual(week.ranking[0]['employee_id'], staff[0].pk)
        (settings.BASE_DIR/'.setup/performance-browser-result.json').write_text(json.dumps({'root': str(root), 'result': json.loads(result.stdout.strip())}), encoding='utf-8')
