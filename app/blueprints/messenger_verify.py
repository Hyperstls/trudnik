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
import re
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
    2026-08-27: добавлен статус webhook-подписок (главный кандидат «бот молчит»).
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

    # Webhook-подписки: зарегистрирован ли наш URL
    subs = get_max_subscriptions()
    expected = _webhook_url(Config.WORKER_SITE_URL)
    result['webhook'] = {
        'expected_url': expected,
        'subscriptions': [{'url': s.get('url'), 'update_types': s.get('update_types')}
                          for s in subs if isinstance(s, dict)],
        'registered': any(isinstance(s, dict) and
                          (s.get('url') or '').rstrip('/') == expected.rstrip('/')
                          for s in subs),
    }
    return jsonify(result)


@messenger_bp.route('/webhook/max', methods=['POST'])
@rate_limit(fail_open=True)
def max_webhook():
    """Принимает события от MAX бота.

    Обрабатывает два типа апдейтов (идемпотентно, всегда 200):
    - bot_started: с payload = наш deep-link токен → авто-верификация.
      ⚠️ MAX шлёт bot_started ТОЛЬКО при первом старте чата с ботом —
      при повторном открытии deep-link событие не приходит.
    - message_created: fallback для повторных стартов и ручного ввода —
      токен извлекается из текста ('/start <token>' или голый 32-hex токен);
      '/start'/'start' без токена → инструкция с ссылкой на профиль.

    Это закрывает симптомы «бот не реагирует на Start» и «/start — команда
    не найдена» (последний отвечает сценарий MaxBot Studio; наш бот отвечает
    сообщением через API параллельно).
    """
    data = request.get_json(silent=True) or {}
    update_type = data.get('update_type', '')
    chat_id = data.get('chat_id')

    if update_type == 'bot_started':
        payload = data.get('payload', '')
        max_uid = str(data.get('user', {}).get('user_id', ''))
        if payload:
            _complete(payload, max_uid, chat_id)
        else:
            # Первый старт без deep-link (открыли бота поиском) — инструкция
            logger.info('messenger_verify: bot_started without payload, chat=%s', chat_id)
            if chat_id:
                _send_max(chat_id, _INSTRUCTION_TEXT,
                          button=_link_button('Открыть «Трудник»',
                                              f'{Config.WORKER_SITE_URL.rstrip("/")}/profile'))

    elif update_type == 'message_created':
        message = data.get('message') or {}
        # MAX Bot API: текст в body.text (объект MessageBody) — см.
        # dev.max.ru/docs-api/objects/Message. Fallback на message.text
        # оставлен толерантности к будущим форматам.
        body = message.get('body') or {}
        text = (body.get('text') or message.get('text') or '').strip()
        sender = message.get('sender') or {}
        max_uid = str(sender.get('user_id', ''))
        if not text:
            return jsonify({'ok': True})

        token = _extract_token(text)
        if token:
            _complete(token, max_uid, chat_id)
        elif text.lower() in ('/start', 'start', 'начать'):
            logger.info('messenger_verify: bare /start from chat=%s — instruction', chat_id)
            if chat_id:
                _send_max(chat_id, _INSTRUCTION_TEXT,
                          button=_link_button('Открыть «Трудник»',
                                              f'{Config.WORKER_SITE_URL.rstrip("/")}/profile'))

    return jsonify({'ok': True})


# Токен верификации — 32 hex-символа (uuid4().hex из start_verification)
_TOKEN_RE = re.compile(r'\b([a-f0-9]{32})\b')

_INSTRUCTION_TEXT = (
    '👋 Это бот подтверждения профиля платформы «Трудник».\n\n'
    'Чтобы подтвердить профиль:\n'
    '1. Откройте приложение «Трудник» — trudnik-hyperstls.amvera.io\n'
    '2. Профиль → «Подтвердить через MAX»\n'
    '3. Перейдите по присланной ссылке — подтверждение произойдёт '
    'автоматически, здесь появится сообщение ✅\n\n'
    'Вводить команды вручную не нужно.'
)


def _extract_token(text: str) -> str | None:
    """Извлекает токен верификации из текста сообщения.

    Поддерживает '/start <token>', 'start <token>' и голый токен.
    """
    m = _TOKEN_RE.search(text)
    return m.group(1) if m else None


# ── Внутренняя логика ─────────────────────────────────────────────

def _link_button(text: str, url: str) -> dict:
    """Inline-кнопка-ссылка (MAX Bot API: attachments.inline_keyboard,
    см. dev.max.ru — «Клавиатура для чат-бота», тип link)."""
    return {
        'type': 'inline_keyboard',
        'payload': {'buttons': [[{'type': 'link', 'text': text, 'url': url}]]},
    }


def _complete(token, messenger_uid, chat_id):
    """Верифицирует токен → помечает профиль → отправляет подтверждение в чат."""
    r = get_redis_client()
    if not r:
        logger.error('messenger_verify: Redis unavailable')
        if chat_id:
            _send_max(chat_id,
                      '⚠️ Сервис подтверждения временно недоступен. '
                      'Попробуйте ещё раз через пару минут.')
        return

    key = f'msg_verify:{token}'
    user_id = r.get(key)
    if not user_id:
        logger.warning('messenger_verify: token not found/expired: %s', token[:8])
        if chat_id:
            _send_max(chat_id,
                      '⌛ Ссылка устарела или уже использована.\n'
                      'Откройте приложение «Трудник» → Профиль → '
                      '«Подтвердить через MAX» и получите новую ссылку.',
                      button=_link_button(
                          'Получить новую ссылку',
                          f'{Config.WORKER_SITE_URL.rstrip("/")}/profile'))
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
        if chat_id:
            _send_max(chat_id,
                      '⚠️ Не удалось подтвердить профиль (ошибка сервера). '
                      'Попробуйте позже или напишите в поддержку.')
        return
    logger.info('messenger_verify: user %s verified via max', user_id)

    if chat_id:
        msg = (
            '✅ Ваш профиль на «Трудник» подтверждён!\n'
            'Теперь вам доступен значок «Проверенный» и все функции платформы.'
        )
        ok = _send_max(chat_id, msg,
                       button=_link_button(
                           'Вернуться в профиль',
                           f'{Config.WORKER_SITE_URL.rstrip("/")}/profile'))
        logger.info('messenger_verify: MAX reply to chat %s: %s',
                    chat_id, 'sent' if ok else 'FAILED')


