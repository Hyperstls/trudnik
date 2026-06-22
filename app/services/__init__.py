"""Сервисы приложения: уведомления, загрузка файлов, рейтинги и др."""

from app.services.storage_service import (
    MAX_UPLOAD_SIZE,
    upload_to_storage,
    upload_photo,
    delete_from_storage,
)

from app.services.ratings_service import (
    update_rating,
    get_user_rating,
)

__all__ = [
    'MAX_UPLOAD_SIZE',
    'upload_to_storage',
    'upload_photo',
    'delete_from_storage',
    'update_rating',
    'get_user_rating',
]
