import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property


@deconstructible
class PrivateStorage(FileSystemStorage):
    """Files outside MEDIA_ROOT, with no public URL. Served only by permission-checked views."""

    def __init__(self):
        super().__init__(base_url=None)

    @cached_property
    def base_location(self):
        # Resolved lazily so override_settings(PRIVATE_MEDIA_ROOT=...) isolates tests from real files.
        return settings.PRIVATE_MEDIA_ROOT

    def _clear_cached_properties(self, setting, **kwargs):
        super()._clear_cached_properties(setting, **kwargs)
        if setting == "PRIVATE_MEDIA_ROOT":
            self.__dict__.pop("base_location", None)
            self.__dict__.pop("location", None)

    def url(self, name):
        raise AttributeError("Private files have no public URL.")


private_storage = PrivateStorage()


@deconstructible
class RandomName:
    """upload_to callable that stores files under a random name, keeping the extension."""

    def __init__(self, prefix):
        self.prefix = prefix

    def __call__(self, instance, filename):
        ext = Path(filename).suffix.lower()[:10]
        return f"{self.prefix}/{uuid.uuid4().hex}{ext}"

    def __eq__(self, other):
        return isinstance(other, RandomName) and other.prefix == self.prefix
