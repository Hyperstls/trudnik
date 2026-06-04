import math
import time
import uuid
from datetime import datetime

import requests
from flask import current_app, session

from app.config import Config

SUPABASE_URL = Config.SUPABASE_URL
SUPABASE_KEY = Config.SUPABASE_ANON_KEY
SERVICE_KEY = Config.SUPABASE_SERVICE_ROLE_KEY


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def refresh_access_token():
    refresh_token = session.get('refresh_token')
    if not refresh_token:
        return False
    url = f'{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token'
    try:
        resp = requests.post(url, json={'refresh_token': refresh_token},
                             headers={'apikey': SUPABASE_KEY, 'Content-Type': 'application/json'},
                             timeout=10)
        if resp.ok:
            data = resp.json()
            session['access_token'] = data['access_token']
            session['refresh_token'] = data.get('refresh_token', refresh_token)
            session.modified = True
            return True
        else:
            session.clear()
            return False
    except requests.RequestException:
        return False


def supabase_request(method, endpoint, **kwargs):
    def _make_request():
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {session.get("access_token", SUPABASE_KEY)}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation',
        }
        if 'headers' in kwargs:
            extra = kwargs.pop('headers')
            headers.update(extra)
        url = f'{SUPABASE_URL}/rest/v1/{endpoint}'
        return requests.request(method, url, headers=headers, timeout=15, **kwargs)

    try:
        resp = _make_request()
        if resp.status_code == 401 and session.get('refresh_token'):
            if refresh_access_token():
                resp = _make_request()
        return resp
    except requests.RequestException as e:
        current_app.logger.error(f"Supabase request error: {e}")
        return type('obj', (object,), {'ok': False, 'status_code': 0, 'text': str(e)})()
    except Exception as e:
        current_app.logger.error(f"Unexpected error in supabase_request: {e}")
        return type('obj', (object,), {'ok': False, 'status_code': 0, 'text': str(e)})()


def upload_to_storage(bucket, file_path, file_data, content_type):
    url = f'{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}'
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {session["access_token"]}',
    }
    try:
        resp = requests.post(url, headers=headers,
                             files={'file': (file_path, file_data, content_type)},
                             timeout=30)
        if resp.status_code in (200, 201):
            return f'{SUPABASE_URL}/storage/v1/object/public/{bucket}/{file_path}?t={int(time.time())}'
    except requests.RequestException:
        pass
    return None


def copy_job(original_job):
    return {
        'employer_id': original_job['employer_id'],
        'organization_name': original_job.get('organization_name', ''),
        'org_description': original_job.get('org_description', ''),
        'object_description': original_job.get('object_description', ''),
        'work_type': original_job.get('work_type', ''),
        'detailed_description': original_job.get('detailed_description', ''),
        'date_time': original_job.get('date_time', ''),
        'payment_amount': original_job.get('payment_amount', 0),
        'address': original_job.get('address', ''),
        'city': original_job.get('city', ''),
        'lat': original_job.get('lat', 55.75),
        'lng': original_job.get('lng', 37.61),
        'status': 'open',
        'max_workers': original_job.get('max_workers', 1),
        'current_workers': 0,
    }


def add_notification(user_id, notification_type, title, message):
    """Добавить уведомление пользователю"""
    notification_data = {
        'user_id': user_id,
        'type': notification_type,
        'title': title,
        'message': message,
        'is_read': False
    }
    supabase_request('POST', 'notifications', json=notification_data)


def update_rating(user_id, new_rating):
    """Обновить средний рейтинг пользователя"""
    ratings_resp = supabase_request('GET', f'ratings?rated_user_id=eq.{user_id}&select=rating')
    if not ratings_resp.ok or not ratings_resp.json():
        return

    ratings_list = ratings_resp.json()
    total = sum(r['rating'] for r in ratings_list)
    avg = round(total / len(ratings_list), 1)

    supabase_request('PATCH', f'profiles?id=eq.{user_id}', json={'rating': avg})
