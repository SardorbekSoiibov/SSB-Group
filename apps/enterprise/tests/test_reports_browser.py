from decimal import Decimal
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
from unittest import skipUnless
import uuid

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from openpyxl import load_workbook

from apps.accounts.models import Role, User
from apps.crm.models import Project
from apps.enterprise import finance


@skipUnless(os.environ.get('SSB_REPORT_BROWSER')=='1','Set SSB_REPORT_BROWSER=1 for real report controls/downloads')
class FinancialReportsBrowserTests(StaticLiveServerTestCase):
    host='127.0.0.1'

    def test_real_filters_sources_downloads_and_mobile(self):
        role=Role.objects.create(name='Report QA founder',rank=0,is_owner=True)
        password=secrets.token_urlsafe(24)
        owner=User.objects.create_user(username='report_browser_owner',password=password,role=role)
        reviewer=User.objects.create_user(username='report_browser_approver',role=role)
        employee=User.objects.create_user(username='report_browser_employee',role=Role.objects.create(name='Report QA staff',rank=60))
        project=Project.objects.create(name='Verified financial report project',manager=owner,created_by=owner)
        project.members.add(employee)
        agreement=finance.request_operation(owner,kind='agreement',amount='10000000',currency='UZS',
            description='Report browser agreement',project=project,idempotency_key=uuid.uuid4(),
            payload={'company_percent':'30','shares':[{'employee':employee.pk,'percent':'70'}]})
        self.assertEqual(agreement.status,'approved')  # Asoschining kelishuvi darhol kuchga kiradi
        finance.request_operation(owner,kind='receipt',amount='10000000',currency='UZS',
            description='Report browser bank receipt',project=project,idempotency_key=uuid.uuid4())
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        root=settings.BASE_DIR/'.setup'/('report-browser-'+uuid.uuid4().hex);root.mkdir(parents=True)
        payload={'server':self.live_server_url,'username':owner.username,'password':password,'port':port,
                 'employee':employee.pk,'project':project.pk,'root':str(root)}
        node=os.environ.get('SSB_NODE') or shutil.which('node');self.assertTrue(node)
        result=subprocess.run([node,str(settings.BASE_DIR/'tools/qa/reports-browser.cjs')],input=json.dumps(payload),
                              text=True,capture_output=True,timeout=100)
        self.assertEqual(result.returncode,0,result.stderr[-3000:]+result.stdout[-1000:])
        sheet=load_workbook(root/'ssb-earnings-UZS.xlsx').active
        self.assertEqual(Decimal(str(sheet.cell(2,2).value)),Decimal('7000000'))
        self.assertTrue((root/'ssb-earnings-UZS.pdf').read_bytes().startswith(b'%PDF-'))
        self.assertIn('7000000',(root/'ssb-earnings-UZS.csv').read_text(encoding='utf-8-sig'))
        evidence=json.loads(result.stdout.strip().splitlines()[-1])
        (settings.BASE_DIR/'.setup/financial-reports-browser-result.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
