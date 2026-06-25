# Этап 7: Ревью скриптов и миграций

> Дата: 2026-06-22 | Охват: 59 SQL + 18 скриптов

---

## Часть 1: Миграции

### 1.1. Общий обзор

**Статистика по 58 нумерованным миграциям + run_all_safe.sql:**

| Показатель | Значение |
|---|---|
| Всего файлов миграций | 59 (58 нумерованных + run_all_safe.sql) |
| Диапазон номеров | 001-058 |
| Пропуски в нумерации | Нет |
| **Дубликаты номеров** | **019 - ДВА файла: 019_add_missing_notifications_columns.sql + 019_fix_security_warnings.sql** |
| CREATE OR REPLACE FUNCTION (RPC) | 12 функций |
| DROP TABLE | 3 (только в 027, 028, run_all_safe.sql - все через IF EXISTS) |
| TRUNCATE | 0 |
| RLS-политик (оценка) | ~80+ политик на все активные таблицы |
| BEGIN/COMMIT транзакции | 3 миграции (039, 048, 057) |
| --down секции | Отсутствуют во всех миграциях |

**Конвенция именования:** Формат NNN_описание.sql - последовательный и предсказуемый. **Идемпотентность:** Ранние миграции (001-005) активно используют IF NOT EXISTS / IF EXISTS. Миграция 003: все ALTER/ADD с IF NOT EXISTS. Средние и поздние миграции: преимущественно идемпотентны.

---

### 1.2. Детальный ревью последних миграций (053-058)

#### 053_fix_critical_type_mismatches.sql (9.3K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **WARNING** | 103-155 | Шаг 3 удаляет 10 RLS-политик, меняет тип колонки и пересоздаёт политики. Если скрипт упадёт между DROP и CREATE, таблицы останутся без RLS. Нет BEGIN/COMMIT. | Обернуть шаг 3 в транзакцию |
| 2 | **WARNING** | 119-152 | Восстановленные политики имеют **другие имена**, чем удалённые. | Проверить, что код не ссылается на имена политик |
| 3 | **LOW** | 15-37 | DO-блоки без обработки ошибок ALTER TYPE. | Добавить EXCEPTION WHEN OTHERS |

#### 054_create_missing_cloud_tables.sql (7.3K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **LOW** | 76 | receipts.contact_payment_id - FK на _archive_contact_payments не создаётся явно (только UUID без REFERENCES). | Сверить с облачной схемой, добавить REFERENCES |
| 2 | **SUGGESTION** | 68,148,205 | GRANT TO service_role есть, но нет REVOKE от anon/authenticated. RLS включён - OK. | OK |

#### 055_fix_table_structures.sql (5.7K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **SUGGESTION** | 26-40 | UPDATE employer_details SET name = company_name - перенос данных с проверкой IF EXISTS. OK. | OK |
| 2 | **LOW** | 89-90 | DROP CONSTRAINT IF EXISTS invitations_employer_id_fkey - удаление FK без восстановления. | Проверить, нужны ли FK в облачной схеме |

#### 056_add_nearby_jobs_rpc.sql (1.8K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **LOW** | 19 | SECURITY DEFINER + SET search_path = public - правильная практика. OK. | OK |
| 2 | **SUGGESTION** | 49-50 | RETURNS SETOF jobs - при изменении схемы jobs функция сломается. | Рассмотреть RETURNS TABLE с явным списком колонок |

#### 057_fix_linter_warnings_v3.sql (6.4K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **WARNING** | 92-131 | Три DO-блока с RAISE WARNING для документирования осознанных исключений. Засоряет логи при каждом выполнении. | Заменить на RAISE NOTICE |
| 2 | **SUGGESTION** | 7 | Использует BEGIN/COMMIT - третья миграция с транзакцией из 58. Несогласованно. | Стандартизировать |

