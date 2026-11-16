"""Qurilmalar (faol sessiyalar) va "Meni eslab qol"."""
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.devices import REMEMBER_FOR, describe
from apps.accounts.models import DeviceSession, Role, User

PASSWORD = "Qurilma-Test-2026!"
CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
DESKTOP_APP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) SSBDesktop/2.0.5 Chrome/120.0 Electron/28.0.0 Safari/537.36"


class DeviceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role = Role.objects.create(name="Xodim · test", rank=100, dashboard="employee", capabilities=[])
        cls.user = User(username="qurilma", first_name="Ali", role=role, status=User.Status.ACTIVE)
        cls.user.set_password(PASSWORD)
        cls.user.save()
        cls.other = User(username="boshqa", first_name="Vali", role=Role.objects.create(name="Xodim · b", rank=100, dashboard="employee"),
                         status=User.Status.ACTIVE)
        cls.other.set_password(PASSWORD)
        cls.other.save()

    def setUp(self):
        cache.clear()

    def login(self, ua=CHROME_WIN, remember=True, user="qurilma", ip="10.0.0.1"):
        c = Client(HTTP_USER_AGENT=ua, REMOTE_ADDR=ip)
        data = {"username": user, "password": PASSWORD}
        if remember:
            data["remember"] = "1"
        r = c.post(reverse("accounts:login"), data, HTTP_X_SSB_MODAL="1")
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertIn("redirect", r.json())
        return c

    def authed(self, c):
        return c.get(reverse("accounts:devices")).status_code == 200

    # ---------------------------------------------------------- eslab qolish

    def test_remember_keeps_session_30_days(self):
        c = self.login(remember=True)
        s = c.session
        self.assertFalse(s.get_expire_at_browser_close())
        self.assertEqual(s.get_expiry_age(), REMEMBER_FOR)
        self.assertTrue(DeviceSession.objects.get(session_key=s.session_key).remembered)

    def test_without_remember_session_ends_with_browser(self):
        c = self.login(remember=False)
        self.assertTrue(c.session.get_expire_at_browser_close())
        self.assertFalse(DeviceSession.objects.get(session_key=c.session.session_key).remembered)

    def test_login_form_has_remember_checked_by_default(self):
        html = Client().get(reverse("accounts:login"), HTTP_X_SSB_MODAL="1").content.decode()
        self.assertIn('name="remember"', html)
        self.assertRegex(html, r'name="remember" value="1"\s+checked')

    # ---------------------------------------------------------- ro'yxat

    def test_each_login_is_a_device_and_list_shows_them(self):
        a = self.login(CHROME_WIN)
        self.login(IPHONE, ip="10.0.0.2")
        self.assertEqual(DeviceSession.objects.filter(user=self.user).count(), 2)
        html = a.get(reverse("accounts:devices")).content.decode()
        self.assertIn("Chrome 131", html)
        self.assertIn("Windows 10/11", html)
        self.assertIn("Safari 17", html)
        self.assertIn("iOS 17", html)
        self.assertIn("Hozir shu qurilmadasiz", html)
        self.assertEqual(html.count('class="dv-item'), 2)

    def test_other_users_devices_never_listed(self):
        a = self.login()
        self.login(user="boshqa")
        html = a.get(reverse("accounts:devices")).content.decode()
        self.assertEqual(html.count('class="dv-item'), 1)

    def test_existing_session_without_record_is_registered(self):
        c = Client(HTTP_USER_AGENT=DESKTOP_APP)
        c.force_login(self.user)
        self.assertTrue(self.authed(c))
        d = DeviceSession.objects.get(user=self.user)
        self.assertEqual(describe(d.user_agent)["kind"], "app")
        self.assertIn("SSB Boshqaruv ilovasi", describe(d.user_agent)["name"])

    def test_expired_sessions_are_dropped_from_list(self):
        a = self.login()
        b = self.login(IPHONE)
        Session.objects.filter(session_key=b.session.session_key).delete()
        html = a.get(reverse("accounts:devices")).content.decode()
        self.assertEqual(html.count('class="dv-item'), 1)
        self.assertFalse(DeviceSession.objects.filter(session_key=b.session.session_key).exists())

    # ---------------------------------------------------------- chiqarish

    def test_revoke_signs_out_that_device_immediately(self):
        a = self.login(CHROME_WIN)
        b = self.login(IPHONE)
        target = DeviceSession.objects.get(session_key=b.session.session_key)
        r = a.post(reverse("accounts:device_revoke", args=[target.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Qurilmadan chiqarildi", r.content.decode())
        self.assertFalse(self.authed(b))              # B endi tizimda emas
        self.assertTrue(self.authed(a))               # A qoladi
        self.assertFalse(Session.objects.filter(session_key=target.session_key).exists())

    def test_cannot_revoke_current_device_by_id(self):
        a = self.login()
        own = DeviceSession.objects.get(session_key=a.session.session_key)
        a.post(reverse("accounts:device_revoke", args=[own.pk]))
        self.assertTrue(self.authed(a))

    def test_cannot_revoke_someone_elses_device(self):
        a = self.login()
        b = self.login(user="boshqa")
        theirs = DeviceSession.objects.get(session_key=b.session.session_key)
        a.post(reverse("accounts:device_revoke", args=[theirs.pk]))
        self.assertTrue(self.authed(b))

    def test_revoke_all_others_keeps_only_current(self):
        a = self.login(CHROME_WIN)
        b = self.login(IPHONE)
        d = self.login(DESKTOP_APP)
        r = a.post(reverse("accounts:device_revoke_others"))
        self.assertIn("2 ta qurilmadan chiqarildi", r.content.decode())
        self.assertTrue(self.authed(a))
        self.assertFalse(self.authed(b))
        self.assertFalse(self.authed(d))
        self.assertEqual(DeviceSession.objects.filter(user=self.user).count(), 1)

    def test_revoke_requires_post_and_login(self):
        a = self.login()
        self.assertEqual(a.get(reverse("accounts:device_revoke_others")).status_code, 405)
        anon = Client()
        r = anon.post(reverse("accounts:device_revoke_others"))
        self.assertEqual(r.status_code, 302)

    def test_password_change_signs_out_other_devices_but_not_current(self):
        a = self.login(CHROME_WIN)
        b = self.login(IPHONE)
        r = a.post(reverse("accounts:password_change"), {
            "old_password": PASSWORD, "new_password1": "Yangi-Parol-2026!x", "new_password2": "Yangi-Parol-2026!x"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.authed(a))
        self.assertFalse(self.authed(b))
        self.assertEqual(DeviceSession.objects.filter(user=self.user).count(), 1)
        self.assertEqual(DeviceSession.objects.get(user=self.user).session_key, a.session.session_key)

    def test_logout_removes_device(self):
        a = self.login()
        key = a.session.session_key
        a.post(reverse("accounts:logout"))
        self.assertFalse(DeviceSession.objects.filter(session_key=key).exists())

    def test_last_seen_and_ip_behind_tunnel(self):
        c = Client(HTTP_USER_AGENT=CHROME_WIN, REMOTE_ADDR="127.0.0.1", HTTP_CF_CONNECTING_IP="203.0.113.7")
        c.post(reverse("accounts:login"), {"username": "qurilma", "password": PASSWORD, "remember": "1"}, HTTP_X_SSB_MODAL="1")
        self.assertEqual(DeviceSession.objects.get(user=self.user).ip, "203.0.113.7")
        # Proksi bo'lmasa sarlavhaga ishonilmaydi
        d = Client(HTTP_USER_AGENT=CHROME_WIN, REMOTE_ADDR="198.51.100.4", HTTP_CF_CONNECTING_IP="1.2.3.4")
        d.post(reverse("accounts:login"), {"username": "boshqa", "password": PASSWORD}, HTTP_X_SSB_MODAL="1")
        self.assertEqual(DeviceSession.objects.get(user=self.other).ip, "198.51.100.4")
