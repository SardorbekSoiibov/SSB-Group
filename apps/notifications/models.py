from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        TASK_ASSIGNED = "task_assigned", "Yangi vazifa"
        DEADLINE_SOON = "deadline_soon", "Yaqinlashayotgan muddat"
        OVERDUE = "overdue", "Muddati o'tgan"
        COMMENT = "comment", "Yangi izoh"
        SUBMITTED = "submitted", "Ish topshirildi"
        REVIEWED = "reviewed", "Ish ko'rib chiqildi"
        APPROVAL = "approval", "Tasdiq so'rovi"
        PROJECT_STATUS = "project_status", "Loyiha holati"
        INQUIRY = "inquiry", "Yangi murojaat"
        ANNOUNCEMENT = "announcement", "E'lon"
        CHAT = "chat_message", "Chat xabari"
        EQUIPMENT = "equipment", "Jihozlar"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True)
    dedupe_key = models.CharField(max_length=120, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedupe_key"], condition=~models.Q(dedupe_key=""), name="uniq_notification_dedupe",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def safe_url(self):
        from django.utils.http import url_has_allowed_host_and_scheme
        from urllib.parse import unquote
        value = self.url
        decoded = unquote(value)
        if (value.startswith('/management/') and '\\' not in decoded
                and not any(ord(char) < 32 for char in decoded)
                and url_has_allowed_host_and_scheme(value, allowed_hosts=set())):
            return value
        from django.urls import reverse
        return reverse('crm:notifications')

    @property
    def priority(self):
        if self.kind in [self.Kind.OVERDUE,self.Kind.APPROVAL]:
            return 'high'
        if self.kind in [self.Kind.DEADLINE_SOON,self.Kind.SUBMITTED]:
            return 'medium'
        return 'normal'

    @property
    def priority_label(self):
        return {'high':'Muhim','medium':'E’tibor talab qiladi','normal':'Oddiy'}[self.priority]


class ClearedReminder(models.Model):
    """Today's deadline reminders a person cleared, so polling does not recreate them. Keeps ids only, never text."""

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    dedupe_key = models.CharField(max_length=120)
    cleared_on = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["recipient", "dedupe_key"], name="uniq_cleared_reminder")]


class TelegramConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    chat_id = models.BigIntegerField(unique=True, null=True, blank=True)
    link_hash = models.CharField(max_length=64, blank=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=False)
    bot_fingerprint = models.CharField(max_length=64, blank=True)


class ChannelCheck(models.Model):
    channel = models.CharField(max_length=20, unique=True)
    fingerprint = models.CharField(max_length=64)
    checked_at = models.DateTimeField(auto_now=True)
    successful = models.BooleanField(default=False)


class TelegramCursor(models.Model):
    offset = models.BigIntegerField(default=0)
    bot_fingerprint = models.CharField(max_length=64, blank=True)


class TelegramAdmin(models.Model):
    """Bot admini: admin panel, kanal qo'shish, post yuborish va yangi admin qo'shish huquqi.

    .env dagi TELEGRAM_ADMIN_IDS — asosiy adminlar: bot orqali o'chirib bo'lmaydi.
    """
    telegram_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=200, blank=True)
    added_by = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class TelegramChannel(models.Model):
    """Bot admin bo'lgan va postlar yuboriladigan kanal yoki guruh."""
    chat_id = models.BigIntegerField(unique=True)
    title = models.CharField(max_length=255)
    username = models.CharField(max_length=64, blank=True)
    added_by = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['title']

    @property
    def label(self):
        return f'{self.title} (@{self.username})' if self.username else self.title


class TelegramBotState(models.Model):
    """Admin bilan suhbatning qaysi bosqichda ekanligi (masalan: post matnini kutyapti)."""
    telegram_id = models.BigIntegerField(unique=True)
    step = models.CharField(max_length=40, blank=True)
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class TelegramPost(models.Model):
    """Kanalga yuborilgan postlar jurnali."""
    channel = models.ForeignKey(TelegramChannel, null=True, on_delete=models.SET_NULL, related_name='posts')
    channel_title = models.CharField(max_length=255)
    message_id = models.BigIntegerField(null=True, blank=True)
    kind = models.CharField(max_length=10, default='text')
    text = models.TextField(blank=True)
    buttons = models.JSONField(default=list, blank=True)
    sent_by = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ExternalDelivery(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='deliveries')
    channel = models.CharField(max_length=20, choices=[('email', 'Email'), ('telegram', 'Telegram')])
    status = models.CharField(max_length=20, default='pending')
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['notification', 'channel'], name='unique_external_delivery')]
