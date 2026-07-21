"""Сервис рейтингов: get_user_rating.

A5: Функция update_rating упрощена - триггер recompute_profile_rating()
автоматически пересчитывает рейтинг при INSERT/UPDATE/DELETE в таблице ratings.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def update_rating(user_id: str, _new_rating: float) -> None:
    """Обновить средний рейтинг пользователя.
    
    A5: DEPRECATED - триггер recompute_profile_rating() теперь автоматически
    пересчитывает рейтинг при изменении таблицы ratings.
    
    Эта функция оставлена для обратной совместимости, но больше не выполняет
    read-modify-write операцию (которая была подвержена race condition).

    Args:
        user_id: UUID пользователя.
        _new_rating: зарезервирован (новый рейтинг, один отзыв).
    """
    # Триггер trg_recompute_rating автоматически обновляет profiles.rating
    # при INSERT/UPDATE/DELETE в ratings. Ничего делать не нужно.
    logger.debug('update_rating called for user %s (trigger handles recomputation)', user_id)


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
