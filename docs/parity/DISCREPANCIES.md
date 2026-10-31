# Расхождения Flask (`origin/main-flask`) → Django (`main`), область auth/registration/profile

**Severity:** P0 — блокер прода/152-ФЗ; P1 — высокий; P2 — средний/UX; P3 — заметка.
**Evidence:** `файл:строка`; для БД — результат read-only запроса.
**Статус:** open — не исправлено (аудит).
**Обновление 2026-10-31:** AUTH-P0-01…P0-04 исправлены контрактами P001–P004
(verify PASS, functional PASS, pattern PASS). Доказательства: [P0_RESULTS.md](P0_RESULTS.md),
`context/agent-pipeline/logs/P00x.verify.log`. AUTH-P1-01, P1-02, P1-06 исправлены
контрактами P101, P102, P106; AUTH-P1-03, P1-04, P1-11 — P103, P104; P1-07/08/14 — P107, P108, P114.
BUILD-01 — B001 (pre_deploy 7/7). TASKS-01 (cross-area: `expire_old_jobs` int(dict)) — T001.
P1-12 — P112 (IDOR-матрица, pattern FAIL→fix→PASS). P1-10 ORM-путь — P110
(DB-default остаётся до P113). P1-05 — P105 (async email, pattern FAIL→fix→PASS).
P1-13 + DB-default P1-10 — локальный dev: 65/65 миграций, `email_verified default=false`,
gate `scripts/check_migrations.py` OK; production — pending deploy-window
([MIGRATION_LEDGER.md](MIGRATION_LEDGER.md)). **SEC-01:** `/admin/env/` показывал секреты
открытым текстом — замаскировано E001 (verify/functional/pattern PASS).
Доказательства: [P1_RESULTS.md](P1_RESULTS.md).

## P0 — блокеры

| ID | Расхождение | Evidence Flask | Evidence Django | Влияние |
|---|---|---|---|---|
| AUTH-P0-01 | **Капча не работает при включении.** Django-форма ждёт `smart_token`, виджет Yandex SmartCaptcha кладёт `smart-token`, Flask читает `smart-token`. | `app/blueprints/auth.py:238,503` | `core/forms_auth.py:48,76`; `core/views_auth.py:88,168`; `templates/core/register.html:70,73-74`; `templates/core/password_reset_request.html:19-21` | В проде с `SMARTCAPTCHA_SERVER_KEY` регистрация и сброс пароля всегда отклоняются. Dev/тесты без ключа этого не видят. |
| AUTH-P0-02 | **Документы верификации читает любой авторизованный.** Flask: owner или admin, иначе 403; Django: только `is_authenticated`. | `app/blueprints/core.py:246-262`; тесты `tests/test_coverage_gaps.py:71-99` | `core/views_profile_ext.py:199-212`; тест `core/tests/test_parity_ext.py:113-116` | Утечка паспортных/личных документов по UUID-пути. Нарушение 152-ФЗ, P0. |
| AUTH-P0-03 | **Публичный профиль отдаёт `contact`** (и выбирает `religion_id`). Flask в публичных полях `contact`/`phone`/`email` не выбирает. | `app/blueprints/profile.py:28`; `templates/profile_worker.html:176-179`; тесты `tests/test_critical_gaps.py:520,567` | `core/views.py:20-25` (`PUBLIC_PROFILE_FIELDS`), `core/templates/core/worker_detail.html:46-47` | Публичная утечка контакта; при наличии `religion_id` — спецкатегория ПДн. Нарушение 152-ФЗ. |
| AUTH-P0-04 | **В редактирование профиля возвращено `religion`.** Flask убрал вероисповедание как спецкатегорию (152-ФЗ ст.10). | `app/blueprints/profile.py:155-156` | `core/forms_profile.py:16-20`; `templates/core/profile.html:46-54` | Сбор спецкатегории ПДн без законного основания/согласия; дискриминационный риск. |

## P1 — высокий

