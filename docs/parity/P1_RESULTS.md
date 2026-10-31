# P1 results — регистрация, валидация, сессии

**Дата:** 2026-10-31
**Контракты:** P101, P102, P106 (pipeline, ветка `feat/agent-pipeline`)
**Метод:** `dispatch → исполнитель → verify (exit-код) → functional review → pattern review → done`.

## Итог

| Контракт | Что сделано | Verify | Functional | Pattern |
|---|---|---|---|---|
| **P101** | Регистрация снова собирает и сохраняет `portfolio_link`, `contact`, `inn`, `is_self_employed`, `experience`, `desired_payment`, `skills`; worker-only поля не пишутся employer'у; skills — `sync_user_skills_raw` с логом; savepoint вокруг `register_user` для `IntegrityError` | 2/2 exit 0 | PASS | PASS |
| **P102** | Портированы `validate_inn_checksum` (10/12, ФНС) и `is_valid_contact`; `validate_password` — ASCII A-Z/a-z, цифра, спецсимвол, без пробелов; валидация в регистрации и профиле | 3/3 exit 0 | PASS | PASS |
| **P106** | После смены пароля `refresh_from_db` + `update_session_auth_hash`: текущая сессия жива, остальные разлогиниваются | 2/2 exit 0 | PASS | PASS |
| **P103** | Login: per-IP 20/час, cache-lockout после 5 неудач (Redis в проде), `PermissionDenied` показывается сообщением; cache fail → fail-closed | 3/3 exit 0 | PASS | PASS |
| **P104** | Cooldown reset/resend в общем cache; IP-лимиты register/reset/resend 10/час; cache fail → fail-closed; `_COOLDOWNS` удалён | 3/3 exit 0 | PASS | PASS |
| **P107** | PDF в verification-docs по magic bytes; avatars/job photos PDF отклоняют; шаблон обновлён | 2/2 exit 0 | PASS | PASS |
| **P108** | Fallback `photo_url` → `avatar_url` на `/profile`, `/workers/<id>`, `/workers`; avatar_url приоритет | 2/2 exit 0 | PASS | PASS |
| **P114** | При удалении аккаунта удаляются avatar/verification-doc/job photos; ошибки файлов логируются, аккаунт удаляется | 2/2 exit 0 | PASS | PASS |
| **B001** | Tailwind `content` и pre-deploy freshness включают `djadmin/core/templates`; CSS пересобран; `pre_deploy_check` 7/7 | 3/3 exit 0 | PASS | PASS |
| **T001** | `expire_old_jobs` корректно читает dict-результат `call_rpc('expire_unfilled_jobs')`; `int(dict)`/TypeError устранён, RPC-счётчик учитывается | 2/2 exit 0 | PASS | PASS |
| **P112** | IDOR-матрица: A не меняет профиль B, экспорт только свой, удаление только себя, жалоба reporter=A/reported=B, self-report отклонён | 2/2 exit 0 | PASS | PASS (после fixing) |
| **P110** | ORM `create_user` → `email_verified=False`, login запрещён; `create_superuser` verified; DB default не тронут (P113) | 2/2 exit 0 | PASS | PASS |
| **P105** | Транзакционная почта: `send_transactional_email.delay` + sync fallback при ошибке enqueue/импорта; Celery retry 3; тесты async/fallback/import-error | 3/3 exit 0 | PASS | PASS (после fixing) |

## Доказательства

- Логи: `context/agent-pipeline/logs/P101.verify.log`, `P102.verify.log`, `P106.verify.log`.
- Тесты:
  - P101: `core.tests.test_auth_flows` — 20 OK; worker-регистрация сохраняет поля/навыки, employer — нет.
  - P102: `test_auth_flows` — 24 OK; `test_profile_flows.ProfileEditTests` — 8 OK; неверный ИНН
    (`500100732258`), контакт `ab`/`!!@@@$$`, пароль с пробелом/кириллицей отклоняются.
  - P106: `ProfileEditTests` — 9 OK; два клиента: текущая сессия 200, вторая 302 на login.
  - P103: `test_auth` + `test_flows` — 35 OK; `test_auth_flows` — 24 OK. 21-й login с IP
    блокируется; 5 неудач → сообщение о блокировке (не 403); cache fail → сообщение.
  - P104: `test_auth_flows` — 26 OK; `test_auth` + `test_flows` — 35 OK. 11-й register
    блокируется; cooldown reset/resend не отправляет второе письмо; cache fail → без профиля.
  - P107: `test_parity_ext.UploadTests` — 11 OK; PDF verification принят, PDF avatar отклонён.
  - P108: `test_public_views` — 14 OK; fallback и приоритет avatar_url на трёх страницах.
  - P114: `test_parity_ext.UploadTests` — 12 OK; после delete_account файлы отсутствуют,
    включая JobPhoto/Job.photo_urls; отсутствующий файл не ломает удаление.
  - B001: `npm run build:css` exit 0; `pre_deploy_check.py` 7/7, «Safe to deploy»;
    scan видит 98 источников, 39 Django-шаблонов (было 59/0).
  - T001: `test_tasks` — 8 OK; `expire_old_jobs: orm=0 rpc=3`, TypeError отсутствует.
  - P112: `test_profile_flows` + `test_parity_ext` — 50 OK. Первый pattern-review дал FAIL
    (self-report мог быть замаскирован rate-limit), после fixing — `cache.clear()` перед
    self-report + различение RPC/rate-limit, повторный pattern-review PASS.
  - P110: `test_auth` + `test_auth_flows` — 42 OK; `create_user` unverified, login запрещён,
    `create_superuser` verified; `make_profile` остаётся verified-фикстурой.
  - P105: `test_auth_flows` — 29 OK; `test_tasks` — 8 OK. Первый pattern-review FAIL
    (импорт задачи вне try обходил fallback), после fixing — импорт внутри try +
    тест `sys.modules['core.tasks']=None`, повторный pattern-review PASS.
