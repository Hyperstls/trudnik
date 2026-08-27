# QA Test Cases — Трудник (полный реестр)

Дата: 2026-08-21. Основано: `docs/qa_test_cases_prompt.md` (генератор), факты сверены с `docs/API_ENDPOINTS.md` (146 маршрутов), `docs/RPC_REGISTRY.md` (30 RPC + 4 trigger), `docs/TEST_COVERAGE_MAP.md`, живым прогоном на локальном docker-стеке.

## Резюме покрытия

- **Автопокрытие**: mock 540 ✓ / integration 147 ✓ / e2e 113 ✓ (2026-08-21, живой стек, код со SmartCaptcha + MAX-only). ~800 автотестов в 60+ файлах.
- **Автотест-колонка**: ссылка на существующий файл-близнец (не дублировать) или `новый` (кандидат на реализацию), или MANUAL (требует рук/датасета).
- **Приоритет**: 32 High / 44 Medium / 34 Low = 110 кейсов.
- **Ключевые границы прод**: CSP strict-dynamic (все скрипты nonce), CSRF на всех мутациях (кроме внешних webhooks MAX), RLS через JWT-claims, circuit breaker на PostgREST, rate-limit login/register (fail-closed) и глобальный 120/мин.
- **Найденные дефекты (требуют фикса)**: SEC-011 (self-block), SEC-012 (webhook без подписи — принято), A11Y-регрессии закрыты 2026-08-16.
- **Фантомы (НЕ тестировать)**: `/api/search/jobs|workers`, `/api/religions`, RPC `create_job/update_job`, Telegram-верификация (удалена 152-ФЗ), Turnstile (заменён на Yandex SmartCaptcha).