| ID | Расхождение | Evidence Flask | Evidence Django | Влияние |
|---|---|---|---|---|
| AUTH-P1-01 | **Регистрация упрощена:** потеряны ИНН, самозанятость, контакт, портфолио, опыт, желаемая оплата, навыки. | `app/blueprints/auth.py:248-334`; `templates/register.html:127-171` | `core/forms_auth.py:32-48`; `templates/core/register.html:16-78` | Не сохраняются данные, которые Flask собирал при регистрации; профиль приходится дозаполнять вручную. |
| AUTH-P1-02 | **Нет валидации ИНН (12 цифр + контрольная сумма) и контакта (мин. 3, формат).** | `app/blueprints/auth.py:220-229`; `app/blueprints/profile.py:131-153` | `core/forms_profile.py:16-33` (plain CharField) | Мусорные/некорректные юридически значимые данные. |
| AUTH-P1-03 | **Login без per-IP rate-limit; per-account lockout in-process; `PermissionDenied` не перехвачен → 403.** | `app/blueprints/auth.py:70-94`; `app/services/auth_service.py:151-183` | `core/views_flow.py:86-102`; `core/auth_backend.py:20-100` | Brute-force с многих IP; multi-worker обходит lockout; заблокированный видит 403 вместо сообщения. |
| AUTH-P1-04 | **Cooldown сброса/ресенда — in-process dict**, не Redis. | `app/blueprints/auth.py:459-483,657-685` | `core/views_auth.py:46-60` | Multi-worker обходит лимит; память растёт; поведение зависит от воркера. |
| AUTH-P1-05 | **Почта отправляется синхронно** в request-цикле; Flask — Celery. | `app/blueprints/auth.py:338-353,524-542` | `core/views_auth.py:63-70,116-123,151-157,180-185` | Регистрация/сброс висят на SMTP; сбой SMTP замедляет/ломает UX. |
| AUTH-P1-06 | **Смена пароля не ротирует сессию и не инвалидирует другие сессии.** Flask blacklist jti + новый JWT. | `app/blueprints/profile.py:372-388`; `app/utils/auth.py:259-274`; тест `tests/test_critical_gaps.py:1521` | `core/views_profile.py:32-47` (`password_changed_at` обновляется, сессия — нет) | Украденная/старая сессия остаётся живой после смены пароля. |
| AUTH-P1-07 | **Верификация не принимает PDF.** Flask: PDF/JPEG/PNG по magic bytes. | `app/blueprints/profile.py:34-56,412-417`; `templates/verify_employer.html:42` | `core/storage.py:12-45`; `templates/core/verify_employer.html:12` | Пользователь не может загрузить PDF-документ, как в Flask. |
| AUTH-P1-08 | **Легаси-аватары `photo_url` не видны:** Django пишет/читает `avatar_url`, шаблоны не имеют fallback на `photo_url`. | `app/blueprints/profile.py:169` (пишет `photo_url`) | `core/views_profile_ext.py:168`; `templates/core/profile.html:10`, `worker_detail.html:13`, `workers_list.html:22` | Аватары, загруженные во Flask, исчезают в каталоге/профиле. |
| AUTH-P1-09 | **Resend подтверждения отправляется уже подтверждённым.** Flask проверяет `email_verified`. | `app/blueprints/auth.py:663-685` | `core/views_auth.py:144-160` | Лишние письма, лишний трафик, слабее защита от email-оракула. |
| AUTH-P1-10 | **`email_verified` по умолчанию `true`** (fail-open); RPC регистрации ставит `false`, но любой другой путь создания профиля даёт подтверждённого пользователя. | RPC ставит `FALSE` (`register_user`) | `core/models.py:101`; БД `profiles.email_verified DEFAULT true` | Fail-open: новый путь создания профиля может обойти подтверждение email. |
| AUTH-P1-11 | **Rate-limit fail-open + нет декораторов** на login/register/reset/resend. | `@rate_limit(fail_open=False)` на login/register | `core/ratelimit.py:28-40` (fail-open); `views_flow.py:86`, `views_auth.py:82,164,144` без декоратора | При сбое кэша защита исчезает; часть эндпоинтов вообще без лимита. |
| AUTH-P1-12 | **RLS обходится ролью БД.** `trudnik` — superuser+BYPASSRLS, `trudnik_dj` — BYPASSRLS; видимость обеспечивают queryset-менеджеры. | Flask ходил через PostgREST/JWT (RLS), admin — точечно | `djadmin/README.md:67-68`; БД: `trudnik` superuser/BYPASSRLS, `trudnik_dj` BYPASSRLS; `profiles` RLS enabled, not forced | Нет «сетки безопасности»: любой пропущенный фильтр = IDOR. Публичный профиль (P0-03) это уже подтверждает. Нужна контрактная матрица IDOR по всем view. |
| AUTH-P1-13 | **Migration ledger отстаёт:** `_migrations` max = 122, но `change_password(text,text)` (149) уже есть в БД. | — | БД: `_migrations` 122; `pg_proc` содержит `change_password(text,text)`; `migrations/149_...sql` | Свежий клон/повторный apply может не получить 123–149; reset/другие функции могут отсутствовать. Нужен deployment-gate. |
| AUTH-P1-14 | **Удаление аккаунта не удаляет файлы ПДн.** `delete_user_cascade` чистит строки БД, но не `uploads/avatars`, `uploads/verification-docs`, `uploads/jobs`. | Flask `delete_account` тоже не чистит файлы (паритет по коду), но для 152-ФЗ это дыра. | `core/views_profile_ext.py:79-94`; БД `delete_user_cascade` (DEFINITION); `core/storage.py` | После удаления аккаунта сканы документов/аватары остаются на диске. Требуется purge файлов + audit-log. |

