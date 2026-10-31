# AUDIT — auth / registration / profile

**Итог:** Django-версия в целом повторяет каркас Flask (те же RPC, токены, bcrypt, консент,
intent→роль), но **не является полным паритетом**. В области есть 4 блокера P0
(капча, доступ к документам верификации, публичный `contact`, вероисповедание),
14 P1 (регистрация/валидация, rate-limit/lockout/cooldown, сессии, PDF, legacy-аватары,
fail-open, RLS/ledger) и 18 P2 (UX/маршруты/мёртвые шаблоны). Заявление о «100% паритете»
для этой области **не подтверждается**.

> **Обновление 2026-10-31:** все 4 P0 исправлены контрактами P001–P004:
> verify PASS, functional PASS, pattern PASS; кросс-регрессия 100 тестов OK.
> P1-01/02/06 исправлены контрактами P101/P102/P106 (кросс-регрессия 109 тестов OK),
> P1-03/04/11 — P103/P104, P1-07/08/14 — P107/P108/P114.
> BUILD-01 — B001 (pre_deploy 7/7), TASKS-01 — T001. P1-12 — P112 (IDOR-матрица),
> P1-10 ORM-путь — P110; P1-05 — P105 (async email). Полный `core` — 226 тестов OK.
> Детали — [P0_RESULTS.md](P0_RESULTS.md), [P1_RESULTS.md](P1_RESULTS.md).
> Остальные: P1-13 + DB-default P1-10 — локально выполнено (65/65, default=false,
> `check_migrations.py` OK); production — pending deploy-window.

## 1. Что сверялось

- Flask: `origin/main-flask` @ `9b3ed42`, worktree `../trudnik-flask`.
- Django: `main` @ `3f4aa40` (+ незакоммиченный `feat/agent-pipeline`).
- Routes: `app/blueprints/auth.py`, `profile.py`, `notifications.py`; Django `core/urls.py`,
  `views_auth.py`, `views_flow.py`, `views_profile.py`, `views_profile_ext.py`.
- Формы/шаблоны: `templates/*.html` (Flask) vs `djadmin/core/templates/core/*.html` (Django).
- RPC/RLS/роли: read-only запросы к dev-БД через MCP (см. `CONTRACT_CHECKS.md`).
- Pattern-review: XSS (`|safe`), fail-open, N+1.

## 2. Бизнес-логика: что совпало

- **Пароль:** та же политика (`validate_password`: ≥8, заглавная, строчная, цифра, спецсимвол).
- **Хэши:** bcrypt `$2a$` 12 раундов; совместимость с pgcrypto и Flask.
- **Токены:** те же соли `password-reset` / `email-verify`, TTL 1 ч / 24 ч, payload
  `{email, pwd_changed_at}`; кросс-совместимость с Flask-токенами.
- **Регистрация:** `register_user(p_email,p_password,p_full_name,p_role,p_worker_visibility)`;
  RPC ставит `email_verified=FALSE`; consent обязателен; `consented_at` пишется;
  `intent=post_jobs` → employer + `worker_visibility=false`.
- **Сброс пароля:** `change_password(text,text)` существует (migration 149) и двигает
  `password_changed_at`; старый токен умирает после смены.
- **Удаление:** `delete_user_cascade`; **жалоба:** `file_report` через `call_rpc_as_user`
  (claims `request.jwt.claims` — корректно).
- **Загрузки:** magic-bytes JPEG/PNG/WebP, лимит 5 МБ, path traversal защищён.
- **Экспорт:** Django исключает `password` (улучшение относительно Flask `select=*`).
- **N+1:** в audited views `select_related` используется; `workers_list` — 1 запрос на страницу,
  `worker_detail` — 4 запроса; N+1 не найден.

## 3. Бизнес-логика: что не совпало

1. **Регистрация упрощена.** Django-форма/шаблон собирают только ФИО, email, пароль, intent,
   город, consent. Flask дополнительно собирал портфолио, контакт, ИНН, самозанятость, опыт,
   желаемую оплату, навыки. Данные не сохраняются (AUTH-P1-01).
2. **Нет валидации ИНН/контакта** в Django-профиле (AUTH-P1-02).
3. **Login:** Django не имеет per-IP лимита; per-account lockout — in-process; `PermissionDenied`
   не перехвачен → 403 вместо сообщения (AUTH-P1-03).
4. **Cooldown сброса/ресенда** — in-process dict, не Redis; multi-worker обходит (AUTH-P1-04).
5. **Почта синхронная**, Flask — Celery (AUTH-P1-05).
6. **Смена пароля не инвалидирует другие сессии** (AUTH-P1-06).
7. **Верификация не принимает PDF** (AUTH-P1-07).
8. **Легаси `photo_url` не виден** — Django читает только `avatar_url` (AUTH-P1-08).
9. **Resend** шлёт письмо уже подтверждённым (AUTH-P1-09).
10. **`email_verified` default true** — fail-open (AUTH-P1-10).
11. **Rate-limit fail-open** + отсутствие декораторов на login/register/reset/resend (AUTH-P1-11).
12. **RLS не применяется** к Django (BYPASSRLS); компенсация — queryset-фильтры, но
    публичный профиль уже течёт (AUTH-P1-12).
13. **Migration ledger 122 vs функция 149** — риск свежего развёртывания (AUTH-P1-13).
14. **Удаление аккаунта не чистит файлы ПДн** (AUTH-P1-14).

