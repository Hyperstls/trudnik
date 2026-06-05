from flask import Flask, session

from app.config import Config


import os

def create_app():
    # Корень проекта — родительская директория пакета app/
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    app = Flask(__name__,
                root_path=project_root,
                template_folder='templates',
                static_folder='static')
    app.config.from_object(Config)
    app.secret_key = app.config['SECRET_KEY']

    @app.context_processor
    def inject_global_user():
        return {'current_user_id': session.get('user_id')}

    # Регистрация blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.profile import profile_bp
    from app.blueprints.jobs import jobs_bp
    from app.blueprints.applications import applications_bp
    from app.blueprints.shifts import shifts_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.favorites import favorites_bp
    from app.blueprints.blacklist import blacklist_bp
    from app.blueprints.notifications import notifications_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.monetization import monetization_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(favorites_bp)
    app.register_blueprint(blacklist_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(monetization_bp)

    return app


# Экземпляр приложения для WSGI/ASGI (Render, Gunicorn и совместимость)
app = create_app()
