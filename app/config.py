import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    _FALLBACK_SECRET = os.environ.get('SECRET_KEY')
    if not _FALLBACK_SECRET:
        raise RuntimeError('SECRET_KEY environment variable is required')
    SECRET_KEY = _FALLBACK_SECRET
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    YANDEX_MAPS_API_KEY = os.environ.get('YANDEX_MAPS_API_KEY', '')
