import os
import warnings
from dotenv import load_dotenv

load_dotenv()


class Config:
    _FALLBACK_SECRET = 'trudnik-dev-secret-change-in-production'
    SECRET_KEY = os.environ.get('SECRET_KEY') or _FALLBACK_SECRET
    if SECRET_KEY == _FALLBACK_SECRET:
        warnings.warn('SECRET_KEY is not set in environment. Using insecure default.', RuntimeWarning)
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    YANDEX_MAPS_API_KEY = os.environ.get('YANDEX_MAPS_API_KEY', '')
