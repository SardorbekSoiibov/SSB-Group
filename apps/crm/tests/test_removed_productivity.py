from django.urls import NoReverseMatch, reverse

from apps.core.testing import CompanyTestCase


class RemovedProductivityTests(CompanyTestCase):
    def test_removed_pages_and_csv_are_not_accessible(self):
        for user in [self.founder, self.ceo, self.dev]:
            self.login(user)
            for path in ['/management/hisobotlar/', '/management/hisobotlar/yetkazish/',
                         '/management/hisobotlar/yuklama/?format=csv']:
                self.assertEqual(self.client.get(path).status_code, 404)
        for name in ['crm:reports', 'crm:report']:
            with self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_navigation_and_role_form_no_longer_offer_productivity(self):
        self.login(self.founder)
        response = self.client.get(reverse('enterprise:overview'))
        self.assertNotContains(response, '/management/hisobotlar/')
        self.assertNotContains(response, 'Ish unumdorligi')
        # "Moliyaviy hisobotlar" ham menyudan olib tashlangan (Asoschi qarori).
        self.assertNotContains(response, reverse('enterprise:reports'))
        response = self.client.get(reverse('crm:role_edit', args=[self.ceo.role_id]))
        self.assertNotContains(response, 'value="reports.view"')
