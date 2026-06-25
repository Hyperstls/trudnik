"""Сервис рейтингов: update_rating, get_user_rating."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def update_rating(user_id: str, _new_rating: float) -> None:
    """Обновить средний рейтинг пользователя.

    Args:
        user_id: UUID пользователя.
        _new_rating: зарезервирован (новый рейтинг, один отзыв).

    Использует admin_request для обхода RLS (вызывается от лица rat'ера, не владельца профиля).
    """
    from app.utils.postgrest_client import postgrest_admin_request

    ratings_resp = postgrest_admin_request(
        'GET',
        f'ratings?rated_user_id=eq.{user_id}&select=rating'
    )
    if not ratings_resp.ok or not ratings_resp.json():
        return

    ratings_list = ratings_resp.json()
    total = sum(r['rating'] for r in ratings_list)
    avg = round(total / len(ratings_list), 1)

    postgrest_admin_request(
        'PATCH',
        f'profiles?id=eq.{user_id}',
        json={'rating': avg}
    )


def get_user_rating(user_id: str) -> Optional[Dict[str, Any]]:
    """Получить агрегированный рейтинг пользователя.

    Args:
        user_id: UUID пользователя.

    Returns:
        Словарь с полями:
          - average_rating: средний рейтинг (float)
          - total_ratings: количество оценок (int)
          - breakdown: распределение по звёздам {1: count, 2: count, ...}
        Или None при ошибке.
    """
    from app.utils.postgrest_client import postgrest_request

    resp = postgrest_request(
        'GET',
        f'ratings?rated_user_id=eq.{user_id}&select=rating'
    )
    if not resp.ok or not resp.json():
        return None

    ratings_list: List[Dict[str, Any]] = resp.json()
    if not ratings_list:
        return {
            'average_rating': 0.0,
            'total_ratings': 0,
            'breakdown': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        }

    total = sum(r['rating'] for r in ratings_list)
    avg = round(total / len(ratings_list), 1)

    breakdown: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in ratings_list:
        star = int(r['rating'])
        if 1 <= star <= 5:
            breakdown[star] = breakdown.get(star, 0) + 1

    return {
        'average_rating': avg,
        'total_ratings': len(ratings_list),
        'breakdown': breakdown,
    }
