"""Re-exports of all blueprint instances for cleaner imports."""

from app.blueprints.auth import auth_bp
from app.blueprints.profile import profile_bp
from app.blueprints.jobs import jobs_bp
from app.blueprints.applications import applications_bp
from app.blueprints.chat import chat_bp
from app.blueprints.favorites import favorites_bp
from app.blueprints.blacklist import blacklist_bp
from app.blueprints.notifications import notifications_bp
from app.blueprints.admin import admin_bp
from app.blueprints.monetization import monetization_bp

__all__ = [
    'auth_bp', 'profile_bp', 'jobs_bp', 'applications_bp',
    'chat_bp', 'favorites_bp', 'blacklist_bp',
    'notifications_bp', 'admin_bp', 'monetization_bp',
]
