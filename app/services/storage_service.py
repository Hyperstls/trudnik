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

    upload_dir = _os.path.join(
        current_app.config.get('UPLOAD_FOLDER', 'uploads'), bucket
    )
    _os.makedirs(upload_dir, exist_ok=True)

    full_path = _os.path.join(upload_dir, file_path)
    try:
        with open(full_path, 'wb') as f:
            f.write(file_data)
        logger.info(
            'File saved: %s/%s (%d bytes)', bucket, file_path, len(file_data)
        )
        return f'/uploads/{bucket}/{file_path}?t={int(time.time())}'
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
    upload_dir = _os.path.join(
        current_app.config.get('UPLOAD_FOLDER', 'uploads'), bucket
    )
    full_path = _os.path.join(upload_dir, file_path)

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
