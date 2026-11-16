"""Opt-in test of the packaged EXE against a temporary Django/PostgreSQL test server."""
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
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.crm.models import Project, Task
from apps.enterprise import operations
from apps.core.testing import unlocked_archive_request
from apps.enterprise.tests.test_archive_access import zip_bytes


@skipUnless(os.environ.get('SSB_WINDOWS_JOURNEY')=='1','Set SSB_WINDOWS_JOURNEY=1 to launch the packaged Windows app')
class WindowsJourneyTests(StaticLiveServerTestCase):
    host='127.0.0.1'
    @override_settings(REQUIRE_MALWARE_SCAN=False,MALWARE_SCANNER='')
    def test_real_packaged_desktop_and_web_share_changes_and_sessions(self):
        role=Role.objects.create(name='QA Founder',rank=0,is_owner=True,dashboard='founder')
        password=secrets.token_urlsafe(24)
        owner=User.objects.create_user(username='qa_windows_founder',password=password,role=role)
        employee=User.objects.create_user(username='qa_windows_employee',role=Role.objects.create(name='QA Employee',rank=60))
        project=Project.objects.create(name='Shared Windows project',manager=owner,created_by=owner,status='in_progress')
        project.members.add(employee)
        task=Task.objects.create(project=project,title='Initial shared task',assignee=employee,created_by=owner)
        archive_code='temporary-archive-'+uuid.uuid4().hex
        operations.set_archive_code(owner,archive_code)
        archive=operations.upload_archive(unlocked_archive_request(owner),project.name,
            SimpleUploadedFile('qa-delivery.zip',zip_bytes('Verified project delivery')),uuid.uuid4())
        web_owner=User.objects.create_user(username='qa_windows_web_owner',role=role)
        client=Client();client.force_login(web_owner)
        client.get(reverse('crm:task_edit',args=[task.pk]))
        cookie='; '.join(f'{key}={value.value}' for key,value in client.cookies.items())
        node=os.environ.get('SSB_NODE') or shutil.which('node')
        self.assertTrue(node,'Node executable required for CDP journey test')
        executable=Path(os.environ.get('SSB_DESKTOP_EXE',settings.BASE_DIR/'desktop/release/win-unpacked/SSB Boshqaruv.exe'))
        self.assertTrue(executable.is_file(),'Build or install the real desktop application first')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        profile=settings.BASE_DIR/'.setup'/('windows-journey-'+uuid.uuid4().hex)
        profile.mkdir(parents=True,exist_ok=True)
        upload_file=profile/'desktop-delivery.zip';upload_file.write_bytes(zip_bytes('Real file uploaded through the Windows interface.'))
        data={'server':self.live_server_url,'exe':str(executable),'profile':str(profile),'port':port,'webUser':web_owner.pk,'desktopUser':owner.pk,
              'username':owner.username,'password':password,'webCookie':cookie,'webCSRF':client.cookies['csrftoken'].value,
              'task':task.pk,'project':project.pk,'employee':employee.pk,
              'editURL':reverse('crm:task_edit',args=[task.pk]),'archiveURL':reverse('enterprise:archive_download',args=[archive.pk]),'archiveCode':archive_code,'projectName':project.name,'uploadFile':str(upload_file)}
        try:
            result=subprocess.run([node,str(settings.BASE_DIR/'desktop/qa/journey.cjs')],input=json.dumps(data),text=True,capture_output=True,timeout=100)
            self.assertEqual(result.returncode,0,result.stderr[-3000:]+result.stdout[-1000:])
            evidence=json.loads(result.stdout.strip().splitlines()[-1]);self.assertTrue(evidence['webToDesktop']);self.assertTrue(evidence['desktopToWeb'])
            task.refresh_from_db();self.assertEqual(task.title,'Desktop session update')
            (settings.BASE_DIR/'.setup/windows-journey-result.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        finally:
            from apps.enterprise.models import ProjectArchive
            for item in ProjectArchive.objects.filter(project=project):item.file.delete(save=False)
