from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

# iOS System Blue — boshqaruv panelining standart asosiy rangi.
DEFAULT_ACCENT = "#007aff"
ACCENT_PRESETS = [
    ("#007aff", "Ko‘k (standart)"),
    ("#5856d6", "Indigo"),
    ("#af52de", "Binafsha"),
    ("#ff2d55", "Pushti"),
    ("#ff3b30", "Qizil"),
    ("#ff9500", "To‘q sariq"),
    ("#34c759", "Yashil"),
    ("#30b0c7", "Firuza"),
    ("#8e8e93", "Grafit"),
]
accent_validator = RegexValidator(r"^#[0-9a-f]{6}$", "Rang #RRGGBB ko‘rinishida bo‘lishi kerak.")


class TimeStamped(models.Model):
    created_at = models.DateTimeField("Yaratilgan", auto_now_add=True)
    updated_at = models.DateTimeField("Yangilangan", auto_now=True)

    class Meta:
        abstract = True


class SingletonModel(models.Model):
    """A table that always holds exactly one row (pk=1)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Singleton settings cannot be deleted.")

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


DEFAULT_ATTACHMENT_EXTENSIONS = [
    "pdf", "png", "jpg", "jpeg", "webp", "svg", "fig", "zip", "txt", "md",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "json",
]


def default_attachment_extensions():
    return list(DEFAULT_ATTACHMENT_EXTENSIONS)


class WorkspaceSettings(SingletonModel):
    """Operational settings for the management system."""

    company_name = models.CharField('Kompaniya nomi',max_length=140,default='SSB Group')
    default_currency = models.CharField('Asosiy valyuta',max_length=3,choices=[('UZS','UZS'),('USD','USD'),('EUR','EUR')],default='UZS')
    date_format = models.CharField('Sana ko‘rinishi',max_length=12,choices=[('d.m.Y','31.12.2026'),('Y-m-d','2026-12-31'),('d/m/Y','31/12/2026')],default='d.m.Y')
    company_share_percent = models.DecimalField('Yangi kelishuv uchun kompaniya ulushi (%)',max_digits=7,decimal_places=4,default=30,validators=[MinValueValidator(0),MaxValueValidator(100)],help_text='Faqat yangi kelishuvga boshlang‘ich qiymat. Tasdiqlangan tarix o‘zgarmaydi.')
    archive_max_mb = models.PositiveSmallIntegerField('Loyiha arxivi hajmi (MB)',default=50,validators=[MinValueValidator(1),MaxValueValidator(50)])

    upload_max_mb = models.PositiveSmallIntegerField(
        "Fayl hajmi chegarasi (MB)", default=20, validators=[MinValueValidator(1), MaxValueValidator(25)]
    )
    allowed_extensions = ArrayField(
        models.CharField(max_length=10), verbose_name="Ruxsat etilgan fayl turlari",
        default=default_attachment_extensions,
        help_text="Vergul bilan: pdf, png, zip …",
    )
    reminder_days_before = models.PositiveSmallIntegerField(
        "Muddatdan necha kun oldin eslatish", default=2, validators=[MaxValueValidator(14)]
    )
    require_project_start_approval = models.BooleanField(
        "Loyihani boshlash uchun tasdiq talab qilinsin", default=True,
        help_text="Yoqilgan bo'lsa, loyiha «Rejalashtirish»dan «Tasdiq kutilmoqda» orqali boshlanadi.",
    )
    accent_color = models.CharField(
        "Boshqaruv paneli asosiy rangi", max_length=7, default=DEFAULT_ACCENT, validators=[accent_validator],
        help_text="Butun kompaniya uchun bitta. Faqat direktor (Asoschi) o‘zgartira oladi.",
    )

    class Meta:
        verbose_name = "Tizim sozlamalari"

    def __str__(self):
        return "Tizim sozlamalari"

    @property
    def extensions(self):
        return [e.lower().lstrip(".") for e in self.allowed_extensions]
