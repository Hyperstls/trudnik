"""Безопасная обработка ошибок PostgREST."""


def safe_error_message(resp, default: str = 'Ошибка сервера') -> str:
    """Извлекает пользовательское сообщение, скрывая технические детали.

    Args:
        resp: объект PostgrestResponse с атрибутами ok, status_code, json(), text.
        default: сообщение по умолчанию.

    Returns:
        Пользовательское сообщение без технических деталей.
    """
    if not resp or resp.ok:
        return default
    try:
        data = resp.json()
        if isinstance(data, dict):
            code = data.get('code', '')
            code_map = {
                '23505': 'Запись с такими данными уже существует',
                '23503': 'Невозможно удалить: есть связанные записи',
                '42501': 'Недостаточно прав для выполнения операции',
                '23502': 'Не заполнено обязательное поле',
                '23514': 'Значение не удовлетворяет ограничениям',
                '22P02': 'Некорректный формат данных',
            }
            if code in code_map:
                return code_map[code]
    except Exception:
        pass
    return default
