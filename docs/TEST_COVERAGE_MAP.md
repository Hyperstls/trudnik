# Карта покрытия тестами (Test Coverage Map)

Дата: 2026-08-15 (обновления: 2026-08-16, 2026-08-21, **2026-09-04 мультирольность**). Метод: статический анализ (`@*_bp.route` в `app/blueprints/*.py` → поиск URL-литералов в `tests/test_*.py`; locustfile.py и conftest* НЕ учитываются как тесты) + ручная верификация ложных срабатываний/пропусков чтением кода тестов.

## 📌 Обновление 2026-09-04 (мультирольность)

Любой пользователь может создавать задания и откликаться; `role_required` удалены с бизнес-действий (доступ = владение). Роль-зависимые тесты обновлены (test_favorites_api worker→200). Прогоны: mock **553 passed**, integration **147 passed**, live-сценарии MR-01..MR-06 ✓ (см. docs/QA_TEST_CASES.md). Регистрация — intent-карточки (both/find_work/post_jobs).

## 📌 Финальное обновление 2026-08-21 (live-прогон, актуальный код)

Полный прогон на живом docker-стеке (код с Yandex SmartCaptcha + MAX-only верификацией; templates/static смонтированы в контейнер):
- **Mock**: 540 passed / 0 failed (включая 6 новых файлов: test_push_endpoints 11, test_notifications_api 12, test_favorites_api 12, test_admin_bulk_endpoints 12, test_misc_gaps 9, test_stop_words_unit 18 + ранее 74)
- **Integration** (`-m integration`, TEST_BASE_URL:8000): **147 passed / 0 failed** / 50 data-skip (fixtures skip без данных — норма)
- **E2E** (tests_e2e, Playwright chromium): **113 passed / 0 failed**
- pre_deploy_check: 0 проблем.

Инфраструктурные находки прогона: C22 lockout и per-IP лимиты чистятся RESP-клиентом в conftest (модуль redis замокан — прямой импорт недоступен); module-scope сессии; ID новых заданий из Location-заголовка; binding-time лотерея PostgREST-мока решена детерминированными monkeypatch в тестах.

Итоговое pytest-покрытие маршрутов: ~97% (142/146). Остаток — только статистика/редиректы без бизнес-логики.

Полный реестр кейсов (110, приоритизирован, включая MANUAL и задокументированные дефекты): **docs/QA_TEST_CASES.md**.

Порог матчинга: самый длинный статический (без `<param>`) сегмент URL ≥ 5 символов. Из-за порога часть маршрутов верифицирована вручную (помечены в столбце Match).

## 📌 Обновление 2026-08-16

Топ-пробелы из summary ниже закрыты новым файлом **`tests/test_coverage_gaps.py`** (19 тестов):
- `/uploads/avatars/*` + `/uploads/verification-docs/*` — path traversal, IDOR (гость/чужой/владелец)
- `/verify-email/<token>` (невалидный/валидный) + `/verify-email/resend`
- Публичные страницы: `/terms`, `/privacy`, `/pricing`, `/faq`, `/robots.txt`
- `/ready` (200/503 с моками зависимостей) + `/metrics` (Prometheus-метрики)
- `/profile/delete-account` без сессии

Также добавлен `tests/test_messenger_verify.py` (17→18 тестов: все messenger-эндпоинты; `/messenger/diagnose` закрыт admin_required) и `tests/test_validators.py` (44). Актуальное pytest-покрытие: ~119/146 (81%).


## admin_dashboard (`app/blueprints/admin_dashboard.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| health_check | GET | `/admin/health` | - | - | ❌ |
| admin_panel | GET | `/admin` | test_a6_completed_to_open.py | admin | ✅ |

## admin_diagnostics (`app/blueprints/admin_diagnostics.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| job_stats | GET | `/admin/job-stats` | test_buttons_backend.py | admin/job-stats | ✅ |
| migrations_status | GET | `/admin/migrations-status` | test_b1_admin_diagnostics_token.py | admin/migrations-status | ✅ |
| reset_circuit_breaker | POST | `/admin/reset-circuit-breaker` | test_b1_admin_diagnostics_token.py | admin/reset-circuit-breaker | ✅ |

