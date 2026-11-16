"""Ishga kela olmaslik so‘rovlari: xodim sabab yozadi, asoschi tasdiqlaydi yoki rad etadi."""

from django.conf import settings
from django.db import models
from django.db.models import Q

USER = settings.AUTH_USER_MODEL


class AbsenceRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ko‘rib chiqilmoqda"
        APPROVED = "approved", "Tasdiqlandi"
        REJECTED = "rejected", "Rad etildi"

    employee = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="absence_requests")
    date_from = models.DateField("Qaysi kundan")
    date_to = models.DateField("Qaysi kungacha")
    reason = models.TextField("Sabab")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    decided_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decision_note = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "enterprise"
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=Q(date_to__gte=models.F("date_from")), name="enterprise_absence_range")]

    def __str__(self):
        return f"{self.employee} · {self.date_from}"

    @property
    def days(self):
        return (self.date_to - self.date_from).days + 1
