import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.storage import RandomName, private_storage

REACTIONS = ['👍', '❤️', '😂', '😮', '😢', '🔥', '✅', '🙏']


class Message(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='chat_sent')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='chat_received')
    body = models.TextField(max_length=4000, blank=True)
    client_id = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    # Telegram-style features. All optional so existing text messages stay valid.
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')
    forwarded_from = models.CharField(max_length=150, blank=True)
    attachment = models.FileField(storage=private_storage, upload_to=RandomName('chat'), blank=True)
    attachment_name = models.CharField(max_length=200, blank=True)
    attachment_size = models.PositiveBigIntegerField(default=0)
    attachment_image = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    pinned_at = models.DateTimeField(null=True, blank=True)
    pinned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    # Bumped on edit/delete/reaction/pin so open conversations can pick up changes to old messages.
    updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['sender', 'recipient', 'id']),
                   models.Index(fields=['recipient', 'read_at'])]
        constraints = [models.UniqueConstraint(fields=['sender', 'client_id'], name='chat_sender_request_unique'),
                       models.CheckConstraint(condition=~Q(sender=F('recipient')), name='chat_distinct_participants'),
                       models.CheckConstraint(condition=~Q(body='') | ~Q(attachment='') | Q(deleted_at__isnull=False),
                                              name='chat_message_has_content')]

    def touch(self, *fields):
        self.updated_at = timezone.now()
        self.save(update_fields=[*fields, 'updated_at'])


class Reaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    emoji = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['message', 'user'], name='chat_one_reaction_per_user')]


class Presence(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name='chat_presence')
    last_seen = models.DateTimeField(default=timezone.now)
    typing_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    typing_at = models.DateTimeField(null=True, blank=True)
