"""Обработчики ошибок Flask: 401, 403, 404, 500, Exception."""

import logging
from flask import render_template, current_app, request, session

logger = logging.getLogger(__name__)


def register_error_handlers(app):
    """Зарегистрировать все обработчики ошибок на Flask-приложении.

    Args:
        app: экземпляр Flask.
    """

    @app.errorhandler(401)
    def unauthorized(e):
        """Обработчик ошибки 401 Unauthorized."""
        user_id = session.get('user_id', 'anonymous')
        logger.warning(
            'Unauthorized access attempt: path=%s ip=%s user=%s',
            request.path, request.remote_addr, user_id
        )
        return render_template('error.html', error_code='401',
                               error='Требуется авторизация'), 401

    @app.errorhandler(403)
    def forbidden(e):
        """Обработчик ошибки 403 Forbidden."""
        user_id = session.get('user_id', 'anonymous')
        logger.warning(
            'Forbidden access attempt: path=%s ip=%s user=%s',
            request.path, request.remote_addr, user_id
        )
        return render_template('error.html', error_code='403',
                               error='Доступ запрещён'), 403

    @app.errorhandler(404)
    def not_found(e):
        """Обработчик ошибки 404 Not Found."""
        logger.info(
            'Page not found: path=%s ip=%s',
            request.path, request.remote_addr
        )
        return render_template('error.html', error_code='404',
                               error='Страница не найдена'), 404

    @app.errorhandler(500)
    def internal_error(_e):
        app.logger.exception('Internal server error')
        return render_template('error.html', error_code='500',
                               error='Внутренняя ошибка сервера'), 500

    @app.errorhandler(Exception)
    def handle_postgrest_error(e):
        """Глобальный обработчик ошибок внешних сервисов."""
        import requests as req_lib
        from werkzeug.exceptions import HTTPException
        # Пропускаем HTTP-исключения (abort, 404, 400 и т.д.) — возвращаем как есть
        if isinstance(e, HTTPException):
            return e
        if isinstance(e, req_lib.RequestException):
            current_app.logger.error('External service error: %s', e)
            return render_template('error.html',
                error_code='503',
                error='Внешний сервис (PostgREST) не отвечает. Пожалуйста, попробуйте позже.'), 503
        # Для остальных ошибок — стандартный 500
        current_app.logger.exception('Unhandled exception')
        return render_template('error.html',
            error_code='500',
            error='Произошла непредвиденная ошибка. Мы уже работаем над её устранением.'), 500