## 4. UI/UX

- Login: набор элементов совпадает; Django проще (нет клиентской валидации/различения причин).
- Register: **сильно упрощён** (86 строк vs 401): нет ИНН/самозанятости/контакта/портфолио/
  опыта/оплаты/навыков; нет пошагового UI.
- Profile: нет удаления фото и кнопки выхода; `confirm()` вместо модалки удаления;
  зато добавлены поля ИНН/самозанятости/`religion` (последнее — P0).
- Public profile: нет чата, ссылки на отзывы, счётчика выполненных, бейджа «Надёжный»;
  URL `/workers/<uuid>` вместо `/profile/<uuid>` без редиректа.
- Verify employer: нет PDF и JS-валидации; шаблон 19 строк vs 159.
- Notification settings: статичные чекбоксы вместо JS/AJAX; API POST не сохраняет.

Полная построчная матрица — `UI_INVENTORY.md` и `ROUTES_MATRIX.md`.

## 5. Безопасность и 152-ФЗ (блокеры)

| ID | Суть | Почему блокер |
|---|---|---|
| AUTH-P0-01 | `smart_token` vs `smart-token` | В проде с капчей регистрация и сброс пароля не работают вообще. |
| AUTH-P0-02 | verification-docs доступны любому авторизованному | Утечка сканов документов; 152-ФЗ. |
| AUTH-P0-03 | публичный профиль отдаёт `contact` | Публичная утечка ПДн; 152-ФЗ. |
| AUTH-P0-04 | в профиле снова собирается `religion` | Спецкатегория ПДн без основания; 152-ФЗ ст.10. |

Дополнительно: `Cache-Control: public` на verification-docs (P0-02), файлы ПДн не удаляются
при удалении аккаунта (P1-14), RLS обходится (P1-12), `email_verified=true` default (P1-10).

## 6. Pattern review (XSS / fail-open / N+1)

- **XSS:** автоэкранирование Django включено; в auth/profile единственный `|safe` —
  `core/templates/core/legal_page.html:6` (`SitePage.content`). Контент правит админ
  через Django admin; это trust boundary, но нужна санитизация/ограничение HTML (P2-10).
- **Fail-open:** `email_verified` default true; `ratelimit` глотает все ошибки кэша;
  login/register/reset/resend без декораторов; lockout/cooldown в памяти процесса.
- **N+1:** в audited views не найден; `workers_list`/`worker_detail`/`profile` —
  фиксированное число запросов. Для остальных областей — отдельный проход.

## 7. Контрактная проверка (факты)

- БД: PostgreSQL 15.8, `current_user=trudnik`; `trudnik` — superuser + BYPASSRLS;
  `trudnik_dj` — BYPASSRLS; `trudnikapp` — без bypass.
- RLS на `profiles/jobs/applications/messages/notifications` включён, но **не forced**,
  owner `trudnik` → Django ORM обходит политики.
- `change_password(text,text)` есть и двигает `password_changed_at`;
  `register_user` ставит `email_verified=false`; `file_report` читает claims;
  `delete_user_cascade` чистит строки, но не файлы.
- `_migrations` max = 122, при этом функция 149 в БД есть — ledger расходится.

Подробности и очередь runtime-проверок — `CONTRACT_CHECKS.md`.

## 8. Рекомендуемый порядок контрактов

1. **P0-01 captcha** — один контракт: поле, шаблоны, тест с mock Yandex validate.
2. **P0-02 verification-doc ACL + cache headers** — owner/admin, no-store, audit.
3. **P0-03 public profile PII** — убрать `contact`/`religion_id`, тест анонимного GET.
4. **P0-04 religion** — убрать поле из формы/шаблона/сохранения.
5. **P1-01/02 регистрация+валидация** — вернуть поля, INN checksum, contact format, skills.
6. **P1-03/04/11 rate-limit/lockout/cooldown** — Redis, per-IP, fail-closed для auth,
   дружелюбные сообщения.
7. **P1-06 сессии** — `cycle_key` + инвалидация других сессий.
8. **P1-07/08 PDF и photo_url fallback**.
9. **P1-14 удаление файлов** + **P1-13 migration gate** + **P1-12 IDOR-матрица**.
10. **P2** — UX/маршруты/мёртвые шаблоны/API prefs.

## 9. Открытые вопросы к владельцу

1. `contact`/`email_public`: что именно считается публичным? Нужен явный consent-флаг?
2. `religion`: удалить полностью или есть законное основание/согласие?
3. PDF в верификации: обязателен ли (Flask принимал PDF)?
4. Rate-limit: допустим ли fail-open для auth или только fail-closed?
5. SMTP-провайдер и регион — РФ? Договор поручения есть?
6. Можно ли перевести Django на `trudnikapp` (NOBYPASSRLS) для публичных чтений?
7. Политика удаления: БД + файлы + бэкапы; сроки.
8. Приоритет P2: пиксельный паритет или осознанные UX-улучшения?

## 10. Ограничения

- Прод-БД и прод-конфигурация не проверялись; выводы о ролях/RLS основаны на dev-БД
  и `djadmin/README.md`.
- Runtime-поведение (капча, ACL, rate-limit, сессии) не подтверждено запуском;
  это очередь контрактов, а не «уже доказано».
- Аудит не меняет код и не создаёт pipeline-контракты; следующий шаг — согласовать
  severity/приоритеты и запустить контракты P0.
