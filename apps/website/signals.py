from django.db.models.signals import m2m_changed, post_delete, post_save

from . import cache


def _bump(sender, **kwargs):
    if sender._meta.app_label == "website":
        cache.bump()


def connect():
    for signal in (post_save, post_delete, m2m_changed):
        signal.connect(_bump, dispatch_uid=f"website-cache-{signal}")
