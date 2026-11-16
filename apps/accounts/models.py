import hashlib

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from apps.core.storage import RandomName, private_storage
from apps.core.uploads import IMAGE_VALIDATORS, validate_contract


class Capability(models.TextChoices):
    """Catalog of security capabilities. Every employee gets exactly the ones the founder ticks."""

    # Shaxsiy kabinet funksiyalari (belgilanmasa xodim ularni ko'rmaydi)
    PROJECTS_OWN = "projects.own", "O'ziga biriktirilgan loyihalarni ko'rish va yuritish"
    PROJECTS_VIEWS = "projects.views", "Loyihalar doskasi, taqvimi va bandligini ko'rish"
    SCHEDULE_VIEW = "schedule.view", "Ish jadvalini ko'rish"
    PERFORMANCE_SELF = "performance.self", "O'z baholash va reytingini ko'rish"
    CHAT_USE = "chat.use", "Xodimlar chatidan foydalanish"
    FINANCE_BALANCE = "finance.balance", "Shaxsiy hisob (balans) ni ko'rish"
    ANNOUNCEMENTS_VIEW = "announcements.view", "E'lonlarni ko'rish"
    ARCHIVE_USE = "archive.use", "Xavfsiz arxivdan foydalanish"

    EXECUTIVE_DASHBOARD = "dashboard.executive", "Kompaniya ko'rsatkichlarini ko'rish"
    EMPLOYEES_VIEW = "employees.view", "Xodimlar katalogini ko'rish"
    EMPLOYEES_MANAGE = "employees.manage", "Xodimlarni qo'shish va boshqarish"
    ROLES_MANAGE = "roles.manage", "Rollar, bo'limlar va huquqlarni boshqarish"
    PROJECTS_VIEW_ALL = "projects.view_all", "Barcha loyihalarni ko'rish"
    PROJECTS_CREATE = "projects.create", "Loyiha yaratish"
    PROJECTS_EDIT = "projects.edit", "Loyihalarni tahrirlash"
    PROJECTS_ASSIGN = "projects.assign", "Loyihaga xodim biriktirish"
    PROJECTS_APPROVE = "projects.approve", "Loyihalarni tasdiqlash"
    PROJECTS_ARCHIVE = "projects.archive", "Loyihalarni arxivlash"
    PROJECTS_BUDGET = "projects.budget", "Loyiha byudjetini ko'rish"
    CLIENTS_VIEW = "clients.view", "Mijozlarni ko'rish"
    CLIENTS_MANAGE = "clients.manage", "Mijozlarni boshqarish"
    INQUIRIES_MANAGE = "inquiries.manage", "Murojaatlarni boshqarish"
    FINANCE_VIEW = "finance.view", "Kompaniya moliyasini ko'rish"
    FINANCE_MANAGE = "finance.manage", "Moliyaviy amal yaratish"
    FINANCE_APPROVE = "finance.approve", "Moliyaviy amallarni tasdiqlash"
    FINANCE_DISTRIBUTE = "finance.distribute", "Loyiha ulushlarini belgilash"
    FINANCE_RULES = "finance.rules", "Moliyaviy tasdiqlash qoidalari"
    ARCHIVE_MANAGE = "archive.manage", "Loyiha arxivlari va kodlari"
    SCHEDULE_MANAGE = "schedule.manage", "Ish jadvalini boshqarish"
    PERFORMANCE_VIEW = "performance.view", "Jamoa faoliyatini ko'rish"
    PERFORMANCE_MANAGE = "performance.manage", "Faoliyatni baholash"
    DASHBOARD_CUSTOMIZE = "dashboard.customize", "Dashboard vidjetlarini sozlash"
    TEAM_MANAGE = "team.manage", "Saytdagi jamoani boshqarish"
    CMS_EDIT = "cms.edit", "Sayt kontentini tahrirlash"
    CMS_PUBLISH = "cms.publish", "Sayt kontentini nashr qilish"
    ANNOUNCEMENTS = "announcements.manage", "E'lonlar yuborish"
    REPORTS_VIEW = "reports.view", "Hisobotlarni ko'rish"
    SETTINGS_MANAGE = "settings.manage", "Tizim sozlamalarini o'zgartirish"
    AUDIT_VIEW = "audit.view", "Audit jurnalini ko'rish"


CAPABILITY_GROUPS = [
    ("Shaxsiy kabinet", ["projects.own", "projects.views", "schedule.view", "performance.self", "chat.use",
                         "finance.balance", "announcements.view", "archive.use"]),
    ("Boshqaruv", ["dashboard.executive", "audit.view", "settings.manage", "announcements.manage"]),
    ("Xodimlar", ["employees.view", "employees.manage", "roles.manage"]),
    ("Loyihalar", ["projects.view_all", "projects.create", "projects.edit", "projects.assign",
                   "projects.approve", "projects.archive", "projects.budget"]),
    ("Mijozlar", ["clients.view", "clients.manage", "inquiries.manage"]),
    ("Moliya", ["finance.view", "finance.manage", "finance.approve", "finance.distribute", "finance.rules"]),
    ("Ish jarayoni", ["archive.manage", "schedule.manage", "performance.view", "performance.manage", "dashboard.customize"]),
    ("Sayt", ["team.manage", "cms.edit", "cms.publish"]),
]


