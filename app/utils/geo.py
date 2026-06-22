"""Гео-вычисления: расстояние между точками, фильтрация по радиусу."""

import math
from typing import Any, Dict, List, Optional


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычислить расстояние (км) между двумя точками по формуле гаверсинусов."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def filter_by_radius(
    items: List[Dict[str, Any]],
    center_lat: float,
    center_lng: float,
    radius_km: float,
    lat_key: str = 'lat',
    lng_key: str = 'lng'
) -> List[Dict[str, Any]]:
    """Отфильтровать список словарей по расстоянию от центральной точки.

    Args:
        items: список словарей с координатами.
        center_lat: широта центра.
        center_lng: долгота центра.
        radius_km: радиус фильтрации в километрах.
        lat_key: ключ для широты в словаре.
        lng_key: ключ для долготы в словаре.

    Returns:
        Отфильтрованный список словарей, упорядоченный по расстоянию.
    """
    if not items or radius_km <= 0:
        return items

    result = []
    for item in items:
        try:
            lat = float(item.get(lat_key, 0))
            lng = float(item.get(lng_key, 0))
        except (TypeError, ValueError):
            continue
        dist = calculate_distance(center_lat, center_lng, lat, lng)
        if dist <= radius_km:
            result.append((dist, item))

    result.sort(key=lambda x: x[0])
    return [item for _, item in result]
