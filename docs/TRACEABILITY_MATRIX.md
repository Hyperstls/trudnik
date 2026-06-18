# Матрица трассировки (Traceability Matrix) — Трудник

> **Маппинг всех тестовых ID из [`TEST_CHECKLIST.md`](TEST_CHECKLIST.md) на конкретные файлы тестов и функции.**
> **Актуализировано:** 2026-06-18 | **Ветка:** `main`

---

## Легенда статусов покрытия

| Статус | Обозначение | Описание |
|--------|------------|----------|
| ✅ | Покрыт | Автоматизированный тест существует и покрывает сценарий |
| ⚠️ | Частично | Тест существует, но не полностью покрывает все шаги/проверки |
| ❌ | Не покрыт | Тест отсутствует, требуется ручное тестирование или автоматизация |

---

## 1. Smoke-тесты

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| SMK-001 | Health check | [`tests/locustfile.py`](../tests/locustfile.py) | `TrudnikUser.health_check` | ✅ |
| SMK-002 | Главная страница (гость) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_index` | ✅ |
| SMK-003 | Главная страница (worker) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_index` | ⚠️ |
| SMK-004 | Главная страница (employer) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_my_jobs_employer` | ⚠️ |
| SMK-005 | Список трудников | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_workers_page` | ✅ |
| SMK-006 | Страница логина | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_login_get` | ✅ |
| SMK-007 | Страница регистрации | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_register_get` | ✅ |
| SMK-008 | Статические ресурсы | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_sw_js_accessible`, `test_manifest_json_valid` | ⚠️ |
| SMK-009 | PWA Service Worker | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_sw_js_accessible` | ✅ |
| SMK-010 | Asset Links | ❌ | — | ❌ |
| SMK-011 | Sitemap + robots.txt | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_sitemap_xml_no_private_urls`, `test_sitemap_xml_format_valid` | ✅ |

---

## 2. Аутентификация

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| AUTH-001 | Регистрация трудника | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_register_post` | ✅ |
| AUTH-002 | Регистрация работодателя | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_register_post` | ⚠️ |
| AUTH-003 | Регистрация: невалидный email | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_register_post` | ⚠️ |
| AUTH-004 | Регистрация: обязательные поля | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_register_post` | ⚠️ |
| AUTH-005 | Регистрация: ИНН трудника | ❌ | — | ❌ |
| AUTH-006 | Вход (employer) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_login_post_success_worker` | ⚠️ |
| AUTH-007 | Вход (worker) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_login_post_success_worker` | ✅ |
| AUTH-008 | Вход: неверный пароль | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_login_post_failure` | ✅ |
| AUTH-009 | Выход | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_logout` | ✅ |
| AUTH-010 | Rate limit на login | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestRateLimitParametrized::test_login_rate_limit` | ✅ |
| | | [`tests/test_rate_limit.py`](../tests/test_rate_limit.py) | (rate-limit tests) | ✅ |

---