## admin_dictionaries (`app/blueprints/admin_dictionaries.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| get_skills | GET | `/admin/skills` | test_buttons_backend.py | admin/skills | ✅ |
| add_skill | POST | `/admin/skills` | test_buttons_backend.py | admin/skills | ✅ |
| reorder_skills | POST | `/admin/skills/reorder` | test_buttons_backend.py | admin/skills/reorder | ✅ |
| update_skill | PUT | `/admin/skills/<skill_id>` | test_buttons_backend.py | admin/skills | ✅ |
| delete_skill | DELETE | `/admin/skills/<skill_id>` | test_buttons_backend.py | admin/skills | ✅ |
| bulk_delete_skills | POST | `/admin/bulk-delete-skills` | - | - | ❌ |
| get_religions | GET | `/admin/religions` | test_coverage_completion.py | admin/religions | ✅ |
| add_religion | POST | `/admin/religions` | test_coverage_completion.py | admin/religions | ✅ |
| reorder_religions | POST | `/admin/religions/reorder` | - | - | ❌ |
| update_religion | PUT | `/admin/religions/<religion_id>` | test_coverage_completion.py | admin/religions | ✅ |
| delete_religion | DELETE | `/admin/religions/<religion_id>` | test_coverage_completion.py | admin/religions | ✅ |
| bulk_delete_religions | POST | `/admin/bulk-delete-religions` | - | - | ❌ |

## admin_jobs (`app/blueprints/admin_jobs.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| update_job_status | POST | `/admin/jobs/<job_id>/status` | test_a6_completed_to_open.py | admin/jobs | ✅ |
| delete_job_admin | POST | `/admin/jobs/<job_id>/delete` | test_a6_completed_to_open.py | admin/jobs | ✅ |
| bulk_delete_jobs | POST | `/admin/bulk-delete-jobs` | - | - | ❌ |

## admin_users (`app/blueprints/admin_users.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| update_user_role | POST | `/admin/users/<user_id>/role` | test_b4_jti_invalidation.py | admin/users | ✅ |
| delete_user | POST | `/admin/users/<user_id>/delete` | test_b4_jti_invalidation.py | admin/users | ✅ |
| unsuspend_user | POST | `/admin/users/<user_id>/unsuspend` | test_b4_jti_invalidation.py | admin/users | ✅ |
| complaints_queue | GET | `/admin/complaints` | test_phase3_autofreeze.py | admin/complaints | ✅ |
| review_complaint | POST | `/admin/complaints/<report_id>/review` | test_phase3_autofreeze.py | admin/complaints | ✅ |
| bulk_delete_users | POST | `/admin/bulk-delete-users` | test_buttons_backend.py | admin/bulk-delete-users | ✅ |
| test_user_tools | GET,POST | `/admin/test-user` | - | - | ❌ |
| edit_site_content | GET,POST | `/admin/content/<slug>` | - | - | ❌ |

## admin_verification (`app/blueprints/admin_verification.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| approve_employer | POST | `/admin/approve/<user_id>` | test_buttons_backend.py | admin/approve | ✅ |
| reject_employer | POST | `/admin/reject/<user_id>` | test_buttons_backend.py | admin/reject | ✅ |

## applications (`app/blueprints/applications.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| apply_job | POST | `/apply/<job_id>` | test_backend_gaps.py | apply | ✅ |
| apply_selected | POST | `/apply-selected` | test_coverage_completion.py | apply-selected | ✅ |
| unapply_job | POST | `/unapply/<job_id>` | test_buttons_backend.py | unapply | ✅ |
| unapply_selected | POST | `/unapply-selected` | - | - | ❌ |
| api_withdraw_application | POST | `/api/applications/<app_id>/withdraw` | test_buttons_backend.py | api/applications | ✅ |
| my_applications | GET | `/my-applications` | test_buttons_backend.py | my-applications | ✅ |
| api_accept_application | POST | `/api/applications/<app_id>/accept` | test_buttons_backend.py | api/applications | ✅ |
| api_reject_application | POST | `/api/applications/<app_id>/reject` | test_buttons_backend.py | api/applications | ✅ |
| api_reopen_application | POST | `/api/applications/<app_id>/reopen` | test_buttons_backend.py | api/applications | ✅ |
| api_batch_applications | POST | `/api/applications/batch` | test_buttons_backend.py | api/applications/batch | ✅ |
| cancel_application | POST | `/application/<app_id>/cancel` | test_a2_no_ilike_injection.py | application | ✅ |

## auth (`app/blueprints/auth.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| login | GET,POST | `/login` | test_a1_bulk_operations.py | login | ✅ |
| register | GET,POST | `/register` | test_api.py | register | ✅ |
| logout | POST | `/logout` | test_auth.py | logout | ✅ |
| password_reset_request | GET,POST | `/password-reset/request` | test_password_reset.py | password-reset/request | ✅ |
| password_reset_confirm | GET,POST | `/password-reset/confirm/<token>` | test_password_reset.py | password-reset/confirm | ✅ |
| verify_email | GET | `/verify-email/<token>` | - | - | ❌ |
| resend_verification | GET,POST | `/verify-email/resend` | - | - | ❌ |

