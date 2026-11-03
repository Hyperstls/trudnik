"""Загрузка файлов (паритет app/services/storage_service.py).

Проверка magic-bytes (JPEG/PNG/WebP; PDF — только для документов верификации)
+ лимит MAX_PHOTO_SIZE_MB (env, default 5).
Файлы — в UPLOAD_FOLDER (прод: /data/uploads, dev: djadmin/_uploads).
"""
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext as _

MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
}
WEBP_MAGIC = (b"RIFF", b"WEBP")
PDF_MAGIC = b"%PDF-"


class UploadError(ValueError):
    pass


def _upload_root() -> Path:
    root = Path(getattr(settings, "UPLOAD_FOLDER", "") or Path(settings.BASE_DIR) / "_uploads")
    root.mkdir(parents=True, exist_ok=True)
    return root


def detect_extension(data: bytes, allow_pdf: bool = False) -> str | None:
    """Расширение по magic bytes: JPEG/PNG/WebP всегда, PDF — при allow_pdf."""
    if allow_pdf and data.startswith(PDF_MAGIC):
        return ".pdf"
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            return ext
    if len(data) > 12 and data[:4] == WEBP_MAGIC[0] and data[8:12] == WEBP_MAGIC[1]:
        return ".webp"
    return None


def save_upload(uploaded_file, subdir: str, allow_pdf: bool = False) -> str:
    """Сохранить файл, вернуть URL-путь '/uploads/<subdir>/<uuid>.<ext>'.

    PDF принимается только при allow_pdf=True (документы верификации).
    Raises UploadError при неверном типе/размере.
    """
    data = uploaded_file.read()
    max_mb = int(os.getenv("MAX_PHOTO_SIZE_MB", "5"))
    if len(data) > max_mb * 1024 * 1024:
        raise UploadError(_("Файл больше %d МБ") % max_mb)
    ext = detect_extension(data, allow_pdf=allow_pdf)
    if ext is None:
        allowed = _("PDF, JPEG, PNG или WebP") if allow_pdf else _("JPEG, PNG или WebP")
        raise UploadError(_("Допустимы только %s") % allowed)
    folder = _upload_root() / subdir
    folder.mkdir(parents=True, exist_ok=True)
    name = "%s%s" % (uuid.uuid4().hex, ext)
    (folder / name).write_bytes(data)
    return "/uploads/%s/%s" % (subdir, name)


def resolve_upload_url(relative_path: str) -> Path | None:
    """Безопасный резолв /uploads/<...> → физический путь (без path traversal)."""
    root = _upload_root().resolve()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents and candidate != root:
        return None
    return candidate if candidate.is_file() else None


def delete_upload_url(url: str) -> bool:
    """Удалить файл по URL-пути '/uploads/<subdir>/<name>' (152-ФЗ ст.21, P1-14).

    Query/fragment отбрасываются; путь резолвится через resolve_upload_url,
    поэтому за пределы upload root выйти нельзя. Ошибки/отсутствие файла → False.
    """
    marker = "/uploads/"
    if not isinstance(url, str) or marker not in url:
        return False
    relative = url.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0]
    if not relative:
        return False
    try:
        path = resolve_upload_url(relative)
        if path is None:
            return False
        path.unlink()
        return True
    except (OSError, ValueError):
        return False
