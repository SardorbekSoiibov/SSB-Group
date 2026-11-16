from django.conf import settings
from django.db import models, transaction, connection
from django.db.models import Count, Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStamped
from apps.core.storage import RandomName, private_storage
from apps.core.uploads import IMAGE_VALIDATORS, downscale_image

User = settings.AUTH_USER_MODEL


class Priority(models.TextChoices):
    LOW = "low", "Past"
    MEDIUM = "medium", "Normal"
    HIGH = "high", "Muhim"
    CRITICAL = "critical", "Shoshilinch"


PRIORITY_WEIGHT = {"low": 0, "medium": 1, "high": 2, "critical": 3}
PREVIEW_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


class Client(TimeStamped):
    name = models.CharField("Kontakt shaxs", max_length=120)
    company = models.CharField("Kompaniya", max_length=160, blank=True)
    email = models.EmailField("Email", blank=True)
    phone = models.CharField("Telefon", max_length=40, blank=True)
    telegram = models.CharField("Telegram", max_length=64, blank=True)
    account_manager = models.ForeignKey(
        User, verbose_name="Mas'ul menejer", null=True, blank=True, on_delete=models.SET_NULL, related_name="clients",
    )
    notes = models.TextField("Izohlar", blank=True)

    class Meta:
        ordering = ["company", "name"]
        verbose_name = "Mijoz"
        verbose_name_plural = "Mijozlar"

    def __str__(self):
        return f"{self.company} ({self.name})" if self.company else self.name

    def get_absolute_url(self):
        return reverse("crm:client_detail", args=[self.pk])


