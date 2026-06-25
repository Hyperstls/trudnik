"""Сервис загрузки файлов: upload_to_storage, upload_photo, delete_from_storage."""

import logging
import os as _os
import time
import uuid
from typing import Optional

from flask import current_app

from app.config import Config

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = Config.MAX_PHOTO_SIZE_MB * 1024 * 1024  # 5 MB

# Разрешённые MIME-типы для фотографий
_ALLOWED_PHOTO_MIME_TYPES = frozenset({
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
})

# Сигнатуры файлов для fallback-проверки MIME (если python-magic недоступен)
_ALLOWED_SIGNATURES = {
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'RIFF': 'image/webp',  # WebP внутри RIFF контейнера
}


def _check_mime_by_signature(data: bytes) -> Optional[str]:
    """Проверить MIME-тип по сигнатурам (magic bytes)."""
    for sig, mime in _ALLOWED_SIGNATURES.items():
        if data[:len(sig)] == sig:
            return mime
    return None


def _detect_mime(data: bytes) -> Optional[str]:
    """Определить MIME-тип файла: пробуем python-magic, затем сигнатуры."""
    try:
        import magic
        return magic.from_buffer(data[:2048], mime=True)
    except Exception:
        pass
    return _check_mime_by_signature(data)


def _validate_path(file_path: str) -> Optional[str]:
    """Проверить путь на path traversal и нуль-байты.
    
    Returns:
        Безопасный нормализованный путь или None при обнаружении атаки.
    """
    if '\x00' in file_path:
        logger.warning('Path traversal attempt blocked (null byte): %s', file_path)
        return None
    safe_path = _os.path.normpath(file_path)
    if safe_path.startswith(('..', '/', '\\')) or _os.path.isabs(safe_path):
        logger.warning('Path traversal attempt blocked: %s', file_path)
        return None
    return safe_path


def upload_to_storage(bucket: str, file_path: str, file_data: bytes,
                       content_type: str) -> Optional[str]:
    """Сохранить файл в локальное хранилище (Amvera-совместимое).

    Файлы сохраняются в UPLOAD_FOLDER/<bucket>/<file_path>.
    Возвращает относительный URL для доступа через /uploads/<bucket>/<file_path>.

    Args:
        bucket: имя бакета (напр. 'avatars', 'verification-docs').
        file_path: путь к файлу внутри бакета.
        file_data: бинарные данные файла.
        content_type: MIME-тип файла (не используется при локальном хранении).

    Returns:
        URL загруженного файла или None при ошибке.
    """
    if file_data and len(file_data) > MAX_UPLOAD_SIZE:
        logger.warning('Upload rejected: file too large (%d bytes)', len(file_data))
        return None

    # Path traversal защита
    safe_path = _validate_path(file_path)
    if safe_path is None:
        return None

    upload_dir = _os.path.join(
        current_app.config.get('UPLOAD_FOLDER', 'uploads'), bucket
    )
    # Разрешить абсолютный путь (защита от race condition смены рабочей директории)
    upload_dir = _os.path.abspath(upload_dir)
    _os.makedirs(upload_dir, exist_ok=True)

    full_path = _os.path.join(upload_dir, safe_path)
    full_path = _os.path.abspath(full_path)
    # Создать все промежуточные директории для файла (например, user_id/)
    dir_path = _os.path.dirname(full_path)
    logger.debug('Ensuring directory exists: %s', dir_path)
    _os.makedirs(dir_path, exist_ok=True)
    # Двойная проверка: убедиться, что директория действительно создалась
    if not _os.path.isdir(dir_path):
        logger.error('Failed to create directory (isdir=False after makedirs): %s', dir_path)
        return None
    try:
        with open(full_path, 'wb') as f:
            f.write(file_data)
        logger.info(
            'File saved: %s/%s (%d bytes)', bucket, safe_path, len(file_data)
        )
        return f'/uploads/{bucket}/{safe_path}?t={int(time.time())}'
    except OSError as e:
        logger.error('File save error: %s', e)
        return None


def upload_photo(file_data: bytes, bucket: str = 'avatars',
                 folder: str = 'photos') -> Optional[str]:
    """Загрузить фотографию в указанный бакет.

    Генерирует уникальное имя файла с расширением .jpg.
    Проверяет размер и MIME-тип (допустимы JPEG, PNG, GIF, WebP, BMP).

    Args:
        file_data: бинарные данные файла.
        bucket: имя бакета (по умолчанию 'avatars').
        folder: подпапка внутри бакета (по умолчанию 'photos').

    Returns:
        URL загруженного файла или None при ошибке.
    """
    if not file_data:
        logger.warning('upload_photo: empty file_data')
        return None

    if len(file_data) > MAX_UPLOAD_SIZE:
        logger.warning('upload_photo: file too large (%d bytes, max %d)',
                       len(file_data), MAX_UPLOAD_SIZE)
        return None

    # Проверка MIME-типа (python-magic или fallback по сигнатурам)
    detected_mime = _detect_mime(file_data)
    if detected_mime and detected_mime not in _ALLOWED_PHOTO_MIME_TYPES:
        logger.warning('Photo upload rejected: invalid MIME type %s', detected_mime)
        return None

    # Генерируем уникальное имя файла
    unique_id = uuid.uuid4().hex[:12]
    file_path = f'{folder}/{unique_id}.jpg'

    return upload_to_storage(bucket, file_path, file_data, 'image/jpeg')


def delete_from_storage(bucket: str, file_path: str) -> bool:
    """Удалить файл из локального хранилища.

    Args:
        bucket: имя бакета (напр. 'avatars', 'verification-docs').
        file_path: путь к файлу внутри бакета.

    Returns:
        True если файл удалён успешно, False если файл не найден или ошибка.
    """
    # Path traversal защита
    safe_path = _validate_path(file_path)
    if safe_path is None:
        return False

    upload_dir = _os.path.join(
        current_app.config.get('UPLOAD_FOLDER', 'uploads'), bucket
    )
    full_path = _os.path.join(upload_dir, safe_path)

    try:
        if _os.path.exists(full_path):
            _os.remove(full_path)
            logger.info('File deleted: %s/%s', bucket, file_path)
            return True
        else:
            logger.warning('File not found for deletion: %s/%s', bucket, file_path)
            return False
    except OSError as e:
        logger.error('File delete error: %s', e)
        return False
