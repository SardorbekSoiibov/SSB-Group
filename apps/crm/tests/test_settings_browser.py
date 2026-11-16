import json
import os
import secrets
import shutil
import socket
import subprocess
import uuid
from datetime import timedelta
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Role, User
from apps.core.models import WorkspaceSettings
from apps.crm.models import Project, Task
from apps.enterprise import weekly_rating as wr
from apps.enterprise.models import WeeklyPlace, WeeklyRating
from apps.notifications.models import Notification


@skipUnless(os.environ.get('SSB_SETTINGS_BROWSER') == '1', 'Set SSB_SETTINGS_BROWSER=1 for the settings modal and shared confirmation')
class SettingsBrowserTests(StaticLiveServerTestCase):
    host = '127.0.0.1'

    def test_settings_modal_and_shared_confirmation(self):
        password = secrets.token_urlsafe(24)
        owner = User.objects.create_user(username='settings_qa', password=password,
                                         role=Role.objects.create(name='Settings QA founder', rank=0, is_owner=True))
        staff_role = Role.objects.create(name='Settings QA staff', rank=60)
        doomed = User.objects.create_user(username='erase_qa_employee', first_name='Ochiriladi', last_name='Xodim', role=staff_role)
        restricted_password = secrets.token_urlsafe(24)
        restricted = User.objects.create_user(username='no_capture_qa', password=restricted_password, role=staff_role, allow_screenshots=False)
        for number in (1, 2):
            Notification.objects.create(recipient=owner, kind='announcement', title=f'QA xabar {number}')
        past = WeeklyRating.objects.create(publish_on=wr.current_week() - timedelta(days=7), prize='Yangi noutbuk', announced=True)
        WeeklyPlace.objects.create(rating=past, employee=restricted, place=1)
        WeeklyPlace.objects.create(rating=past, employee=doomed, place=2)
        rating_project = Project.objects.create(code='QA-RATE', name='Reyting loyihasi', manager=owner, created_by=owner)
        Task.objects.create(project=rating_project, title='Qabul qilingan QA ish', assignee=restricted, status=Task.Status.APPROVED,
                            approved_at=timezone.now(), created_by=owner)
        doomed_project = Project.objects.create(code='QA-DEL', name='Ochiriladigan loyiha', description='QA tavsifi', manager=owner, created_by=owner)
        Task.objects.create(project=doomed_project, title='QA vazifa', assignee=restricted, created_by=owner)
        root = settings.BASE_DIR / '.setup' / ('settings-browser-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        Image.new('RGB', (500, 500), '#2f7fd6').save(root / 'photo-one.png')
        Image.new('RGB', (500, 300), '#30a46c').save(root / 'photo-two.png')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        payload = {'server': self.live_server_url, 'username': owner.username, 'password': password, 'port': port, 'root': str(root),
                   'settingsURL': reverse('crm:settings'), 'rolesURL': reverse('crm:roles'),
                   'desktopURL': reverse('enterprise:desktop'), 'employeeURL': reverse('crm:employee_detail', args=[doomed.pk]),
                   'employeesURL': reverse('crm:employees'), 'ratingURL': reverse('enterprise:rating'), 'performanceURL': reverse('enterprise:performance'), 'projectURL': doomed_project.get_absolute_url(), 'projectsURL': reverse('crm:projects'),
                   'profileURL': reverse('crm:profile'), 'notificationsURL': reverse('crm:notifications'), 'scheduleURL': reverse('enterprise:schedule'),
                   'photoOne': str(root / 'photo-one.png'), 'photoTwo': str(root / 'photo-two.png'), 'staffId': restricted.pk, 'staffUsername': restricted.username,
                   'restrictedUser': restricted.username, 'restrictedPassword': restricted_password}
        node = os.environ.get('SSB_NODE') or shutil.which('node')
        self.assertTrue(node)
        try:
            result = subprocess.run([node, str(settings.BASE_DIR / 'tools/qa/settings-browser.cjs')], input=json.dumps(payload),
                                    text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=240)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:] + result.stdout[-1000:])
            self.assertEqual(WorkspaceSettings.load().company_name, 'Sinov Kompaniyasi')
            self.assertEqual(WorkspaceSettings.load().upload_max_mb, 15)
            self.assertFalse(User.objects.filter(pk=doomed.pk).exists())
            self.assertFalse(Project.objects.filter(pk=doomed_project.pk).exists())
            self.assertFalse(Notification.objects.filter(recipient=owner).exists())
            staff_role.refresh_from_db()
        finally:
            shutil.rmtree(root / 'profile', ignore_errors=True)