## blacklist (`app/blueprints/blacklist.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| blacklist | GET | `/blacklist` | test_a1_bulk_operations.py | blacklist | ✅ |
| block_user | POST | `/blacklist/<user_id>` | test_a1_bulk_operations.py | blacklist | ✅ |
| unblock_user | POST | `/unblock/<user_id>` | test_buttons_backend.py | unblock | ✅ |

## chat (`app/blueprints/chat.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| chats_list | GET | `/chats` | test_buttons_backend.py | chats | ✅ |
| chat | GET | `/chat/<application_id>` | test_chat.py | /chat/ (строка 67: GET /chat/<id> → redirect) | ✅ |
| chat_new | GET | `/chat/new/<worker_id>` | test_coverage_completion.py | chat/new | ✅ |
| send_message | POST | `/api/send_message` | test_a3_chat_rate_limit.py | api/send_message | ✅ |
| poll_messages | GET | `/api/messages/<application_id>/poll` | test_chat.py | api/messages | ✅ |
| delete_chats | POST | `/api/delete-chats` | test_coverage_completion.py | api/delete-chats | ✅ |

## core (`app/blueprints/core.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| metrics | GET | `/metrics` | - | - | ❌ |
| health_check | GET | `/health` | test_api.py | health | ✅ |
| ready_check | GET | `/ready` | - | - | ❌ |
| circuit_breaker_health | GET | `/health/circuit-breaker` | - | - | ❌ |
| postgrest_health | GET | `/health/postgrest` | - | - | ❌ |
| uploaded_avatar | GET | `/uploads/avatars/<path:filename>` | - | - | ❌ |
| uploaded_verification_doc | GET | `/uploads/verification-docs/<path:filename>` | - | - | ❌ |
| service_worker | GET | `/sw.js` | test_critical_gaps.py | sw.js | ✅ |
| offline | GET | `/offline` | test_architecture.py | offline | ✅ |
| assetlinks | GET | `/.well-known/assetlinks.json` | test_api.py | .well-known/assetlinks.json | ✅ |
| favicon | GET | `/favicon.ico` | - | - | ❌ |
| jobs_redirect | GET | `/jobs` | - | - | ❌ |
| search_redirect | GET | `/search` | - | - | ❌ |
| static_directory_redirect | GET | `/static/` | test_api.py | static | ✅ |
| terms | GET | `/terms` | - | - | ❌ |
| privacy | GET | `/privacy` | - | - | ❌ |
| client_error_report | POST | `/api/client-error` | test_e3_client_error_endpoint.py | api/client-error | ✅ |

## employers (`app/blueprints/employers.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| employers_list | GET | `/employers` | test_buttons_backend.py | employers | ✅ |
| employer_detail | GET | `/employers/<employer_id>` | test_buttons_backend.py | employers | ✅ |
| toggle_favorite | POST | `/employers/<employer_id>/favorite` | test_buttons_backend.py | employers | ✅ |
| add_employer_favorite_api | POST | `/api/employers/favorites/add` | test_buttons_backend.py | api/employers/favorites/add | ✅ |
| remove_employer_favorite_api | POST | `/api/employers/favorites/remove` | - | - | ❌ |
| check_employer_favorite_api | POST | `/api/employers/favorites/check` | - | - | ❌ |

## favorites (`app/blueprints/favorites.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| favorites | GET | `/favorites` | test_buttons_backend.py | favorites | ✅ |
| add_favorite | POST | `/favorite/<target_id>` | test_buttons_backend.py | favorite | ✅ |
| remove_favorite | POST | `/unfavorite/<target_id>` | test_buttons_backend.py | unfavorite | ✅ |
| add_favorite_api | POST | `/api/favorites/add` | test_buttons_backend.py | api/favorites/add | ✅ |
| remove_favorite_api | POST | `/api/favorites/remove` | test_buttons_backend.py | api/favorites/remove | ✅ |
| check_favorite_api | POST | `/api/favorites/check` | - | - | ❌ |
| remove_favorites_selected | POST | `/api/favorites/remove-selected` | test_buttons_backend.py | api/favorites/remove-selected | ✅ |