| ID | Категория | Компонент | Тип | Название теста | Предусловия | Шаги | Ожидаемый результат | Приоритет | Автотест |
|----|-----------|-----------|-----|----------------|-------------|------|----------------------|-----------|----------|
| TC-001 | Auth | auth.py | integration | Логин с валидными кредами | Пользователь существует, email подтверждён | POST /login (email, password, csrf_token) | 302 → каталог или /my-jobs; сессия авторизована | High | test_buttons_backend.py::test_guest_login_valid_credentials |
| TC-002 | Auth | auth.py | integration | Логин с неверным паролем | Пользователь существует | POST /login с ошибочным паролем | 200 форма, flash «Неверный email или пароль» | High | test_buttons_backend.py::test_guest_login_invalid_password |
| TC-003 | Auth | auth.py | security | Open redirect через ?next= | — | POST /login?next=//evil.com | Location не содержит внешний домен | High | test_buttons_backend.py::test_guest_login_open_redirect |
| TC-004 | Auth | auth.py | security | POST /login без CSRF | — | POST /login без токена | 400 | High | test_buttons_backend.py::test_guest_login_missing_csrf |
| TC-005 | Auth | auth.py | security | Per-account lockout (C22) | 5+ неудачных попыток | Повторные POST /login | flash «Аккаунт временно заблокирован… 15 минут»; Redis login_lockout:{email} | High | новый (Redis-состояние) |
| TC-006 | Auth | auth.py | security | Per-IP лимит логина | 20+ POST/час с одного IP | POST /login | flash «Слишком много попыток с вашего IP» | High | MANUAL (счётчик Redis) |
| TC-007 | Auth | auth.py | integration | Регистрация worker с consent | — | POST /register (все поля + consent=on) | 302/200, профиль создан, consented_at заполнен (152-ФЗ) | High | test_buttons_backend.py::test_guest_register_worker |
| TC-008 | Auth | auth.py | security | Регистрация без чекбокса согласия | — | POST /register без consent | Отказ, поле consent подсвечено | High | test_buttons_backend.py::test_guest_register_no_consent |
| TC-009 | Auth | auth.py | integration | Регистрация с ИНН самозанятого | — | POST /register с ИНН 500100732259 + is_self_employed=on | Успех; ИНН с валидной контрольной суммой принят | Medium | test_buttons_backend.py::test_guest_register_worker_with_inn |
| TC-010 | Auth | validators.py | unit | Невалидная контрольная сумма ИНН | — | validate_inn_checksum('7707083894') | False | Medium | test_validators.py |
| TC-011 | Auth | validators.py | unit | Слабый пароль отклонён | — | validate_password('aa1!aaaa') | Ошибка про заглавную букву | Medium | test_validators.py |
| TC-012 | Auth | captcha.py | unit | SmartCaptcha: нет server-ключа → fail-closed | SMARTCAPTCHA_SERVER_KEY пуст | verify_captcha('token') | False + warning в логе | High | test_x10_captcha.py |
| TC-013 | Auth | captcha.py | contract | SmartCaptcha: валидация против API Яндекса | Ключи заданы | GET smartcaptcha…/validate с заглушкой ok | True при status=ok; False при иных. ✅ LIVE 2026-08-22: server-key принят API Яндекса (HTTP 200 на прямой вызов); bogus/empty токены → False (fail-closed) | High | test_x10_captcha.py |
| TC-014 | Auth | captcha.py | integration | Виджет на регистрации (РФ-эндпоинт) | Ключи заданы | GET /register | script src=smartcaptcha.yandexcloud.net; НЕТ challenges.cloudflare.com (CSP). ✅ LIVE 2026-08-22 (прод, trudnik-hyperstls.amvera.io): виджет отрисован на шаге 2 (хост-чек пройден), клик «Я не робот» → smart-token 396 симв. в hidden input — полный цикл работает; на скрытом шаге авто-оживает при показе (smartCaptcha.update() не требуется) | High | test_x10_captcha.py |
| TC-015 | Auth | auth.py | integration | verify-email: невалидный токен | — | GET /verify-email/bad-token | 302 → /register, flash «недействительна» | High | test_coverage_gaps.py |
| TC-016 | Auth | auth.py | integration | verify-email: валидный токен | Токен сгенерирован | GET /verify-email/<valid> | PATCH profiles.email_verified=true, 302 → /login | High | test_coverage_gaps.py |
| TC-017 | Auth | auth.py | integration | Смена пароля (одноразовый юзер) | Временный пользователь | POST /profile/change-password | Успех; старые сессии других девайсов инвалидированы (pwd_changed_at) | Medium | test_buttons_backend.py::test_worker_can_change_password |
| TC-018 | Auth | auth.py | integration | Сброс пароля: письмо с токеном | SMTP-заглушка | POST /password-reset → GET подтверждающую ссылку | Письмо содержит одноразовый токен с TTL | Medium | test_auth.py (mock) |
| TC-019 | Jobs | jobs.py | integration | Создание задания (прямой POST /jobs/new) | Employer-сессия | POST /jobs/new (все поля + координаты) | 302 → /jobs/<id>; задание в статусе open | High | conftest created_job_id |
| TC-020 | Jobs | jobs.py | security | Стоп-слова ТК РФ: «ставка» в заголовке | — | POST /jobs/new title='Часовая ставка!' | Отклонено: найдено стоп-слово | High | test_stop_words_unit.py |
| TC-021 | Jobs | jobs.py | security | Стоп-слова: «ЗАРПЛАТА» капсом | — | check_stop_words('ЗАРПЛАТА') | Найдено (lower() перед сравнением) | Medium | test_stop_words_unit.py |
| TC-022 | Jobs | jobs.py | security | ГРАНИЦА: «зарплату» не ловится | — | check_stop_words('Выдаём зарплату') | [] — лемматизации НЕТ (задокументированная граница) | Medium | test_stop_words_unit.py (фиксирует) |
| TC-023 | Jobs | jobs.py | security | ГРАНИЦА: «з а р п л а т а» обход пробелами | — | check_stop_words('з а р п л а т а') | [] — обход работает (риск, задокументирован) | Low | test_stop_words_unit.py (фиксирует) |
| TC-024 | Jobs | jobs.py | integration | Редактирование с accepted-откликами | Задание с принятым откликом | POST /jobs/<id>/edit с title | 409/flash: менять можно только description и contact_phone | High | test_coverage_completion.py::test_edit_job_with_accepted_application |
| TC-025 | Jobs | jobs.py | integration | Отзыв (unapply) за 12ч до начала | Принятый отклик, <12ч до deadline | POST /unapply/<job_id> | Отказ: окно закрыто | Medium | test_buttons_backend.py |
| TC-026 | Jobs | jobs.py | integration | Каталог: фильтр по оплате | — | GET /?payment_min=100&payment_max=10000 | 200; некорректные границы не роняют каталог | Medium | test_coverage_completion.py::test_filter_by_payment |
| TC-027 | Jobs | jobs.py | e2e | Карта заданий грузится | Yandex Maps доступен | Открыть каталог, вкладка карты | Контейнер карты виден, маркеры заданий рендерятся | Medium | tests_e2e/test_map_geolocation.py |
| TC-028 | Jobs | jobs_api.py | integration | /api/skills — публичный справочник | — | GET /api/skills | 200, JSON {skills: [...]} | Low | test_coverage_completion.py::test_skills_religions_api |
| TC-029 | Jobs | jobs_api.py | integration | /api/religions НЕ существует | — | GET /api/religions | 404 (публичного API религий нет) | Low | test_coverage_completion.py (фиксирует 404) |
| TC-030 | Jobs | jobs.py | integration | Repost задания (JOB-E-010) | Завершённое задание | POST repost | 302 на новый /jobs/<id>, фото/навыки сохранены | Medium | test_coverage_completion.py::test_repost_job_preserves_photo_and_skills |
| TC-031 | Jobs | jobs.py | MANUAL | Batch-отклик >50 заданий | 51+ открытых заданий | POST /apply-selected с 51 ID | Обрабатывается или режется по лимиту без 500 | Low | MANUAL (датасет) |
| TC-032 | Applications | applications.py | integration | Отклик на задание (RPC apply_job_atomic) | Открытое задание, worker | POST /apply/<job_id> | Отклик pending; уведомление работодателю через outbox | High | test_buttons_backend.py |
| TC-033 | Applications | applications.py | integration | Повторный отклик → flash | Уже есть отклик | POST /apply/<job_id> ещё раз | Flash «Вы уже откликались» | Medium | test_coverage_completion.py::test_duplicate_apply_returns_flash |
| TC-034 | Applications | applications.py | integration | Accept отклика (RPC accept_application) | Pending-отклик | POST /api/applications/<id>/accept | 200; статус accepted; current_workers+1 | High | test_buttons_backend.py |
| TC-035 | Applications | applications.py | integration | Атомарность accept: 2 отклика на 1 место | max_workers=1, два worker | Оба accept почти одновременно | Только один принят, второй rejected/409 | High | test_buttons_backend.py::test_employer_accept_atomic_rpc |
| TC-036 | Applications | applications.py | integration | Reject → reopen | Отклонённый отклик | POST reject → POST reopen | 200; статус обратно pending (или 400/409 при гонке) | Medium | test_buttons_backend.py::test_employer_can_reopen_application |
| TC-037 | Applications | applications.py | integration | apply-selected пустой список | Worker-сессия | POST /apply-selected без job_ids | Flash «Не выбрано ни одного задания» + redirect | Low | test_coverage_completion.py::test_batch_applications_limit |
| TC-038 | Applications | applications.py | security | Отклик на своё задание | Employer откликается на свой job | POST /apply/<own_job_id> | RPC-код own_job, отказ | High | test_c4_apply_job_race.py (атомарность) |
| TC-039 | Applications | applications.py | integration | TOCTOU: accept устаревшего отклика | Отклик уже обработан | Повторный accept | 409 «Заявка уже обработана» (идемпотентность) | Medium | test_c1_accept_reject_toctou.py |
| TC-040 | Applications | applications.py | integration | unapply-selected (массовый отзыв) | Worker с откликами | POST /unapply-selected с job_ids | Отклики отозваны, redirect на / | Medium | test_misc_gaps.py |
| TC-041 | Chat | chat.py | integration | Чат открывается после accept | Принятый отклик | GET /chat/<application_id> | 200, история сообщений | High | test_chat.py |
| TC-042 | Chat | chat.py | integration | Сообщение >2000 символов | Открытый чат | POST /api/send_message (2001 симв.) | 400 Bad Request | Medium | test_coverage_completion.py::test_send_message_too_long_returns_400 |
| TC-043 | Chat | chat.py | security | Чат после отзыва отклика | Отзыв за окном допустимым | Сообщение в чат отменённого отклика | Отказ (доступ к чату закрыт) | High | test_a4_chat_after_withdraw.py |
| TC-044 | Chat | chat.py | integration | Rate limit сообщений чата | Открытый чат | >N сообщений подряд | 429/flash «Слишком много» | Medium | test_a3_chat_rate_limit.py |
| TC-045 | Chat | chat.py | e2e | Realtime-обновление чата | WS-сервер поднят | Два браузера в одном чате | Сообщение появляется без перезагрузки | Medium | MANUAL (2 браузера) |
| TC-046 | Chat | chat.py | integration | Poll сообщений | Открытый чат | GET /api/messages/<id>/poll | 200 JSON (или 304-подобное поведение) | Low | test_coverage_completion.py::test_poll_messages_endpoint_accessible |
| TC-047 | Messenger | messenger_verify.py | integration | Deep-link верификации MAX | Авторизован | GET /messenger/start/max | 200 {link: max.ru/…?start=<token>} | Medium | test_messenger_verify.py |
| TC-048 | Messenger | messenger_verify.py | integration | Telegram отключён (152-ФЗ) | — | GET /messenger/start/telegram | 400 (платформа удалена) | Medium | test_messenger_verify.py (фиксирует) |
| TC-049 | Messenger | messenger_verify.py | security | Webhook MAX без подписи (ПРИНЯТО) | — | POST /messenger/webhook/max произвольным JSON | 200 (подпись не проверяется — задокументированное решение) | Medium | test_messenger_verify.py::test_webhooks_have_no_signature_check |
| TC-050 | Messenger | messenger_verify.py | integration | bot_started завершает верификацию | Токен в Redis | POST webhook с валидным payload | RPC verify_via_messenger вызван, токен удалён (одноразовость); юзеру — ✅ + inline-кнопка «Вернуться в профиль». 2026-08-27: message_created-fallback (body.text) закрывает повторные старты (bot_started приходит только при первом старте/возобновлении — dev.max.ru); «/start»/голый токен тоже верифицируют; «/start» без токена → инструкция с кнопкой; self-heal подписки (beat, 10 мин) — ensure_max_webhook | High | test_messenger_verify.py |
| TC-051 | Messenger | messenger_verify.py | security | diagnose закрыт для не-админа | — | GET /messenger/diagnose гостём и worker | 302 → /login / flash «требуются права администратора» (регрессия: был публичным) | High | test_messenger_verify.py::test_requires_admin |
| TC-052 | Notifications | notifications.py | integration | unread-count | Авторизован | GET /api/notifications/unread-count | 200 {unread: N} | Low | test_notifications_api.py |
| TC-053 | Notifications | notifications.py | integration | read-all | Есть непрочитанные | POST /api/notifications/read-all | 200 success; все is_read=true | Low | test_notifications_api.py |
| TC-054 | Notifications | notifications.py | integration | Настройки: выключение email-канала | Авторизован | POST preferences {type: email_enabled, enabled: false} | 200; PATCH profiles.notification_prefs | Low | test_notifications_api.py |
| TC-055 | Notifications | notifications.py | integration | Настройки: неизвестный тип | Авторизован | POST preferences {type: bogus} | 400 | Low | test_notifications_api.py |
| TC-056 | Notifications | notifications.py | integration | Push-подписка: валидный subscription | Авторизован | POST /push/subscription (endpoint+keys) | 200 success; PushService.save вызван | Medium | test_push_endpoints.py |
| TC-057 | Notifications | notifications.py | integration | Push-подписка: пустое тело | Авторизован | POST /push/subscription {} | 400 | Low | test_push_endpoints.py |
| TC-058 | Notifications | notifications.py | integration | VAPID public key из env | — | GET /push/vapid-public-key | 200 {public_key} (или пусто при незаданном) | Low | test_push_endpoints.py |
| TC-059 | Notifications | outbox | integration | Transactional outbox: письмо работодателю | Новый отклик | Дождаться beat (10с) | Письмо в очереди; drain отправляет по prefs (отключённый тип не уходит) | Medium | test_phase3 (mock Celery) |
| TC-060 | Notifications | notifications.py | MANUAL | Счётчик в шапке | Есть уведомления | Открыть любую страницу | Бейдж с числом непрочитанных | Low | MANUAL (рендер HTML) |
| TC-061 | Ratings | ratings.py | integration | Оценка после завершения | Completed-задание | POST /api/ratings (1-5) | 200 upsert; recompute_profile_rating пересчитал среднее | High | test_a5_rating_trigger.py |
| TC-062 | Ratings | ratings.py | security | Диапазон rating 0/6/-1/10 | — | POST /api/ratings с невалидным | 400 «rating от 1 до 5» | Medium | test_coverage_completion.py::test_rating_range_validation |
| TC-063 | Ratings | ratings.py | security | Самооценка запрещена | — | POST rating с rated_user_id=сам | 400 «Нельзя оценить самого себя» | Medium | код ratings.py (валидация) |
| TC-064 | Ratings | ratings.py | security | Оценка незавершённого задания | Открытое задание | POST /api/ratings | 400 «только завершённое» | Medium | код ratings.py |
| TC-065 | Favorites | favorites.py | integration | Добавить трудника в избранное | Employer | POST /api/favorites/add | 200 success | Low | test_favorites_api.py |
| TC-066 | Favorites | favorites.py | integration | Worker на favorites-API → отказ | Worker-сессия | POST /api/favorites/check | 302/403 (role_required employer) | Medium | test_favorites_api.py::test_worker_role_denied |
| TC-067 | Favorites | favorites.py | integration | Избранное работодателей (worker) | Worker | POST /api/employers/favorites/add | 200 success | Low | test_favorites_api.py |
| TC-068 | Blacklist | blacklist.py | integration | Блокировка трудника | Employer | POST /blacklist/<worker_id> | Успех; трудник не видит задания | Medium | test_buttons_backend.py::test_employer_can_block_worker |
| TC-069 | Blacklist | blacklist.py | security | Self-block отклоняется (ИСПРАВЛЕНО 2026-08-21) | Любой employer | POST /blacklist/<свой id> | 400 «Нельзя заблокировать самого себя» (ajax) / flash (HTML) | High | test_coverage_completion.py::test_block_self_rejected |
| TC-070 | Blacklist | blacklist.py | integration | Разблокировка | Есть блокировка | POST /unblock/<id> | Успех; задания снова видны | Low | test_buttons_backend.py::test_employer_can_unblock_worker |
| TC-071 | Admin | admin_users.py | integration | Bulk-delete пользователей | Admin, не-админы в списке | POST /admin/bulk-delete-users | deleted=N; другого админа удалить нельзя (403) | High | test_admin_bulk_endpoints.py |
| TC-072 | Admin | admin_users.py | integration | Защита админа от удаления | Admin | POST bulk-delete с чужим admin-id | 403 «Cannot delete another admin» | High | test_admin_bulk_endpoints.py (код) |
| TC-073 | Admin | admin_jobs.py | integration | Bulk-delete заданий | Admin | POST /admin/bulk-delete-jobs (≤50) | deleted=N, cascade RPC | Medium | test_admin_bulk_endpoints.py |
| TC-074 | Admin | admin_dictionaries.py | integration | Bulk-delete навыков: лимит 50 | Admin | 51 skill_id | 400 «Max 50» | Low | test_admin_bulk_endpoints.py |
| TC-075 | Admin | admin_users.py | integration | Тестовый пользователь (manual activate) | Admin | GET/POST /admin/test-user | Страница 200; создание pre-verified пользователя | Medium | test_admin_bulk_endpoints.py |
| TC-076 | Admin | admin_dashboard.py | integration | Редактирование текстов terms/privacy | Admin | GET/POST /admin/content/terms | 200; HTML-контент сохраняется | Medium | test_admin_bulk_endpoints.py |
| TC-077 | Admin | admin_verification.py | integration | Верификация работодателя | Admin, заявка pending | POST approve | Статус → approved, значок «Проверенный» | High | test_buttons_backend.py (admin flow) |
| TC-078 | Admin | admin_diagnostics.py | security | X-Admin-Token эндпоинты | — | GET /admin/migrations-status без токена | 403/401 | High | test_b1_admin_diagnostics_token.py |
| TC-079 | Admin | admin_jobs.py | integration | Смена статуса задания | Admin | POST смена статуса | Статус обновлён, уведомления участникам | Medium | test_buttons_backend.py |
| TC-080 | Security | middleware.py | security | CSRF на всех мутациях | — | POST/PATCH/DELETE без токена на случайном эндпоинте | 400 | High | test_phase1b_compliance.py |
| TC-081 | Security | middleware.py | security | CSP: nonce на каждом script | Любая страница | Проверить все <script> имеют nonce | CSP strict-dynamic работает; inline-хендлеры блокированы | High | pre_deploy_check.py + test_static_checks.py |
| TC-082 | Security | middleware.py | security | CSP: SmartCaptcha в allowlist | Капча включена | Разобрать Content-Security-Policy | script-src содержит smartcaptcha.yandexcloud.net; НЕТ cloudflare | High | test_x10_captcha.py |
| TC-083 | Security | core.py | security | uploads: path traversal | — | GET /uploads/avatars/..%2F..%2Fconfig.py | 404, содержимое не отдаётся | High | test_coverage_gaps.py |
| TC-084 | Security | core.py | security | verification-docs IDOR | Чужой авторизованный | GET /uploads/verification-docs/<чужой uid>/<файл> | 403 (только владелец/админ) | High | test_coverage_gaps.py |
| TC-085 | Security | postgrest_client.py | security | profiles GET без select= → 401 | — | Прямой запрос через user-JWT | 401 (column-level GRANT, миграция 132) | High | test_rls_integration.py |
| TC-086 | Security | postgrest_client.py | contract | Circuit breaker: 10 фейлов → OPEN | PostgREST недоступен | 10+ неудачных запросов | OPEN; health-check восстанавливает; 403 НЕ размыкает | Medium | test_b1 (мониторинг CB) |
| TC-087 | Security | decorators.py | MANUAL | ГРАНИЦА: fail-open login_required | БД недоступна | Запрос к защищённой странице | Текущее: пропуск с warn; задокументированный компромисс | Medium | MANUAL (даунтаун БД) |
| TC-088 | Security | postgrest_client.py | MANUAL | ГРАНИЦА: _ADMIN_WARN_PREFIXES warn-not-block | — | admin-запрос из неразрешённого модуля | Warn в лог, не блок | Low | MANUAL |
| TC-089 | Security | auth.py | security | JWT app_role из сессии, не клиента | — | Подмена роли в запросе | Роль берётся из session/БД, подмена игнорируется | High | test_rls_integration.py |
| TC-090 | Security | sw.js | integration | Service Worker: исключения навигации | PWA установлена | Навигация на /admin, /chat и др. | SW не перехватывает (нет Navigation error); skip-list актуален | Medium | test_static_checks.py (sw.js) |
| TC-091 | Security | redis | MANUAL | TTL-рассогласование сессия/JWT/WS | — | Аудит конфигов | Сессия 1ч = JWT 1ч; WS-JWT отдельный; задокументировать компромисс | Low | MANUAL |
| TC-092 | Health | core.py | integration | /health: полный статус | Стек поднят | GET /health | 200: status=ok, database=ok, redis=ok, CB состояния | High | test_coverage_gaps.py + live |
| TC-093 | Health | core.py | integration | /ready: fail-fast | PostgREST недоступен | GET /ready | 503 с reason (Dockerfile HEALTHCHECK) | High | test_coverage_gaps.py |
| TC-094 | Health | core.py | integration | /metrics Prometheus | — | GET /metrics | 200; trudnik_* метрики присутствуют | Medium | test_coverage_gaps.py |
| TC-095 | Health | core.py | integration | /admin/health публичный (ПРИНЯТО) | — | GET /admin/health | 200 только timestamp (задокументированное решение) | Low | test_coverage_gaps.py / MANUAL |
| TC-096 | Pages | seo/core | integration | Публичные страницы 200 | — | GET /terms, /privacy, /pricing, /faq, /robots.txt | 200; robots содержит User-agent | Low | test_coverage_gaps.py |
| TC-097 | Pages | faq.py | e2e | FAQ: аккордеоны без JS | — | Открыть /faq, кликнуть <details> | 5 групп раскрываются нативно (CSP-safe) | Low | новый (дёшево) |
| TC-098 | Pages | base.html | e2e | Гость видит ссылки входа | — | GET /jobs/<id> | Ссылка /login присутствует | Low | test_buttons_backend.py |
| TC-099 | Pages | base.html | integration | Футер © 2026 (актуальность шаблонов) | Docker-стек с монтированием templates | GET / | «© 2026 Трудник» (не 2024 — признак устаревшего образа) | Low | новый (smoke-регрессия dev-стека) |
| TC-100 | A11y | chat.html | e2e | aria-live новых сообщений | Открытый чат | Отправить сообщение скринридер-профиль | #messages имеет role=log + aria-live=polite (объявление) | Medium | axe-аудит (f-серия) |
| TC-101 | A11y | рейтинг-виджеты | e2e | aria-label звёзд оценки | Страница оценки | Инспектор доступности | Кнопки «Оценка N» различимы | Low | test_f1_aria_labels.py |
| TC-102 | A11y | формы | e2e | Все inputs связаны с label | — | axe-core по формам | 0 critical a11y-нарушений | Medium | pytest -m a11y |
| TC-103 | Deploy | config.py | unit | Production guards | DEPLOYMENT_ENV=production | Инициализация с mock/без секретов | RuntimeError (не стартуем прод с mock) | High | test_architecture.py |
| TC-104 | Deploy | CI | MANUAL | ГРАНИЦА: `|| echo FAILED` в CI | — | Прочитать workflow | Задокументированный риск: шаг не падает при фейле; кандидат на фикс | Medium | MANUAL |
| TC-105 | Deploy | Amvera | MANUAL | Деплой: rebuild → /health | Push в amvera/master | rebuild, ждать 3 мин, GET /health | status=ok до считания деплоя успешным | High | MANUAL (по 06_amvera_deploy.md) |
| TC-106 | Deploy | migrations | MANUAL | Self-heal применяет миграции | Прод жив | Ждать 120с (beat) | Миграции 123-139 + NOTIFY pgrst reload; новые RPC видимы | High | MANUAL (логи celery-beat) |
| TC-107 | Load | locustfile | MANUAL | Smoke-нагрузка (после чистки фантомов) | Стек поднят; фантомные пути удалены | locust 1 пользователь 30с | 0 ошибок на живых путях | Low | MANUAL (locustfile содержит битые /api/search/* — чинить перед прогоном) |
| TC-108 | Data | 152-ФЗ | integration | Экспорт ПДн | Авторизован | GET /profile/export-data | Данные пользователя выгружаются | Medium | test_misc_gaps.py |
| TC-109 | Data | 152-ФЗ | security | Удаление аккаунта | Авторизован | POST /profile/delete-account (гость → 302) | Удаление каскадом; подтверждение обязательно | High | test_coverage_gaps.py + test_misc_gaps.py |
| TC-110 | Data | profiles | integration | Спецкатегории ПДн не собираются | — | Аудит формы регистрации | Нет полей вероисповедания; ИНН добровольно | Medium | test_a7_ratings_pii.py + код |

## Дефекты и границы (сводка для владельца)

1. **TC-069 — ИСПРАВЛЕНО 2026-08-21**: `/blacklist/<user_id>` теперь отклоняет блокировку самого себя (400/flash «Нельзя заблокировать самого себя»). Тест обновлён на корректное поведение.
2. **TC-049 (принято)**: webhook MAX без проверки подписи — любой POST получает 200. Задокументировано тестом; при росте значимости добавить проверку подписи Яндекса/MAX.
3. **TC-022/023 (принято)**: STOP_WORDS без лемматизации — «зарплату» и «з а р п л а т а» проходят. Усиление — отдельная задача (pymorphy не входит в стек).
4. **TC-087/088/091/104 (задокументированные компромиссы)**: fail-open login_required при даунтауне БД; admin warn-not-block; TTL-рассогласования; CI `|| echo FAILED`.
5. **TC-107**: locustfile содержит фантомные пути — перед нагрузочным прогоном вычистить.