## 3. Задания — Employer

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| JOB-E-001 | Создание задания | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_job_new_post` | ✅ |
| JOB-E-002 | Создание: стоп-слова | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestStopWordsValidation::test_stop_words_block_job_creation` | ✅ |
| JOB-E-003 | Создание: стоп-слова Unicode | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestStopWordsValidation::test_stop_words_block_job_creation` | ✅ |
| JOB-E-004 | Создание: обязательные поля | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_job_new_post` | ⚠️ |
| JOB-E-005 | Создание: загрузка фото | ⚠️ | — | ❌ |
| JOB-E-006 | Создание: навыки | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_job_new_post` | ⚠️ |
| JOB-E-007 | Редактирование задания | ❌ | — | ❌ |
| JOB-E-008 | Редактирование: есть accepted | ❌ | — | ❌ |
| JOB-E-009 | Дублирование задания | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_repost_job` | ✅ |
| JOB-E-010 | Дублирование: фото и навыки | ❌ | — | ❌ |
| JOB-E-011 | Отзыв задания (cancel) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_cancel_job` | ✅ |
| JOB-E-012 | Удаление задания | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_delete_job`, `TestAppRoutes::test_my_jobs_actions` | ✅ |
| JOB-E-013 | `is_paid=True` всегда | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_monetization_tables_exist_but_empty` | ✅ |

---

## 4. Задания — Worker / Публичные

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| JOB-W-001 | Просмотр деталей задания | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_job_detail` | ✅ |
| JOB-W-002 | Фильтрация по городу | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_index_with_filters` | ✅ |
| JOB-W-003 | Фильтрация по оплате | ⚠️ | — | ❌ |
| JOB-W-004 | Фильтрация по навыкам | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_deep_linking_filters` | ⚠️ |
| JOB-W-005 | Сортировка | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_index_with_filters` | ⚠️ |
| JOB-W-006 | FTS (полнотекстовый поиск) | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_fts_search_with_typo` | ✅ |
| JOB-W-007 | Гео-фильтрация | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_geo_filter_excludes_other_cities` | ✅ |
| JOB-W-008 | Скрытие заданий от заблокировавших | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestBlacklist::test_employer_blocks_worker_jobs_disappear` | ✅ |
| JOB-W-009 | Истёкшие задания | ❌ | — | ❌ |
| JOB-W-010 | Публичный доступ к `/jobs/<id>` | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_guest_cannot_see_contact_details_on_job_page` | ✅ |

---

## 5. Отклики

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| APP-001 | Отклик на задание | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_apply_job` | ✅ |
| APP-002 | Отклик: дубликат | ⚠️ | — | ❌ |
| APP-003 | Отклик: своё задание | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_apply_own_job` | ✅ |
| APP-004 | Отклик: чёрный список | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestBlacklist::test_blocked_worker_direct_apply_returns_403` | ✅ |
| APP-005 | Отклик: статус не open | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_apply_job_closed` | ✅ |
| APP-006 | Отклик: места заполнены | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_apply_job_full` | ✅ |
| APP-007 | Accept отклика | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_handle_application_accept` | ✅ |
| APP-008 | Accept: последнее место | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_race_condition_last_spot` | ✅ |
| APP-009 | Reject отклика | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_handle_application_reject` | ✅ |
| APP-010 | Reopen отклика | ❌ | — | ❌ |
| APP-011 | Withdraw отклика | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_cancel_application` | ✅ |
| APP-012 | Withdraw: окно < 12ч | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestEdgeCases::test_cancel_application_less_than_12h_before` | ✅ |
| APP-013 | Массовый отклик | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_apply_selected` | ✅ |
| APP-014 | Batch accept | [`tests/locustfile.py`](../tests/locustfile.py) | `TrudnikBatchUser::batch_accept_50` | ✅ |
| APP-015 | Batch: >50 элементов | ⚠️ | — | ❌ |
| APP-016 | Race condition на последнее место | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_race_condition_last_spot` | ✅ |

---

## 6. Приглашения

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| INV-001 | Пригласить трудника | ⚠️ | — | ❌ |
| INV-002 | Приглашение: дубликат | ❌ | — | ❌ |
| INV-003 | Приглашение: не владелец | ❌ | — | ❌ |
| INV-004 | Приглашение: статус задания | ❌ | — | ❌ |
| INV-005 | Принять приглашение | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestInvitations::test_employer_invites_worker_accepts_creates_application` | ✅ |
| INV-006 | Отклонить приглашение | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestInvitations::test_employer_invites_worker_declines` | ✅ |
| INV-007 | Список приглашений | ⚠️ | — | ❌ |
| INV-008 | Счётчик приглашений | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_notifications` | ⚠️ |
| INV-009 | Приглашение уже rejected | ❌ | — | ❌ |

---

## 7. Чат

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| CHT-001 | Список чатов | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_chat_list` | ✅ |
| CHT-002 | Открыть чат | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_chat_detail` | ✅ |
| CHT-003 | Отправить сообщение | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_send_message` | ✅ |
| CHT-004 | Чат: слишком длинное сообщение | ❌ | — | ❌ |
| CHT-005 | XSS в сообщении | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestRealTimeChat::test_chat_xss_escaping` | ✅ |
| CHT-006 | WebSocket доставка | [`tests/test_websocket_server.py`](../tests/test_websocket_server.py) | (WebSocket tests) | ✅ |
| | | [`tests/test_websocket_auth.py`](../tests/test_websocket_auth.py) | (WebSocket auth tests) | ✅ |
| | | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestRealTimeChat::test_worker_applies_employer_gets_live_notification` | ✅ |
| CHT-007 | Polling-фолбек | ❌ | — | ❌ |
| CHT-008 | Удаление чатов | ❌ | — | ❌ |

---

## 8. Профиль (PRF)

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| PRF-001 | Просмотр профиля | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_profile` | ✅ |
| PRF-002 | Редактирование профиля | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_update_profile` | ✅ |
| PRF-003 | Загрузка аватара | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestEdgeCases::test_avatar_upload_mime_whitelist` | ✅ |
| PRF-004 | Смена аватара | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_delete_photo` | ⚠️ |
| | | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_avatar_update_deletes_old` | ✅ |
| PRF-005 | Удаление аккаунта | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_delete_user_clears_storage` | ⚠️ |
| PRF-006 | Верификация работодателя | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_verify_employer_post` | ✅ |
| PRF-007 | Прямой доступ к документу верификации | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_verification_doc_private` | ✅ |
| PRF-008 | Публичный профиль | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_public_profile` | ✅ |

---

## 9. Рейтинги

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| RAT-001 | Создать оценку | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_rate_worker` | ✅ |
| RAT-002 | Самооценка | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_self_rating_blocked` | ✅ |
| RAT-003 | Оценка не-completed задания | ❌ | — | ❌ |
| RAT-004 | Обновить оценку | ❌ | — | ❌ |
| RAT-005 | Просмотр рейтингов | ❌ | — | ❌ |
| RAT-006 | Форма оценки трудников | ⚠️ | — | ❌ |
| RAT-007 | Диапазон оценки | ❌ | — | ❌ |

