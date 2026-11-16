from datetime import timedelta
from io import BytesIO
import zipfile
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.core.testing import CompanyTestCase
from apps.accounts.models import User
from apps.enterprise import operations
from apps.enterprise.models import ProjectArchive, WorkShift, PerformanceReview


class EnterpriseOperationsTests(CompanyTestCase):
    def test_weekly_batch_is_idempotent_and_only_creates_unapproved_drafts(self):
        from django.core.management import call_command
        from io import StringIO
        from apps.enterprise.models import ReviewApproval, WeeklyEvaluation
        output=StringIO()
        call_command('generate_weekly_reviews',actor=self.founder.username,stdout=output)
        count=WeeklyEvaluation.objects.count();self.assertGreater(count,0)
        call_command('generate_weekly_reviews',actor=self.founder.username,stdout=output)
        self.assertEqual(WeeklyEvaluation.objects.count(),count)
        self.assertEqual(ReviewApproval.objects.count(),0)
        self.assertEqual(self.dev.ledger_entries.count(),0)

    @override_settings(REQUIRE_MALWARE_SCAN=False,MALWARE_SCANNER='')
    def test_document_mime_structure_and_binary_text_are_rejected(self):
        buffer=BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('not-a-document.txt','hello')
        with self.assertRaises(ValidationError):operations.inspect_upload(SimpleUploadedFile('fake.docx',buffer.getvalue()))
        with self.assertRaises(ValidationError):operations.inspect_upload(SimpleUploadedFile('fake.txt',b'MZ\x00binary'))
    @override_settings(PERFORMANCE_AI_ENDPOINT='https://ai-gateway.example/review',PERFORMANCE_AI_KEY='test-only-key')
    def test_configured_ai_receives_metrics_without_employee_or_financial_identity(self):
        import json
        from unittest.mock import patch, MagicMock
        today=timezone.localdate()
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'analysis':'Muddatlarni oldindan rejalashtiring.'}).encode()
        with patch('apps.enterprise.operations.urlopen',return_value=response) as gateway:
            review=operations.create_review(self.founder,self.dev,today,today,'Evidence based manager feedback',80,90)
        self.assertEqual(review.analysis_source,'configured_ai')
        payload=json.loads(gateway.call_args.args[0].data)
        self.assertEqual(set(payload),{'metrics','task'})
        self.assertNotIn(self.dev.username,json.dumps(payload))
        self.assertFalse(hasattr(review,'reviewapproval'))
        self.assertEqual(self.dev.ledger_entries.count(),0)

    @override_settings(REQUIRE_MALWARE_SCAN=True,MALWARE_SCANNER='')
    def test_production_upload_fails_closed_without_malware_scanner(self):
        with self.assertRaises(ValidationError):operations.inspect_upload(SimpleUploadedFile('work.txt',b'Work source'))

    def test_partial_review_scores_are_rejected_in_form(self):
        from apps.enterprise.forms import ReviewForm
        today=timezone.localdate()
        form=ReviewForm({'employee':self.dev.pk,'period_start':str(today),'period_end':str(today),
                         'feedback':'Manager assessment with source','quality_score':'80'},actor=self.founder)
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_quick_actions_respect_server_permissions_and_have_real_routes(self):
        self.login(self.dev)
        response=self.client.get(reverse('enterprise:overview'))
        self.assertFalse(any(item['url']==reverse('crm:employee_create') for item in response.context['quick_actions']))
        self.login(self.founder)
        response=self.client.get(reverse('enterprise:overview'))
        for item in response.context['quick_actions']:
            self.assertEqual(self.client.get(item['url']).status_code,200,item['label'])
    def test_schedule_overlap_and_employee_privacy(self):
        start=timezone.now()+timedelta(days=1)
        shift=operations.save_shift(self.founder,self.dev,start,start+timedelta(hours=8),'Ofis')
        with self.assertRaises(ValidationError):operations.save_shift(self.founder,self.dev,start+timedelta(hours=1),start+timedelta(hours=2),'Ofis')
        self.login(self.designer)
        response=self.client.get(reverse('enterprise:schedule'))
        self.assertEqual(list(response.context['shifts']),[])
        self.assertIn(self.client.post(reverse('enterprise:cancel_shift',args=[shift.pk])).status_code,[403,404])

    @override_settings(REQUIRE_MALWARE_SCAN=False,MALWARE_SCANNER='')
    def test_archive_hash_code_and_path_validation(self):
        policy=operations.set_archive_code(self.founder,'secret-code-2026')
        self.assertNotEqual(policy.access_hash,'secret-code-2026')
        buffer=BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:archive.writestr('../escape.txt','bad')
        with self.assertRaises(ValidationError):operations.inspect_upload(SimpleUploadedFile('file.zip',buffer.getvalue()))
        with self.assertRaises(ValidationError):operations.inspect_upload(SimpleUploadedFile('file.exe',b'bad'))

    def test_cofounder_single_account_and_inactive_role_ends_session(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():User.objects.create(username='second_cofounder',role=self.cofounder.role)
        self.login(self.dev);role=self.dev.role;role.is_active=False;role.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(reverse('enterprise:overview')).status_code,302)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_performance_never_changes_finance_and_requires_approval(self):
        today=timezone.localdate()
        review=operations.create_review(self.founder,self.dev,today-timedelta(days=7),today,'Ish sifati bo‘yicha rahbar izohi')
        self.assertEqual(review.analysis_source,'rules')
        self.login(self.dev);self.assertNotContains(self.client.get(reverse('enterprise:performance_history')),review.feedback)
        operations.approve_review(self.founder,review)
        self.assertContains(self.client.get(reverse('enterprise:performance_history')),review.feedback)
        self.assertEqual(self.dev.ledger_entries.count(),0)

    def test_all_enterprise_pages_render_for_founder(self):
        self.login(self.founder)
        for page in ['overview','finance','balance','rules','schedule','archives','performance','reports','search','desktop']:
            response=self.client.get(reverse('enterprise:'+page))
            self.assertEqual(response.status_code,200,(page,response.status_code))
            import os
            if os.environ.get('SSB_CAPTURE_ENTERPRISE'):
                from pathlib import Path
                from django.conf import settings
                root=Path(settings.BASE_DIR)/'.setup'/'enterprise-audit';root.mkdir(parents=True,exist_ok=True)
                (root/f'{page}.html').write_bytes(response.content)

    @override_settings(REQUIRE_MALWARE_SCAN=False,MALWARE_SCANNER='')
    def test_archive_download_requires_code_and_rotation_invalidates_grant(self):
        import shutil, tempfile, uuid
        from apps.core.testing import unlocked_archive_request
        directory=tempfile.mkdtemp(prefix='ssb-archive-ops-')
        try:
            with override_settings(PRIVATE_MEDIA_ROOT=directory):
                operations.set_archive_code(self.founder,'secret-archive-2026')
                from apps.enterprise.tests.test_archive_access import project
                archive=operations.upload_archive(unlocked_archive_request(self.dev),self.project.name,project(),uuid.uuid4())
                self.login(self.dev)
                url=reverse('enterprise:archive_download',args=[archive.pk])
                self.assertEqual(self.client.get(url).status_code,302)
                self.client.post(reverse('enterprise:archive_unlock'),{'code':'secret-archive-2026'})
                self.assertEqual(self.client.get(url).status_code,200)
                from apps.enterprise.archive_access import CHALLENGE_KEY
                response=self.client.post(url,{'answer':str(self.client.session[CHALLENGE_KEY]['answer'])})
                self.assertEqual(response.status_code,200)
                # Release the streamed file without closing TestCase's atomic DB connection.
                for close in response._resource_closers:
                    close()
                operations.set_archive_code(self.founder,'changed-archive-2026')
                self.assertEqual(self.client.post(url,{'answer':'1'}).status_code,403)
                self.login(self.outsider)
                self.assertEqual(self.client.post(url,{'answer':'1'}).status_code,403)
        finally:
            shutil.rmtree(directory,ignore_errors=True)

    def test_role_deactivation_and_cofounder_form_validation(self):
        from apps.accounts.forms import EmployeeForm
        form=EmployeeForm(actor=self.founder)
        form.cleaned_data={'role':self.cofounder.role}
        with self.assertRaises(ValidationError):form.clean_role()
        self.login(self.founder)
        response=self.client.post(reverse('crm:role_status',args=[self.dev.role_id]))
        self.assertEqual(response.status_code,302)
        self.dev.role.refresh_from_db();self.assertFalse(self.dev.role.is_active)
        self.assertEqual(self.client.post(reverse('crm:role_status',args=[self.founder.role_id])).status_code,403)

    def test_performance_report_exports_approved_source_only(self):
        today=timezone.localdate()
        review=operations.create_review(self.founder,self.dev,today-timedelta(days=7),today,'Sifat va hissa tekshirildi',80,90)
        self.assertIn('formula',review.metrics)
        self.login(self.founder)
        response=self.client.get(reverse('enterprise:reports'),{'report':'performance','export':'csv'})
        self.assertNotIn(self.dev.display_name,response.content.decode())
        operations.approve_review(self.founder,review)
        response=self.client.get(reverse('enterprise:reports'),{'report':'performance','export':'csv'})
        self.assertIn(self.dev.display_name,response.content.decode())

    def test_widget_permissions_validated_on_server(self):
        self.login(self.dev)
        self.assertEqual(self.client.post(reverse('enterprise:layout'),{'layout':'[{"key":"finance","size":"wide"}]'}).status_code,403)