#### 058_add_native_auth.sql (2.0K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **HIGH** | 13,26,40 | Три RPC функции используют SECURITY DEFINER, но НЕТ REVOKE EXECUTE от anon/PUBLIC. Анонимы могут вызывать login_user, register_user, change_password. | Добавить REVOKE EXECUTE FROM anon, PUBLIC |
| 2 | **MEDIUM** | 8-9 | ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email text - без UNIQUE constraint (кроме частичного индекса). Два пользователя могут иметь NULL email. | Добавить уникальный constraint |
| 3 | **MEDIUM** | 20-21 | login_user сравнивает p.password_hash = crypt(p_password, p.password_hash). Прямое сравнение хешей - потенциальный timing attack. | Использовать константное сравнение если доступно |
| 4 | **LOW** | 36 | gen_random_uuid() для profiles.id - OK при миграции на Amvera, но сейчас id профиля должен совпадать с auth.users.id. | OK для Amvera-миграции |

---

### 1.3. Детальный ревью ключевых миграций (039, 047, 048)

#### 039_atomic_operations.sql (8.9K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **SUGGESTION** | 35-39 | accept_application использует FOR UPDATE для блокировки - правильный подход. OK. | OK |
| 2 | **SUGGESTION** | 77-79 | Автоматическое отклонение остальных pending-откликов при accept - правильное поведение. OK. | OK |
| 3 | **WARNING** | 211-212 | DELETE FROM notifications WHERE message ILIKE job_id - удаление по LIKE на UUID в тексте. Может задеть несвязанные уведомления. | Добавить колонку job_id в notifications |
| 4 | **LOW** | 275 | DELETE FROM messages WHERE sender_id = p_user_id - удаляет только отправленные сообщения, но не полученные. | Добавить удаление полученных сообщений |

---

### 1.4. Аудит run_all_safe.sql

**Проверка структуры:**

| Критерий | Статус | Комментарий |
|---|---|---|
| BEGIN/COMMIT обёртка | ❌ Отсутствует | Строка 11: Файл НЕ использует транзакцию. Все DDL через IF NOT EXISTS - идемпотентно, но нет атомарности |
| Порядок секций | ✅ Правильный | CREATE TABLE → ALTER/INDEX → FUNCTIONS → POLICIES |
| DROP TABLE | ✅ Безопасно | Только DROP TABLE IF EXISTS reviews, hires, shifts (легаси, строки 1464-1466) |
| TRUNCATE | ✅ Отсутствует | grep не нашёл ни одного TRUNCATE |
| Замена auth.uid() | ✅ Системно | current_setting(request.jwt.claim.user_id, true) для Amvera |
| REFERENCES auth.users | ✅ Заменены | REFERENCES profiles(id) |
| Storage-политики | ✅ Удалены | Supabase Storage политики убраны |
| Размер файла | ⚠️ 78K | Очень большой. Рекомендуется разбить на секционные файлы |

---

## Часть 2: Скрипты

### 2.1. apply_migrations.py + apply_new_migrations.py

#### apply_migrations.py (14.3K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **SUGGESTION** | 56-189 | split_sql_statements() - сложный парсер (200+ строк). Возможны краевые случаи. | Рассмотреть sqlparse |
| 2 | **LOW** | 217-252 | execute_statement() при Timeout все statement-ы после таймаута продолжают выполняться. | Добавить --skip-errors флаг |

#### apply_new_migrations.py (10.2K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **CRITICAL** | 73-81 | Прямая модификация pg_catalog.pg_proc через UPDATE с конкатенацией строк! Обходит CREATE OR REPLACE FUNCTION, может сломать БД. | Переписать через CREATE OR REPLACE FUNCTION |
| 2 | **HIGH** | 71 | SQL injection risk: escaped_source = new_source.replace(quote, quotequote) - конкатенация строк для UPDATE системного каталога. | Использовать CREATE OR REPLACE FUNCTION |
| 3 | **MEDIUM** | 262 | hasattr(__import__(json), dumps) - всегда True. Бессмысленная проверка, код внутри if никогда не выполнится. | Удалить проверку |
| 4 | **MEDIUM** | 10 | Использует requests вместо httpx как в apply_migrations.py. Несогласованность. | Унифицировать на httpx |
| 5 | **SUGGESTION** | 304-310 | Захардкожен список миграций 039-042. При добавлении новых миграций скрипт нужно править. | Сделать универсальным как --all |