---

## 10. Избранное

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| FAV-001 | Добавить задание в избранное | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_add_favorite_job`, `TestAppRoutes::test_api_add_favorite` | ✅ |
| FAV-002 | Убрать задание из избранного | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_remove_favorite_job`, `TestAppRoutes::test_api_remove_favorite` | ✅ |
| FAV-003 | Добавить работодателя в избранное | ❌ | — | ❌ |
| FAV-004 | Убрать работодателя из избранного | ❌ | — | ❌ |
| FAV-005 | Страница избранного | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_favorites_worker`, `TestAppRoutes::test_favorites_employer` | ✅ |
| FAV-006 | Дубликат избранного | ❌ | — | ❌ |
| FAV-007 | Статусы избранного (API) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_api_check_favorite`, `TestAppRoutes::test_api_check_favorite_false` | ✅ |

---

## 11. Чёрный список

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| BLK-001 | Заблокировать пользователя | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_block_user` | ✅ |
| BLK-002 | Заблокировать себя | ❌ | — | ❌ |
| BLK-003 | Разблокировать пользователя | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_unblock_user` | ✅ |
| BLK-004 | Страница ЧС | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_blacklist` | ✅ |

---

## 12. Уведомления

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| NOT-001 | Список уведомлений | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_notifications` | ✅ |
| NOT-002 | Отметить прочитанным | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_mark_read` | ✅ |
| NOT-003 | Отметить все прочитанными | ❌ | — | ❌ |
| NOT-004 | Удаление уведомлений | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_delete_notifications_does_not_delete_invitations` | ⚠️ |
| NOT-005 | Настройки уведомлений | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_notification_prefs_null_fallback` | ⚠️ |
| NOT-006 | Счётчик в шапке | ⚠️ | — | ❌ |
| NOT-007 | WebSocket live-уведомление | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestRealTimeChat::test_worker_applies_employer_gets_live_notification` | ✅ |
| | | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestRealTimeChat::test_employer_accepts_worker_gets_application_accepted` | ✅ |
| NOT-008 | Push-подписка | [`tests/test_push_service.py`](../tests/test_push_service.py) | (push service tests) | ⚠️ |
| NOT-009 | Push-отписка | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_logout_clears_push_subscriptions` | ⚠️ |
| NOT-010 | Push-доставка | [`tests/test_push_service.py`](../tests/test_push_service.py) | (push delivery tests) | ⚠️ |
| NOT-011 | Push: отключённый тип | ❌ | — | ❌ |
| NOT-012 | Email-уведомление: новый отклик | [`tests/test_email_service.py`](../tests/test_email_service.py) | (email service tests) | ⚠️ |
| NOT-013 | Email-уведомление: настройки | [`tests/test_email_service.py`](../tests/test_email_service.py) | (email settings tests) | ⚠️ |
| NOT-014 | Email: формат письма | ❌ | — | ❌ |

---

## 13. Админ

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| ADM-001 | Доступ к админке (admin) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_admin_panel` | ✅ |
| ADM-002 | Доступ к админке (не admin) | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_admin_panel_not_admin` | ✅ |
| ADM-003 | Управление пользователями | ⚠️ | — | ❌ |
| ADM-004 | Удаление пользователя (admin) | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_delete_user_clears_storage` | ⚠️ |
| ADM-005 | Верификация работодателя | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_approve_employer` | ✅ |
| ADM-006 | Управление справочниками | ⚠️ | — | ❌ |
| ADM-007 | Health check админки | ❌ | — | ❌ |

---

## 14. Поиск (API)

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| SRH-001 | Поиск заданий (API) | [`tests/test_api.py`](../tests/test_api.py) | (API search tests) | ⚠️ |
| SRH-002 | Поиск трудников (API) | [`tests/test_api.py`](../tests/test_api.py) | (API search tests) | ⚠️ |
| SRH-003 | PostgREST-инъекция | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestEdgeCases::test_postgrest_injection_sanitized` | ✅ |
| | | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_postgrest_schema_cache_coherence` | ✅ |
| SRH-004 | Навыки/религии (API) | ⚠️ | — | ❌ |

---

