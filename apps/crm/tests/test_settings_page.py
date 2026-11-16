from django.test import override_settings
from django.urls import reverse

from apps.core.models import WorkspaceSettings
from apps.core.testing import CompanyTestCase


class SettingsPageTests(CompanyTestCase):
    def payload(self, **changes):
        ws = WorkspaceSettings.load()
        data = {'company_name': ws.company_name, 'default_currency': 'UZS', 'date_format': ws.date_format,
                'company_share_percent': ws.company_share_percent, 'archive_max_mb': ws.archive_max_mb,
                'upload_max_mb': ws.upload_max_mb, 'allowed_extensions': ', '.join(ws.extensions),
                'reminder_days_before': ws.reminder_days_before, 'require_project_start_approval': 'on'}
        data.update(changes)
        return data

    def test_status_is_honest_and_written_for_people(self):
        self.login(self.founder)
        page = self.client.get(reverse('crm:settings'))
        self.assertContains(page, 'Ulanmagan', count=2)
        self.assertNotContains(page, 'Ulangan<')
        for leaked in ('>False<', 'apps/notifications', 'EMAIL_*', 'notify()'):
            self.assertNotContains(page, leaked)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')
    def test_mail_backend_alone_does_not_claim_verified_connection(self):
        self.login(self.founder)
        self.assertNotContains(self.client.get(reverse('crm:settings')), 'Ulangan<')

    def test_values_are_shown_and_saved(self):
        self.login(self.founder)
        response = self.client.post(reverse('crm:settings'), self.payload(company_name='Yangi nom'))
        self.assertRedirects(response, reverse('crm:settings'))
        self.assertContains(self.client.get(reverse('crm:settings')), 'Yangi nom')

    def test_rejected_values_are_not_shown_as_current(self):
        self.login(self.founder)
        response = self.client.post(reverse('crm:settings'), self.payload(upload_max_mb=999, allowed_extensions='pdf, exe'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Xavfli fayl turlariga')
        self.assertEqual(response.context['current'].upload_max_mb, WorkspaceSettings.load().upload_max_mb)

    def test_employee_cannot_open_settings(self):
        self.login(self.dev)
        self.assertEqual(self.client.get(reverse('crm:settings')).status_code, 403)
