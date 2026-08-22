"""Верификация профиля через мессенджер MAX (Phase 3, Часть A).

2026-08: Telegram-провайдер ОТКЛЮЧЁН (152-ФЗ ст. 12 — исключение трансграничной
передачи ПДн в иностранный сервис; см. docs/rkn_notification_fill.md, вариант A).
Остался только MAX (российский мессенджер) + email-верификация (079).

Deep-link flow:
  1. Trudnik user clicks «Подтвердить через MAX».
  2. /messenger/start/max → генерирует одноразовый токен (Redis) + deep link.
  3. User opens bot → bot /start <token>.
  4. Webhook получает событие → верифицирует токен → verify_via_messenger RPC.
  5. Bot отправляет подтверждение в чат.
"""
import logging
import uuid

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from flask import Blueprint, jsonify, request, session

from app.config import Config
from app.decorators import login_required, admin_required, rate_limit
from app.utils import postgrest_rpc
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
messenger_bp = Blueprint('messenger_verify', __name__, url_prefix='/messenger')

# Значения вынесены в Config (app/config.py), override через env:
# MAX_API_URL / MESSENGER_VERIFY_TTL / MESSENGER_API_TIMEOUT
_MAX_API = Config.MAX_API_URL
_VERIFY_TTL = Config.MESSENGER_VERIFY_TTL


def _max_token():
    return Config.MAX_BOT_TOKEN


def _max_botname():
    return Config.MAX_BOT_USERNAME


# ── Генерация deep-link для пользователя ──────────────────────────
@messenger_bp.route('/start/<platform>', methods=['GET'])
@login_required
@rate_limit(fail_open=True)
def start_verification(platform):
    """Генерирует deep-link для подтверждения через MAX (AJAX).

    Telegram отключён (трансграничная передача, 152-ФЗ ст. 12) → 404.
    """
    if platform not in ('max',):
        return jsonify({'success': False, 'error': 'unknown_platform'}), 400

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'not_logged_in'}), 401

    token = uuid.uuid4().hex
    r = get_redis_client()
    if not r:
        return jsonify({'success': False, 'error': 'redis_unavailable'}), 503
    r.setex(f'msg_verify:{token}', _VERIFY_TTL, str(user_id))

    link = f'https://max.ru/{_max_botname()}?start={token}'

    return jsonify({'success': True, 'link': link, 'platform': 'max'})


# ── Webhook: MAX ──────────────────────────────────────────────────
@messenger_bp.route('/diagnose', methods=['GET'])
@login_required
@admin_required
def diagnose():
    """Диагностика outbound-доступности API MAX с прода (только админ).

    Без admin_required эндпоинт был публичным и раскрывал статус bot-токенов +
    совершал исходящие запросы от имени любого посетителя (исправлено 2026-08-16).
    """
    import requests as _req
    result = {'max': {'token_set': bool(_max_token()), 'reachable': False, 'error': ''}}

    # MAX: GET /me
    if _max_token():
        try:
            r = _req.get(f'{_MAX_API}/me', headers={'Authorization': _max_token()}, timeout=Config.MESSENGER_API_TIMEOUT, verify=False)
            result['max']['reachable'] = r.ok
            result['max']['status'] = r.status_code
            if r.ok:
                d = r.json()
                result['max']['bot'] = d.get('username', '?')
            else:
                result['max']['error'] = r.text[:100]
        except Exception as e:
            result['max']['error'] = str(e)[:200]

    return jsonify(result)


@messenger_bp.route('/webhook/max', methods=['POST'])
@rate_limit(fail_open=True)
def max_webhook():
    """Принимает события от MAX бота (bot_started с payload = наш токен)."""
    data = request.get_json(silent=True) or {}
    update_type = data.get('update_type', '')

    if update_type == 'bot_started':
        payload = data.get('payload', '')
        max_uid = str(data.get('user', {}).get('user_id', ''))
        chat_id = data.get('chat_id')
        if payload:
            _complete(payload, max_uid, chat_id)

    return jsonify({'ok': True})


# ── Внутренняя логика ─────────────────────────────────────────────
def _complete(token, messenger_uid, chat_id):
    """Верифицирует токен → помечает профиль → отправляет подтверждение в чат."""
    r = get_redis_client()
    if not r:
        logger.error('messenger_verify: Redis unavailable')
        return

    key = f'msg_verify:{token}'
    user_id = r.get(key)
    if not user_id:
        logger.warning('messenger_verify: token not found/expired: %s', token[:8])
        return
    r.delete(key)  # one-time

    if isinstance(user_id, bytes):
        user_id = user_id.decode()

    rpc = postgrest_rpc(
        'verify_via_messenger',
        {'p_user_id': user_id, 'p_provider': 'max', 'p_messenger_uid': messenger_uid},
        use_admin=True,
    )
    if not rpc.ok:
        logger.error('messenger_verify: RPC failed for %s: %s', user_id, (rpc.text or '')[:200])
        return
    logger.info('messenger_verify: user %s verified via max', user_id)

    if chat_id:
        msg = '✅ Ваш профиль на «Трудник» подтверждён! Теперь вам доступны все функции платформы. Вернитесь в приложение — кнопка «Я подтвердил — проверить».'
        _send_max(chat_id, msg)
        logger.info('messenger_verify: MAX reply sent to chat %s', chat_id)


def _send_max(chat_id, text):
    token = _max_token()
    if not token:
        return
    try:
        requests.post(
            f'{_MAX_API}/messages',
            json={'chat_id': chat_id, 'text': text},
            headers={'Authorization': token, 'Content-Type': 'application/json'},
            timeout=Config.MESSENGER_API_TIMEOUT,
            verify=False,  # MAX API SSL cert not in Docker CA store
        )
    except Exception as e:
        logger.warning('messenger_verify: MAX send failed: %s', e)


# ── Регистрация вебхуков (вызывается один раз после деплоя) ───────
def register_webhooks(base_url):
    """Регистрирует вебхук на MAX. base_url = https://..."""
    mx = _max_token()
    if mx:
        url = f'{base_url}/messenger/webhook/max'
        try:
            resp = requests.post(
                f'{_MAX_API}/subscriptions',
                json={'url': url, 'update_types': ['bot_started', 'message_created']},
                headers={'Authorization': mx, 'Content-Type': 'application/json'},
                timeout=Config.MESSENGER_API_TIMEOUT,
                verify=False,
            )
            logger.info('MAX webhook registered (%s): %s', url, resp.text[:100])
        except Exception as e:
            logger.warning('MAX subscriptions failed: %s', e)
