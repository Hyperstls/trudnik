# E2E: критические пользовательские сценарии (J133)

Локальный Playwright-набор проверяет путь, который нельзя надёжно покрыть
модульными тестами:

1. регистрация нового пользователя (3 шага, согласие, подтверждение email);
2. переключение светлой/тёмной темы с сохранением после reload;
3. работодатель создаёт задание через степпер;
4. анонимный просмотр задания учитывается один раз за 24 часа;
5. трудник откликается на задание;
6. работодатель принимает отклик;
7. обе стороны видят сообщение в чате;
8. трудник отмечает выполнение работы.

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
- прогоняет a11y-гейт авторизованных страниц (R046):
  `AXE_AUTH=1 E2E_BASE_URL=http://127.0.0.1:8801 node scripts/axe_audit.mjs`;
- в любом исходе останавливает сервер и удаляет `e2e-*` (`e2e_seed --cleanup`).

Требования: локальная БД из `.env` (`DATABASE_URL`) с применённой схемой,
Python 3.12 venv, Node 20+, Chromium Playwright.

## Что считается успехом

Все 8 шагов печатают `✓`, итог — `8 passed, 0 failed`. При падении Playwright
печатает шаг и ошибку; лог Django лежит в `$TMPDIR/trudnik-e2e-server.log`.

## A11y-гейт авторизованных страниц (R046)

После critical flows тот же сервер проверяется axe-core (WCAG 2.0/2.1 A+AA) на
страницах `/profile`, `/my-applications`, `/my-jobs`, `/chats`, `/notifications`,
`/searches`, `/favorites`, `/jobs/new` — в light/dark и desktop/mobile.

- Логин: `E2E_EMAIL` (по умолчанию `e2e-employer@example.com`) и `E2E_PASSWORD`.
- В режиме `AXE_AUTH=1` **critical и serious** нарушения валят прогон (exit 1);
  отчёт — `axe-report.json`, `mode: "auth"`.
- Публичный режим (`node scripts/axe_audit.mjs` без `AXE_AUTH`) не изменился:
  serious — предупреждения, critical — exit 1; используется в UX quality.

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
