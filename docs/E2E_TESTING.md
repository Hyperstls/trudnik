# E2E: критические пользовательские сценарии (J133)

Локальный Playwright-набор проверяет путь, который нельзя надёжно покрыть
модульными тестами:

1. регистрация нового пользователя (3 шага, согласие, подтверждение email);
2. работодатель создаёт задание через степпер;
3. трудник откликается на задание;
4. работодатель принимает отклик;
5. обе стороны видят сообщение в чате.

## Запуск

```bash
npm ci
npx playwright install chromium
bash scripts/e2e/run_critical_flows.sh
```

Скрипт сам:

- выставляет `DJANGO_CAPTCHA_DISABLED=1`, пустые ключи SmartCaptcha/Яндекс.Карт,
  console-email и `REDIS_URL=""` (in-memory cache/channel layer);
- запускает `runserver 127.0.0.1:8801 --noreload`;
- создаёт одноразовых пользователей `e2e-*` и задание `E2E Уборка`
  (`manage.py e2e_seed`);
- гоняет `scripts/e2e/critical_flows.mjs`;
- в любом исходе останавливает сервер и удаляет `e2e-*` (`e2e_seed --cleanup`).

Требования: локальная БД из `.env` (`DATABASE_URL`) с применённой схемой,
Python 3.12 venv, Node 20+, Chromium Playwright.

## Что считается успехом

Все 5 шагов печатают `✓`, итог — `5 passed, 0 failed`. При падении Playwright
печатает шаг и ошибку; лог Django лежит в `$TMPDIR/trudnik-e2e-server.log`.

## Ограничения

- Набор локальный: CI не поднимает схему из SQL-миграций (она живёт вне Django
  migrations, см. `docs/django_migration_prompt.md`, ADR-8).
- `runserver` не обслуживает WebSocket (`/ws/user/` → 404); чат в E2E проверяется
  через HTTP-отправку и серверный рендер. WebSocket-доставка покрыта
  `core.tests.test_ws_notifications` и прод-мониторингом.
- Данные одноразовые: префикс `e2e-`; не используйте его для реальных аккаунтов.
