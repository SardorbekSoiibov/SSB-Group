from django.urls import reverse
from apps.core.testing import CompanyTestCase
from apps.core.currencies import SUPPORTED_CURRENCIES
from apps.crm.forms import ProjectForm, WorkspaceSettingsForm
from apps.enterprise.forms import OperationForm, RuleForm
from apps.crm.models import Project


class WorkspaceUiTests(CompanyTestCase):
    def test_new_operation_and_settings_offer_only_two_currencies(self):
        self.assertEqual([code for code, _ in SUPPORTED_CURRENCIES], ['UZS', 'USD'])
        forms = [OperationForm(actor=self.founder), RuleForm(), WorkspaceSettingsForm(),
                 ProjectForm(actor=self.founder, show_budget=True)]
        for form in forms:
            name = 'default_currency' if isinstance(form, WorkspaceSettingsForm) else 'currency'
            self.assertEqual(list(form.fields[name].choices), SUPPORTED_CURRENCIES)
        form = OperationForm({'currency': 'EUR'}, actor=self.founder)
        self.assertFalse(form.is_valid())
        self.assertIn('currency', form.errors)

    def test_historical_project_currency_is_preserved(self):
        self.project.currency = 'EUR'
        self.project.save(update_fields=['currency'])
        form = ProjectForm(instance=self.project, actor=self.founder, show_budget=True)
        self.assertTrue(form.fields['currency'].disabled)
        self.assertEqual(form.fields['currency'].initial, 'EUR')
        self.assertEqual(Project.objects.get(pk=self.project.pk).currency, 'EUR')

    def test_windows_links_are_web_only(self):
        self.login(self.founder)
        target = reverse('enterprise:desktop')
        web = self.client.get(reverse('enterprise:overview'))
        self.assertContains(web, 'href="' + target + '"')
        for agent in ('SSBDesktop/2.0.1', 'Mozilla/5.0 Electron/45.2.1'):
            desktop = self.client.get(reverse('enterprise:overview'), HTTP_USER_AGENT=agent)
            self.assertNotContains(desktop, 'href="' + target + '"')
            self.assertEqual(desktop.context['is_desktop_app'], True)

    def test_profile_has_focused_editor_and_password_link(self):
        self.login(self.dev)
        response = self.client.get(reverse('crm:profile'))
        self.assertContains(response, 'data-record-template="profile-form"')
        self.assertContains(response, 'class="profile-details"')
        self.assertContains(response, 'id="record-dialog"')
        invalid = self.client.post(reverse('crm:profile'), {'first_name': 'x' * 151})
        self.assertEqual(invalid.status_code, 200)
        self.assertIn('first_name', invalid.context['form'].errors)
        self.dev.refresh_from_db()
        self.assertNotEqual(self.dev.first_name, 'x' * 151)

    def test_audit_keeps_permission_and_offers_readable_filters(self):
        self.login(self.founder)
        response = self.client.get(reverse('crm:audit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="dan"')
        self.assertContains(response, 'name="gacha"')
        self.login(self.dev)
        self.assertEqual(self.client.get(reverse('crm:audit')).status_code, 403)

    def test_windows_page_downloads_from_a_modal_and_warns_about_the_signature(self):
        from pathlib import Path
        from django.conf import settings
        self.login(self.dev)
        page = self.client.get(reverse('enterprise:desktop'))
        self.assertNotContains(page, 'Imzosiz build')
        self.assertNotContains(page, 'NSIS')
        if Path(settings.DESKTOP_RELEASE_PATH).is_file():
            self.assertContains(page, 'id="desktop-dialog"')
            self.assertContains(page, reverse('enterprise:desktop_download'))
            self.assertContains(page, 'raqamli imzolanmagan')

