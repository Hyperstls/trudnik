# Contract checks — что проверено фактически и что ещё нужно

Проверки выполнены **read-only** через MCP PostgreSQL. Это dev/контейнерная БД
(`current_database=trudnik`, host `172.19.0.6`), **не прод**. Прод не запрашивался.

## 1. Идентичность и роли

| Проверка | Результат |
|---|---|
| PostgreSQL | `15.8` (Alpine/musl) |
| `current_user` / `session_user` | `trudnik` |
| `trudnik` | `rolsuper=true`, `rolbypassrls=true`, `rolcanlogin=true` |
| `trudnik_dj` | `rolsuper=false`, **`rolbypassrls=true`**, `rolcanlogin=false` |
| `trudnikapp` | `rolsuper=false`, `rolbypassrls=false`, `rolcanlogin=false` |
| Django `.env` | `DATABASE_URL` = `trudnik@db:5432/trudnik` (пароль не выводился); settings remap `db` → `localhost:5433` |
| Prod README | Django использует `trudnik_dj` (BYPASSRLS); «видимость гарантируют queryset-менеджеры» (`djadmin/README.md:67-68`) |

**Вывод:** и `trudnik`, и `trudnik_dj` обходят RLS. RLS — не «сетка безопасности»;
компенсирующий контроль — фильтры Django. Любой пропущенный фильтр = IDOR.
Публичный профиль (AUTH-P0-03) это уже демонстрирует.

## 2. RLS

| Таблица | `relrowsecurity` | `relforcerowsecurity` | Owner |
|---|---|---|---|
| `profiles` | true | **false** | `trudnik` |
| `jobs` | true | false | `trudnik` |
| `applications` | true | false | `trudnik` |
| `messages` | true | false | `trudnik` |
| `notifications` | true | false | `trudnik` |

Политики `profiles`:
- SELECT: `jwt.user_id = id` **OR** `role IN ('worker','employer')`;
- UPDATE: `jwt.user_id = id`;
- INSERT: `jwt.user_id = id AND role IN ('worker','employer')`.

Так как роль приложения — owner/BYPASSRLS, политики не применяются к Django ORM.

## 3. RPC — фактические сигнатуры

| RPC | Аргументы | Возврат | Статус |
|---|---|---|---|
| `register_user` | `text,text,text,text,boolean` | `uuid` | есть; ставит `email_verified=FALSE`; `RAISE email_exists/invalid_role` |
| `change_password` | `text,text` (email, new) | `boolean` | есть; `SET password_hash=crypt(...,bf,12), password_changed_at=now()` |
| `change_password` | `uuid,text,text` (user, old, new) | `boolean` | есть (смена из профиля) |
| `delete_user_cascade` | `uuid` | `jsonb` | есть; удаляет строки, **но не файлы на диске** |
| `file_report` | `uuid,text` | `jsonb` | есть; читает `request.jwt.claims` → Django использует `call_rpc_as_user` |
| `login_user` | `text,text` | `TABLE(user_id,role,full_name,email_verified)` | есть; Django login идёт через ORM/`ProfileBackend`, не через RPC |
| `accept_invitation_atomic` | `uuid,uuid` | `jsonb` | есть |
| `sync_user_skills` | — | — | **отсутствует в этой БД**; Django использует raw-SQL `sync_user_skills_raw` (совместимо с комментарием в коде) |

## 4. Колонки/дефолты `profiles`

| Колонка | Тип | Default | Замечание |
|---|---|---|---|
| `email_verified` | boolean | **true** | fail-open (AUTH-P1-10); RPC регистрации ставит false |
| `password_changed_at` | timestamptz | now() | используется для B10/B11 |
| `worker_visibility` | boolean | true | ок |
| `contact` | text | — | публично отдаётся Django (AUTH-P0-03) |
| `religion_id` | uuid | — | спецкатегория; Django снова собирает (AUTH-P0-04) |
| `photo_url` | text | — | Flask-аватары |
| `avatar_url` | text | — | Django-аватары; fallback нет (AUTH-P1-08) |