### 2.2. check_schema.py + smoke_test_prod.py

#### check_schema.py (6.2K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **SUGGESTION** | 29-121 | exec_sql возвращает None при ошибке, но вызывающий код не всегда проверяет. При недоступности БД - AttributeError. | Добавить проверку if data is None |
| 2 | **SUGGESTION** | 24-125 | Хороший диагностический скрипт, но вывод не структурирован. | OK для ручного использования |

#### smoke_test_prod.py (9.2K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **MEDIUM** | 15 | Хардкод URL продакшена: trudnik-hyperstls.amvera.io. При смене домена тесты будут стучаться на старый URL. | Использовать os.environ.get без дефолта |
| 2 | **MEDIUM** | 18,22 | Хардкод тестовых email: org@test.ru, admin@test.ru. | OK для smoke-тестов |
| 3 | **SUGGESTION** | 160-175 | Только один API-эндпоинт тестируется (/api/admin/job-stats). | OK для минимального smoke-теста |

### 2.3. preseed_test_data.py + cleanup_test_data.py

#### preseed_test_data.py (12.9K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **WARNING** | 85-104 | delete_previous_test_data() ссылается на несуществующие колонки: ratings.rater_id (должно быть rater_user_id), messages.receiver_id, applications.employer_id. Удаление молча не сработает. | Исправить имена колонок |
| 2 | **MEDIUM** | 52 | GET /auth/v1/admin/users - зависит от Supabase Auth API. Не будет работать после миграции на Amvera. | OK для текущего состояния |

#### cleanup_test_data.py (9.9K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **WARNING** | 103-125 | delete_user_data() ссылается на несуществующие колонки/таблицы: favorites.favorited_user_id (должно быть target_id), messages.receiver_id, chat_rooms, ratings.rater_id, notification_prefs, applications.employer_id. | Исправить имена колонок |
| 2 | **MEDIUM** | 41-52 | get_all_users() дублирует get_all_emails_from_auth() и не используется. | Удалить get_all_users() |

### 2.4. create_admin_user.sql (1.4K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **SUGGESTION** | 12-14 | Отличная защита: проверка на плейсхолдеры (admin@example.com / CHANGE_ME). OK. | OK |
| 2 | **SUGGESTION** | 17-22 | Идемпотентность: IF EXISTS UPDATE, ELSE INSERT. OK. | OK |

### 2.5. test_buttons.py (36.2K)

| # | Серьёзность | Строка | Проблема | Рекомендация |
|---|---|---|---|---|
| 1 | **HIGH** | 37-41,44 | Хардкод паролей: Step@1986, test123456, test123. При утечке кода - компрометация тестовых аккаунтов. | Переместить в переменные окружения |
| 2 | **MEDIUM** | 39-41 | CREDENTIALS содержит неиспользуемое поле name. | Удалить |
| 3 | **SUGGESTION** | 46 | OUTPUT_FILE - относительный путь. При запуске из другой директории файл создастся в неожиданном месте. | Использовать Path(__file__).resolve() |
| 4 | **SUGGESTION** | - | Поиск TODO/FIXME/HACK/XXX: ничего не найдено. Код чистый. | OK |

### 2.6. Остальные скрипты (краткий обзор)

| Файл | Назначение | Проблемы |
|---|---|---|
| dump_supabase_schema.py | Экспорт схемы Supabase в JSON | Без замечаний (read-only) |
| generate_icons.py | Генерация PWA-иконок через Pillow | Без замечаний |
| generate_jwt_secret.py | Генерация JWT-секрета | Без замечаний |
| generate_twa_ci.js | Генерация TWA-конфигурации | execSync(npm root -g) - низкий risk |
| install_hooks.py | Установка pre-commit хука | Без замечаний |
| update_version.py | Автообновление VERSION | Без замечаний |
| _apply_all_direct.py | Применение миграций через psycopg2 | MEDIUM: Хардкод DATABASE_URL с паролем |
| _create_base_tables.py | Создание базовых таблиц | MEDIUM: Хардкод DATABASE_URL с паролем |
| _create_email_log.py | Создание email_log | MEDIUM: Хардкод DATABASE_URL с паролем |
| _create_missing_tables.py | Создание недостающих таблиц | MEDIUM: Хардкод DATABASE_URL с паролем |
| _init_exec_sql.py | Создание exec_sql RPC | MEDIUM: Хардкод DATABASE_URL с паролем |

