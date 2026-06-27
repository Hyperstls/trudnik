import logging
import json
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Структурированный JSON-форматтер для логов."""

    def format(self, record):
        log_obj = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        if hasattr(record, 'request_id'):
            log_obj['request_id'] = record.request_id
        if record.exc_info and record.exc_info[0]:
            log_obj['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_json_logging(log_level: int = logging.INFO) -> None:
    """Настраивает корневой логгер на JSON-вывод."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Удаляем существующие хендлеры, чтобы избежать дублирования
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