## jobs (`app/blueprints/jobs.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| index | GET | `/` | test_worker_job_visibility.py | app_client.get('/') (строки 23,47) | ✅ |
| workers | GET | `/workers` | test_a1_bulk_operations.py | workers | ✅ |
| job_detail | GET | `/jobs/<job_id>` | test_buttons_backend.py | GET /jobs/{id} (62,84) + 404-кейс test_backend_gaps.py:477 | ✅ |
| pricing | GET | `/pricing` | - | - | ❌ |
| job_new | GET,POST | `/job/new` | test_api.py | job/new | ✅ |
| my_jobs | GET | `/my-jobs` | test_a1_bulk_operations.py | my-jobs | ✅ |
| my_jobs_action | POST | `/my-jobs/action` | test_a1_bulk_operations.py | my-jobs/action | ✅ |
| repost_job | POST | `/repost-job/<job_id>` | test_buttons_backend.py | repost-job | ✅ |
| cancel_job | POST | `/cancel-job/<job_id>` | test_buttons_backend.py | cancel-job | ✅ |
| restore_job | POST | `/restore-job/<job_id>` | test_buttons_backend.py | restore-job | ✅ |
| api_force_complete_job | POST | `/api/jobs/<job_id>/force-complete` | test_buttons_backend.py | force-complete | ✅ |
| delete_job | POST | `/delete-job/<job_id>` | test_buttons_backend.py | delete-job | ✅ |
| invitations_page | GET | `/invitations` | test_api.py | invitations | ✅ |
| reject_all_invitations | POST | `/api/invitations/reject-all` | test_buttons_backend.py | api/invitations/reject-all | ✅ |
| edit_job | GET,POST | `/jobs/<job_id>/edit` | test_buttons_backend.py | POST /jobs/{id}/edit (626) | ✅ |
| add_favorite_job | POST | `/favorite-job/<job_id>` | test_buttons_backend.py | favorite-job | ✅ |
| remove_favorite_job | POST | `/unfavorite-job/<job_id>` | test_buttons_backend.py | unfavorite-job | ✅ |

## jobs_api (`app/blueprints/jobs_api.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| api_skills | GET | `/api/skills` | test_api.py | api/skills | ✅ |
| invite_worker | POST | `/api/invite/<job_id>/<worker_id>` | test_buttons_backend.py | api/invite | ✅ |
| list_invitations | GET | `/api/invitations` | test_api.py | api/invitations | ✅ |
| respond_invitation | POST | `/api/invitations/<invitation_id>/respond` | test_api.py | api/invitations | ✅ |

## messenger_verify (`app/blueprints/messenger_verify.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| start_verification | GET | `/messenger/start/<platform>` | test_messenger_verify.py | messenger/start | ✅ |
| diagnose | GET | `/messenger/diagnose` | test_messenger_verify.py | messenger/diagnose | ✅ |
| max_webhook | POST | `/messenger/webhook/max` | test_messenger_verify.py | messenger/webhook/max | ✅ |
| telegram_webhook | POST | `/messenger/webhook/telegram` | test_messenger_verify.py | messenger/webhook/telegram | ✅ |

## notifications (`app/blueprints/notifications.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| get_ws_token | GET | `/api/ws/token` | test_ws_token.py | api/ws/token | ✅ |
| notifications | GET | `/notifications` | test_a2_no_ilike_injection.py | notifications | ✅ |
| api_unread_count | GET | `/api/notifications/unread-count` | - | - | ❌ |
| api_notifications | GET | `/api/notifications` | test_buttons_backend.py | api/notifications | ✅ |
| api_read_all | POST | `/api/notifications/read-all` | - | - | ❌ |
| api_delete_notification | POST | `/api/notifications/<notification_id>/delete` | test_buttons_backend.py | api/notifications | ✅ |
| api_delete_all_notifications | POST | `/api/notifications/delete-all` | test_buttons_backend.py | api/notifications/delete-all | ✅ |
| mark_read_route | POST | `/notification/<notification_id>/read` | test_a2_no_ilike_injection.py | notification | ✅ |
| notification_settings_page | GET | `/notifications/settings` | test_buttons_backend.py | notifications/settings | ✅ |
| api_get_preferences | GET | `/api/notifications/preferences` | test_buttons_backend.py | api/notifications/preferences | ✅ |
| api_update_preferences | POST | `/api/notifications/preferences` | test_buttons_backend.py | api/notifications/preferences | ✅ |
| push_vapid_public_key | GET | `/push/vapid-public-key` | - | - | ❌ |
| push_vapid_public_key_alias | GET | `/notifications/push/vapid-public-key` | - | - | ❌ |
| push_subscribe | POST | `/push/subscription` | - | - | ❌ |
| push_unsubscribe | DELETE | `/push/subscription` | - | - | ❌ |
| push_get_subscriptions | GET | `/push/subscription` | - | - | ❌ |

