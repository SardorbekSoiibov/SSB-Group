from django.core.cache import cache
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from apps.core.testing import PASSWORD, CompanyTestCase


class AuthenticationTests(CompanyTestCase):
    def setUp(self):
        cache.clear()

    def test_login_and_logout_history_never_stores_password(self):
        self.client.post(reverse('accounts:login'),{'username':'dev','password':'wrong-secret'})
        self.client.post(reverse('accounts:login'),{'username':'dev','password':PASSWORD})
        self.client.post(reverse('accounts:logout'))
        self.assertTrue(AuditEvent.objects.filter(action='auth.login',actor=self.dev).exists())
        self.assertTrue(AuditEvent.objects.filter(action='auth.logout',actor=self.dev).exists())
        failed=AuditEvent.objects.get(action='auth.login_failed')
        self.assertNotIn('wrong-secret',str(failed.changes))

    def test_disabled_role_cannot_authenticate(self):
        role=self.dev.role;role.is_active=False;role.save()
        response=self.client.post(reverse('accounts:login'),{'username':'dev','password':PASSWORD})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_login_and_logout(self):
        r = self.client.post(reverse("accounts:login"), {"username": "dev", "password": PASSWORD})
        self.assertRedirects(r, reverse("enterprise:overview"))
        self.assertEqual(self.client.get(reverse("enterprise:overview")).status_code, 200)
        self.client.post(reverse("accounts:logout"))
        r = self.client.get(reverse("enterprise:overview"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])

    def test_wrong_password_rejected_and_rate_limited(self):
        for _ in range(8):
            r = self.client.post(reverse("accounts:login"), {"username": "dev", "password": "wrong"})
            self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse("accounts:login"), {"username": "dev", "password": PASSWORD})
        self.assertEqual(r.status_code, 429)

    def test_passwords_are_hashed(self):
        self.assertNotEqual(self.dev.password, PASSWORD)
        self.assertTrue(self.dev.password.startswith(("pbkdf2_", "argon2", "bcrypt")))

    def test_suspended_user_cannot_log_in(self):
        self.dev.status = User.Status.SUSPENDED
        self.dev.save()
        r = self.client.post(reverse("accounts:login"), {"username": "dev", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.wsgi_request.user.is_authenticated)


class EmployeeManagementTests(CompanyTestCase):
    def test_ceo_invites_employee_with_link(self):
        self.login(self.ceo)
        r = self.client.post(reverse("crm:employee_create"), {
            "first_name": "Ali", "last_name": "Valiyev", "username": "ali", "role": Role.objects.get(name="Xodim").pk,
        })
        user = User.objects.get(username="ali")
        self.assertRedirects(r, reverse("crm:employee_detail", args=[user.pk]), fetch_redirect_response=False)
        self.assertEqual(user.status, User.Status.INVITED)
        self.assertFalse(user.has_usable_password())
        page = self.client.get(reverse("crm:employee_detail", args=[user.pk]))
        link = page.context["invite"]["link"]
        self.assertTrue(AuditEvent.objects.filter(action="user.created", target_id=str(user.pk)).exists())

        self.client.logout()
        path = link.split("testserver")[1]
        r = self.client.get(path, follow=True)  # Django swaps the token into the session and redirects
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "Yangi-parol-2026!", "new_password2": "Yangi-parol-2026!"})
        self.assertRedirects(r, reverse("accounts:login"))
        user.refresh_from_db()
        self.assertEqual(user.status, User.Status.ACTIVE)
        self.assertTrue(user.check_password("Yangi-parol-2026!"))

    def test_cannot_assign_role_above_own_rank(self):
        self.login(self.ceo)
        r = self.client.post(reverse("crm:employee_create"), {
            "first_name": "X", "last_name": "Y", "username": "xy", "role": Role.objects.get(name="Hammuassis").pk,
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="xy").exists())

    def test_employee_cannot_edit_self_or_others(self):
        self.login(self.dev)
        self.assertEqual(self.client.get(reverse("crm:employee_edit", args=[self.dev.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("crm:employee_status", args=[self.designer.pk]), {"status": "suspended"}).status_code, 403)

    def test_manager_cannot_manage_peer_or_senior(self):
        self.login(self.ceo)
        self.assertEqual(self.client.get(reverse("crm:employee_edit", args=[self.cofounder.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("crm:employee_edit", args=[self.ceo.pk])).status_code, 403)

    def test_profile_form_cannot_change_role(self):
        self.login(self.dev)
        owner = Role.objects.get(is_owner=True)
        self.client.post(reverse("crm:profile"), {"first_name": "Dev", "last_name": "", "phone": "+998901112233", "role": owner.pk})
        self.dev.refresh_from_db()
        self.assertEqual(self.dev.role.name, "Xodim")
        self.assertEqual(self.dev.phone, "+998901112233")

    def test_deactivation_keeps_history(self):
        self.login(self.founder)
        r = self.client.post(reverse("crm:employee_status", args=[self.dev.pk]), {"status": "deactivated"})
        self.assertEqual(r.status_code, 302)
        self.dev.refresh_from_db()
        self.assertFalse(self.dev.is_active)
        self.assertTrue(self.project.members.filter(pk=self.dev.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(action="user.status", target_id=str(self.dev.pk)).exists())


class RoleEscalationTests(CompanyTestCase):
    def test_non_owner_cannot_grant_capabilities_they_lack(self):
        self.ceo.role.capabilities.append("roles.manage")
        self.ceo.role.save()
        self.login(self.ceo)
        r = self.client.post(reverse("crm:role_create"), {
            "name": "Super", "rank": 25, "dashboard": "management", "scope": "company", "capabilities": ["settings.manage"],
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Role.objects.filter(name="Super").exists())

    def test_non_owner_cannot_edit_own_or_higher_role(self):
        self.ceo.role.capabilities.append("roles.manage")
        self.ceo.role.save()
        self.login(self.ceo)
        self.assertEqual(self.client.get(reverse("crm:role_edit", args=[self.ceo.role.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("crm:role_edit", args=[self.cofounder.role.pk])).status_code, 403)

    def test_owner_configures_cofounder_access(self):
        self.login(self.founder)
        role = self.cofounder.role
        r = self.client.post(reverse("crm:role_edit", args=[role.pk]), {
            "name": role.name, "rank": role.rank, "dashboard": "cofounder", "scope": "company", "capabilities": ["clients.view"],
        })
        self.assertEqual(r.status_code, 302)
        role.refresh_from_db()
        self.assertEqual(role.capabilities, ["clients.view"])
        self.assertTrue(AuditEvent.objects.filter(action="role.updated").exists())
        self.login(self.cofounder)
        self.assertEqual(self.client.get(reverse("crm:audit")).status_code, 403)
        self.assertEqual(self.client.get(reverse("crm:clients")).status_code, 200)

    def test_cofounder_does_not_get_founder_powers(self):
        self.login(self.cofounder)
        for name in ("crm:roles", "crm:settings", "crm:employee_create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_dashboards_differ_by_role(self):
        for user, kind in ((self.founder, "founder"), (self.cofounder, "cofounder"),
                           (self.ceo, "management"), (self.dev, "employee")):
            self.login(user)
            response=self.client.get(reverse("enterprise:overview"))
            self.assertTemplateUsed(response,'boshqaruv/dashboards/'+{'founder':'founder','cofounder':'cofounder','management':'director','employee':'employee'}[user.dashboard_kind]+'.html')
            self.assertEqual(response.context['dashboard_kind'],kind)
            self.assertContains(response,str(user.role))
            self.assertEqual('finance' in response.context['available'],user.has_cap('finance.view'))