def _send_max(chat_id, text, button: dict | None = None) -> bool:
    """Отправляет сообщение в чат MAX (опционально с inline-кнопкой).

    Возвращает True при 2xx. Формат кнопки — attachments.inline_keyboard
    (dev.max.ru/docs-api — «Клавиатура для чат-бота»).
    """
    token = _max_token()
    if not token:
        logger.warning('messenger_verify: MAX_BOT_TOKEN not set — reply skipped')
        return False
    payload = {'chat_id': chat_id, 'text': text}
    if button:
        payload['attachments'] = [button]
    try:
        resp = requests.post(
            f'{_MAX_API}/messages',
            json=payload,
            headers={'Authorization': token, 'Content-Type': 'application/json'},
            timeout=Config.MESSENGER_API_TIMEOUT,
            verify=False,  # MAX API SSL cert not in Docker CA store
        )
        if resp.status_code >= 300:
            logger.warning('messenger_verify: MAX send %s failed: %s %s',
                           chat_id, resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as e:
        logger.warning('messenger_verify: MAX send failed: %s', e)
        return False


# ── Регистрация вебхука (self-heal, идемпотентно) ──────────────────
# Оба типа обязательны: bot_started — первый старт deep-link,
# message_created — fallback повторных стартов (см. max_webhook).
_NEEDED_UPDATE_TYPES = ('bot_started', 'message_created')


def _webhook_url(base_url: str) -> str:
    return base_url.rstrip('/') + '/messenger/webhook/max'


def get_max_subscriptions() -> list:
    """Список активных подписок MAX API (для diagnose/self-heal)."""
    token = _max_token()
    if not token:
        return []
    try:
        resp = requests.get(
            f'{_MAX_API}/subscriptions',
            headers={'Authorization': token},
            timeout=Config.MESSENGER_API_TIMEOUT,
            verify=False,
        )
        if resp.ok:
            data = resp.json()
            # GET /subscriptions возвращает {'subscriptions': [...]} —
            # tolerant к plain-list на случай смены формата
            return data if isinstance(data, list) else data.get('subscriptions', [])
    except Exception as e:
        logger.warning('messenger_verify: GET subscriptions failed: %s', e)
    return []


def _find_subscription(subs: list, url: str) -> dict | None:
    want = url.rstrip('/')
    for s in subs:
        if isinstance(s, dict) and (s.get('url') or '').rstrip('/') == want:
            return s
    return None


def _register_subscription(url: str, token: str) -> tuple[bool, str]:
    """POST /subscriptions. Возвращает (ok, error)."""
    try:
        resp = requests.post(
            f'{_MAX_API}/subscriptions',
            json={'url': url, 'update_types': list(_NEEDED_UPDATE_TYPES)},
            headers={'Authorization': token, 'Content-Type': 'application/json'},
            timeout=Config.MESSENGER_API_TIMEOUT,
            verify=False,
        )
        if resp.status_code < 300:
            return True, ''
        return False, f'HTTP {resp.status_code}: {resp.text[:150]}'
    except Exception as e:
        return False, str(e)[:200]


def ensure_max_webhook(base_url: str | None = None) -> dict:
    """Гарантирует, что webhook MAX зарегистрирован на наш URL с нужными типами.

    Идемпотентно; сверяет и URL, и update_types — старая подписка только с
    bot_started (без message_created) равносильна «бот молчит» на повторных
    стартах, поэтому при несовпадении типов подписка пересоздаётся
    (DELETE /subscriptions?url= + POST — API не гарантирует апдейт in-place).
    Вызывается self-heal-задачей (maintenance_tasks, каждые 10 мин).
    """
    if base_url is None:
        base_url = Config.WORKER_SITE_URL
    url = _webhook_url(base_url)
    token = _max_token()
    result = {'ok': False, 'url': url, 'action': '', 'error': ''}
    if not token:
        result['error'] = 'MAX_BOT_TOKEN not set'
        return result

    try:
        existing = _find_subscription(get_max_subscriptions(), url)
        if existing is not None:
            have = set(existing.get('update_types') or [])
            if set(_NEEDED_UPDATE_TYPES) <= have:
                result.update(ok=True, action='already_registered')
                return result
            # Типы не совпадают → пересоздаём (API не гарантирует in-place update)
            try:
                requests.delete(
                    f'{_MAX_API}/subscriptions',
                    params={'url': url},
                    headers={'Authorization': token},
                    timeout=Config.MESSENGER_API_TIMEOUT,
                    verify=False,
                )
            except Exception as e:
                logger.warning('messenger_verify: subscription delete failed: %s', e)

        ok, err = _register_subscription(url, token)
        if ok:
            result.update(ok=True,
                          action='registered' if existing is None else 'updated')
            logger.info('messenger_verify: MAX webhook %s: %s', result['action'], url)
        else:
            result['error'] = err
            logger.warning('messenger_verify: MAX subscription failed: %s', err)
    except Exception as e:
        result['error'] = str(e)[:200]
        logger.warning('messenger_verify: ensure_max_webhook failed: %s', e)
    return result