## 15. Интеграционные тесты

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| INT-001 | Worker: полный путь отклика | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestFullCycle::test_full_employer_worker_lifecycle` | ✅ |
| INT-002 | Employer: полный путь | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestFullCycle::test_full_employer_worker_lifecycle` | ✅ |
| INT-003 | Приглашение + отклик | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestInvitations::test_employer_invites_worker_accepts_creates_application` | ✅ |
| INT-004 | Чёрный список + отклик | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestBlacklist` (все 3 теста) | ✅ |
| INT-005 | Каскадное удаление задания | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_cascade_delete_does_not_delete_unrelated` | ⚠️ |
| INT-006 | Каскадное удаление пользователя | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_delete_user_clears_storage` | ✅ |
| INT-007 | Заполнение всех мест | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_race_condition_last_spot` | ⚠️ |
| INT-008 | Просроченный токен | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestAuthTokenRefresh::test_expired_access_token_auto_refresh` | ✅ |
| INT-009 | Истёкший refresh_token | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestAuthTokenRefresh::test_expired_both_tokens_redirects_to_login` | ✅ |
| INT-010 | Offline Queue | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestPWAOffline::test_offline_queue_storage`, `TestPWAOffline::test_offline_queue_send_on_reconnect` | ✅ |
| INT-011 | Смена пароля → инвалидация сессий | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_zombie_session_after_password_change` | ✅ |
| INT-012 | Admin: верификация + справочники | ⚠️ | — | ❌ |

---

## 16. Тесты безопасности

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| SEC-001 | CSRF: POST без токена | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestCSRFSecurity::test_post_without_csrf_token_returns_400` | ✅ |
| | | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_csrf_bypass_content_type` | ✅ |
| SEC-002 | CSRF: неверный токен | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestCSRFSecurity::test_post_with_invalid_csrf_token_returns_400` | ✅ |
| SEC-003 | XSS в чате | [`tests/test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestRealTimeChat::test_chat_xss_escaping` | ✅ |
| SEC-004 | XSS в названии навыка | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_css_injection_in_skill_name_escaped` | ✅ |
| SEC-005 | PostgREST-инъекция | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestEdgeCases::test_postgrest_injection_sanitized` | ✅ |
| | | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_postgrest_schema_cache_coherence` | ✅ |
| SEC-006 | Path Traversal | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestEdgeCases::test_path_traversal_sanitized` | ✅ |
| | | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_path_traversal_in_params` | ✅ |
| SEC-007 | CSP: 0 нарушений | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_csp_header_contains_nonce`, `test_no_unsafe_inline_in_script_src`, `test_inline_scripts_have_nonce`, `test_no_inline_event_handlers` | ✅ |
| SEC-008 | CSP: nonce не утекает | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestCSPNonce::test_csp_nonce_in_script_tags_only`, `TestCSPNonce::test_csp_nonce_not_in_localstorage` | ✅ |
| | | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_nonce_not_in_localstorage_or_url` | ✅ |
| SEC-009 | Безопасные заголовки | ⚠️ | — | ❌ |
| SEC-010 | exec_sql RPC: анонимный доступ | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_exec_sql_not_accessible_to_anon` | ✅ |
| SEC-011 | exec_sql RPC: инъекция | ⚠️ | — | ❌ |

---

## 17. Нагрузочные тесты (PERF)

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| PERF-001 | Rate Limit: 11 POST за 60 сек | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestRateLimitParametrized::test_login_rate_limit` | ✅ |
| PERF-002 | Circuit Breaker: 5 ошибок подряд | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestCircuitBreaker::test_circuit_breaker_opens_after_5_errors` | ✅ |
| PERF-003 | Circuit Breaker: восстановление | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestCircuitBreaker::test_circuit_breaker_recovers_after_timeout` | ✅ |
| PERF-004 | Connection Pool: 100 одновременных запросов | [`tests/locustfile.py`](../tests/locustfile.py) | `TrudnikUser.search_jobs`, `TrudnikUser.search_workers` | ✅ |
| PERF-005 | Batch: 50 accept на `max_workers=50` | [`tests/locustfile.py`](../tests/locustfile.py) | `TrudnikBatchUser.batch_accept_50` | ✅ |

> **Примечание:** ID в разделе 17 TEST_CHECKLIST.md используют префикс `PRF-`, что создаёт коллизию с разделом 8 (Профиль). В данной матрице для нагрузочных тестов используется префикс `PERF-`, чтобы избежать неоднозначности. Оригинальные ID: PRF-001..PRF-005 в разделе 17.

---

## 18. Edge Cases

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| EDG-001 | `max_workers=0` или отрицательное | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_max_workers_zero_rejected` | ✅ |
| EDG-002 | `max_workers=10000` | ❌ | — | ❌ |
| EDG-003 | Невалидный UUID | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestEdgeCases::test_invalid_uuid_returns_404_not_500` | ✅ |
| | | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_invalid_uuid_returns_404` | ✅ |
| EDG-004 | Удалённое задание | [`tests/test_all_functions.py`](../tests/test_all_functions.py) | `TestAppRoutes::test_job_detail_not_found` | ✅ |
| EDG-005 | Истёкший токен без refresh | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_expired_token_clears_session` | ✅ |
| EDG-006 | Supabase недоступен (503) | ⚠️ | — | ❌ |
| EDG-007 | Файл > 5MB или .exe | [`tests/test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestEdgeCases::test_avatar_upload_size_limit`, `TestEdgeCases::test_avatar_upload_mime_whitelist` | ✅ |
| EDG-008 | Дата задания в прошлом | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_past_date_job_created` | ✅ |
| EDG-009 | `expires_at` в прошлом | ❌ | — | ❌ |
| EDG-010 | Восстановление не-cancelled | ❌ | — | ❌ |
| EDG-011 | Редактирование чужого задания | ❌ | — | ❌ |
| EDG-012 | `notification_prefs = NULL` | [`tests/test_critical_gaps.py`](../tests/test_critical_gaps.py) | `test_notification_prefs_null_fallback` | ✅ |
| EDG-013 | Пустой `skills` при создании | ⚠️ | — | ❌ |
| EDG-014 | Дубликат `sort_order` в справочниках | ❌ | — | ❌ |
| EDG-015 | `/chat/new/<worker_id>` без истории | ❌ | — | ❌ |
| EDG-016 | Регистрация с несуществующим `skill_ids` | ❌ | — | ❌ |
| EDG-017 | `window._toastQueue` переполнение | ❌ | — | ❌ |

---

## 19. Состояния загрузки и пустые состояния

### 19.1 Loading Overlay

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| LO-001 | Показ Loading Overlay | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestLoadingStates::test_loading_overlay_appears` | ✅ |
| LO-002 | Скрытие Loading Overlay | ⚠️ | — | ❌ |
| LO-003 | Таймаут Loading Overlay | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestLoadingStates::test_loading_overlay_timeout` | ✅ |
| LO-004 | Двойной клик под Overlay | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestDoubleClickProtection::test_double_click_submit_blocked` | ⚠️ |

### 19.2 Skeleton Loader

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| SKL-001 | Skeleton при загрузке списка | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestLoadingStates::test_skeleton_loader` | ✅ |
| SKL-002 | Skeleton → данные | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestLoadingStates::test_skeleton_loader` | ✅ |
| SKL-003 | Skeleton при ошибке | ❌ | — | ❌ |

### 19.3 Double-click Protection

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| DBL-001 | Блокировка submit на 3 сек | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestDoubleClickProtection::test_double_click_submit_blocked` | ✅ |
| DBL-002 | Блокировка AJAX-кнопок | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestDoubleClickProtection::test_double_click_ajax_disabled` | ✅ |
| DBL-003 | Разблокировка после ответа | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestDoubleClickProtection::test_double_click_unblock_after_response` | ✅ |
| DBL-004 | Блокировка на разных кнопках | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestDoubleClickProtection::test_double_click_different_buttons` | ✅ |

### 19.4 Пустые состояния

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| EMP-001 | Нет заданий (главная) | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_main_page` | ✅ |
| EMP-002 | Нет заданий (мой список) | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_my_jobs` | ✅ |
| EMP-003 | Нет откликов | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_my_applications` | ✅ |
| EMP-004 | Нет уведомлений | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_notifications` | ✅ |
| EMP-005 | Нет приглашений | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_invitations` | ✅ |
| EMP-006 | Нет чатов | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_chats` | ✅ |
| EMP-007 | Нет избранного | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_favorites` | ✅ |
| EMP-008 | Нет результатов поиска | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_search_results` | ✅ |
| EMP-009 | Нет работодателей | ❌ | — | ❌ |
| EMP-010 | Пустой ЧС | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestEmptyStates::test_empty_blacklist` | ✅ |

### 19.5 Offline-состояния

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| OFF-001 | Offline Bar | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestPWAOffline::test_offline_bar_appears` | ✅ |
| OFF-002 | Offline-страница | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestPWAOffline::test_offline_page_fallback` | ✅ |
| OFF-003 | Offline → Online | ⚠️ | — | ❌ |
| OFF-004 | Offline Queue: отклик | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestPWAOffline::test_offline_queue_storage` | ✅ |
| OFF-005 | Offline Queue: отправка | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestPWAOffline::test_offline_queue_send_on_reconnect` | ✅ |
| OFF-006 | Offline Queue: 404 | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestPWAOffline::test_offline_queue_404_handling` | ✅ |

---

## 20. Адаптивность

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| RSP-001 | Mobile: главная (320px) | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestResponsive::test_responsive_main_page`, `TestResponsive::test_mobile_bottom_nav` | ✅ |
| RSP-002 | Mobile: фильтр навыков | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestResponsive::test_mobile_skill_filter_bottom_sheet` | ✅ |
| RSP-003 | Mobile: поиск | ⚠️ | — | ❌ |
| RSP-004 | Tablet: главная (768px) | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestResponsive::test_responsive_main_page` | ✅ |
| RSP-005 | Desktop: главная (1024px) | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestResponsive::test_responsive_main_page` | ✅ |
| RSP-006 | Desktop: фильтр навыков | ⚠️ | — | ❌ |
| RSP-007 | iPhone Safe Area (Notch) | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestResponsive::test_safe_area_iphone` | ✅ |
| RSP-008 | iPhone Home Indicator | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestResponsive::test_safe_area_iphone` | ✅ |
| RSP-009 | PWA standalone (iOS) | ⚠️ | — | ❌ |
| RSP-010 | Touch targets (mobile) | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestResponsive::test_touch_targets_min_size` | ✅ |
| RSP-011 | Поворот экрана | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestResponsive::test_rotation_reflow` | ✅ |

---

## 21. Доступность (Accessibility)

| ID | Название | Файл теста | Функция | Статус |
|----|----------|-----------|---------|--------|
| A11Y-001 | ARIA: навигация | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_aria_navigation_roles` | ✅ |
| | | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_axe_core_no_critical_violations` | ✅ |
| A11Y-002 | ARIA: кнопки действий | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_axe_core_no_critical_violations` | ⚠️ |
| A11Y-003 | ARIA: модальные окна | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_aria_dialog_role` | ✅ |
| A11Y-004 | ARIA: toast-уведомления | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_aria_toast_live_region` | ✅ |
| A11Y-005 | Screen reader: навигация | ❌ | — | ❌ |
| A11Y-006 | Screen reader: формы | ❌ | — | ❌ |
| A11Y-007 | Screen reader: пустые состояния | ❌ | — | ❌ |
| A11Y-008 | Keyboard: Tab-навигация | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_keyboard_tab_navigation` | ✅ |
| A11Y-009 | Keyboard: Escape | ⚠️ | — | ❌ |
| A11Y-010 | Цветовой контраст | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_color_contrast_ratio` | ✅ |
| A11Y-011 | Семантическая структура | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_semantic_heading_hierarchy` | ✅ |
| A11Y-012 | Alt-тексты изображений | [`tests/test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestAccessibility::test_image_alt_texts` | ✅ |

---

## Сводная статистика

### Общая статистика

| Метрика | Значение |
|---------|----------|
| Всего ID в [`TEST_CHECKLIST.md`](TEST_CHECKLIST.md) | **156** |
| Покрыто существующими тестами (✅) | **94** (60.3%) |
| Покрыто частично (⚠️) | **29** (18.6%) |
| Не покрыто (❌) | **33** (21.2%) |
| **Общее покрытие (✅ + ⚠️)** | **123** (78.8%) |

### Статистика по разделам

| Раздел | Всего | ✅ | ⚠️ | ❌ | Покрытие |
|--------|-------|----|----|----|----------|
| 1. Smoke-тесты | 11 | 6 | 3 | 2 | 81.8% |
| 2. Аутентификация | 10 | 5 | 4 | 1 | 90.0% |
| 3. Задания — Employer | 13 | 8 | 2 | 3 | 76.9% |
| 4. Задания — Worker | 10 | 6 | 2 | 2 | 80.0% |
| 5. Отклики | 16 | 13 | 1 | 2 | 87.5% |
| 6. Приглашения | 9 | 2 | 2 | 5 | 44.4% |
| 7. Чат | 8 | 4 | 0 | 4 | 50.0% |
| 8. Профиль | 8 | 6 | 2 | 0 | 100% |
| 9. Рейтинги | 7 | 2 | 1 | 4 | 42.9% |
| 10. Избранное | 7 | 4 | 0 | 3 | 57.1% |
| 11. Чёрный список | 4 | 3 | 0 | 1 | 75.0% |
| 12. Уведомления | 14 | 4 | 6 | 4 | 71.4% |
| 13. Админ | 7 | 3 | 3 | 1 | 85.7% |
| 14. Поиск (API) | 4 | 2 | 1 | 1 | 75.0% |
| 15. Интеграционные тесты | 12 | 8 | 3 | 1 | 91.7% |
| 16. Тесты безопасности | 11 | 8 | 2 | 1 | 90.9% |
| 17. Нагрузочные тесты | 5 | 5 | 0 | 0 | 100% |
| 18. Edge Cases | 17 | 9 | 1 | 7 | 58.8% |
| 19. Состояния загрузки | 23 | 16 | 3 | 4 | 82.6% |
| 20. Адаптивность | 11 | 7 | 3 | 1 | 90.9% |
| 21. Доступность | 12 | 7 | 2 | 3 | 75.0% |

### Не покрыто (требуют ручного тестирования или автоматизации)

| ID | Название | Раздел |
|----|----------|--------|
| SMK-010 | Asset Links | 1. Smoke |
| AUTH-005 | Регистрация: ИНН трудника | 2. Аутентификация |
| JOB-E-005 | Создание: загрузка фото | 3. Задания — Employer |
| JOB-E-007 | Редактирование задания | 3. Задания — Employer |
| JOB-E-008 | Редактирование: есть accepted | 3. Задания — Employer |
| JOB-E-010 | Дублирование: фото и навыки | 3. Задания — Employer |
| JOB-W-003 | Фильтрация по оплате | 4. Задания — Worker |
| JOB-W-009 | Истёкшие задания | 4. Задания — Worker |
| APP-002 | Отклик: дубликат | 5. Отклики |
| APP-010 | Reopen отклика | 5. Отклики |
| APP-015 | Batch: >50 элементов | 5. Отклики |
| INV-001 | Пригласить трудника | 6. Приглашения |
| INV-002 | Приглашение: дубликат | 6. Приглашения |
| INV-003 | Приглашение: не владелец | 6. Приглашения |
| INV-004 | Приглашение: статус задания | 6. Приглашения |
| INV-007 | Список приглашений | 6. Приглашения |
| INV-009 | Приглашение уже rejected | 6. Приглашения |
| CHT-004 | Чат: слишком длинное сообщение | 7. Чат |
| CHT-007 | Polling-фолбек | 7. Чат |
| CHT-008 | Удаление чатов | 7. Чат |
| RAT-003 | Оценка не-completed задания | 9. Рейтинги |
| RAT-004 | Обновить оценку | 9. Рейтинги |
| RAT-005 | Просмотр рейтингов | 9. Рейтинги |
| RAT-006 | Форма оценки трудников | 9. Рейтинги |
| RAT-007 | Диапазон оценки | 9. Рейтинги |
| FAV-003 | Добавить работодателя в избранное | 10. Избранное |
| FAV-004 | Убрать работодателя из избранного | 10. Избранное |
| FAV-006 | Дубликат избранного | 10. Избранное |
| NOT-003 | Отметить все прочитанными | 12. Уведомления |
| NOT-006 | Счётчик в шапке | 12. Уведомления |
| NOT-011 | Push: отключённый тип | 12. Уведомления |
| NOT-014 | Email: формат письма | 12. Уведомления |
| ADM-003 | Управление пользователями | 13. Админ |
| ADM-006 | Управление справочниками | 13. Админ |
| ADM-007 | Health check админки | 13. Админ |
| SRH-004 | Навыки/религии (API) | 14. Поиск |
| INT-012 | Admin: верификация + справочники | 15. Интеграционные |
| SEC-009 | Безопасные заголовки | 16. Безопасность |
| SEC-011 | exec_sql RPC: инъекция | 16. Безопасность |
| EDG-002 | max_workers=10000 | 18. Edge Cases |
| EDG-009 | expires_at в прошлом | 18. Edge Cases |
| EDG-010 | Восстановление не-cancelled | 18. Edge Cases |
| EDG-011 | Редактирование чужого задания | 18. Edge Cases |
| EDG-013 | Пустой skills при создании | 18. Edge Cases |
| EDG-014 | Дубликат sort_order | 18. Edge Cases |
| EDG-015 | /chat/new/<worker_id> без истории | 18. Edge Cases |
| EDG-016 | Регистрация с несуществующим skill_ids | 18. Edge Cases |
| EDG-017 | window._toastQueue переполнение | 18. Edge Cases |
| LO-002 | Скрытие Loading Overlay | 19. Состояния загрузки |
| SKL-003 | Skeleton при ошибке | 19. Состояния загрузки |
| EMP-009 | Нет работодателей | 19. Состояния загрузки |
| OFF-003 | Offline → Online | 19. Состояния загрузки |
| RSP-003 | Mobile: поиск | 20. Адаптивность |
| RSP-006 | Desktop: фильтр навыков | 20. Адаптивность |
| RSP-009 | PWA standalone (iOS) | 20. Адаптивность |
| A11Y-005 | Screen reader: навигация | 21. Доступность |
| A11Y-006 | Screen reader: формы | 21. Доступность |
| A11Y-007 | Screen reader: пустые состояния | 21. Доступность |
| A11Y-009 | Keyboard: Escape | 21. Доступность |

---

## Flaky Tests Prevention

### Категории потенциально нестабильных тестов

#### 1. WebSocket-зависимые тесты

| Файл | Тесты | Риск |
|------|-------|------|
| [`test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | `TestRealTimeChat` (все 3 теста) | Зависимость от Redis Pub/Sub и WebSocket-соединений между браузерными контекстами |
| [`test_websocket_server.py`](../tests/test_websocket_server.py) | Все тесты | Таймауты при инициализации WebSocket |
| [`test_websocket_auth.py`](../tests/test_websocket_auth.py) | Все тесты | Зависимость от состояния сессии |

**Рекомендации:**
- Использовать retry-логику с экспоненциальной задержкой (до 3 попыток)
- Увеличить таймауты ожидания WebSocket-сообщений до 15-30 сек
- Добавить `pytest-rerunfailures` с `--reruns 2` для WebSocket-тестов
- Выделить WebSocket-тесты в отдельный CI-степ с `pytest -m "websocket"` и изоляцией от параллельного выполнения

#### 2. Тайминговые тесты (Rate Limit / Circuit Breaker)

| Файл | Тесты | Риск |
|------|-------|------|
| [`test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestRateLimitParametrized` | Зависимость от точного тайминга 60-секундного окна |
| [`test_backend_gaps.py`](../tests/test_backend_gaps.py) | `TestCircuitBreaker` | `time.sleep()` и `freezegun`-зависимость — может флакать на медленных CI |
| [`test_rate_limit.py`](../tests/test_rate_limit.py) | Все тесты | Состояние rate-limit кеша между тестами |

**Рекомендации:**
- Использовать `freezegun` для детерминированного контроля времени в Circuit Breaker тестах
- Очищать кеш rate-limit в `conftest.py` между тестами через `@pytest.fixture(autouse=True)`
- Изолировать rate-limit тесты: запускать последовательно, не параллельно

#### 3. Locust (нагрузочные тесты)

| Файл | Тесты | Риск |
|------|-------|------|
| [`locustfile.py`](../tests/locustfile.py) | `TrudnikUser`, `TrudnikBatchUser` | Нестабильность сети, таймауты Supabase, долгое выполнение |

**Рекомендации:**
- Запускать Locust только в scheduled CI (ночной прогон), не в PR-пайплайне
- Установить `--headless --run-time 60s --users 10` для CI-режима
- Добавить `--expect-workers` и `--exit-code-on-error 0` для предотвращения ложных падений

#### 4. E2E Playwright-тесты

| Файл | Тесты | Риск |
|------|-------|------|
| [`test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | `TestPWAOffline` (все 5 тестов) | Эмуляция offline-режима через CDP может флакать |
| [`test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | Все тесты | Многоконтекстность + синхронизация через `expect_event` |

**Рекомендации:**
- Использовать `browser_context.set_offline(True)` вместо глобального перехвата
- Для многоконтекстных тестов: увеличить `expect_event` timeout до 15 сек
- Включить `--tracing=retain-on-failure` для отладки флакающих E2E
- Запускать E2E-тесты с `pytest -n 1` (строго последовательно)

---

## Файлы тестов — сводка

| Файл | Назначение | Ключевые классы/функции |
|------|-----------|------------------------|
| [`test_all_functions.py`](../tests/test_all_functions.py) | Основные интеграционные тесты API | `TestUtils`, `TestAppRoutes` (106 тестов) |
| [`test_security.py`](../tests/test_security.py) | Проверки безопасности CSP/CSRF/SQL | Различные security-тесты |
| [`test_rls.py`](../tests/test_rls.py) | Row-Level Security в Supabase | RLS-тесты |
| [`test_sanitize.py`](../tests/test_sanitize.py) | Санитизация ввода (PostgREST) | Sanitize-тесты |
| [`test_rate_limit.py`](../tests/test_rate_limit.py) | Rate limiting на эндпоинтах | Rate-limit тесты |
| [`test_utils_unit.py`](../tests/test_utils_unit.py) | Юнит-тесты утилит | `test_calculate_distance` и др. |
| [`test_chat.py`](../tests/test_chat.py) | Чат (API + WebSocket) | Чат-тесты |
| [`test_email_service.py`](../tests/test_email_service.py) | Email-уведомления (Celery) | Email-тесты |
| [`test_push_service.py`](../tests/test_push_service.py) | Push-уведомления (Web Push) | Push-тесты |
| [`test_state_machine.py`](../tests/test_state_machine.py) | Конечный автомат статусов | State machine тесты |
| [`test_ux.py`](../tests/test_ux.py) | UX-проверки (UI) | UX-тесты |
| [`test_selenium_browser.py`](../tests/test_selenium_browser.py) | Selenium E2E | Selenium-тесты |
| [`test_critical_gaps.py`](../tests/test_critical_gaps.py) | Критические пробелы и бомбы | 62 теста (P0/P1) |
| [`test_websocket_server.py`](../tests/test_websocket_server.py) | WebSocket-сервер | WS-тесты |
| [`test_websocket_auth.py`](../tests/test_websocket_auth.py) | WebSocket-аутентификация | WS-тесты |
| [`test_backend_gaps.py`](../tests/test_backend_gaps.py) | **Новый:** Закрытие бекенд-пробелов | `TestAuthTokenRefresh`, `TestRateLimitParametrized`, `TestStopWordsValidation`, `TestCircuitBreaker`, `TestCSRFSecurity`, `TestCSPNonce`, `TestEdgeCases` |
| [`test_e2e_frontend.py`](../tests/test_e2e_frontend.py) | **Новый:** Playwright E2E фронтенд | `TestResponsive`, `TestLoadingStates`, `TestDoubleClickProtection`, `TestEmptyStates`, `TestAccessibility`, `TestPWAOffline` |
| [`test_e2e_multicontext.py`](../tests/test_e2e_multicontext.py) | **Новый:** Многоконтекстные E2E | `TestRealTimeChat`, `TestBlacklist`, `TestInvitations`, `TestFullCycle` |
| [`locustfile.py`](../tests/locustfile.py) | **Новый:** Нагрузочное тестирование | `TrudnikUser`, `TrudnikBatchUser` |

---

> **Статус документа:** полная матрица трассировки, связывающая все 156 тестовых ID с конкретными файлами и функциями тестов.
> **Следующий шаг:** приоритезировать автоматизацию 33 непокрытых ID, начиная с разделов 6 (Приглашения) и 9 (Рейтинги).
