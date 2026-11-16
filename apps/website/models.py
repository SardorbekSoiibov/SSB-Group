from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import SingletonModel, TimeStamped
from apps.core.storage import RandomName
from apps.core.uploads import IMAGE_VALIDATORS, downscale_image


class PublicationStatus(models.TextChoices):
    DRAFT = "draft", "Qoralama"
    PUBLISHED = "published", "Nashr qilingan"
    ARCHIVED = "archived", "Arxiv"


class PublishedQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=PublicationStatus.PUBLISHED)


class Publishable(TimeStamped):
    status = models.CharField(
        "Holat", max_length=12, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT, db_index=True,
    )
    order = models.PositiveIntegerField("Tartib", default=0)
    published_at = models.DateTimeField("Nashr sanasi", null=True, blank=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["order", "-created_at"]

    @property
    def is_published(self):
        return self.status == PublicationStatus.PUBLISHED

    def set_status(self, status):
        self.status = status
        if status == PublicationStatus.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()


def unique_slug(instance, source, field="slug"):
    base = slugify(source)[:70] or "item"
    slug, n = base, 2
    model = type(instance)
    while model.objects.filter(**{field: slug}).exclude(pk=instance.pk).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


class SiteSettings(SingletonModel):
    company_name = models.CharField("Kompaniya nomi", max_length=80, default="SSB Group")
    hero_title = models.CharField("Hero sarlavhasi", max_length=160, default="Biznesingiz uchun ishonchli dasturiy tizimlar")
    hero_text = models.TextField(
        "Hero matni",
        default="SSB Group veb-saytlar, CRM tizimlari, Telegram botlar va biznes jarayonlarini avtomatlashtirish "
        "bo'yicha loyihalarni g'oyadan ishga tushirishgacha olib boradi.",
    )
    intro_title = models.CharField("Kirish sarlavhasi", max_length=160, default="Biz kimmiz")
    intro_text = models.TextField("Kirish matni", blank=True)
    about_text = models.TextField("Kompaniya haqida", blank=True)
    mission = models.TextField("Missiya", blank=True)
    vision = models.TextField("Vizyon", blank=True)
    philosophy = models.TextField("Ishlash falsafasi", blank=True)
    team_structure = models.TextField("Jamoa tuzilmasi", blank=True)
    objectives = models.TextField("Uzoq muddatli maqsadlar", blank=True)
    email = models.EmailField("Email", blank=True)
    phone = models.CharField("Telefon", max_length=40, blank=True)
    address = models.CharField("Manzil", max_length=200, blank=True)
    working_hours = models.CharField("Ish vaqti", max_length=100, blank=True)
    telegram = models.URLField("Telegram havolasi", blank=True)
    instagram = models.URLField("Instagram havolasi", blank=True)
    linkedin = models.URLField("LinkedIn havolasi", blank=True)
    github = models.URLField("GitHub havolasi", blank=True)
    footer_text = models.CharField("Footer matni", max_length=200, blank=True)
    seo_title = models.CharField("SEO sarlavha", max_length=70, default="SSB Group — IT kompaniya")
    seo_description = models.CharField(
        "SEO tavsif", max_length=170,
        default="Veb-saytlar, CRM tizimlari, Telegram botlar va biznesni avtomatlashtirish. SSB Group — Toshkent.",
    )
    og_image = models.ImageField("Ijtimoiy tarmoq rasmi", upload_to=RandomName("og"), blank=True, validators=IMAGE_VALIDATORS)
    privacy_text = models.TextField("Maxfiylik siyosati", blank=True)

    class Meta:
        verbose_name = "Sayt sozlamalari"

    def __str__(self):
        return "Sayt sozlamalari"


class Highlight(Publishable):
    """Short structured content blocks for the home and about pages."""

    class Kind(models.TextChoices):
        VALUE = "value", "Qadriyat"
        REASON = "reason", "Nega SSB Group"
        PROCESS = "process", "Ish jarayoni bosqichi"
        MILESTONE = "milestone", "Kompaniya tarixi"
        EXPERTISE = "expertise", "Texnologik tajriba"

    kind = models.CharField("Turi", max_length=20, choices=Kind.choices, db_index=True)
    title = models.CharField("Sarlavha", max_length=120)
    body = models.TextField("Matn", blank=True)
    date_label = models.CharField("Sana (tarix uchun)", max_length=40, blank=True)

    class Meta(Publishable.Meta):
        verbose_name = "Blok"
        verbose_name_plural = "Bloklar"

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"


class Technology(models.Model):
    name = models.CharField("Nomi", max_length=60, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Texnologiya"
        verbose_name_plural = "Texnologiyalar"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Service(Publishable):
    class Icon(models.TextChoices):
        WEB = "web", "Veb"
        CRM = "crm", "CRM"
        BOT = "bot", "Bot"
        DESIGN = "design", "Dizayn"
        AUTOMATION = "automation", "Avtomatlashtirish"
        CODE = "code", "Dasturlash"
        PRODUCT = "product", "Mahsulot"

    title = models.CharField("Nomi", max_length=120)
    slug = models.SlugField(unique=True, blank=True)
    summary = models.CharField("Qisqa tavsif", max_length=220)
    description = models.TextField("To'liq tavsif", blank=True)
    icon = models.CharField("Belgi", max_length=20, choices=Icon.choices, default=Icon.CODE)
    image = models.ImageField("Rasm", upload_to=RandomName("services"), blank=True, validators=IMAGE_VALIDATORS)
    benefits = models.TextField("Afzalliklar", blank=True, help_text="Har bir afzallik alohida qatorda.")
    technologies = models.ManyToManyField(Technology, verbose_name="Texnologiyalar", blank=True, related_name="services")
    seo_description = models.CharField("SEO tavsif", max_length=170, blank=True)

    class Meta(Publishable.Meta):
        verbose_name = "Xizmat"
        verbose_name_plural = "Xizmatlar"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        downscale_image(self, "image")
        super().save(*args, **kwargs)

    def benefit_list(self):
        return [b.strip(" -•") for b in self.benefits.splitlines() if b.strip()]

    def get_absolute_url(self):
        return reverse("website:service_detail", args=[self.slug])


class PortfolioCategory(models.Model):
    name = models.CharField("Nomi", max_length=80, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    order = models.PositiveIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Portfolio kategoriyasi"
        verbose_name_plural = "Portfolio kategoriyalari"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class PortfolioProject(Publishable):
    class ProjectState(models.TextChoices):
        COMPLETED = "completed", "Yakunlangan"
        SUPPORTED = "supported", "Qo'llab-quvvatlanmoqda"
        ONGOING = "ongoing", "Davom etmoqda"

    title = models.CharField("Nomi", max_length=140)
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(
        PortfolioCategory, verbose_name="Kategoriya", null=True, blank=True, on_delete=models.SET_NULL, related_name="projects",
    )
    cover = models.ImageField(
        "Muqova", upload_to=RandomName("portfolio"), blank=True, validators=IMAGE_VALIDATORS,
        width_field="cover_width", height_field="cover_height",
    )
    cover_width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    cover_height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    summary = models.CharField("Qisqa tavsif", max_length=240)
    description = models.TextField("Batafsil tavsif", blank=True)
    case_study = models.TextField("Keys: vazifa, yechim, natija", blank=True)
    technologies = models.ManyToManyField(Technology, verbose_name="Texnologiyalar", blank=True, related_name="portfolio")
    services = models.ManyToManyField(Service, verbose_name="Xizmatlar", blank=True, related_name="portfolio")
    client_name = models.CharField("Mijoz nomi", max_length=120, blank=True)
    show_client = models.BooleanField("Mijoz nomini ko'rsatishga ruxsat bor", default=False)
    project_state = models.CharField("Loyiha holati", max_length=12, choices=ProjectState.choices, default=ProjectState.COMPLETED)
    completed_on = models.DateField("Yakunlangan sana", null=True, blank=True)
    live_url = models.URLField("Sayt yoki demo havolasi", blank=True)
    featured = models.BooleanField("Bosh sahifada ko'rsatish", default=False)
    source_project = models.OneToOneField(
        "crm.Project", verbose_name="Ichki loyiha", null=True, blank=True, on_delete=models.SET_NULL, related_name="portfolio_entry",
    )
    seo_description = models.CharField("SEO tavsif", max_length=170, blank=True)

    class Meta(Publishable.Meta):
        verbose_name = "Portfolio loyihasi"
        verbose_name_plural = "Portfolio"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        downscale_image(self, "cover")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("website:project_detail", args=[self.slug])

    @property
    def public_client(self):
        return self.client_name if self.show_client else ""


class PortfolioImage(models.Model):
    project = models.ForeignKey(PortfolioProject, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        "Rasm", upload_to=RandomName("portfolio"), validators=IMAGE_VALIDATORS,
        width_field="width", height_field="height",
    )
    width = models.PositiveIntegerField(null=True, editable=False)
    height = models.PositiveIntegerField(null=True, editable=False)
    caption = models.CharField("Izoh", max_length=160, blank=True)
    order = models.PositiveIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "pk"]

    def save(self, *args, **kwargs):
        downscale_image(self, "image")
        super().save(*args, **kwargs)


class TeamMember(Publishable):
    """Public team profile. Separate from the internal account so only approved fields go public."""

    user = models.OneToOneField(
        "accounts.User", verbose_name="Xodim hisobi", null=True, blank=True, on_delete=models.SET_NULL, related_name="public_profile",
    )
    name = models.CharField("Ism familiya", max_length=120)
    public_title = models.CharField("Ommaviy lavozim", max_length=120)
    bio = models.TextField("Qisqa biografiya", blank=True)
    photo = models.ImageField(
        "Rasm", upload_to=RandomName("team"), blank=True, validators=IMAGE_VALIDATORS,
        width_field="photo_width", height_field="photo_height",
    )
    photo_width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    photo_height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    skills = models.CharField("Ko'nikmalar", max_length=255, blank=True, help_text="Vergul bilan ajrating.")
    linkedin = models.URLField("LinkedIn", blank=True)
    github = models.URLField("GitHub", blank=True)
    telegram = models.URLField("Telegram", blank=True)
    website = models.URLField("Shaxsiy sayt", blank=True)

    class Meta(Publishable.Meta):
        verbose_name = "Jamoa a'zosi"
        verbose_name_plural = "Jamoa"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        downscale_image(self, "photo")
        super().save(*args, **kwargs)

    def skill_list(self):
        return [s.strip() for s in self.skills.split(",") if s.strip()]

    @property
    def initials(self):
        return "".join(p[0] for p in self.name.split()[:2]).upper()


class Testimonial(Publishable):
    author = models.CharField("Muallif", max_length=120)
    author_title = models.CharField("Lavozimi", max_length=120, blank=True)
    company = models.CharField("Kompaniya", max_length=120, blank=True)
    quote = models.TextField("Fikr")
    project = models.ForeignKey(
        PortfolioProject, verbose_name="Loyiha", null=True, blank=True, on_delete=models.SET_NULL, related_name="testimonials",
    )

    class Meta(Publishable.Meta):
        verbose_name = "Mijoz fikri"
        verbose_name_plural = "Mijozlar fikrlari"

    def __str__(self):
        return f"{self.author} — {self.company}"