## P2 — средний/UX/долги

| ID | Расхождение | Evidence | Влияние |
|---|---|---|---|
| AUTH-P2-01 | Нет удаления фото профиля (`/profile/delete-photo`). | Flask `templates/profile.html:64-66`; Django `templates/core/profile.html` (нет формы) | Нельзя удалить аватар, только заменить. |
| AUTH-P2-02 | На странице профиля нет кнопки выхода; Flask — есть. | Flask `templates/profile.html:231-234`; Django `profile.html` | Выход только из общего меню (если есть). |
| AUTH-P2-03 | Публичный профиль без чата, ссылки «Все отзывы», счётчика выполненных, бейджа «Надёжный». | Flask `templates/profile_worker.html:57-70,156-174`; Django `templates/core/worker_detail.html` | UX-паритет/доверие. |
| AUTH-P2-04 | URL публичного профиля `/profile/<uuid>` → `/workers/<uuid>`, редиректа нет. | Flask `app/blueprints/profile.py:439`; Django `core/urls.py:26` | Ломаются старые ссылки/закладки/внешние ссылки. |
| AUTH-P2-05 | Невалидный email-токен ведёт на `resend`, Flask — на `register`. | Flask `auth.py:631-632`; Django `views_auth.py:139-141` | Мелкое UX-расхождение. |
| AUTH-P2-06 | Honeypot даёт видимую ошибку «Регистрация невозможна», Flask — тихий редирект. | Flask `auth.py:151-154`; Django `forms_auth.py:60-65` | Бот может детектировать honeypot. |
| AUTH-P2-07 | Сброс пароля: `payload["email"]` без `.get` — KeyError при нештатном payload. | Flask `auth.py:559`; Django `views_auth.py:196,211` | 500 на подписанном, но нестандартном токене (низкий риск). |
| AUTH-P2-08 | CSRF-ошибка: Django default 403; Flask commit `9b3ed42` обещает дружелюбный редирект. | Django `settings.py` без `CSRF_FAILURE_VIEW`; Flask commit `9b3ed42` | Плохой UX при устаревшей сессии. |
| AUTH-P2-09 | Капча: Django не передаёт IP в Yandex validate; Flask передаёт. | Flask `auth.py:238,503`; Django `views_auth.py:88,168` | Слабее антибот-сигнал. |
| AUTH-P2-10 | `legal_page.html` рендерит `page.content|safe` — stored XSS при компрометации админа/контента. | Django `templates/core/legal_page.html:6` | XSS-риск (trust boundary — админ). Нужна санитизация/доверенный контент. |
| AUTH-P2-11 | Корневые `templates/*.html` — мёртвые копии Flask; Django использует `djadmin/core/templates/core/*`. | `settings.py:135-150` (`DIRS=[]`, `APP_DIRS=True`); views рендерят `core/...` | Путаница при правках/документации, риск править не тот файл. |
| AUTH-P2-12 | Регистрация: max length `full_name` 300 / `city` 200 vs Flask 150/100; в Flask-шаблоне 100/50. | Flask `auth.py:59-60`; Django `forms_auth.py:39-40` | Ослабленная валидация длины. |
| AUTH-P2-13 | `worker_detail` выбирает `religion_id` в контекст без необходимости. | Django `core/views.py:20-25` | Least privilege: спецкатегория ПДн в контексте. |
| AUTH-P2-14 | Регистрация: упрощённый шаблон (86 строк vs 401), нет пошагового UI/подсказок. | Flask `templates/register.html`; Django `templates/core/register.html` | UX-паритет. |
| AUTH-P2-15 | Верификация: упрощённый шаблон (19 строк vs 159), нет JS-валидации размера/формата. | Flask `templates/verify_employer.html`; Django `templates/core/verify_employer.html` | UX/ошибки загрузки. |
| AUTH-P2-16 | `report_user`: Django всегда redirect; Flask для AJAX отдаёт JSON. | Flask `profile.py:478-489`; Django `views_profile_ext.py:100-111` | Если фронт ждёт JSON — сломается; текущий Django-шаблон использует обычную форму. |
| AUTH-P2-17 | `notification_prefs`: Flask — динамический JS/AJAX-список; Django — статичные чекбоксы. | Flask `templates/notification_settings.html`; Django `templates/core/notification_settings.html` | UX/функциональность (проверить полный набор типов). |
| AUTH-P2-18 | `POST /api/notifications/preferences` не обновляет prefs: Django-view только возвращает JSON на любой метод. | Flask `notifications.py:160,182`; Django `views_profile_ext.py:146-152`; `urls.py:52` | JS-клиенты, использующие API, не сохранят настройки. Форма `/notifications/settings` работает. |

