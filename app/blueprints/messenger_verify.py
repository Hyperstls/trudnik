"""Phase 3 (Часть A): верификация через мессенджеры MAX + Telegram.

Deep-link flow:
  1. Trudnik user clicks «Подтвердить через MAX/Telegram».
  2. /messenger/start/<platform> → генерирует одноразовый токен (Redis) + deep link.
  3. User opens bot → bot /start <token>.
  4. Webhook получает событие → верифицирует токен → verify_via_messenger RPC.
  5. Bot отправляет подтверждение в чат.
"""
import logging
import os
import uuid

import requests
from flask import Blueprint, jsonify, request, session

from app.decorators import login_required
from app.utils import postgrest_rpc
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
messenger_bp = Blueprint('messenger_verify', __name__, url_prefix='/messenger')

_MAX_API = 'https://platform-api2.max.ru'
_TG_API = 'https://api.telegram.org/bot'
_VERIFY_TTL = 600  # 10 минут на подтверждение


def _max_token():
    return os.environ.get('MAX_BOT_TOKEN', '')


def _tg_token():
    return os.environ.get('TELEGRAM_BOT_TOKEN', '')


def _max_botname():
    return os.environ.get('MAX_BOT_USERNAME', 'se13803803_bot')


def _tg_botname():
    return os.environ.get('TELEGRAM_BOT_USERNAME', 'Trudnik_bot')


# ── Генерация deep-link для пользователя ──────────────────────────
@messenger_bp.route('/start/<platform>', methods=['GET'])
@login_required
def start_verification(platform):
    """Генерирует deep-link для подтверждения через мессенджер (AJAX)."""
    if platform not in ('max', 'telegram'):
        return jsonify({'success': False, 'error': 'unknown_platform'}), 400

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'not_logged_in'}), 401

    token = uuid.uuid4().hex
    r = get_redis_client()
    if not r:
        return jsonify({'success': False, 'error': 'redis_unavailable'}), 503
    r.setex(f'msg_verify:{token}', _VERIFY_TTL, str(user_id))

    if platform == 'max':
        link = f'https://max.ru/{_max_botname()}?start={token}'
    else:
        link = f'https://t.me/{_tg_botname()}?start={token}'

    return jsonify({'success': True, 'link': link, 'platform': platform})


# ── Webhook: MAX ──────────────────────────────────────────────────
@messenger_bp.route('/webhook/max', methods=['POST'])
def max_webhook():
    """Принимает события от MAX бота (bot_started с payload = наш токен)."""
    data = request.get_json(silent=True) or {}
    update_type = data.get('update_type', '')

    if update_type == 'bot_started':
        payload = data.get('payload', '')
        max_uid = str(data.get('user', {}).get('user_id', ''))
        chat_id = data.get('chat_id')
        if payload:
            _complete(payload, 'max', max_uid, chat_id, 'max')

    return jsonify({'ok': True})


# ── Webhook: Telegram ─────────────────────────────────────────────
@messenger_bp.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Принимает обновления от Telegram бота (/start <token>)."""
    data = request.get_json(silent=True) or {}
    message = data.get('message') or data.get('edited_message') or {}
    text = message.get('text', '')

    if text.startswith('/start '):
        payload = text.split(' ', 1)[1].strip()
        tg_uid = str(message.get('from', {}).get('id', ''))
        chat_id = message.get('chat', {}).get('id')
        if payload:
            _complete(payload, 'telegram', tg_uid, chat_id, 'telegram')

    return jsonify({'ok': True})


# ── Внутренняя логика ─────────────────────────────────────────────
def _complete(token, provider, messenger_uid, chat_id, platform):
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
        {'p_user_id': user_id, 'p_provider': provider, 'p_messenger_uid': messenger_uid},
        use_admin=True,
    )
    if not rpc.ok:
        logger.error('messenger_verify: RPC failed for %s: %s', user_id, (rpc.text or '')[:200])
        return
    logger.info('messenger_verify: user %s verified via %s', user_id, platform)

    if chat_id:
        msg = '✅ Ваш профиль на «Трудник» подтверждён! Теперь вам доступны все функции платформы.'
        if platform == 'max':
            _send_max(chat_id, msg)
        else:
            _send_telegram(chat_id, msg)


def _send_max(chat_id, text):
    token = _max_token()
    if not token:
        return
    try:
        requests.post(
            f'{_MAX_API}/messages',
            json={'chat_id': chat_id, 'text': text},
            headers={'Authorization': token, 'Content-Type': 'application/json'},
            timeout=10,
        )
    except Exception as e:
        logger.warning('messenger_verify: MAX send failed: %s', e)


def _send_telegram(chat_id, text):
    token = _tg_token()
    if not token:
        return
    try:
        requests.post(
            f'{_TG_API}{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text},
            timeout=10,
        )
    except Exception as e:
        logger.warning('messenger_verify: Telegram send failed: %s', e)


# ── Регистрация вебхуков (вызывается один раз после деплоя) ───────
def register_webhooks(base_url):
    """Регистрирует вебхуки на MAX и Telegram. base_url = https://..."""
    tg = _tg_token()
    if tg:
        url = f'{base_url}/messenger/webhook/telegram'
        try:
            resp = requests.post(
                f'{_TG_API}{tg}/setWebhook',
                json={'url': url, 'allowed_updates': ['message']},
                timeout=10,
            )
            logger.info('Telegram webhook registered (%s): %s', url, resp.text[:100])
        except Exception as e:
            logger.warning('Telegram setWebhook failed: %s', e)

    mx = _max_token()
    if mx:
        url = f'{base_url}/messenger/webhook/max'
        try:
            resp = requests.post(
                f'{_MAX_API}/subscriptions',
                json={'url': url, 'update_types': ['bot_started', 'message_created']},
                headers={'Authorization': mx, 'Content-Type': 'application/json'},
                timeout=10,
            )
            logger.info('MAX webhook registered (%s): %s', url, resp.text[:100])
        except Exception as e:
            logger.warning('MAX subscriptions failed: %s', e)