class Inquiry(TimeStamped):
    class Stage(models.TextChoices):
        NEW = "new", "Yangi"
        CONTACTED = "contacted", "Bog'lanildi"
        DISCUSSION = "discussion", "Muhokama"
        PROPOSAL = "proposal", "Taklif yuborildi"
        APPROVED = "approved", "Kelishildi"
        REJECTED = "rejected", "Rad etildi"
        CONVERTED = "converted", "Loyihaga aylandi"

    class ContactMethod(models.TextChoices):
        PHONE = "phone", "Telefon qo'ng'irog'i"
        TELEGRAM = "telegram", "Telegram"
        EMAIL = "email", "Email"

    class Budget(models.TextChoices):
        UNKNOWN = "", "Hali aniq emas"
        S = "lt_1k", "$1 000 gacha"
        M = "1k_5k", "$1 000 – 5 000"
        L = "5k_15k", "$5 000 – 15 000"
        XL = "gt_15k", "$15 000 dan yuqori"

    class Source(models.TextChoices):
        WEBSITE = "website", "Sayt"
        TELEGRAM = "telegram", "Telegram"
        REFERRAL = "referral", "Tavsiya"
        EVENT = "event", "Tadbir"
        OTHER = "other", "Boshqa"

    name = models.CharField("Ism", max_length=120)
    contact = models.CharField("Aloqa ma'lumoti", max_length=160)
    preferred_method = models.CharField("Qulay aloqa usuli", max_length=10, choices=ContactMethod.choices)
    service = models.ForeignKey(
        "website.Service", verbose_name="Xizmat", null=True, blank=True, on_delete=models.SET_NULL, related_name="inquiries",
    )
    description = models.TextField("Loyiha tavsifi")
    budget = models.CharField("Taxminiy byudjet", max_length=10, choices=Budget.choices, blank=True)
    source = models.CharField("Manba", max_length=10, choices=Source.choices, default=Source.WEBSITE)
    stage = models.CharField("Bosqich", max_length=12, choices=Stage.choices, default=Stage.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        User, verbose_name="Mas'ul", null=True, blank=True, on_delete=models.SET_NULL, related_name="inquiries",
    )
    client = models.ForeignKey(
        Client, verbose_name="Mijoz", null=True, blank=True, on_delete=models.SET_NULL, related_name="inquiries",
    )
    follow_up_on = models.DateField("Keyingi aloqa sanasi", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Murojaat"
        verbose_name_plural = "Murojaatlar"

    def __str__(self):
        return f"#{self.pk} {self.name}"

    def get_absolute_url(self):
        return reverse("crm:inquiry_detail", args=[self.pk])

    @property
    def is_open(self):
        return self.stage not in (self.Stage.REJECTED, self.Stage.CONVERTED)


class InquiryNote(models.Model):
    inquiry = models.ForeignKey(Inquiry, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    body = models.TextField("Izoh")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ProjectQuerySet(models.QuerySet):
    def with_progress(self):
        """Progress comes from the project's own stages (bosqichlar); tasks are no longer used."""
        return self.annotate(
            stage_total=Count("milestones", distinct=True),
            stage_done=Count("milestones", filter=Q(milestones__is_done=True), distinct=True),
        )


class Project(TimeStamped):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        PLANNING = "planning", "Rejalashtirilmoqda"
        AWAITING_APPROVAL = "awaiting_approval", "Tasdiq kutilmoqda"
        IN_PROGRESS = "in_progress", "Jarayonda"
        ON_HOLD = "on_hold", "To'xtatilgan"
        UNDER_REVIEW = "under_review", "Tekshiruvda"
        COMPLETED = "completed", "Tugallangan"
        ARCHIVED = "archived", "Arxiv"
        CANCELLED = "cancelled", "Bekor qilingan"

    code = models.CharField("Kod", max_length=20, unique=True, editable=False)
    name = models.CharField("Nomi", max_length=160)
    description = models.TextField("Tavsif", blank=True)
    objectives = models.TextField("Loyiha maqsadlari", blank=True)
    cover = models.ImageField(
        "Muqova rasmi", storage=private_storage, upload_to=RandomName("project-covers"), blank=True, validators=IMAGE_VALIDATORS,
    )
    client = models.ForeignKey(
        Client, verbose_name="Mijoz", null=True, blank=True, on_delete=models.SET_NULL, related_name="projects",
    )
    inquiry = models.OneToOneField(
        Inquiry, verbose_name="Murojaat", null=True, blank=True, on_delete=models.SET_NULL, related_name="project",
    )
    manager = models.ForeignKey(
        User, verbose_name="Loyiha menejeri", null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_projects",
    )
    members = models.ManyToManyField(User, verbose_name="Jamoa", blank=True, related_name="projects")
    department = models.ForeignKey(
        "accounts.Department", verbose_name="Bo'lim", null=True, blank=True, on_delete=models.SET_NULL, related_name="projects",
    )
    start_date = models.DateField("Boshlanish", null=True, blank=True)
    deadline = models.DateField("Muddat", null=True, blank=True, db_index=True)
    priority = models.CharField("Ustuvorlik", max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField("Holat", max_length=20, choices=Status.choices, default=Status.PLANNING, db_index=True)
    budget = models.DecimalField("Byudjet", max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField("Valyuta", max_length=3, default="USD")
    internal_notes = models.TextField("Ichki izohlar", blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Loyiha"
        verbose_name_plural = "Loyihalar"

    def __str__(self):
        return f"{self.code} · {self.name}"

    def save(self, *args, **kwargs):
        downscale_image(self, "cover")
        if not self.code:
            with transaction.atomic():
                with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock(73910240)')
                last = Project.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
                self.code = f"SSB-{last + 1:04d}"
                while Project.objects.filter(code=self.code).exists():
                    last += 1
                    self.code = f"SSB-{last + 1:04d}"
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("crm:project_detail", args=[self.pk])

    @property
    def is_closed(self):
        return self.status in (self.Status.COMPLETED, self.Status.ARCHIVED, self.Status.CANCELLED)

    @property
    def is_overdue(self):
        return bool(self.deadline and not self.is_closed and self.deadline < timezone.localdate())

    def progress(self):
        """Done stages / all stages, in percent. A completed project is always 100%."""
        if self.status in (self.Status.COMPLETED, self.Status.ARCHIVED):
            return 100
        total = getattr(self, "stage_total", None)
        done = getattr(self, "stage_done", None)
        if total is None:
            total = self.milestones.count()
            done = self.milestones.filter(is_done=True).count()
        return round(done * 100 / total) if total else 0

    def team(self):
        people = list(self.members.all())
        if self.manager and self.manager not in people:
            people.insert(0, self.manager)
        return people


class ProjectAssignment(models.Model):
    """What one person is responsible for on a project. Membership itself stays in Project.members."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_assignments")
    responsibility = models.CharField("Mas'uliyati", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="crm_one_assignment_per_person")]


class ProjectComment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    body = models.TextField("Izoh")
    is_announcement = models.BooleanField("Loyiha e'loni", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ProjectFile(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="files")
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    file = models.FileField(storage=private_storage, upload_to=RandomName("project-files"))
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    @property
    def is_image(self):
        return self.original_name.lower().endswith(PREVIEW_EXTENSIONS)


class ProjectApproval(models.Model):
    class Kind(models.TextChoices):
        START = "start", "Boshlashga ruxsat"
        COMPLETION = "completion", "Yakunlanishi tasdiqlandi"
        PUBLICATION = "publication", "Portfolioga chiqarishga ruxsat"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="approvals")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField("Bosqich", max_length=160)
    due_date = models.DateField("Muddat", null=True, blank=True)
    is_done = models.BooleanField("Bajarildi", default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "due_date", "pk"]

    def __str__(self):
        return self.title


class Task(TimeStamped):
    class Status(models.TextChoices):
        NEW = "new", "Biriktirilmagan"
        ASSIGNED = "assigned", "Yangi"
        ACCEPTED = "accepted", "Qabul qilindi"
        IN_PROGRESS = "in_progress", "Jarayonda"
        BLOCKED = "blocked", "To'siq bor"
        SUBMITTED = "submitted", "Tekshiruvga yuborildi"
        CHANGES_REQUESTED = "changes_requested", "Qayta ishlash kerak"
        APPROVED = "approved", "Bajarildi"
        CANCELLED = "cancelled", "Bekor qilindi"

    OPEN = (Status.NEW, Status.ASSIGNED, Status.ACCEPTED, Status.IN_PROGRESS, Status.BLOCKED, Status.SUBMITTED, Status.CHANGES_REQUESTED)

    project = models.ForeignKey(Project, verbose_name="Loyiha", on_delete=models.CASCADE, related_name="tasks")
    parent = models.ForeignKey(
        "self", verbose_name="Asosiy vazifa", null=True, blank=True, on_delete=models.CASCADE, related_name="subtasks",
    )
    milestone = models.ForeignKey(
        Milestone, verbose_name="Bosqich", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks",
    )
    title = models.CharField("Nomi", max_length=200)
    description = models.TextField("Tavsif", blank=True)
    acceptance_criteria = models.TextField("Qabul mezonlari", blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="created_tasks")
    assignee = models.ForeignKey(
        User, verbose_name="Ijrochi", null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks",
    )
    priority = models.CharField("Ustuvorlik", max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    start_date = models.DateField("Boshlanish", null=True, blank=True)
    deadline = models.DateField("Muddat", null=True, blank=True)
    status = models.CharField("Holat", max_length=20, choices=Status.choices, default=Status.NEW)
    depends_on = models.ManyToManyField(
        "self", verbose_name="Bog'liq vazifalar", symmetrical=False, blank=True, related_name="blocking",
    )
    progress = models.PositiveSmallIntegerField("Bajarilishi", default=0)
    assigned_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["deadline", "-created_at"]
        verbose_name = "Vazifa"
        verbose_name_plural = "Vazifalar"
        indexes = [
            models.Index(fields=["assignee", "status"]),
            models.Index(fields=["project", "status"]),
            models.Index(fields=["deadline"]),
        ]
        constraints = [models.CheckConstraint(condition=Q(progress__lte=100), name="crm_task_progress_bounds")]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("crm:task_detail", args=[self.pk])

    @property
    def is_open(self):
        return self.status in self.OPEN

    @property
    def is_overdue(self):
        return bool(self.deadline and self.is_open and self.deadline < timezone.localdate())

    @property
    def shown_progress(self):
        return 100 if self.status == self.Status.APPROVED else self.progress

    def unfinished_dependencies(self):
        return self.depends_on.exclude(status__in=[self.Status.APPROVED, self.Status.CANCELLED])


class TaskAssignment(models.Model):
    """A co-worker on a task. Task.assignee stays the one responsible person, so a task is only ever counted once."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_assignments")
    responsibility = models.CharField("Mas'uliyati", max_length=200, blank=True)
    progress = models.PositiveSmallIntegerField("Bajarilishi", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["task", "user"], name="crm_one_task_assignment_per_person"),
            models.CheckConstraint(condition=Q(progress__lte=100), name="crm_assignment_progress_bounds"),
        ]


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    body = models.TextField("Izoh")
    is_clarification = models.BooleanField("Aniqlik kiritish so'rovi", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Attachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    file = models.FileField(storage=private_storage, upload_to=RandomName("attachments"))
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    is_deliverable = models.BooleanField("Natija fayli", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    @property
    def is_image(self):
        return self.original_name.lower().endswith(PREVIEW_EXTENSIONS)


class TaskReview(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Qabul qilindi"
        CHANGES = "changes_requested", "Qayta ishlashga qaytarish"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TaskEvent(models.Model):
    """Per-task activity history shown on the task page (status changes, submissions)."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def from_label(self):
        return Task.Status(self.from_status).label if self.from_status else ""

    def to_label(self):
        return Task.Status(self.to_status).label if self.to_status else ""


class Announcement(models.Model):
    title = models.CharField("Sarlavha", max_length=160)
    body = models.TextField("Matn")
    link_label = models.CharField("Tugma matni", max_length=40, blank=True)
    link_url = models.URLField("Tugma havolasi", max_length=500, blank=True)
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    pinned = models.BooleanField("Yuqorida qadash", default=False)
    # Hackaton tafsilotlari (hammasi ixtiyoriy): kartada alohida belgilar bo'lib ko'rinadi.
    event_date = models.DateField("Hackaton sanasi", null=True, blank=True)
    registration_deadline = models.DateField("Ro‘yxatdan o‘tish muddati", null=True, blank=True)
    location = models.CharField("Joy / format", max_length=160, blank=True)
    prize = models.CharField("Mukofot", max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pinned", "-created_at"]
        verbose_name = "Hackaton e'loni"
        verbose_name_plural = "Hackaton e'lonlari"

    def __str__(self):
        return self.title

    @property
    def button_label(self):
        return self.link_label or "Havolani ochish"

    @property
    def registration_left(self):
        """Ro'yxatdan o'tishga necha kun qoldi (0 — bugun oxirgi kun, manfiy — yopilgan, None — muddat yo'q)."""
        if not self.registration_deadline:
            return None
        from django.utils import timezone
        return (self.registration_deadline - timezone.localdate()).days

    @property
    def is_past(self):
        from django.utils import timezone
        return bool(self.event_date and self.event_date < timezone.localdate())


class AnnouncementImage(models.Model):
    """E'lon rasmlari. Soni cheklanmagan; fayllar shaxsiy xotirada, faqat ruxsatli xodimlarga ko'rsatiladi."""

    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        "Rasm", storage=private_storage, upload_to=RandomName("announcements"), validators=IMAGE_VALIDATORS,
        width_field="width", height_field="height",
    )
    width = models.PositiveIntegerField(null=True, editable=False)
    height = models.PositiveIntegerField(null=True, editable=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def save(self, *args, **kwargs):
        downscale_image(self, "image")
        super().save(*args, **kwargs)


CONTRACT_EXTENSIONS = ("pdf", "doc", "docx", "jpg", "jpeg", "png", "webp")
CONTRACT_MAX_MB = 25


def validate_contract(f):
    from pathlib import Path
    from django.core.exceptions import ValidationError

    ext = Path(f.name).suffix.lower().lstrip(".")
    if ext not in CONTRACT_EXTENSIONS:
        raise ValidationError("Shartnoma PDF, Word (DOC/DOCX) yoki rasm (JPG/PNG/WEBP) bo‘lishi kerak.")
    if f.size > CONTRACT_MAX_MB * 1024 * 1024:
        raise ValidationError(f"Shartnoma hajmi {CONTRACT_MAX_MB} MB dan oshmasligi kerak.")


class Partner(models.Model):
    """Kompaniya hamkori: logosi barcha xodimlar bedjigida chiqadi, shartnomasini faqat Asoschi ko'radi."""

    name = models.CharField("Hamkor nomi", max_length=120)
    logo = models.ImageField("Logotip", storage=private_storage, upload_to=RandomName("partners"),
                             validators=IMAGE_VALIDATORS)
    contract = models.FileField("Hamkorlik shartnomasi", storage=private_storage, upload_to=RandomName("partner-contracts"),
                                validators=[validate_contract])
    contract_name = models.CharField(max_length=200, blank=True, editable=False)
    signed_on = models.DateField("Shartnoma sanasi", null=True, blank=True)
    website = models.URLField("Veb-sayt", blank=True)
    note = models.CharField("Izoh", max_length=240, blank=True)
    show_on_badge = models.BooleanField("Bedjikda ko‘rsatish", default=True)
    order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.name

    @property
    def logo_version(self):
        import hashlib
        return hashlib.sha256(self.logo.name.encode()).hexdigest()[:10] if self.logo else ""

    @property
    def contract_ext(self):
        from pathlib import Path
        return Path(self.contract.name).suffix.lower().lstrip(".").upper() if self.contract else ""

    def save(self, *args, **kwargs):
        downscale_image(self, "logo")
        super().save(*args, **kwargs)


class Equipment(models.Model):
    """Ofis jihozi. Asoschi qo'shadi va xodimga biriktiradi; biriktirilgan xodim uning butligiga javobgar."""

    class Category(models.TextChoices):
        LAPTOP = "laptop", "Noutbuk"
        COMPUTER = "computer", "Kompyuter"
        MONITOR = "monitor", "Monitor"
        PHONE = "phone", "Telefon / planshet"
        PERIPHERAL = "peripheral", "Klaviatura, sichqoncha, quloqchin"
        PRINTER = "printer", "Printer / skaner"
        NETWORK = "network", "Tarmoq jihozi"
        CAMERA = "camera", "Kamera / foto-video"
        FURNITURE = "furniture", "Mebel"
        OTHER = "other", "Boshqa"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Omborda (bo‘sh)"
        IN_USE = "in_use", "Foydalanishda"
        REPAIR = "repair", "Ta’mirda"
        BROKEN = "broken", "Nosoz"
        LOST = "lost", "Yo‘qolgan"
        RETIRED = "retired", "Hisobdan chiqarilgan"

    class Condition(models.TextChoices):
        NEW = "new", "Yangi"
        GOOD = "good", "Yaxshi"
        FAIR = "fair", "O‘rtacha"
        POOR = "poor", "Yomon"

    name = models.CharField("Nomi", max_length=140, help_text="Masalan: Acer Aspire 7 noutbuk")
    category = models.CharField("Turi", max_length=20, choices=Category.choices, default=Category.LAPTOP)
    inventory_number = models.CharField("Inventar raqami", max_length=40, unique=True, blank=True,
                                        help_text="Bo‘sh qoldirsangiz avtomatik beriladi (INV-0001).")
    serial_number = models.CharField("Seriya raqami", max_length=80, blank=True)
    specs = models.CharField("Xususiyatlari", max_length=240, blank=True, help_text="Masalan: i7, 16 GB RAM, 512 GB SSD")
    photo = models.ImageField("Rasm", storage=private_storage, upload_to=RandomName("equipment"), blank=True,
                              validators=IMAGE_VALIDATORS)
    status = models.CharField("Holati", max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    condition = models.CharField("Texnik ahvoli", max_length=10, choices=Condition.choices, default=Condition.GOOD)
    location = models.CharField("Joylashuvi", max_length=120, blank=True, help_text="Masalan: 2-qavat, dasturchilar xonasi")
    purchase_date = models.DateField("Sotib olingan sana", null=True, blank=True)
    price = models.DecimalField("Narxi", max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField("Valyuta", max_length=3, default="UZS", choices=[("UZS", "UZS"), ("USD", "USD"), ("EUR", "EUR")])
    warranty_until = models.DateField("Kafolat muddati", null=True, blank=True)
    note = models.TextField("Izoh", blank=True)
    holder = models.ForeignKey(User, verbose_name="Mas’ul xodim", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="equipment")
    assigned_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]

    def __str__(self):
        return f"{self.name} ({self.inventory_number})" if self.inventory_number else self.name

    def get_absolute_url(self):
        return reverse("crm:equipment_detail", args=[self.pk])

    @property
    def photo_version(self):
        import hashlib
        return hashlib.sha256(self.photo.name.encode()).hexdigest()[:10] if self.photo else ""

    @property
    def warranty_active(self):
        return bool(self.warranty_until and self.warranty_until >= timezone.localdate())

    @property
    def icon(self):
        return {"phone": "phone", "printer": "file", "network": "send", "camera": "camera",
                "furniture": "home", "other": "grid"}.get(self.category, "desktop")

    @property
    def needs_ack(self):
        return bool(self.holder_id and not self.acknowledged_at)

    def save(self, *args, **kwargs):
        downscale_image(self, "photo")
        creating = not self.inventory_number
        if creating:
            self.inventory_number = f"tmp-{timezone.now().timestamp()}"
        super().save(*args, **kwargs)
        if creating:
            self.inventory_number = f"INV-{self.pk:04d}"
            Equipment.objects.filter(pk=self.pk).update(inventory_number=self.inventory_number)


class EquipmentEvent(models.Model):
    """Jihoz tarixi: kim, qachon, kimga berdi/qaytardi, holat o'zgarishi va xodim xabarlari."""

    class Kind(models.TextChoices):
        CREATED = "created", "Ro‘yxatga olindi"
        ASSIGNED = "assigned", "Biriktirildi"
        RETURNED = "returned", "Qaytarib olindi"
        ACKNOWLEDGED = "acknowledged", "Xodim qabul qildi"
        ISSUE = "issue", "Muammo xabar qilindi"
        STATUS = "status", "Holati o‘zgardi"
        EDITED = "edited", "Ma’lumot tahrirlandi"

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    person = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


@receiver(post_delete, sender=Equipment)
def _drop_equipment_photo(sender, instance, **kwargs):
    name = instance.photo.name
    if name:
        transaction.on_commit(lambda: private_storage.delete(name))


@receiver(post_delete, sender=Partner)
def _drop_partner_files(sender, instance, **kwargs):
    names = [f.name for f in (instance.logo, instance.contract) if f and f.name]
    if names:
        transaction.on_commit(lambda: [private_storage.delete(n) for n in names])


@receiver(post_delete, sender=AnnouncementImage)
def _drop_announcement_image_file(sender, instance, **kwargs):
    """Rasm yozuvi o'chirilsa (e'lon bilan birga ham), fayl tranzaksiya muvaffaqiyatli tugagach o'chiriladi."""
    name = instance.image.name
    if name:
        transaction.on_commit(lambda: private_storage.delete(name))