## P3 — заметки (не дефекты)

- **BUILD-01 (P2, вне auth): Tailwind-конфиг и pre-deploy scan смотрят не туда.**
  `tailwind.config.js` `content` = `./templates/**/*.html` + `./static/js/**/*.js`;
  `scripts/pre_deploy_check.py` [7/7] сканирует те же корневые `templates/`. Реальные
  Django-шаблоны лежат в `djadmin/core/templates/core/` и не попадают ни в сборку, ни в
  проверку свежести. Следствие: `pre_deploy_check` падает на legacy `templates/terms.html`,
  а `npm run build:css` собирает CSS не из актуальных Django-шаблонов. Лечение: добавить
  `./djadmin/core/templates/**/*.html` в `content`, обновить scan, пересобрать CSS,
  прогнать UI-проверки. P003-классы в текущем CSS уже есть, визуального регресса нет.
- **Экспорт ПДн:** Django исключает `password` из JSON (`views_profile_ext.py:41`), Flask `select=*` мог включать `password_hash`. Это **улучшение** Django; сохранить.
- **Пароли:** Django `set_password` пишет bcrypt `$2a$` 12 раундов (`models.py:135-147`), совместимо с pgcrypto/Flask; migration 149 `change_password` также `$2a$` и двигает `password_changed_at`.
- **Токены:** соли/TTL/payload совпадают (`core/tokens.py` vs Flask `auth.py:403-452`), кросс-совместимость есть.
- **RPC:** `register_user(5 args)`, `change_password(text,text)`, `change_password(uuid,text,text)`, `delete_user_cascade`, `file_report`, `login_user`, `accept_invitation_atomic` — существуют в БД (см. CONTRACT_CHECKS).
- **N+1 в audited views:** `favorite_people`/`blacklist_view`/`invitations` используют `select_related`; `worker_detail` — 4 запроса; `workers_list` — 1 запрос на страницу. N+1 не обнаружен в этой области.
- **XSS в auth/profile:** автоэкранирование Django; единственный `|safe` — `legal_page.html:6` (P2-10).

## Следующие контракты (предложение)

P0: `AUTH-P0-01` (капча), `AUTH-P0-02` (verification-doc ACL), `AUTH-P0-03` (public profile PII),
`AUTH-P0-04` (religion).
P1: `AUTH-P1-01/02` (регистрация+валидация), `AUTH-P1-03/04/11` (rate-limit/lockout/cooldown),
`AUTH-P1-06` (session invalidation), `AUTH-P1-07/08` (PDF/photo_url), `AUTH-P1-12/13` (RLS/ledger).
P2 — после P0/P1.