- **Кросс-регрессия:** `test_auth`, `test_auth_flows`, `test_flows`, `test_profile_flows`,
  `test_public_views`, `test_parity_ext` → **114 tests, OK**.
- **Полный `manage.py test core`:** **231 test, OK** (после L001/миграций); в логе до T001 был
  `TypeError: int() argument ... dict` в `expire_old_jobs` — исправлен T001;
  после T001 задача пишет `rpc=3`/`rpc=106`, TypeError отсутствует.
- **Pre-deploy:** `scripts/pre_deploy_check.py` → **7/7, 0 проблем, Safe to deploy**.
- Диф P1-батча: 9 уникальных файлов:
  `forms_auth.py`, `views_auth.py`, `templates/core/register.html`, `forms_profile.py`,
  `views_profile.py`, `ratelimit.py`, `auth_backend.py`, `views_flow.py`,
  `tests/test_auth.py`, `tests/test_auth_flows.py`, `tests/test_profile_flows.py`
  (часть файлов пересекается между контрактами).

## Решения и последствия

1. **Политика пароля теперь строго Flask-паритет:** ASCII `A-Z`/`a-z`, цифра, спецсимвол,
   без пробелов. Это влияет только на **новые** пароли (регистрация, сброс, смена);
   существующие пароли продолжают работать на login, потому что login не вызывает
   `validate_password`. Миграции/принудительной смены нет.
2. **ИНН** принимается только 12 цифр + контрольная сумма; для `intent=post_jobs` валидация
   пропускается, потому что INN — worker-only поле.
3. **Контакт** — email / телефон / `@username`, минимум 3 символа; пустой контакт допустим.
4. **Навыки** при регистрации сохраняются только worker; ошибка синхронизации навыков
   логируется, но не откатывает регистрацию (пользователь уже создан RPC).
5. **Сессии:** Django хранит auth-hash в сессии; после смены пароля текущая сессия обновляется,
   остальные сбрасываются при следующем запросе. Это современный Django-паттерн
   (`update_session_auth_hash`), без JWT/jti.
6. **Login:** `django.contrib.auth.authenticate` глушит `PermissionDenied` бэкенда, поэтому
   view после `authenticate` проверяет `ProfileBackend.lock_remaining(email)` — иначе
   6-я попытка показывала бы общее «неверный пароль», а не блокировку. Это осознанный
   обход поведения Django, покрыт тестом.
7. **Rate-limit auth:** per-IP ключи `rl:ip:<bucket>:<ip>`; сбой cache → fail-closed
   (сообщение, не 500). Для login — 20/час, register/reset/resend — 10/час.

## P1-13 / DB-default P1-10 — локально выполнено

- Клон `trudnik_migtest` (pg_dump/restore) → rehearsal; первый apply выявил несовместимость
  migration 130 со старой 4-арг `register_user`; 130 сделан идемпотентным (DO/to_regprocedure).
- Клон: 65/65 миграций, `email_verified default=false`.
- Dev `trudnik`: бэкап `/tmp/trudnik_pre_p113.dump`, применено 123–150 (28 шт.), 65/65.
- Gate `scripts/check_migrations.py` → `RESULT: OK` (pending=0, default=false, reset RPC present).
- Production Amvera не трогался; процедура окна — [MIGRATION_LEDGER.md](MIGRATION_LEDGER.md).

## Осталось

- **Production:** применить 123–150 в окно с бэкапом; затем `check_migrations.py` (exit 0).
- **P2 auth/profile:** UX/маршруты/мёртвые шаблоны (см. DISCREPANCIES.md).
- **Jobs/applications P1:** JOB-P1-01…13 — аудит готов, контракты впереди
  ([DISCREPANCIES_JOBS.md](DISCREPANCIES_JOBS.md)).
- **Коммиты:** `9a7c0a4` (pipeline tooling/audit) и `00e0cc2` (parity-фиксы) на
  `feat/agent-pipeline`; `main` — `3f4aa40` без изменений. `state.json` и `*.verify.log` —
  runtime, в git не коммитятся (`.gitignore`); durable evidence — `progress.md`,
  `decisions.md`, `tasks/`, `packs/`, `docs/parity/`.
