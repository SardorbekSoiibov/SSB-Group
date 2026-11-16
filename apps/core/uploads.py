"""Upload validation shared by public CMS images and private CRM attachments."""

from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import FileExtensionValidator
from PIL import Image

IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
MAX_IMAGE_MB = 8
MAX_IMAGE_SIDE = 2400

validate_image_extension = FileExtensionValidator(IMAGE_EXTENSIONS)


def validate_image_size(f):
    if f.size > MAX_IMAGE_MB * 1024 * 1024:
        raise ValidationError(f"Rasm hajmi {MAX_IMAGE_MB} MB dan oshmasligi kerak.")


IMAGE_VALIDATORS = [validate_image_extension, validate_image_size]


CONTRACT_EXTENSIONS = ["pdf", "docx", "doc", "jpg", "jpeg", "png"]
MAX_CONTRACT_MB = 15
# Fayl nomiga emas, mazmuniga qaraymiz: kengaytmasi o'zgartirilgan boshqa fayl qabul qilinmaydi.
CONTRACT_SIGNATURES = {
    "pdf": (b"%PDF-",), "docx": (b"PK\x03\x04",), "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",), "png": (b"\x89PNG\r\n\x1a\n",),
}


def validate_contract(f):
    ext = Path(f.name).suffix.lower().lstrip(".")
    if ext not in CONTRACT_EXTENSIONS:
        raise ValidationError("Shartnoma PDF, Word (DOC, DOCX) yoki rasm (JPG, PNG) bo‘lsin.")
    if f.size > MAX_CONTRACT_MB * 1024 * 1024:
        raise ValidationError(f"Shartnoma fayli {MAX_CONTRACT_MB} MB dan oshmasin.")
    if getattr(f, "_committed", True) is False or hasattr(f, "content_type"):
        position = f.tell() if hasattr(f, "tell") else 0
        f.seek(0)
        head = f.read(16)
        f.seek(position)
        if not head.startswith(CONTRACT_SIGNATURES[ext]):
            raise ValidationError("Fayl mazmuni uning turiga mos emas. Asl PDF, Word yoki rasm faylini yuklang.")


def validate_attachment(f, workspace):
    ext = Path(f.name).suffix.lower().lstrip(".")
    if ext not in workspace.extensions:
        raise ValidationError(f"«.{ext}» turidagi fayllarga ruxsat yo'q.")
    if f.size > workspace.upload_max_mb * 1024 * 1024:
        raise ValidationError(f"Fayl hajmi {workspace.upload_max_mb} MB dan oshmasligi kerak.")


def downscale_image(instance, field_name):
    """Shrink oversized uploads in place so public pages never ship huge originals."""
    field_file = getattr(instance, field_name)
    if not field_file or getattr(field_file, "_committed", True):
        return
    field_file.seek(0)
    img = Image.open(field_file)
    if max(img.size) <= MAX_IMAGE_SIDE:
        field_file.seek(0)
        return
    fmt = (img.format or "JPEG").upper()
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format=fmt, quality=86, optimize=True)
    name = field_file.name
    field_file.file = ContentFile(buf.getvalue(), name=name)
    instance._meta.get_field(field_name).update_dimension_fields(instance, force=True)
