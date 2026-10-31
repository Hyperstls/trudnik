# P0 results — auth / registration / profile

**Дата:** 2026-10-31
**Контракты:** P001–P004 (pipeline, ветка `feat/agent-pipeline`)
**Метод:** `dispatch → исполнитель (без истории) → verify (exit-код) → functional review →
pattern review (XSS/fail-open/N+1) → review --ok`.

## Итог

| Контракт | Что исправлено | Файлы | Verify | Functional | Pattern | Статус |
|---|---|---|---|---|---|---|
| P001 | Капча читает `smart-token` (Yandex), `smart_token` — fallback; fail-closed сохранён; ключ капчи передаётся в render сброса | `views_auth.py`, `test_auth_flows.py` | 3/3 exit 0 | PASS | PASS | done |
| P002 | verification-docs: owner/admin, остальным 404; `private, no-store`, `attachment`, `nosniff`; ACL по каноническому пути | `views_profile_ext.py`, `test_parity_ext.py` | 2/2 exit 0 | PASS | PASS | done |
| P003 | Публичный профиль: убраны `contact`, `email_public`, `religion_id`; нейтральный текст про контакты | `views.py`, `worker_detail.html`, `test_public_views.py` | 2/2 exit 0 | PASS | PASS | done |
| P004 | `religion` убран из `ProfileForm` и `ProfileAdmin.fieldsets`; колонка dormant | `forms_profile.py`, `admin/users.py`, `test_profile_flows.py` | 2/2 exit 0 | PASS | PASS | done |

## Доказательства

- Логи: `context/agent-pipeline/logs/P001.verify.log` … `P004.verify.log`.
- Тесты:
  - P001: `core.tests.test_auth_flows` — 18 тестов OK; два новых теста проверяют переданный токен.
  - P002: `core.tests.test_parity_ext.UploadTests` — 9 тестов OK (guest/other/owner/admin, headers,
    traversal, alias `avatars/../verification-docs/...`).
  - P003: `core.tests.test_public_views` — 10 тестов OK; новый тест проверяет реальные
    contact/email/religion для анонима и другого пользователя.
  - P004: `core.tests.test_profile_flows.ProfileEditTests` — 6 тестов OK; POST с religion
    не меняет `religion_id`.
- **Кросс-регрессия:** `manage.py test core.tests.test_auth test_auth_flows test_flows
  test_profile_flows test_public_views test_parity_ext --keepdb` → **100 tests, OK**.
- **Диф:** 10 tracked-файлов, +194/−21. Все — из контрактов P001–P004.

## Осталось / release notes

1. **Tailwind/build drift (BUILD-01).**
   `scripts/pre_deploy_check.py` [7/7] падает: `tailwind.min.css` старше `templates/terms.html`.
   Причина — не наши P0-правки: `tailwind.config.js` (`content`) и pre-deploy scan смотрят
   только корневые `templates/` (legacy Flask), а Django-шаблоны лежат в
   `djadmin/core/templates/core/`. `npm run build:css` в текущем виде соберёт CSS не из тех
   шаблонов и создаст ложное ощущение «свежести». Нужна отдельная задача: включить
   `djadmin/core/templates/**/*.html` в `content`, обновить scan в `pre_deploy_check.py`,
   затем пересобрать CSS и проверить UI. Классы, затронутые P003
   (`text-neutral-500`, `text-neutral-700`, `mb-4`, `text-sm`), в текущем CSS уже есть —
   визуального регресса от P003 нет.
2. **Коммит не делался.** Изменения лежат в рабочем дереве `feat/agent-pipeline`.
   Перед коммитом: решить BUILD-01 и `npm run build:css`, затем `pre_deploy_check.py` (0 проблем),
   `py_compile` изменённых файлов, полный `pytest`/`manage.py test`.
3. **P1/P2 открыты:** регистрация/валидация, rate-limit/lockout/cooldown, сессии, PDF,
   legacy-аватары, deletion файлов, migration ledger, RLS/IDOR-матрица, UX/маршруты.
   Следующие контракты — по приоритету P1.

## Что подтверждено двумя гейтами

- Contract verify: реальные exit-коды команд, не текстовый вывод.
- Functional review: отдельный ревьюер, только diff + критерии, без отчёта исполнителя.
- Pattern review: отдельный ревьюер, XSS/fail-open/N+1; вердикты записаны в `decisions.md`
  через `note` (P001–P004).
- Паттерн-ревью **не** заменял verify: P0-контракты не переходили в `done` без зелёного verify.
