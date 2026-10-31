"""Загрузка файлов (паритет app/services/storage_service.py).

Проверка magic-bytes (JPEG/PNG/WebP) + лимит MAX_PHOTO_SIZE_MB (env, default 5).
Файлы — в UPLOAD_FOLDER (прод: /data/uploads, dev: djadmin/_uploads).
"""
import os
import uuid
from pathlib import Path

from django.conf import settings

MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
}
WEBP_MAGIC = (b"RIFF", b"WEBP")


class UploadError(ValueError):
    pass


def _upload_root() -> Path:
    root = Path(getattr(settings, "UPLOAD_FOLDER", "") or Path(settings.BASE_DIR) / "_uploads")
    root.mkdir(parents=True, exist_ok=True)
    return root


def detect_extension(data: bytes) -> str | None:
    for magic, ext in MAGIC.items():
        if data.startswith(magic):
            return ext
    if len(data) > 12 and data[:4] == WEBP_MAGIC[0] and data[8:12] == WEBP_MAGIC[1]:
        return ".webp"
    return None


def save_upload(uploaded_file, subdir: str) -> str:
    """Сохранить файл, вернуть URL-путь '/uploads/<subdir>/<uuid>.<ext>'.

    Raises UploadError при неверном типе/размере.
    """
    data = uploaded_file.read()
    max_mb = int(os.getenv("MAX_PHOTO_SIZE_MB", "5"))
    if len(data) > max_mb * 1024 * 1024:
        raise UploadError("Файл больше %d МБ" % max_mb)
    ext = detect_extension(data)
    if ext is None:
        raise UploadError("Допустимы только JPEG, PNG или WebP")
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
