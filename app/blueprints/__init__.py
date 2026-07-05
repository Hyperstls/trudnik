"""Re-exports of all blueprint instances for cleaner imports."""

from app.blueprints.auth import auth_bp
from app.blueprints.profile import profile_bp
from app.blueprints.jobs import jobs_bp
from app.blueprints.jobs_api import jobs_api_bp
from app.blueprints.applications import applications_bp
from app.blueprints.chat import chat_bp
from app.blueprints.favorites import favorites_bp
from app.blueprints.blacklist import blacklist_bp
from app.blueprints.notifications import notifications_bp
from app.blueprints.admin_dashboard import admin_dashboard_bp
from app.blueprints.admin_users import admin_users_bp
from app.blueprints.admin_jobs import admin_jobs_bp
from app.blueprints.admin_dictionaries import admin_dictionaries_bp
from app.blueprints.admin_verification import admin_verification_bp
from app.blueprints.admin_diagnostics import admin_diagnostics_bp
from app.blueprints.ratings import ratings_bp
from app.blueprints.seo import seo_bp
from app.blueprints.employers import employers_bp
from app.blueprints.core import core_bp

__all__ = [
    'auth_bp', 'profile_bp', 'jobs_bp', 'jobs_api_bp',
    'applications_bp', 'chat_bp', 'favorites_bp',
    'blacklist_bp', 'notifications_bp',
    'admin_dashboard_bp', 'admin_users_bp', 'admin_jobs_bp',
    'admin_dictionaries_bp', 'admin_verification_bp', 'admin_diagnostics_bp',
    'ratings_bp', 'seo_bp', 'employers_bp', 'core_bp',
]
