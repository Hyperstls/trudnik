# MAX: верификация профиля и бот

## Что настроено

- Deep link `https://max.ru/<bot>?start=<token>` (токен 10 минут, одноразовый).
- Webhook `POST /messenger/webhook/max` с проверкой `X-Max-Bot-Api-Secret`
  (fail-closed: без секрета 503, неверный 401).
- Self-heal подписки: Celery beat `ensure_max_webhook` каждые 10 минут и
  дополнительно при открытии `/messenger/start/max`. Подписка пересоздаётся,
  если изменился URL, набор `update_types` или `MAX_WEBHOOK_SECRET`; старые
  URL с тем же путём удаляются. Нужные типы: `bot_started`, `message_created`,
  `message_callback`.
- Бот отвечает в чат:
  - после deep link — сообщение с inline-кнопкой «Подтвердить профиль»
    (callback `confirm:<token>`) и ссылкой «Открыть профиль»;
  - нажатие кнопки — профиль подтверждается, сообщение обновляется результатом,
    кнопка исчезает;
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
   - `Webhook-подписка: registered/already_registered/updated`;
   - URL совпадает с `https://<домен>/messenger/webhook/max`.
3. **401 на вебхуке / в чате пусто.** Подписка могла быть создана без секрета
   (или со старым секретом): `MAX` присылает события без
   `X-Max-Bot-Api-Secret`, прод отвечает 401. Начиная с R010
   `ensure_max_webhook` хранит подпись `url + update_types + secret` и
   пересоздаёт подписку при расхождении. Дождитесь цикла beat (до 10 минут)
   или откройте `/messenger/start/max`; в логах должно быть
   `MAX webhook updated`.
4. **Дубли подписок.** Старые URL с путём `/messenger/webhook/max`
   удаляются автоматически; в `GET /subscriptions` должен остаться один
   канонический URL.
5. Если в логах `MAX send chat=... failed: HTTP 400` — проверить, что `chat_id` уходит query-параметром `/messages?chat_id=...`, а не в JSON (R020).
6. Если ошибка TLS — проверить `MAX_CA_BUNDLE`.
7. Если подписка не создаётся — проверить `MAX_BOT_TOKEN` и доступ к
   `platform-api2.max.ru` с прода.
8. После успешной подписки открыть профиль → «Подтвердить через MAX» заново:
   старые deep-link токены одноразовые и живут 10 минут.

## Это 2FA?

MAX-верификация — это **подтверждение профиля** (значок «Проверенный»),
а не второй фактор входа. Отдельная 2FA по email-коду сделана в R003–R005:
`profiles.two_factor_enabled`, экран кода после пароля, 5 попыток, TTL 10 минут.
