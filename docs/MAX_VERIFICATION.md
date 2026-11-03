# MAX: верификация профиля и бот

## Что настроено

- Deep link `https://max.ru/<bot>?start=<token>` (токен 10 минут, одноразовый).
- Webhook `POST /messenger/webhook/max` с проверкой `X-Max-Bot-Api-Secret`
  (fail-closed: без секрета 503, неверный 401).
- Self-heal подписки: Celery beat `ensure_max_webhook` каждые 10 минут и
  дополнительно при открытии `/messenger/start/max`.
- Бот отвечает в чат:
  - успех — «Профиль подтверждён» + кнопка «Вернуться в профиль»;
  - истёкшая ссылка — просьба получить новую;
  - `/start` без токена или любой текст — инструкция.
- Диагностика: `/messenger/diagnose` (staff) показывает token, API URL,
  webhook URL и статус подписки.

## Переменные Amvera

```text
MAX_BOT_TOKEN=<токен из business.max.ru>
MAX_BOT_USERNAME=se13803803_bot
MAX_WEBHOOK_SECRET=<секрет подписи>
MAX_API_URL=https://platform-api2.max.ru
MESSENGER_API_TIMEOUT=10
# MAX_CA_BUNDLE=/app/certs/russian_trusted_root_ca.crt
```

`MAX_CA_BUNDLE` по умолчанию указывает на публичный «Russian Trusted Root CA»
из `certs/`; `verify=False` не используется.

## Если бот молчит

1. Открыть `/messenger/diagnose` под staff-аккаунтом.
2. Проверить:
   - `Bot token: задан`;
   - `Webhook-подписка: registered/already_registered`;
   - URL совпадает с `https://<домен>/messenger/webhook/max`.
3. Если ошибка TLS — проверить `MAX_CA_BUNDLE`.
4. Если подписка не создаётся — проверить `MAX_BOT_TOKEN` и доступ к
   `platform-api2.max.ru` с прода.
5. После успешной подписки открыть профиль → «Подтвердить через MAX» заново:
   старые deep-link токены одноразовые и живут 10 минут.

## Это 2FA?

Нет. Это **верификация профиля** (значок «Проверенный»), а не второй фактор
входа. Для полноценной 2FA нужен отдельный сценарий: бот присылает одноразовый
код, а форма логина запрашивает его после пароля. Это можно сделать бесплатно
на том же MAX Bot API, но это отдельная продуктовая задача.
