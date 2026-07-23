import logging
import json
import os
from datetime import datetime, timezone


# Contextual request-id storage for non-Flask contexts (Celery tasks, scripts)
import threading
_context = threading.local()


def set_request_id(rid: str) -> None:
    """Set request_id for the current thread (Celery tasks, etc.)."""
    _context.request_id = rid


def get_request_id() -> str | None:
    """Get request_id from Flask g or thread-local context."""
    try:
        from flask import g
        if hasattr(g, 'request_id'):
            return g.request_id
    except (RuntimeError, ImportError):
        pass
    return getattr(_context, 'request_id', None)


def clear_request_id() -> None:
    """Clear thread-local request_id."""
    if hasattr(_context, 'request_id'):
        del _context.request_id


class JsonFormatter(logging.Formatter):
    """Структурированный JSON-форматтер для логов.

    Включает request_id во ВСЕ записи лога:
    - Flask requests: из g.request_id (middleware set_request_id)
    - Celery tasks: из thread-local (set_request_id via task_prerun signal)
    - Beat/standalone: None (beat tasks не имеют request_id)
    """

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
        rid = get_request_id()
        if rid:
            log_obj['request_id'] = rid
        if record.exc_info and record.exc_info[0]:
            log_obj['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_json_logging(log_level: int = logging.INFO) -> None:
    """Настраивает корневой логгер на JSON-вывод."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Celery signal: inject _request_id into thread-local for structured logging
    try:
        from celery.signals import task_prerun, task_postrun

        @task_prerun.connect
        def _inject_request_id(task_id, task, args, kwargs, **kw):
            """Set request_id from task kwargs (_request_id) before task runs."""
            rid = kwargs.get('_request_id') if isinstance(kwargs, dict) else None
            if rid:
                set_request_id(rid)

        @task_postrun.connect
        def _clear_request_id(task_id, task, args, kwargs, retval, state, **kw):
            """Clear request_id after task completes."""
            clear_request_id()
    except ImportError:
        pass
