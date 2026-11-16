from django.core.cache import cache
from django.urls import reverse
from apps.core.testing import CompanyTestCase, PASSWORD


class ModalLoginTests(CompanyTestCase):
    def setUp(self):
        cache.clear()

    def test_modal_get_returns_only_form_and_csrf(self):
        response=self.client.get(reverse('accounts:login'), HTTP_X_SSB_MODAL='1')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'login-modal-form')
        self.assertContains(response,'csrfmiddlewaretoken')
        self.assertNotContains(response,'<html')

    def test_invalid_modal_login_stays_in_modal(self):
        response=self.client.post(reverse('accounts:login'),{'username':'dev','password':'incorrect'},HTTP_X_SSB_MODAL='1')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'role="alert"')
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_valid_modal_login_authenticates_and_returns_safe_destination(self):
        response=self.client.post(reverse('accounts:login'),{'username':'dev','password':PASSWORD,'next':'https://external.example/'},HTTP_X_SSB_MODAL='1')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['redirect'],reverse('enterprise:overview'))
        self.assertEqual(int(self.client.session['_auth_user_id']),self.dev.pk)

    def test_login_has_no_password_reset_link(self):
        for headers in [{}, {'HTTP_X_SSB_MODAL': '1'}]:
            response=self.client.get(reverse('accounts:login'),**headers)
            self.assertNotContains(response, reverse('accounts:password_reset'))

    def test_logout_returns_to_public_home_and_clears_session(self):
        self.login(self.dev)
        response=self.client.post(reverse('accounts:logout'))
        self.assertRedirects(response,reverse('website:home'))
        self.assertNotIn('_auth_user_id',self.client.session)
