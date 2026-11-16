from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only record of sensitive operations."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events",
    )
    action = models.CharField("Amal", max_length=60, db_index=True)
    target_type = models.CharField(max_length=60, db_index=True)
    target_id = models.CharField(max_length=40, blank=True, db_index=True)
    target_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit yozuvi"
        verbose_name_plural = "Audit jurnali"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target_repr}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("Audit events are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit events cannot be deleted.")