class Department(models.Model):
    name = models.CharField("Nomi", max_length=120, unique=True)
    slug = models.SlugField(unique=True)
    head = models.ForeignKey(
        "accounts.User", verbose_name="Rahbar", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="headed_departments",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Bo'lim"
        verbose_name_plural = "Bo'limlar"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or "bolim"
        super().save(*args, **kwargs)


class Role(models.Model):
    """A security role. Separate from job title and department."""

    class Dashboard(models.TextChoices):
        FOUNDER = "founder", "Asoschi"
        COFOUNDER = "cofounder", "Hammuassis"
        MANAGEMENT = "management", "Rahbariyat"
        EMPLOYEE = "employee", "Xodim"

    class Scope(models.TextChoices):
        COMPANY = "company", "Butun kompaniya"
        DEPARTMENT = "department", "Faqat o'z bo'limi"

    is_active = models.BooleanField("Rol faol", default=True)
    name = models.CharField("Nomi", max_length=80, unique=True)
    rank = models.PositiveSmallIntegerField(
        "Daraja", help_text="Kichik raqam — yuqori lavozim. Foydalanuvchi faqat o'zidan quyi darajadagilarni boshqaradi.",
    )
    dashboard = models.CharField("Dashboard turi", max_length=20, choices=Dashboard.choices, default=Dashboard.EMPLOYEE)
    scope = models.CharField("Ko'lami", max_length=20, choices=Scope.choices, default=Scope.COMPANY)
    capabilities = ArrayField(
        models.CharField(max_length=40, choices=Capability.choices), verbose_name="Huquqlar", default=list, blank=True,
    )
    is_owner = models.BooleanField(
        "Asoschi roli", default=False, editable=False,
        help_text="Barcha huquqlarga ega. Faqat boshlang'ich sozlashda yaratiladi.",
    )
    description = models.CharField("Tavsif", max_length=255, blank=True)

    class Meta:
        ordering = ["rank", "name"]
        verbose_name = "Rol"
        verbose_name_plural = "Rollar"

    PERSONAL_PREFIX = "Xodim · "

    def __str__(self):
        if self.is_owner:
            return "Asoschi"
        if self.is_personal:
            return "Xodim"
        return self.name

    @property
    def is_personal(self):
        """Each employee has a private role that holds exactly the functions the founder granted."""
        return self.name.startswith(self.PERSONAL_PREFIX)

    def has(self, cap):
        return self.is_owner or cap in self.capabilities

    def capability_labels(self):
        labels = dict(Capability.choices)
        if self.is_owner:
            return ["Barcha huquqlar"]
        return [labels.get(c, c) for c in self.capabilities]


class User(AbstractUser):
    class Status(models.TextChoices):
        INVITED = "invited", "Taklif yuborilgan"
        ACTIVE = "active", "Faol"
        SUSPENDED = "suspended", "To'xtatilgan"
        DEACTIVATED = "deactivated", "Ishdan ketgan"

    photo = models.ImageField(
        "Rasm", storage=private_storage, upload_to=RandomName("users"), blank=True, validators=IMAGE_VALIDATORS,
    )
    job_title = models.CharField("Lavozim", max_length=120, blank=True)
    department = models.ForeignKey(
        Department, verbose_name="Bo'lim", null=True, blank=True, on_delete=models.SET_NULL, related_name="members",
    )
    role = models.ForeignKey(Role, verbose_name="Xavfsizlik roli", null=True, on_delete=models.PROTECT, related_name="users")
    manager = models.ForeignKey(
        "self", verbose_name="Bevosita rahbar", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports",
    )
    status = models.CharField("Holat", max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    joined_on = models.DateField("Ishga kirgan sana", null=True, blank=True)
    # Mehnat shartnomasi: fayl maxfiy omborda, faqat xodimning o'zi va uni boshqaradiganlar yuklab oladi.
    contract = models.FileField(
        "Mehnat shartnomasi", storage=private_storage, upload_to=RandomName("contracts"), blank=True,
        validators=[validate_contract], help_text="PDF, Word yoki skanerlangan rasm, 15 MB gacha.",
    )
    contract_number = models.CharField("Shartnoma raqami", max_length=60, blank=True)
    contract_signed_on = models.DateField("Imzolangan sana", null=True, blank=True)
    contract_ends_on = models.DateField(
        "Amal qilish muddati", null=True, blank=True, help_text="Bo‘sh qoldirilsa — muddatsiz shartnoma.",
    )
    skills = ArrayField(models.CharField(max_length=60), verbose_name="Ko'nikmalar", default=list, blank=True)
    phone = models.CharField("Telefon", max_length=40, blank=True)
    telegram = models.CharField("Telegram", max_length=64, blank=True)
    is_verified = models.BooleanField("Tasdiqlangan hisob", default=False)
    allow_screenshots = models.BooleanField(
        "Skrinshot olishga ruxsat", default=True,
        help_text="O‘chirilsa, Windows ilovasida skrinshot tizim darajasida to‘siladi.",
    )
    muted_notifications = ArrayField(
        models.CharField(max_length=40), verbose_name="O'chirilgan bildirishnomalar", default=list, blank=True,
    )

    class Meta:
        ordering = ["first_name", "last_name"]
        verbose_name = "Xodim"
        verbose_name_plural = "Xodimlar"

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        # Login is possible only for invited (to set a password) or active accounts.
        self.is_active = self.status in (self.Status.ACTIVE, self.Status.INVITED)
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def photo_version(self):
        """Changes with the file, so a new photo is never hidden by the browser cache."""
        return hashlib.sha256(self.photo.name.encode()).hexdigest()[:10] if self.photo else ""

    @property
    def contract_extension(self):
        return self.contract.name.rsplit(".", 1)[-1].upper() if self.contract else ""

    @property
    def contract_state(self):
        """'active' | 'expiring' (30 kun ichida tugaydi) | 'expired' | '' (shartnoma yo'q)."""
        if not self.contract:
            return ""
        if not self.contract_ends_on:
            return "active"
        from django.utils import timezone
        left = (self.contract_ends_on - timezone.localdate()).days
        return "expired" if left < 0 else "expiring" if left <= 30 else "active"

    @property
    def screenshot_blocked(self):
        return not self.allow_screenshots and not self.is_owner

    @property
    def initials(self):
        parts = [p for p in (self.first_name, self.last_name) if p] or [self.username]
        return "".join(p[0] for p in parts[:2]).upper()

    @property
    def is_owner(self):
        return self.is_superuser or bool(self.role_id and self.role.is_owner)

    @property
    def rank(self):
        if self.is_superuser:
            return 0
        return self.role.rank if self.role_id else 9999

    def personal_role(self):
        """Returns (creating if needed) this employee's own role. The founder keeps the owner role."""
        if self.is_owner:
            return self.role
        if self.role_id and self.role.is_personal and not User.objects.filter(role_id=self.role_id).exclude(pk=self.pk).exists():
            return self.role
        name = (Role.PERSONAL_PREFIX + self.username)[:80]
        role, _ = Role.objects.get_or_create(name=name, defaults={
            "rank": 100, "dashboard": Role.Dashboard.EMPLOYEE, "scope": Role.Scope.COMPANY,
            "capabilities": [], "description": "Shaxsiy huquqlar",
        })
        if self.role_id != role.pk:
            self.role = role
            if self.pk:
                User.objects.filter(pk=self.pk).update(role=role)
        return role

    def set_capabilities(self, caps):
        role = self.personal_role()
        if role is None or role.is_owner:
            return
        allowed = set(Capability.values)
        role.capabilities = sorted(c for c in set(caps) if c in allowed)
        role.save(update_fields=["capabilities"])

    def has_cap(self, cap):
        if not self.is_authenticated or not self.is_active:
            return False
        if self.is_owner:
            return True
        # Lavozimi hackaton bilan bog'liq xodim Hackaton e'lonlari bo'limini ko'radi va e'lon yoza oladi.
        if cap in ("announcements.view", "announcements.manage") and self.is_hackathon_staff:
            return True
        return bool(self.role_id and self.role.is_active and cap in self.role.capabilities)

    @property
    def is_hackathon_staff(self):
        """Lavozimida «hackaton/hakaton/hackathon» so'zi bor xodim (masalan: «Hackaton menejeri», «Hackatonchi»)."""
        import re
        return bool(self.status == self.Status.ACTIVE and re.search(r"ha[ck]{1,2}at(h)?on", self.job_title or "", re.I))

    def caps(self):
        if self.is_owner:
            return set(Capability.values)
        return set(self.role.capabilities) if self.role_id else set()

    @property
    def company_scope(self):
        return self.is_owner or (self.role_id and self.role.scope == Role.Scope.COMPANY)

    @property
    def dashboard_kind(self):
        if self.is_owner:
            return Role.Dashboard.FOUNDER
        return self.role.dashboard if self.role_id else Role.Dashboard.EMPLOYEE

    def get_absolute_url(self):
        return reverse("crm:employee_detail", args=[self.pk])


class DeviceSession(models.Model):
    """Hisobga kirilgan bitta qurilma (brauzer yoki Windows ilovasi) = bitta sessiya.

    Qurilmadan chiqarish sessiyani bazadan o'chiradi, shuning uchun o'sha qurilma keyingi so'rovdayoq tizimdan chiqadi.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    session_key = models.CharField(max_length=40, unique=True)
    user_agent = models.CharField(max_length=400, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    remembered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField()

    class Meta:
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.user} · {self.session_key[:6]}…"