## profile (`app/blueprints/profile.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| profile | GET | `/profile` | test_a5_rating_trigger.py | profile | ✅ |
| update_profile | POST | `/profile/update` | test_backend_gaps.py | profile/update | ✅ |
| delete_photo | POST | `/profile/delete-photo` | - | - | ❌ |
| delete_account | POST | `/profile/delete-account` | - | - | ❌ |
| export_data | GET | `/profile/export-data` | test_phase1b_compliance.py | profile/export-data | ✅ |
| change_password | POST | `/profile/change-password` | test_buttons_backend.py | profile/change-password | ✅ |
| verify_employer | GET,POST | `/verify-employer` | test_buttons_backend.py | verify-employer | ✅ |
| public_profile | GET | `/profile/<user_id>` | test_a5_rating_trigger.py | profile | ✅ |
| report_user | POST | `/profile/<user_id>/report` | test_a5_rating_trigger.py | profile | ✅ |

## ratings (`app/blueprints/ratings.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| get_job_ratings | GET | `/api/ratings/<job_id>` | test_a7_ratings_pii.py | api/ratings | ✅ |
| get_user_rating | GET | `/api/ratings/user/<user_id>` | test_a7_ratings_pii.py | api/ratings/user | ✅ |
| upsert_rating | POST | `/api/ratings` | test_a7_ratings_pii.py | api/ratings | ✅ |
| get_completed_jobs_for_rating | GET | `/api/ratings/completed-jobs/<target_user_id>` | test_buttons_backend.py | api/ratings/completed-jobs | ✅ |
| get_user_rating_details | GET | `/api/ratings/user/<user_id>/details` | test_a7_ratings_pii.py | api/ratings/user | ✅ |
| user_ratings_page | GET | `/ratings/user/<user_id>` | test_a7_ratings_pii.py | ratings/user | ✅ |
| rate_workers_page | GET | `/jobs/<job_id>/rate-workers` | test_buttons_frontend.py | rate-workers | ✅ |

## seo (`app/blueprints/seo.py`)

| Endpoint | Method | URL | Test file | Match | Status |
|----------|--------|-----|-----------|-------|--------|
| robots | GET | `/robots.txt` | - | - | ❌ |
| sitemap | GET | `/sitemap.xml` | test_critical_gaps.py | sitemap.xml | ✅ |

---

## Summary

- Всего маршрутов: **146** (20 blueprints)
- Покрыто pytest-тестами: **111** (**76%**)
- Не покрыто: **35**


## Топ-5 непокрытых по критичности

1. **`/uploads/avatars/<path:filename>` + `/uploads/verification-docs/<path:filename>`** — path traversal и IDOR: доступ к чужим верификационным документам без теста авторизации. Security-критично (правило 03_security_review.md п.16).
2. **`/verify-email/<token>` + `/verify-email/resend`** — auth-флоу подтверждения email: валидация/одноразовость токена, rate limit. Безопасность токена не протестирована.
3. **`/profile/delete-photo` + `/profile/delete-account`** — деструктивные операции, 152-ФЗ (право на удаление ПДн, ст.9/14). Ошибка здесь = потеря данных пользователя или невозможность их удалить.
4. **`/push/subscription` (POST/DELETE/GET) + оба `/push/vapid-public-key`** — HTTP-слой не протестирован: test_c10/test_push_service покрывают только service-слой (push_service), не эндпоинты.
5. **`/metrics` (публичный Prometheus) + `/ready` (Dockerfile HEALTHCHECK прода)** — /metrics может утечь внутренние метрики без авторизации; /ready отказ = ложные рестарты контейнера на Amvera.

Прочие непокрытые (35 всего): admin bulk-операции (skills/religions/jobs), /admin/test-user, /admin/content/<slug>, /admin/health, /unapply-selected, /health/circuit-breaker, /health/postgrest, api/notifications/unread-count + read-all, api/employers/favorites/{remove,check}, api/favorites/check, /favicon.ico, /terms, /privacy, /pricing, /robots.txt, /jobs (тривиальный редирект).

## Рекомендации

- Приоритет 1: тесты авторизации на /uploads/* (path traversal + IDOR) — потенциальная уязвимость.
- Приоритет 2: тесты verify-email флоу (истёкший/повторный/чужой токен).
- Приоритет 3: smoke-тесты публичных страниц (/terms, /privacy, /pricing, /robots.txt) — дешёвые, ловят регрессии шаблонов.
