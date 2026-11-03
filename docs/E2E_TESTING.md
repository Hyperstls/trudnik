# E2E: критические пользовательские сценарии (J133)

Локальный Playwright-набор проверяет путь, который нельзя надёжно покрыть
модульными тестами:

1. регистрация нового пользователя (3 шага, согласие, подтверждение email);
2. работодатель создаёт задание через степпер;
3. анонимный просмотр задания учитывается один раз за 24 часа;
4. трудник откликается на задание;
5. работодатель принимает отклик;
6. обе стороны видят сообщение в чате.

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

Все 6 шагов печатают `✓`, итог — `6 passed, 0 failed`. При падении Playwright
печатает шаг и ошибку; лог Django лежит в `$TMPDIR/trudnik-e2e-server.log`.

## CI

`.github/workflows/e2e.yml` поднимает `postgis/postgis:15-3.4`, загружает
`tests/fixtures/schema.sql` (схема без данных) и запускает тот же скрипт на
каждый push в `feat/agent-pipeline`/`main` и pull request в `main`.

Схема живёт в SQL-миграциях, поэтому после изменения БД пересоберите fixture:

```bash
.venv\Scripts\python.exe scripts/dump_schema.py
git add tests/fixtures/schema.sql
```

## Ограничения

- `runserver` не обслуживает WebSocket (`/ws/user/` → 404); чат в E2E проверяется
  через HTTP-отправку и серверный рендер. WebSocket-доставка покрыта
  `core.tests.test_ws_notifications` и прод-мониторингом.
- Данные одноразовые: префикс `e2e-`; не используйте его для реальных аккаунтов.
- Fixture — схема, не данные; после миграций его нужно обновлять (см. выше).