## 5. Migration ledger

`_migrations` (колонки `filename`, `applied_at`, `checksum`) содержит максимум
`122_fix_outbox_grants.sql` (2026-07-14). При этом `change_password(text,text)` из
`migrations/149_change_password_email_overload.sql` в БД **есть**. То есть ledger
и фактическая схема расходятся. Для свежего клона/повторного apply это риск
(AUTH-P1-13): reset может упасть, если 149 не применится.

## 6. Очередь runtime contract-проверок (следующая фаза)

Каждая проверка — команда с exit-кодом, а не «посмотреть глазами».

| # | Проверка | Ожидание |
|---|---|---|
| 1 | POST `/register` с валидным `smart-token` (mock Yandex `/validate` → `status=ok`) и вариант `smart_token` | проходит только реальное имя поля; доказывает/опровергает AUTH-P0-01 |
| 2 | `/uploads/verification-docs/...`: guest / другой user / owner / admin / traversal | guest 302/404, другой 403/404, owner/admin 200, traversal 404 |
| 3 | GET `/workers/<id>` анонимно | в HTML нет `contact`, `religion`, `phone`, `email` (кроме явного `email_public`, если это разрешено) |
| 4 | GET `/profile` и POST с `religion` | поля `religion` нет; значение не сохраняется |
| 5 | POST `/register` со всеми Flask-полями | ИНН, самозанятость, контакт, портфолио, опыт, оплата, навыки сохранены |
| 6 | ИНН `123` / неверная контрольная сумма; контакт `x` | форма отклоняет, запись не создаётся |
| 7 | 21 login-запрос с одного IP; 5 неверных паролей; неподтверждённый email | 429/блок; сообщение о блокировке (не 403); сообщение «подтвердите email» |
| 8 | Два процесса: reset request дважды за 5 минут | второй заблокирован (in-process cooldown ловится) |
| 9 | SMTP с задержкой 10 с; регистрация | latency в бюджете; сбой SMTP не ломает регистрацию |
| 10 | Две сессии; смена пароля в одной; запрос во второй | вторая сессия недействительна |
| 11 | Upload PDF и `.exe` в verification | PDF принят, `.exe` отклонён |
| 12 | Профиль только с `photo_url` | аватар виден в `/profile` и `/workers/<id>` |
| 13 | Resend для verified email | письмо не отправляется |
| 14 | Профиль, созданный в обход RPC (`email_verified` default) | вход запрещён до подтверждения |
| 15 | Сбой cache/Redis на login/register | лимит не исчезает (fail-closed или явно документированный fail-open) |
| 16 | Чистый клон: применить миграции до 149 | `change_password(text,text)` существует |
| 17 | Удаление аккаунта с аватаром и verification-doc | файлы удалены с диска, ПДн не осталось |
| 18 | POST `/api/notifications/preferences` | prefs обновляются (паритет Flask) |
| 19 | POST с устаревшим CSRF | дружелюбный редирект или документированный 403 |
| 20 | `site_pages.content` с `<script>` | санитизировано или доступно только доверенному админу |
| 21 | `assertNumQueries` для `workers_list`, `worker_detail`, `profile` | в бюджете, без N+1 |
| 22 | IDOR: user A → профиль/экспорт/удаление/документ user B | 403/404, без утечки |

## 7. Ограничения этого этапа

- Прод-БД не проверялась; выводы о ролях/RLS относятся к dev/контейнеру и к конфигурации
  из `djadmin/README.md` (prod `trudnik_dj`, BYPASSRLS).
- Runtime-поведение (капча, ACL, rate-limit, сессии) пока **не** подтверждено запуском;
  это очередь п.6 и следующих контрактов.
- Статический анализ не заменяет contract verification (ваш п.4): оба гейта обязательны.