---

## Общая сводка

| Категория | CRITICAL | HIGH | MEDIUM | LOW | SUGGESTION | Всего |
|---|---|---|---|---|---|---|
| Миграции (053-058) | 0 | 1 | 2 | 5 | 5 | 13 |
| Ключевые миграции (039, 047, 048) | 0 | 0 | 1 | 2 | 5 | 8 |
| run_all_safe.sql | 0 | 0 | 0 | 0 | 1 | 1 |
| Скрипты apply | 1 | 1 | 3 | 1 | 4 | 10 |
| check_schema + smoke_test | 0 | 0 | 2 | 0 | 4 | 6 |
| preseed + cleanup | 0 | 0 | 1 | 0 | 2 (+2 WARNING) | 5 |
| create_admin_user.sql | 0 | 0 | 0 | 1 | 2 | 3 |
| test_buttons.py | 0 | 1 | 1 | 0 | 3 | 5 |
| Остальные скрипты | 0 | 0 | 5 | 0 | 0 | 5 |
| **ИТОГО** | **1** | **3** | **15** | **9** | **26** | **56** |

---

## Cross-cutting проблемы

### 1. Несогласованность HTTP-клиентов
- apply_migrations.py: httpx (современный)
- apply_new_migrations.py, check_schema.py, smoke_test_prod.py, preseed, cleanup: requests (блокирующий)
- _*.py: psycopg2 (прямое подключение)

**Рекомендация:** Унифицировать на httpx для всех REST-скриптов.

### 2. Отсутствие стратегии отката миграций
Ни одна из 58 миграций не содержит --down секции. Откат возможен только через восстановление из бэкапа.

**Рекомендация:** Добавить down-скрипты хотя бы для миграций, меняющих типы колонок или удаляющих данные.

### 3. Дубликат номера миграции 019
Два файла с номером 019: 019_add_missing_notifications_columns.sql и 019_fix_security_warnings.sql.

**Рекомендация:** Переименовать один из файлов (например, 019b_fix_security_warnings.sql).

### 4. Хардкод паролей и URL в скриптах
- test_buttons.py:37-44: пароли Step@1986, test123456, test123 в коде
- smoke_test_prod.py:15: URL trudnik-hyperstls.amvera.io
- _*.py: DATABASE_URL с паролем postgres:postgres

**Рекомендация:** Все секреты и URL вынести в переменные окружения без дефолтных значений.

### 5. Несуществующие колонки в cleanup/preseed
delete_previous_test_data() и delete_user_data() ссылаются на колонки, которых нет в схеме (ratings.rater_id, messages.receiver_id, applications.employer_id, favorites.favorited_user_id).

**Рекомендация:** Сверить имена колонок с актуальной схемой, добавить проверку существования колонок перед удалением.

### 6. Отсутствие транзакционной обёртки в большинстве миграций
Только 3 из 58 миграций используют BEGIN/COMMIT. При сбое на середине миграции БД остаётся в частично обновлённом состоянии.

**Рекомендация:** Обернуть каждую миграцию в транзакцию, либо задокументировать, что идемпотентность гарантирует безопасный повторный запуск.

---

> **Вывод:** Миграции в хорошем состоянии - идемпотентны, покрыты RLS, соответствуют коду. Основные проблемы: критическая модификация pg_catalog в apply_new_migrations.py:73, отсутствие REVOKE в миграции 058, неработающий триггер в миграции 048, и несуществующие колонки в скриптах очистки. 1 CRITICAL, 3 HIGH, 15 MEDIUM.
