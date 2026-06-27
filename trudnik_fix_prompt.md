# ПРОМТ ДЛЯ ИИ-АГЕНТА: Комплексный рефакторинг проекта Trudnik

## Контекст проекта

Веб-приложение Trudnik — платформа поиска подработок верующими людьми с учётом религиозной принадлежности. Стек: Flask 3 + PostgREST (HTTP API над PostgreSQL) + Redis + uvicorn (ASGI, совмещённый с FastAPI WebSocket) + Jinja2/Tailwind CSS + Celery (заявлен, но не развёрнут в prod). Развёртывание: Amvera Cloud (https://trudnik-hyperstls.amvera.io), бесплатный тариф BEGINNER (0.25 CPU, 0.5 GB RAM). Домен админки: /admin. Приложение бесплатное, готовится к монетизации (pay-per-job + подписки для работодателей).

Рабочая директория: `/home/z/my-project/trudnik/trudnik/`. Все пути ниже указаны относительно неё.

**Твоя задача**: выполнить все исправления, описанные ниже. Каждый пункт содержит категорию критичности, описание проблемы с указанием файла:строки, конкретные шаги/код для исправления и ожидаемый результат. Приоритеты: 🔴 Критическая → 🟠 Высокая → 🟡 Средняя → 🟢 Низкая. Внутри каждой категории (бэкенд/фронтенд/UX/UI/инфраструктура) строго соблюдай порядок от критических к низким. Не пропускай критические и высокие пункты — они блокируют production.

**Жёсткие ограничения:**
1. Не включать `debug=True` в production.
2. Не коммитить секреты (пароли, токены, ключи) в репозиторий. Использовать только переменные окружения.
3. Не использовать `select=*` в PostgREST-запросах к таблице `profiles` (содержит `password_hash`, `inn`, `phone`, `email`).
4. Все пользовательские UUID из URL параметров пропускать через декоратор `@validate_uuid(...)`.
5. Не использовать `==` для сравнения токенов/паролей — только `hmac.compare_digest` или `secrets.compare_digest`.
6. Не удалять и не переписывать существующие миграции 001–074. Все новые изменения — миграция `075_audit_remediation.sql`.
7. Все DDL-изменения делать идемпотентными (`CREATE INDEX IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `DROP CONSTRAINT IF EXISTS`).
8. После внесения изменений обновить `VERSION` файл через `git add VERSION && git commit --amend --no-edit` либо новый коммит `chore: apply audit remediation`.

---

## РАЗДЕЛ 1. БЭКЕНД (Flask + PostgREST + БД)

### 🔴 КРИТИЧЕСКАЯ — 1.1. Утечка `password_hash`, `inn`, `phone`, `email` через `public_profile`

**Файл:** `app/blueprints/profile.py:266-274`

**Проблема:** Маршрут `/profile/<user_id>` публичный (нет `@login_required`) и использует `select=*` к таблице `profiles`. Любой аноним может получить bcrypt-хэш пароля, ИНН, телефон, email любого пользователя, зная его UUID. UUID утекают через списки заданий, откликов, чатов. Это полный компрометатор аккаунтов.

**Шаги:**

1. Заменить `select=*` на явный список публичных полей:
```python
PUBLIC_PROFILE_FIELDS = (
    'id,full_name,role,city,photo_url,avatar_url,bio,skills,experience,'
    'desired_payment,rating,ratings_count,total_reviews,verification_status,'
    'religion,religion_id,portfolio_link,is_self_employed,created_at'
)
resp = postgrest_request('GET', f'profiles?id=eq.{user_id}&select={PUBLIC_PROFILE_FIELDS}')
```

2. В миграции `075_audit_remediation.sql` добавить column-level GRANT:
```sql
REVOKE SELECT ON profiles FROM anon, authenticated;
GRANT SELECT (id, role, full_name, photo_url, avatar_url, age, bio, city,
              experience, desired_payment, rating, total_reviews, ratings_count,
              skills, religion, religion_id, portfolio_link, is_self_employed,
              email_public, created_at)
   ON profiles TO anon, authenticated;
```

3. Найти и заменить все остальные `select=*` (или отсутствие `select=`) к `profiles` в `app/utils/auth.py:148`, `app/blueprints/profile.py:24`, `app/blueprints/employers.py:102,124` на явные списки полей.

**Ожидаемый результат:** `password_hash`, `inn`, `phone`, `contact`, `email`, `verification_doc_url` недоступны через публичные API. Bcrypt-хэши не утекают.

---

### 🔴 КРИТИЧЕСКАЯ — 1.2. PostgREST-инъекция через `<app_id>` без валидации

**Файлы:** `app/__init__.py:316-331`, `app/blueprints/applications.py:429,579-687`

**Проблема:** Маршруты `/api/applications/<app_id>/accept|reject|reopen` принимают `app_id` из URL и интерполируют его в f-строки PostgREST-запросов (`f'applications?id=eq.{app_id}&...'`). Нет `@validate_uuid('app_id')`. Атакующий может отправить `POST /api/applications/abc%26select=password_hash,inn,phone/email%26id=eq.anything/accept` и получить чувствительные поля.

**Шаги:**

1. Импортировать `validate_uuid` из `app.decorators` в `app/__init__.py` и `app/blueprints/applications.py`.
2. Добавить декоратор ко всем маршрутам с UUID-параметрами:
```python
@app.route('/api/applications/<app_id>/accept', methods=['POST'])
@login_required
@rate_limit
@validate_uuid('app_id')
def api_accept_application(app_id):
    return api_handle_application(app_id, 'accept')
```
3. Аналогично для `/reject` и `/reopen`.
4. В `app/blueprints/applications.py:579` (cancel_application) и во всех остальных маршрутах с `<app_id>`, `<job_id>`, `<user_id>`, `<skill_id>`, `<religion_id>` — добавить `@validate_uuid(...)`.

**Ожидаемый результат:** Не-UUID значения в URL возвращают HTTP 400 до попадания в PostgREST-запрос.

---

### 🔴 КРИТИЧЕСКАЯ — 1.3. `SECRET_KEY` используется как `X-Admin-Token` для деструктивных API

**Файлы:** `app/__init__.py:210`, `app/blueprints/admin.py:717,794,839,967`

**Проблема:** Маршруты `/api/reset-users`, `/api/fix-permissions`, `/api/reset-circuit-breaker` защищены только сравнением `X-Admin-Token == SECRET_KEY`. `SECRET_KEY` — это Flask session signing key: при утечке атакующий может подделать любую сессию (включая админскую). Заголовок попадает в логи Amvera, прокси, devtools — экспоненциально расширяет поверхность утечки. `/api/reset-users` удаляет всех пользователей и создаёт тестовые аккаунты с паролем `Step@1986` (захардкожен в `admin.py:908-911`). `/api/fix-permissions` даёт роли `anon` `ALL PRIVILEGES ON ALL TABLES` — ломает RLS.

**Шаги:**

1. Ввести отдельную переменную окружения `ADMIN_API_TOKEN` (32-байта hex, `secrets.token_hex(32)`). Не использовать `SECRET_KEY`.
2. В `app/config.py` добавить:
```python
ADMIN_API_TOKEN = os.environ.get('ADMIN_API_TOKEN', '')
if os.environ.get('DEPLOYMENT_ENV') == 'production' and not ADMIN_API_TOKEN:
    raise RuntimeError('ADMIN_API_TOKEN is required in production')
```
3. В `app/blueprints/admin.py` заменить все проверки:
```python
import hmac
token = request.headers.get('X-Admin-Token', '')
expected = current_app.config.get('ADMIN_API_TOKEN', '')
if not token or not hmac.compare_digest(token, expected):
    return jsonify({'success': False, 'error': 'Unauthorized'}), 401
```
4. В `app/__init__.py:210` обновить условие bypass для `/api/reset-*` и `/api/fix-permissions`:
```python
if request.path in ('/api/reset-users', '/api/fix-permissions', '/api/reset-circuit-breaker') \
   and hmac.compare_digest(request.headers.get('X-Admin-Token', ''), app.config.get('ADMIN_API_TOKEN', '')):
    return
```
5. Полностью отключить `/api/reset-users` и `/api/fix-permissions` в production:
```python
if current_app.config.get('DEPLOYMENT_ENV') == 'production':
    return jsonify({'error': 'Endpoint disabled in production'}), 403
```
6. Удалить захардкоженный `Step@1986` из `admin.py:908-911` — генерировать случайный пароль и логировать его один раз.

**Ожидаемый результат:** Деструктивные админские API защищены отдельным токеном с constant-time сравнением и недоступны в production. Утечка `SECRET_KEY` больше не даёт полного компрометирования.

---

### 🔴 КРИТИЧЕСКАЯ — 1.4. RLS: `profiles` SELECT открывает все поля, INSERT позволяет создать admin

**Файл:** `migrations/067_bootstrap_amvera.sql:744-748`

**Проблема:** Политика `ON profiles FOR SELECT USING (true)` позволяет любому аутентифицированному читать все колонки. Политика `ON profiles FOR INSERT WITH CHECK (true)` позволяет создавать пользователя с `role='admin'`. Это привилегированная эскалация.

**Шаги:** Создать миграцию `migrations/075_audit_remediation.sql`:

```sql
BEGIN;

-- 1. Column-level GRANT (дополняет 1.1)
REVOKE SELECT ON profiles FROM anon, authenticated;
GRANT SELECT (id, role, full_name, photo_url, avatar_url, age, bio, city,
              experience, desired_payment, rating, total_reviews, ratings_count,
              skills, religion, religion_id, portfolio_link, is_self_employed,
              email_public, created_at)
   ON profiles TO anon, authenticated;

-- 2. Запретить INSERT с role='admin'
DROP POLICY IF EXISTS "Service can insert profiles" ON profiles;
CREATE POLICY "Users can insert own profile" ON profiles
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.user_id', true)::uuid = id
        AND role IN ('worker', 'employer')
    );

-- 3. SELECT только свои полные данные (email, password_hash и т.д.)
DROP POLICY IF EXISTS "Users can read profiles" ON profiles;
CREATE POLICY "Users can read own full profile" ON profiles
    FOR SELECT USING (
        current_setting('request.jwt.claim.user_id', true)::uuid = id
        OR role IN ('worker', 'employer')  -- публичные поля других читаем через column-level GRANT
    );

COMMIT;
```

**Ожидаемый результат:** Анонимные и обычные пользователи не могут читать `password_hash`, `inn`, `phone`, `email`. Невозможно создать аккаунт с `role='admin'` через RPC `register_user`.

---

### 🔴 КРИТИЧЕСКАЯ — 1.5. `register_user` RPC принимает `role='admin'`

**Файл:** `migrations/067_bootstrap_amvera.sql:1091-1105` (сигнатура: `(p_email, p_password, p_full_name, p_role)`) и `migrations/manual_fix_all.sql:80` (другая сигнатура: `(p_email, p_password, p_role, p_full_name)`)

**Проблема:** Сигнатуры не совпадают между 067 и `manual_fix_all.sql`. RPC не проверяет `p_role IN ('worker','employer')` — атакующий может передать `'admin'`. GRANT даёт `anon` право вызова.

**Шаги:** В `075_audit_remediation.sql`:

```sql
-- Унифицировать сигнатуру (067 порядок: email, password, full_name, role)
DROP FUNCTION IF EXISTS public.register_user(text, text, text, text);
CREATE OR REPLACE FUNCTION public.register_user(
    p_email text, p_password text, p_full_name text, p_role text DEFAULT 'worker'
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE v_user_id uuid;
BEGIN
    IF p_role NOT IN ('worker', 'employer') THEN
        RAISE EXCEPTION 'invalid_role';
    END IF;
    IF EXISTS (SELECT 1 FROM public.profiles WHERE email = p_email) THEN
        RAISE EXCEPTION 'email_exists';
    END IF;
    INSERT INTO public.profiles (id, email, password_hash, full_name, role)
    VALUES (gen_random_uuid(), p_email, crypt(p_password, gen_salt('bf', 12)), p_full_name, p_role)
    RETURNING id INTO v_user_id;
    RETURN v_user_id;
END;
$$;
REVOKE EXECUTE ON FUNCTION public.register_user(text, text, text, text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.register_user(text, text, text, text) TO anon, authenticated, service_role;
```

Также проверить `app/blueprints/auth.py:287-292` — убедиться, что Flask вызывает RPC с правильным порядком аргументов (email, password, full_name, role).

**Ожидаемый результат:** Невозможно создать admin-аккаунт через `register_user`. Сигнатура унифицирована.

---

### 🔴 КРИТИЧЕСКАЯ — 1.6. `delete_job_cascade` и `delete_user_cascade` GRANTed to `authenticated`

**Файл:** `migrations/067_bootstrap_amvera.sql:2228-2232`, `migrations/069_fix_rpc_security_gaps.sql:898-903`

**Проблема:** Любой аутентифицированный пользователь может вызвать `delete_job_cascade(any_job_id)` и `delete_user_cascade(any_user_id)`. Внутри функций нет проверки владельца. Это потеря данных.

**Шаги:** В `075_audit_remediation.sql`:

```sql
REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid)  FROM authenticated;
REVOKE EXECUTE ON FUNCTION public.delete_user_cascade(uuid) FROM authenticated;
GRANT  EXECUTE ON FUNCTION public.delete_job_cascade(uuid)  TO service_role;
GRANT  EXECUTE ON FUNCTION public.delete_user_cascade(uuid) TO service_role;
```

Также внутри функций добавить проверку (для `delete_job_cascade`):
```sql
IF NOT EXISTS (
    SELECT 1 FROM public.jobs
    WHERE id = p_job_id
      AND employer_id = current_setting('request.jwt.claim.user_id', true)::uuid
) AND current_setting('request.jwt.claim.role', true) NOT IN ('admin', 'service_role') THEN
    RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
END IF;
```

**Ожидаемый результат:** Обычные пользователи не могут удалять чужие задания/профили.

---

### 🔴 КРИТИЧЕСКАЯ — 1.7. `apply_job_atomic` двойной инкремент `current_workers`

**Файл:** `migrations/069_fix_rpc_security_gaps.sql:300-383`

**Проблема:** Версия 069 инкрементирует `current_workers` при подаче заявки (status='pending'). Затем `accept_application` (069:72-75) инкрементирует снова при accept. Для `max_workers=3` после 3 PENDING заявок `current_workers=3` и `accept_application` отказывает. Рынок заданий мёртв.

**Шаги:** В `075_audit_remediation.sql` переписать `apply_job_atomic` без инкремента:

```sql
CREATE OR REPLACE FUNCTION public.apply_job_atomic(
    p_job_id uuid, p_worker_id uuid
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_max_workers int; v_current_workers int; v_status text; v_employer_id uuid;
    v_app_id uuid;
BEGIN
    SELECT max_workers, current_workers, status, employer_id
      INTO v_max_workers, v_current_workers, v_status, v_employer_id
      FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;
    IF v_status NOT IN ('open', 'active') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание недоступно для отклика', 'code', 'job_not_open');
    END IF;
    IF v_employer_id = p_worker_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'own job', 'code', 'own_job');
    END IF;
    IF EXISTS (SELECT 1 FROM public.blacklists
               WHERE user_id = v_employer_id AND blocked_user_id = p_worker_id) THEN
        RETURN jsonb_build_object('success', false, 'error', 'blacklisted', 'code', 'blacklisted');
    END IF;

    INSERT INTO public.applications (job_id, worker_id, status)
    VALUES (p_job_id, p_worker_id, 'pending')
    RETURNING id INTO v_app_id;

    RETURN jsonb_build_object('success', true, 'application_id', v_app_id, 'employer_id', v_employer_id);
EXCEPTION WHEN unique_violation THEN
    RETURN jsonb_build_object('success', false, 'error', 'duplicate', 'code', 'duplicate');
END;
$$;
REVOKE EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO authenticated, service_role;
```

**Ожидаемый результат:** `current_workers` инкрементируется только при `accept_application`. Работодатели могут принимать отклики.

---

### 🔴 КРИТИЧЕСКАЯ — 1.8. `jobs.status` CHECK-конструкция не содержит статусы, используемые RPC

**Файл:** `migrations/067_bootstrap_amvera.sql:211-212`

**Проблема:** Constraint разрешает только `('open','completed','cancelled')`. RPC пишут `'active'` (069:373), `'in_progress'` (067:1844-1862). На runtime — `ERROR: new row for relation "jobs" violates check constraint "jobs_status_check"`.

**Шаги:** В `075_audit_remediation.sql`:

```sql
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('draft','open','active','in_progress','completed','cancelled','paid','expired'));
```

**Ожидаемый результат:** RPC могут писать все статусы из state-machine без ошибок.

---

### 🔴 КРИТИЧЕСКАЯ — 1.9. `accept_application` / `reject_application` без проверки владельца

**Файл:** `migrations/069_fix_rpc_security_gaps.sql:28-179`

**Проблема:** RPC `accept_application(p_job_id, p_app_id)` не проверяет, что caller является `employer_id` задания. GRANT даёт `authenticated` право вызова. Любой работник может «принять» чужой отклик.

**Шаги:** В `075_audit_remediation.sql` переписать с проверкой владельца в начале функции:

```sql
CREATE OR REPLACE FUNCTION public.accept_application(p_job_id uuid, p_app_id uuid)
RETURNS json LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_current_workers int; v_max_workers int; v_job_status text;
    v_new_count int; v_new_status text; v_employer_id uuid;
BEGIN
    SELECT current_workers, max_workers, status, employer_id
      INTO v_current_workers, v_max_workers, v_job_status, v_employer_id
      FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.role', true) NOT IN ('admin', 'service_role') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;
    IF v_job_status != 'open' THEN
        RETURN json_build_object('success', false, 'error', 'Задание закрыто для принятия');
    END IF;
    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object('success', false, 'error', 'Все места заняты');
    END IF;

    v_new_count := v_current_workers + 1;
    v_new_status := CASE WHEN v_new_count >= v_max_workers THEN 'completed' ELSE 'open' END;

    UPDATE public.jobs SET status = v_new_status, current_workers = v_new_count
    WHERE id = p_job_id;

    UPDATE public.applications SET status = 'accepted'
    WHERE id = p_app_id AND job_id = p_job_id AND status IN ('pending', 'rejected');

    IF NOT FOUND THEN
        UPDATE public.jobs SET status = v_job_status, current_workers = v_current_workers
        WHERE id = p_job_id;
        RETURN json_build_object('success', false, 'error', 'Отклик не найден или уже обработан');
    END IF;

    UPDATE public.applications SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending' AND id != p_app_id;

    RETURN json_build_object('success', true, 'current_workers', v_new_count, 'job_status', v_new_status);
END;
$$;
```

Аналогично для `reject_application`.

**Ожидаемый результат:** Только владелец задания (или admin) может принимать/отклонять отклики.

---

### 🔴 КРИТИЧЕСКАЯ — 1.10. `messages` INSERT позволяет писать в любой `application_id`

**Файл:** `migrations/067_bootstrap_amvera.sql:835-838`

**Проблема:** Политика проверяет только `sender_id = current_user`, но не проверяет, что sender участвует в application. Любой может отправить сообщение в любой чат.

**Шаги:** В `075_audit_remediation.sql`:

```sql
DROP POLICY IF EXISTS "Application participants can insert messages" ON messages;
CREATE POLICY "Application participants can insert messages" ON messages
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.user_id', true)::uuid = sender_id
        AND EXISTS (
            SELECT 1 FROM applications a
            WHERE a.id = messages.application_id
              AND (a.worker_id = sender_id
                   OR EXISTS (SELECT 1 FROM jobs j
                              WHERE j.id = a.job_id AND j.employer_id = sender_id))
        )
    );
```

**Ожидаемый результат:** Сообщения могут отправлять только участники application.

---

### 🔴 КРИТИЧЕСКАЯ — 1.11. `notifications` и `email_log` INSERT открыты для всех

**Файл:** `migrations/067_bootstrap_amvera.sql:845-846, 1051-1052`

**Проблема:** Политики `WITH CHECK (true)` позволяют любому вставлять записи от имени любого user_id.

**Шаги:** В `075_audit_remediation.sql`:

```sql
DROP POLICY IF EXISTS "Service can insert notifications" ON notifications;
CREATE POLICY "Service can insert notifications" ON notifications
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');

DROP POLICY IF EXISTS "Service can insert email logs" ON email_log;
CREATE POLICY "Service can insert email logs" ON email_log
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
```

Убедиться, что `app/utils/postgrest_client.py:postgrest_admin_request` использует JWT с `role='service_role'` (или `'trudnikapp'` с наследованием `service_role`).

**Ожидаемый результат:** Только service-role может создавать уведомления и email-логи.

---

### 🟠 ВЫСОКАЯ — 1.12. Bcrypt rounds = 6 (OWASP требует ≥12)

**Файлы:** `app/utils/auth.py:20` (`BCRYPT_ROUNDS = 6`), `migrations/067_bootstrap_amvera.sql:1101,1118` (`gen_salt('bf')` без второго аргумента = 6 rounds)

**Проблема:** 6 rounds ≈ 64 итерации — на современной GPU брутфорс идёт миллиарды хэшей/сек. При утечке БД пароли вскрываются за часы.

**Шаги:**

1. В `app/utils/auth.py:20` изменить `BCRYPT_ROUNDS = 12`.
2. В `075_audit_remediation.sql` обновить `register_user`, `change_password`, `login_user` (migration 067 строки 1078, 1091, 1108) на `gen_salt('bf', 12)`.
3. Добавить миграцию для rehash-on-login: при успешном входе, если `password_hash` начинается с `$2a$06$` или `$2b$06$`, перехэшировать пароль с rounds=12 и UPDATE.

```sql
-- Внутри login_user RPC после успешной проверки:
IF substring(p.password_hash from 1 for 7) IN ('$2a$06$', '$2b$06$', '$2y$06$') THEN
    UPDATE public.profiles SET password_hash = crypt(p_password, gen_salt('bf', 12))
    WHERE id = v_user_id;
END IF;
```

**Ожидаемый результат:** Новые пароли хэшируются с rounds=12. Старые автоматически перешифруются при следующем входе.

---

### 🟠 ВЫСОКАЯ — 1.13. `/login` и `/register` без CSRF (login CSRF)

**Файл:** `app/__init__.py:204`

**Проблема:** Оба маршрута исключены из CSRF-проверки. Login CSRF позволяет атакующему подставить свои credentials жертве и собирать действия жертвы в аккаунте атакующего.

**Шаги:**

1. В `templates/login.html` и `templates/register.html` добавить скрытое поле:
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
```
2. Удалить из `app/__init__.py:204` строку `if request.path in ('/login', '/register'): return`.
3. Убедиться, что JS-автоинъекция в `base.html:1192-1209` покрывает и эти формы.

**Ожидаемый результат:** Login/register защищены CSRF-токеном.

---

### 🟠 ВЫСОКАЯ — 1.14. `/profile/delete-photo` без CSRF

**Файлы:** `app/__init__.py:207`, `templates/profile.html` (или соответствующий JS)

**Шаги:**

1. Удалить из `app/__init__.py:207` строку bypass.
2. В JS, который вызывает `fetch('/profile/delete-photo', ...)`, добавить заголовок `X-CSRF-Token` (патч в `base.html:1211-1224` уже делает это глобально для fetch — убедиться, что он срабатывает).

**Ожидаемый результат:** Удаление фото защищено CSRF.

---

### 🟠 ВЫСОКАЯ — 1.15. `login_required` проглатывает ошибки JWT decode

**Файл:** `app/decorators.py:36-48`

**Проблема:** При ошибке `jwt.DecodeError`/`ExpiredSignatureError`/`InvalidTokenError` декоратор `pass`-ит и выполняет view. Атакующий с подделанным JWT попадает в view.

**Шаги:** Заменить `pass` на:
```python
except (jwt.DecodeError, jwt.ExpiredSignatureError, jwt.InvalidTokenError):
    session.clear()
    return redirect(url_for('auth.login'))
```

**Ожидаемый результат:** Невалидный JWT → logout + redirect на /login.

---

### 🟠 ВЫСОКАЯ — 1.16. `admin_required` не перечитывает role из БД

**Файл:** `app/decorators.py:105-116`

**Проблема:** Доверяет `session['role']`. Если админа понизили в БД, он сохраняет админский доступ до разлогина. Сравнить с `role_required` (`decorators.py:54-87`), который каждый раз делает запрос в PostgREST.

**Шаги:** Добавить DB-перепроверку (как в `role_required`):
```python
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('auth.login'))
        # Перечитать роль из БД
        try:
            resp = postgrest_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
            data = resp.json() if resp.ok else []
            live_role = data[0].get('role') if data else None
        except Exception:
            live_role = None
        if live_role != 'admin':
            session.clear()
            flash('Доступ запрещён. Требуются права администратора.', 'error')
            return redirect(url_for('jobs.index'))
        session['role'] = 'admin'  # обновить кэш
        return f(*args, **kwargs)
    return decorated_function
```

**Ожидаемый результат:** При понижении роли в БД админский доступ мгновенно отзывается.

---

### 🟠 ВЫСОКАЯ — 1.17. Rate limit на /login слабый, fail-open, без per-account lockout

**Файлы:** `app/decorators.py:209-256`, `app/utils/rate_limit.py`

**Проблема:** Limit 10/min per-IP. Атакующий с 10 000 IP = 14M попыток/день. При падении Redis лимит полностью отключается (`return f(*args, **kwargs)`). `request.remote_addr` unreliable без `ProxyFix`.

**Шаги:**

1. В `app/__init__.py` добавить `werkzeug.middleware.proxy_fix.ProxyFix`:
```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
```
2. В `app/blueprints/auth.py` перед вызовом `login_user` добавить per-account lockout:
```python
from app.utils.redis_client import get_redis_client
email_key = f"auth:fail:{email.lower()}"
r = get_redis_client()
if r is not None:
    fails = int(r.get(email_key) or 0)
    if fails >= 5:
        ttl = r.ttl(email_key)
        flash(f'Слишком много попыток. Попробуйте через {ttl//60+1} мин.', 'danger')
        return redirect(url_for('auth.login'))
```
3. При неудачном входе инкрементировать счётчик с TTL 15 мин:
```python
if r is not None:
    pipe = r.pipeline()
    pipe.incr(email_key)
    pipe.expire(email_key, 900)  # 15 минут
    pipe.execute()
```
4. При успешном входе — `r.delete(email_key)`.
5. В `app/decorators.py:237-238` для `/login` и `/register` сделать fail-closed:
```python
if redis_client is None and request.path in ('/login', '/register'):
    abort(503, description='Сервис аутентификации временно недоступен')
```

**Ожидаемый результат:** 5 неудачных попыток на email → блокировка 15 мин. Redis-падение не отключает защиту login.

---

### 🟠 ВЫСОКАЯ — 1.18. JWT role захардкожен на `'trudnikapp'` (RLS bypassed)

**Файлы:** `app/utils/auth.py:115-122`, `app/utils/postgrest_client.py:293-317,332-343`

**Проблема:** При refresh и при каждом `postgrest_request` JWT mint-ится с `role='trudnikapp'`. Это значит, что RLS-политики, проверяющие `request.jwt.claim.role IN ('worker','employer','admin')`, **не работают** после первого refresh. Защита держится только на WHERE-условиях приложения.

**Шаги:**

1. Сохранить реальную роль пользователя в сессии (уже есть `session['role']`).
2. В `app/utils/auth.py:refresh_access_token` использовать роль из сессии:
```python
def refresh_access_token() -> bool:
    user_id = session.get('user_id')
    role = session.get('role', 'authenticated')
    if not user_id:
        return False
    token = generate_jwt(user_id, role)
    session['access_token'] = token
    return True
```
3. В `app/utils/postgrest_client.py:get_user_headers` использовать реальную роль:
```python
def get_user_headers(user_id=None):
    from flask import session
    role = session.get('role', 'authenticated') if not user_id else \
           session.get('role', 'authenticated')
    token = generate_jwt(str(user_id) if user_id else '', role)
    return {'Authorization': f'Bearer {token}', ...}
```
4. Убедиться, что `trudnikapp` имеет GRANT на необходимые таблицы (либо использовать `authenticated`).

**Ожидаемый результат:** RLS-политики работают с реальными ролями пользователей.

---

### 🟠 ВЫСОКАЯ — 1.19. Fake refresh token — сессии бесконечно обновляются

**Файлы:** `app/blueprints/auth.py:58` (`session['refresh_token'] = 'jwt'`), `app/utils/auth.py:101-125`

**Проблема:** `refresh_token` — это просто маркер `'jwt'`. Пока Flask-сессия жива, приложение mint-ит новый JWT на каждый запрос. Logout не инвалидирует уже выданные JWT (нет jti blacklist).

**Шаги:**

1. Уменьшить `exp_seconds` в `generate_jwt` с 3600 до 300 (5 минут).
2. Реализовать jti blacklist в Redis:
```python
# В login:
jti = secrets.token_hex(16)
session['jti'] = jti
# Добавить jti в множество активных сессий пользователя
r.sadd(f"sessions:{user_id}", jti)

# В logout:
r.srem(f"sessions:{user_id}", session.get('jti'))
session.clear()

# В login_required перед выполнением view:
if not r.sismember(f"sessions:{user_id}", decoded.get('jti')):
    session.clear()
    return redirect(url_for('auth.login'))
```
3. В `change_password` сбрасывать все сессии пользователя:
```python
r.delete(f"sessions:{user_id}")
```

**Ожидаемый результат:** Logout реально отзывает доступ. Украденный JWT валиден максимум 5 минут.

---

### 🟠 ВЫСОКАЯ — 1.20. `update_user_role` и `update_job_status` в admin используют user JWT (RLS может блокировать)

**Файл:** `app/blueprints/admin.py:183, 222`

**Проблема:** Используется `postgrest_request` (JWT текущего админа) вместо `postgrest_admin_request` (service_role). RLS может молча блокировать.

**Шаги:** Заменить `postgrest_request` на `postgrest_admin_request` в строках 183 и 222.

**Ожидаемый результат:** Админские операции гарантированно проходят RLS.

---

### 🟠 ВЫСОКАЯ — 1.21. `cancel_application` fallback без проверки владельца

**Файл:** `app/blueprints/applications.py:579-687`

**Проблема:** Если RPC `cancel_worker_atomic` недоступен, fallback-логика делает PATCH к `jobs` и `applications` без проверки, что caller — владелец задания. Любой работник может «отменить» чужой accept.

**Шаги:** Перед RPC добавить ownership check:
```python
# Проверить, что caller — владелец задания
job_resp = postgrest_request('GET', f'jobs?id=eq.{job_id}&select=employer_id')
if not job_resp.ok or not job_resp.json():
    flash('Задание не найдено', 'danger')
    return redirect(url_for('applications.my_applications'))
if job_resp.json()[0]['employer_id'] != session.get('user_id'):
    flash('Нет доступа', 'danger')
    return redirect(url_for('applications.my_applications'))
```

**Ожидаемый результат:** Только владелец задания может отменять принятые отклики.

---

### 🟠 ВЫСОКАЯ — 1.22. `restore_job` не атомарный (4 отдельных HTTP-запроса)

**Файл:** `app/blueprints/jobs.py:669-719`

**Проблема:** 4 PATCH-запроса к PostgREST. Race condition, partial failure, TOCTOU. Сравнить с `cancel_job` и `force_complete_job`, которые используют атомарные RPC.

**Шаги:** Создать RPC `restore_job_atomic` в `075_audit_remediation.sql`:

```sql
CREATE OR REPLACE FUNCTION public.restore_job_atomic(p_job_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid; v_status text; v_count int;
BEGIN
    SELECT employer_id, status INTO v_employer_id, v_status
    FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено');
    END IF;
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid THEN
        RETURN jsonb_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF
    IF v_status != 'cancelled' THEN
        RETURN jsonb_build_object('success', false, 'error', 'Восстановить можно только отменённое задание');
    END IF;

    UPDATE public.applications SET status = 'rejected'
    WHERE job_id = p_job_id AND status IN ('pending', 'accepted');

    UPDATE public.jobs SET status = 'open', current_workers = 0
    WHERE id = p_job_id;

    RETURN jsonb_build_object('success', true);
END;
$$;
REVOKE EXECUTE ON FUNCTION public.restore_job_atomic(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.restore_job_atomic(uuid) TO authenticated, service_role;
```

В `app/blueprints/jobs.py:669` заменить тело на вызов RPC `restore_job_atomic`.

**Ожидаемый результат:** Восстановление задания атомарно.

---

### 🟠 ВЫСОКАЯ — 1.23. Валидация диапазонов в `job_new` и `edit_job`

**Файл:** `app/blueprints/jobs.py:480-489, 891-901`

**Проблема:** Нет range-чеков на `payment_amount`, `max_workers`, `lat`, `lng`. Можно создать задание с `payment=-1000`, `max_workers=0` или `lat=999`.

**Шаги:** В `job_new` после чтения формы:
```python
try:
    payment = float(request.form.get('payment') or 0)
    if not (0 <= payment <= 1_000_000):
        flash('Оплата должна быть от 0 до 1 000 000 ₽', 'danger')
        return redirect(url_for('jobs.job_new'))
    max_workers = int(request.form.get('max_workers') or 1)
    if not (1 <= max_workers <= 100):
        flash('Число работников должно быть от 1 до 100', 'danger')
        return redirect(url_for('jobs.job_new'))
    lat = float(request.form.get('latitude') or Config.DEFAULT_LAT)
    lng = float(request.form.get('longitude') or Config.DEFAULT_LNG)
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        flash('Некорректные координаты', 'danger')
        return redirect(url_for('jobs.job_new'))
except (ValueError, TypeError):
    flash('Некорректные числовые значения', 'danger')
    return redirect(url_for('jobs.job_new'))
```

В `edit_job` дополнительно:
```python
new_max = int(request.form.get('max_workers', job.get('max_workers', 1)))
if not (1 <= new_max <= 100):
    flash('Число работников должно быть от 1 до 100', 'danger'); return redirect(...)
if new_max < job.get('current_workers', 0):
    flash(f'Нельзя установить max_workers меньше текущего числа принятых ({job["current_workers"]})', 'danger')
    return redirect(...)
```

Также в `075_audit_remediation.sql`:
```sql
ALTER TABLE jobs ADD CONSTRAINT jobs_payment_amount_check CHECK (payment_amount IS NULL OR payment_amount >= 0);
```

**Ожидаемый результат:** Некорректные данные отвергаются на app-уровне и в БД.

---

### 🟠 ВЫСОКАЯ — 1.24. MIME-валидация загружаемых аватаров

**Файл:** `app/blueprints/profile.py:87-109` (avatar), `app/blueprints/profile.py:241-258` (verify_employer)

**Проблема:** Проверяется только расширение файла (`ext in ALLOWED_PHOTO_EXTENSIONS`). `photo.content_type` легко подделать. Можно загрузить polyglot JPEG/HTML для XSS или PHP-Shell.

**Шаги:** Использовать функцию `upload_photo` из `app/services/storage_service.py:124-158`, которая валидирует MIME через `python-magic`:

```python
from app.services.storage_service import upload_photo
try:
    photo_url = upload_photo('avatars', f'{user_id}/{uuid.uuid4().hex}_{safe_name}', photo_data, allowed_types=('image/jpeg','image/png','image/webp'))
except ValueError as e:
    flash(str(e), 'danger')
    return redirect(url_for('profile.profile'))
```

Дополнительно в `app/__init__.py:uploaded_file` (route `/uploads/<path:filename>`) добавить:
```python
response.headers['Content-Disposition'] = 'inline'
response.headers['X-Content-Type-Options'] = 'nosniff'
# Запретить исполнение скриптов в uploads
response.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self'"
```

**Ожидаемый результат:** Загрузка polyglot-файлов невозможна. MIME-тип проверяется по magic bytes.

---

### 🟠 ВЫСОКАЯ — 1.25. `applications.my_applications` — пагинация ломается при фильтре по навыкам

**Файл:** `app/blueprints/applications.py:376-415`

**Проблема:** `total` берётся из `Content-Range` (без фильтра), а `applications` фильтруется по навыкам уже после пагинации. При `per_page=20` и 5 совпадениях пользователь видит 5 строк, но пагинация говорит «страница 1 из 5». На странице 2 — 0 результатов.

**Шаги:** Перенести фильтр по навыкам в PostgREST-запрос. Сначала получить список `worker_id` с нужными навыками, затем использовать `worker_id=in.(...)`:

```python
if skills_filter:
    # 1. Найти всех работников с ВСЕМИ выбранными навыками (AND)
    skill_ids = [sanitize_postgrest(s) for s in selected_skills]
    # Через RPC или PostgREST: SELECT user_id FROM user_skills WHERE skill_id IN (...) GROUP BY user_id HAVING COUNT(DISTINCT skill_id) = N
    skills_resp = postgrest_request('GET',
        f'user_skills?skill_id=in.({",".join(skill_ids)})&select=user_id&order=user_id')
    if skills_resp.ok:
        from collections import Counter
        counter = Counter(row['user_id'] for row in skills_resp.json())
        matching_workers = [uid for uid, cnt in counter.items() if cnt == len(skill_ids)]
        if not matching_workers:
            applications, total = [], 0
        else:
            worker_filter = f'&worker_id=in.({",".join(matching_workers)})'
            # ... добавить worker_filter в основной запрос
```

**Ожидаемый результат:** Пагинация корректна при активном фильтре по навыкам.

---

### 🟠 ВЫСОКАЯ — 1.26. `monetization` — комментарий про «только оплаченные задания» не соответствует коду

**Файл:** `app/blueprints/jobs.py:128-129`

**Проблема:** Комментарий гласит «Запрос только оплаченных открытых заданий», но фильтра `is_paid=eq.true` НЕТ. Монетизация не enforced.

**Шаги:**

1. Если монетизация включена (env `MONETIZATION_ENABLED=true`):
```python
if current_app.config.get('MONETIZATION_ENABLED'):
    query += '&is_paid=eq.true'
```
2. Добавить в `app/config.py`:
```python
MONETIZATION_ENABLED = os.environ.get('MONETIZATION_ENABLED', 'false').lower() in ('true', '1', 'yes')
```
3. Создать middleware для проверки `is_paid` в `apply_job_atomic` (опционально, если платный отклик).

**Ожидаемый результат:** При включении монетизации неоплаченные задания не показываются.

---

### 🟠 ВЫСОКАЯ — 1.27. `delete_job_cascade` использует `ILIKE '%uuid%'` вместо FK

**Файл:** `migrations/069_fix_rpc_security_gaps.sql:220`

**Проблема:** `DELETE FROM notifications WHERE message ILIKE '%' || p_job_id::text || '%'` — O(N) скан, false positives. Колонка `notifications.job_id` существует и проиндексирована.

**Шаги:** В `075_audit_remediation.sql` заменить тело `delete_job_cascade`:
```sql
CREATE OR REPLACE FUNCTION public.delete_job_cascade(p_job_id uuid)
RETURNS json LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE v_deleted int;
BEGIN
    DELETE FROM public.notifications WHERE job_id = p_job_id;
    DELETE FROM public.jobs WHERE id = p_job_id;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    IF v_deleted = 0 THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;
    RETURN json_build_object('success', true, 'message', 'Задание удалено');
END;
$$;
REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO service_role;
```

**Ожидаемый результат:** Удаление использует индекс, без false positives.

---

### 🟡 СРЕДНЯЯ — 1.28. `session.permanent` не установлен — `PERMANENT_SESSION_LIFETIME` игнорируется

**Файлы:** `app/config.py:107`, `app/blueprints/auth.py:55-62`

**Шаги:** В `_login_user_session`:
```python
session.permanent = True
session.clear()  # session fixation protection
session['access_token'] = _generate_jwt(user_id, role)
session['user_id'] = user_id
session['role'] = role
session['email'] = email
session['_csrf_token'] = secrets.token_hex(32)  # rotate CSRF token
session.modified = True
```

**Ожидаемый результат:** Сессия живёт 30 минут, затем автоматически разлогинивает.

---

### 🟡 СРЕДНЯЯ — 1.29. Logout через GET (CSRF-able)

**Файл:** `app/blueprints/auth.py:363`

**Шаги:**
1. Изменить на `@auth_bp.route('/logout', methods=['POST'])`.
2. В `templates/base.html` заменить `<a href="/logout">` на форму:
```html
<form method="POST" action="/logout" class="inline">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <button type="submit" class="...">Выйти</button>
</form>
```

**Ожидаемый результат:** Logout защищён от CSRF.

---

### 🟡 СРЕДНЯЯ — 1.30. Нет flow «забыл пароль»

**Шаги:** Создать маршруты:
- `POST /password-reset/request` — принимает email, генерирует `secrets.token_urlsafe(32)`, сохраняет в Redis `reset_token:{token} = user_id` с TTL 1 час, отправляет email со ссылкой.
- `GET /password-reset/confirm?token=...` — проверяет токен, показывает форму нового пароля.
- `POST /password-reset/confirm` — устанавливает новый пароль, инвалидирует все сессии (`r.delete(f"sessions:{user_id}")`), помечает токен использованным.
- Rate-limit: 3 запроса на email/час, 10 на IP/час.
- Email-enumeration: всегда показывать «Если email зарегистрирован, ссылка отправлена».

**Ожидаемый результат:** Пользователь может восстановить пароль без обращения в support.

---

### 🟡 СРЕДНЯЯ — 1.31. INN без проверки контрольной суммы

**Файл:** `app/blueprints/auth.py:280-283`

**Шаги:** Добавить функцию `validate_inn_checksum(inn: str) -> bool` в `app/utils/validators.py`, реализующую алгоритм ФНС (мод 11 с весовыми коэффициентами для 12-значного ИНН физических лиц). Использовать в `auth.py:280`.

**Ожидаемый результат:** Поддельные ИНН отвергаются.

---

### 🟡 СРЕДНЯЯ — 1.32. Уведомления не транзакционные с действием

**Файлы:** `app/blueprints/applications.py:70-81,466-471,495-500`, `app/blueprints/jobs.py:654-661,706-713,751-758`, `app/blueprints/chat.py:143-146`, `app/services/notification_service.py:76-227`

**Проблема:** `notify()` вызывается AFTER DB-мутации в отдельном потоке. Если поток падает — уведомление потеряно. `notification_service.create` имеет 6 независимых точек отказа.

**Шаги:** Внедрить transactional outbox:

1. Создать таблицу `notification_outbox`:
```sql
CREATE TABLE notification_outbox (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX idx_outbox_unprocessed ON notification_outbox (id) WHERE processed_at IS NULL;
```
2. В каждом RPC (apply_job_atomic, accept_application и т.д.) вставлять запись в `notification_outbox` в той же транзакции.
3. Celery beat таска `process_notification_outbox` каждые 5 секунд: читает непрочитанные записи, диспатчит в `notification_service.create`, Redis pub/sub, email, push, помечает `processed_at`.

**Ожидаемый результат:** At-least-once доставка уведомлений. Потерянные сообщения восстанавливаются.

---

### 🟡 СРЕДНЯЯ — 1.33. `copy_job` теряет `is_paid`/`tariff`

**Файл:** `app/utils/business.py:7-32`

**Шаги:** Добавить поля в возвращаемый dict:
```python
'is_paid': False,  # копия всегда неоплаченная
'tariff': original_job.get('tariff', 'basic'),
```

**Ожидаемый результат:** Копия задания создаётся с правильным тарифом, но требует оплаты.

---

### 🟡 СРЕДНЯЯ — 1.34. Не хватает CHECK-конструкций в БД

**Шаги:** В `075_audit_remediation.sql`:
```sql
ALTER TABLE profiles      ADD CONSTRAINT profiles_role_check CHECK (role IN ('worker','employer','admin'));
ALTER TABLE profiles      ADD CONSTRAINT profiles_email_check CHECK (email IS NULL OR email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');
ALTER TABLE profiles      ADD CONSTRAINT profiles_age_check  CHECK (age IS NULL OR (age >= 18 AND age <= 100));
ALTER TABLE profiles      ADD CONSTRAINT profiles_inn_check  CHECK (inn IS NULL OR inn = '' OR inn ~ '^[0-9]{10,12}$');
ALTER TABLE job_payments  ADD CONSTRAINT job_payments_amount_check CHECK (amount >= 0);
ALTER TABLE receipts      ADD CONSTRAINT receipts_amount_check CHECK (amount >= 0);
```

**Ожидаемый результат:** БД отвергает невалидные данные на уровне схемы.

---

### 🟡 СРЕДНЯЯ — 1.35. Нет пространственного индекса для `nearby_jobs`

**Файл:** `migrations/067_bootstrap_amvera.sql:1497-1531`

**Шаги:** В `075_audit_remediation.sql`:
```sql
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS geom geography(POINT, 4326);
UPDATE jobs SET geom = ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography
WHERE lat IS NOT NULL AND lng IS NOT NULL AND geom IS NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_geom ON jobs USING GIST(geom);

CREATE OR REPLACE FUNCTION jobs_geom_update() RETURNS trigger AS $$
BEGIN
    IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
        NEW.geom := ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326)::geography;
    ELSE
        NEW.geom := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_jobs_geom ON jobs;
CREATE TRIGGER trg_jobs_geom BEFORE INSERT OR UPDATE OF lat, lng ON jobs
    FOR EACH ROW EXECUTE FUNCTION jobs_geom_update();

CREATE OR REPLACE FUNCTION public.nearby_jobs(
    lat double precision, lng double precision, radius_km double precision DEFAULT 50
) RETURNS SETOF jobs
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE _point geography := ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography;
BEGIN
    RETURN QUERY
    SELECT * FROM public.jobs
    WHERE status = 'open' AND geom IS NOT NULL
      AND ST_DWithin(geom, _point, radius_km * 1000)
    ORDER BY ST_Distance(geom, _point);
END;
$$;
```

**Ожидаемый результат:** `nearby_jobs` использует GiST-индекс, масштабируется до 100K+ заданий.

---

### 🟡 СРЕДНЯЯ — 1.36. Индексы для `jobs.created_at`, `jobs.city`, `jobs.date_time`

**Шаги:** В `075_audit_remediation.sql`:
```sql
CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON jobs (status, created_at DESC) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_jobs_city ON jobs (city) WHERE city IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_date_time ON jobs (date_time) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_applications_job_status ON applications (job_id, status);
```

**Ожидаемый результат:** Сортировка и фильтрация по умолчанию использует индексы.

---

### 🟡 СРЕДНЯЯ — 1.37. `print('DIAG ...')` в production-коде admin.py

**Файл:** `app/blueprints/admin.py:351,355,367,510,514,536`

**Шаги:** Заменить все `print('DIAG ...')` на `current_app.logger.debug(...)`.

**Ожидаемый результат:** В stdout нет debug-вывода.

---

### 🟡 СРЕДНЯЯ — 1.38. `tab='dictionaries'` и `tab='stats'` — orphan tabs

**Файлы:** `app/blueprints/admin.py:370,539`, `templates/admin.html:36-43,79`

**Шаги:**
1. Заменить `tab='dictionaries'` на `tab='skills'` (или `tab='religions'`) в `add_skill` и `add_religion`.
2. Добавить `stats` в массив nav-tabs в `admin.html:36-43` ИЛИ удалить ссылку "📊 Статистика" из quick actions.

**Ожидаемый результат:** После создания навыка/религии пользователь видит соответствующий таб, а не пустую страницу.

---

### 🟡 СРЕДНЯЯ — 1.39. Дублирующий endpoint `verify_employer`

**Файл:** `app/blueprints/admin.py:649-656`

**Шаги:** Удалить `verify_employer` (дубликат `approve_employer`). Если нужен alias — добавить 301 redirect.

**Ожидаемый результат:** Нет мёртвого кода.

---

### 🟡 СРЕДНЯЯ — 1.40. `delete_skill` не транзакционный

**Файл:** `app/blueprints/admin.py:412-420`

**Шаги:** Создать RPC `delete_skill_cascade(p_skill_id uuid)` в `075_audit_remediation.sql`:
```sql
CREATE OR REPLACE FUNCTION public.delete_skill_cascade(p_skill_id uuid)
RETURNS json LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE v_deleted int;
BEGIN
    DELETE FROM public.user_skills WHERE skill_id = p_skill_id;
    DELETE FROM public.job_skills  WHERE skill_id = p_skill_id;
    DELETE FROM public.skills      WHERE id = p_skill_id;
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    IF v_deleted = 0 THEN
        RETURN json_build_object('success', false, 'error', 'Навык не найден');
    END IF;
    RETURN json_build_object('success', true);
END;
$$;
REVOKE EXECUTE ON FUNCTION public.delete_skill_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_skill_cascade(uuid) TO service_role;
```
В `admin.py` заменить каскад DELETE-запросов на вызов RPC.

**Ожидаемый результат:** Удаление навыка атомарно.

---

### 🟡 СРЕДНЯЯ — 1.41. `delete_religion` без cascade

**Файл:** `app/blueprints/admin.py:582`

**Шаги:** Добавить в `delete_religion` предварительную очистку `profiles.religion_id = NULL WHERE religion_id = ...` (FK уже `ON DELETE SET NULL`, так что БД сама обнулит — но проверить constraint в 067:586). Если FK RESTRICT — изменить на SET NULL или CASCADE.

**Ожидаемый результат:** Удаление религии не падает с FK violation.

---

### 🟡 СРЕДНЯЯ — 1.42. Нет audit-лога админских действий

**Шаги:**
1. Создать таблицу `audit_log`:
```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor_id UUID REFERENCES profiles(id),
    action TEXT NOT NULL,
    target_type TEXT,
    target_id UUID,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```
2. Добавить хелпер `log_admin_action(action, target_type, target_id, metadata)` в `app/blueprints/admin.py`.
3. Вызывать в каждом мутирующем admin-роуте (role change, delete, verify, skill/religion CRUD).

**Ожидаемый результат:** Все админские действия записаны.

---

### 🟢 НИЗКАЯ — 1.43. Версия BCrypt-JWT — генерация `jti` без использования

**Файл:** `app/utils/auth.py:71-77`

Уже покрыто в 1.19 — `jti` будет использоваться в Redis-сете.

---

### 🟢 НИЗКАЯ — 1.44. Не хватает COOP/CORP/X-Permitted-Cross-Domain-Policies

**Файл:** `app/__init__.py:166-191`

**Шаги:** Добавить в `add_security_headers`:
```python
response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
```
Удалить устаревший `X-XSS-Protection` (или установить в `0`).

**Ожидаемый результат:** Защита от Spectre-подобных атак усилена.

---

### 🟢 НИЗКАЯ — 1.45. `_archive_contact_payments` и `receipts` — мёртвая схема

**Шаги:** В `075_audit_remediation.sql`:
```sql
ALTER TABLE receipts DROP CONSTRAINT IF EXISTS receipts_contact_payment_id_fkey;
ALTER TABLE receipts ADD COLUMN IF NOT EXISTS job_payment_id UUID REFERENCES job_payments(id) ON DELETE SET NULL;
-- Опционально: DROP TABLE _archive_contact_payments;
```

**Ожидаемый результат:** `receipts` может ссылаться на актуальные `job_payments`.

---

### 🟢 НИЗКАЯ — 1.46. `schema_migrations` определена, но не используется

**Шаги:** В `075_audit_remediation.sql` вставить записи о применённых миграциях:
```sql
INSERT INTO schema_migrations (version, checksum, description) VALUES
    ('067','bootstrap','Bootstrap Amvera PostgreSQL'),
    ('068','pgadmin_gaps','Fix pgAdmin gaps'),
    ('069','rpc_security','Fix RPC security gaps'),
    ('070','skills_church','Replace skills with church theme'),
    ('071','auth_permissions','Fix auth permissions'),
    ('072','skills_v2','Fix skills v2'),
    ('073','admin_rls','Fix admin RLS policies'),
    ('074','rls_roles','Fix RLS roles'),
    ('075','audit_remediation','Critical DB audit remediation')
ON CONFLICT (version) DO NOTHING;
```

В `scripts/apply_migrations.py` добавить проверку `INSERT INTO schema_migrations ... ON CONFLICT DO NOTHING` в конце каждого файла.

**Ожидаемый результат:** Можно узнать, какие миграции применены.

---

## РАЗДЕЛ 2. ФРОНТЕНД (HTML/CSS/JS)

### 🔴 КРИТИЧЕСКАЯ — 2.1. Динамическая форма bulk-action без CSRF-токена

**Файл:** `templates/index.html:144-162`

**Проблема:** `bulkAction()` создаёт форму через `document.createElement('form')` и вызывает `form.submit()`. Программный `form.submit()` не триггерит событие `submit`, поэтому глобальный listener в `base.html:1156` не добавляет `_csrf_token`. POST к `/apply-selected` или `/unapply-selected` возвращает 400.

**Шаги:**
```javascript
function bulkAction(action) {
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = action === 'apply' ? '/apply-selected' : '/unapply-selected';
    // Добавить CSRF-токен
    var csrf = document.createElement('input');
    csrf.type = 'hidden';
    csrf.name = '_csrf_token';
    csrf.value = document.querySelector('meta[name="csrf-token"]').content;
    form.appendChild(csrf);
    // Добавить выбранные job_ids
    document.querySelectorAll('input[name="job_ids"]:checked').forEach(function(cb) {
        var inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'job_ids';
        inp.value = cb.value;
        form.appendChild(inp);
    });
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
}
```

**Ожидаемый результат:** Bulk-apply/unapply работает.

---

### 🔴 КРИТИЧЕСКАЯ — 2.2. `{{ worker_site_url }}` не определена — битая ссылка в логотипе

**Файл:** `templates/base.html:566`

**Проблема:** Переменная `worker_site_url` не внедряется ни одним context processor. Логотип ведёт на пустой href, перезагружая текущую страницу.

**Шаги:**

Вариант 1 (быстрый): заменить на `href="/"`.
Вариант 2 (правильный): добавить в `app/context_processors.py`:
```python
@context_processor
def inject_worker_site_url():
    from flask import current_app
    return {'worker_site_url': current_app.config.get('WORKER_SITE_URL', '/')}
```

**Ожидаемый результат:** Клик по логотипу ведёт на главную.

---

### 🔴 КРИТИЧЕСКАЯ — 2.3. CSP блокирует тайлы Яндекс.Карт

**Файл:** `app/__init__.py:172-181`

**Проблема:** `connect-src` не содержит `https://*.yandex.ru` и `https://core-renderer-tiles.maps.yandex.net`. Карта в `job_new.html` и `job_detail.html` не загружается.

**Шаги:** Обновить CSP `connect-src`:
```python
f"connect-src 'self' https://*.maps.yandex.net https://yastatic.net https://geocode-maps.yandex.ru "
f"https://*.yandex.ru https://core-renderer-tiles.maps.yandex.net "
f"https://fonts.googleapis.com https://fonts.gstatic.com ws://localhost:* wss://*; "
```

**Ожидаемый результат:** Карта грузится.

---

### 🟠 ВЫСОКАЯ — 2.4. `manifest.json` shortcut ведёт на несуществующий `/job-new`

**Файл:** `static/manifest.json:50`

**Шаги:** Заменить `"url": "/job-new"` на `"url": "/job/new"`.

**Ожидаемый результат:** PWA-ярлык «Создать задание» работает.

---

### 🟠 ВЫСОКАЯ — 2.5. `loadDraft()` перезаписывает данные редактирования

**Файл:** `templates/job_new.html:419-444`

**Проблема:** При редактировании существующего задания (`is_edit=true`) форма заполняется с сервера, но `loadDraft()` сразу перезаписывает значения из localStorage, где могут лежать данные с прошлой неудачной попытки создания.

**Шаги:**
```javascript
{% if not is_edit %}
loadDraft();
{% endif %}
```
Или в JS:
```javascript
const isEdit = {{ 'true' if is_edit else 'false' }};
if (!isEdit) {
    loadDraft();
}
```

**Ожидаемый результат:** При редактировании пользователь видит серверные данные, а не stale-черновик.

---

### 🟠 ВЫСОКАЯ — 2.6. `notifications-ws.js` не может обновить счётчик (нет `id` у badge)

**Файлы:** `templates/base.html:612,625`, `static/js/notifications-ws.js:159-170`

**Проблема:** `_updateNotificationCounter` ищет `document.getElementById('notifications-badge')` и `'chat-badge'`, но в шаблоне badge — это `<span>` без `id`. Счётчик молча не обновляется.

**Шаги:** Добавить `id`:
```html
<span id="notifications-badge" class="...">{{ unread_count if unread_count else '' }}</span>
...
<span id="chat-badge" class="...">{{ unread_chats if unread_chats else '' }}</span>
```

**Ожидаемый результат:** Счётчик уведомлений/чатов обновляется в реальном времени.

---

### 🟠 ВЫСОКАЯ — 2.7. Нет fallback на HTTP-polling для уведомлений

**Файл:** `static/js/notifications-ws.js:200-217`, `static/js/notifications-init.js`

**Шаги:** В `notifications-init.js` после исчерпания WS-реконнектов:
```javascript
ws.on('reconnect_failed', () => {
    console.warn('WS exhausted, falling back to polling');
    setInterval(() => {
        fetch('/api/notifications/unread-count', {credentials: 'same-origin'})
            .then(r => r.json())
            .then(data => {
                const badge = document.getElementById('notifications-badge');
                if (badge) badge.textContent = data.count || '';
            })
            .catch(() => {});
    }, 30000);
});
```

**Ожидаемый результат:** Уведомления приходят даже при падении WS.

---

### 🟠 ВЫСОКАЯ — 2.8. `notifications-ws.js` — `notificationsList` и `chatMessages` handlers пустые

**Файл:** `static/js/notifications-init.js:19-23,33-38`

**Шаги:** Реализовать добавление новых элементов в DOM:
- Для `notificationsList`: prepенд новой карточки в `#notifications-list`.
- Для `chatMessages`: append нового сообщения в `#chat-messages` + скролл вниз.

**Ожидаемый результат:** Real-time обновление DOM, а не только toast.

---

### 🟠 ВЫСОКАЯ — 2.9. Чат: polling дублирует WS-сообщения

**Файл:** `templates/chat.html:148-154`

**Шаги:** В `pollMessages`:
```javascript
function pollMessages() {
    // Не дублировать, если WS активен
    if (window.NotificationsWS && window.NotificationsWS.ws && 
        window.NotificationsWS.ws.readyState === 1) {
        return;
    }
    // ... существующий код polling
}
```

**Ожидаемый результат:** Polling работает только когда WS упал.

---

### 🟠 ВЫСОКАЯ — 2.10. XSS в register.html при рендере названий навыков

**Файл:** `templates/register.html:371-376` (и `templates/profile.html:138`)

**Шаги:** Заменить string interpolation на `textContent`:
```javascript
const span = document.createElement('span');
span.className = 'text-neutral-700';
span.textContent = s.name;  // не innerHTML
```

В `_filter_skills.html:143-146` аналогично для `data-skill`.

**Ожидаемый результат:** Навык с именем `<script>` не выполнится.

---

### 🟠 ВЫСОКАЯ — 2.11. INN-поле без `pattern`

**Файл:** `templates/register.html:143-147`

**Шаги:**
```html
<input type="text" name="inn" maxlength="12" pattern="\d{12}" inputmode="numeric"
       title="ИНН должен содержать ровно 12 цифр" ...>
```

**Ожидаемый результат:** Браузер валидирует INN на клиенте.

---

### 🟠 ВЫСОКАЯ — 2.12. Серверные ошибки регистрации не показываются у полей

**Файл:** `templates/register.html:26-174`

**Шаги:** Добавить блоки `{% if field_error %}` рядом с каждым полем. В `auth.py` при `flash` добавить `field_errors` dict и пробросить в template.

**Ожидаемый результат:** Пользователь видит, какое именно поле невалидно.

---

### 🟡 СРЕДНЯЯ — 2.13. Mass-action bar перекрывает bottom-nav

**Файл:** `templates/my_applications.html:19-21`

**Шаги:** Заменить `fixed bottom-0` на `fixed bottom-20` (или `bottom-16`), чтобы бар был выше нижней навигации. Аналогично проверить `index.html` (там уже `bottom-20`).

**Ожидаемый результат:** Во время bulk-select пользователь может пользоваться нижней навигацией.

---

### 🟡 СРЕДНЯЯ — 2.14. Skeleton-loader определён, но не используется

**Файлы:** `templates/base.html:434-443`, `templates/index.html`, `templates/workers.html`, `templates/my_jobs.html`, `templates/my_applications.html`

**Шаги:** Добавить skeleton-блоки в листинги:
```html
<div id="skeleton-list" class="grid gap-3">
    {% for _ in range(6) %}
    <div class="skeleton-card animate-pulse bg-neutral-100 rounded-xl h-32"></div>
    {% endfor %}
</div>
<div id="jobs-list" class="hidden">
    {% for job in jobs %}...{% endfor %}
</div>
```
JS после загрузки скрывает skeleton, показывает list.

**Ожидаемый результат:** Воспринимаемая скорость загрузки выше.

---

### 🟡 СРЕДНЯЯ — 2.15. Нет breadcrumbs

**Файлы:** `templates/job_detail.html`, `templates/chat.html`, `templates/profile_worker.html`

**Шаги:** Добавить навигационные крошки:
```html
<nav class="text-sm text-neutral-500 mb-3" aria-label="Breadcrumb">
    <a href="/" class="hover:text-primary-500">Главная</a>
    <span class="mx-1">/</span>
    <a href="/?tab=jobs" class="hover:text-primary-500">Задания</a>
    <span class="mx-1">/</span>
    <span class="text-neutral-800">{{ job.organization_name }}</span>
</nav>
```

**Ожидаемый результат:** Понятная навигация.

---

### 🟡 СРЕДНЯЯ — 2.16. Дублирование CSRF-поля в profile.html

**Файл:** `templates/profile.html:77`

**Шаги:** Удалить явный `<input type="hidden" name="csrf_token" ...>` — глобальная автоинъекция добавит `_csrf_token`.

**Ожидаемый результат:** Нет дубля CSRF-полей.

---

### 🟡 СРЕДНЯЯ — 2.17. Skill-мультиселект без поиска в register/profile

**Файлы:** `templates/register.html:128-141`, `templates/profile.html:128-140`

**Шаги:** Извлечь переиспользуемый компонент из `_filter_skills.html` (с поиском) в отдельный макрос или Web Component. Использовать в register/profile.

**Ожидаемый результат:** С 50+ навыками пользователь может искать.

---

### 🟡 СРЕДНЯЯ — 2.18. Religion select: register грузит из API, profile — захардкожено

**Файл:** `templates/profile.html:113-122`

**Шаги:** Переписать profile.html на загрузку из `/api/religions` (как в register.html:296-318).

**Ожидаемый результат:** Изменение списка религий в БД автоматически отражается в UI.

---

### 🟡 СРЕДНЯЯ — 2.19. `notifications.html` — кнопка удаления 28×28px (меньше 44px)

**Файл:** `templates/notifications.html:63-66`

**Шаги:** Увеличить до `width:44px; height:44px` и убрать `right:-10px` (заменить на `right:0`).

**Ожидаемый результат:** Touch-target соответствует Apple HIG.

---

### 🟡 СРЕДНЯЯ — 2.20. `chat.html` — input без `aria-label`

**Файл:** `templates/chat.html:54-57`

**Шаги:** Добавить `aria-label="Сообщение"`.

**Ожидаемый результат:** Скринридер озвучивает назначение поля.

---

### 🟢 НИЗКАЯ — 2.21. Заголовок страницы всегда «Трудник»

**Шаги:** Добавить `{% block title %}...{% endblock %}` в каждый шаблон с осмысленным заголовком (например, «Задание — {{ job.title }}», «Профиль — {{ user.full_name }}»).

---

### 🟢 НИЗКАЯ — 2.22. `base.html:578-579` — дублирующие span с противоположными классами

**Шаги:** Удалить `<span class="sm:hidden">Трудник</span>`, оставить только `<span class="hidden sm:inline">Трудник</span>` (или наоборот в зависимости от желаемого поведения).

---

### 🟢 НИЗКАЯ — 2.23. CSS-переменные не определены

**Шаги:** В `templates/base.html` в `<style>`:
```css
:root {
    --brand: #d97706;
    --brand-dark: #b45309;
    --danger: #ef4444;
    --success: #10b981;
    --neutral-50: #fafafa;
    --neutral-900: #171717;
}
```
Заменить хардкод `#d97706` на `var(--brand)` во всех местах.

---

## РАЗДЕЛ 3. UX/UI И ДИЗАЙН

### 🟠 ВЫСОКАЯ — 3.1. Кнопка «Текущая версия» только на дашборде и невидима

**Файлы:** `templates/admin.html:74-83`, `static/js/admin-version.js`

**Проблема:** Кнопка `<button id="current-version-btn">🔖 Текущая версия</button>` рендерится только внутри `{% if tab == 'dashboard' %}`. На остальных табах её нет. Текст версии спрятан (`<span id="git-version" hidden>`), показывается только в tooltip при hover.

**Шаги:**

1. Перенести кнопку в header admin-панели (видна на всех табах):
```html
<!-- В admin.html header, рядом с бейджем admin -->
<div class="flex items-center gap-2">
    <span class="text-xs text-neutral-500">Версия:</span>
    <button id="current-version-btn" class="text-xs px-2 py-1 rounded hover:bg-neutral-100 font-mono"
            title="Нажмите, чтобы скопировать">
        {{ actual_version[:7] if actual_version else 'dev' }}
    </button>
</div>
```
2. В `admin.py` рендерить `actual_version` на каждый запрос (не только dashboard).

**Ожидаемый результат:** Версия видна в header на всех табах.

---

### 🟠 ВЫСОКАЯ — 3.2. Bulk-delete JS показывает employer вместо job name

**Файл:** `templates/admin.html:928`

**Проблема:** `td:nth-child(3)` — но имя задания в `td:nth-child(2)`. В диалоге подтверждения показывается неправильный текст.

**Шаги:** Изменить селектор на `td:nth-child(2)`.

**Ожидаемый результат:** В диалоге подтверждения — название задания.

---

### 🟠 ВЫСОКАЯ — 3.3. Confirm modal без focus trap и ARIA

**Файлы:** `templates/base.html:680-689`, `templates/workers.html:146-170`

**Шаги:**
1. Добавить атрибуты:
```html
<div id="confirm-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="confirm-modal-title" class="modal-backdrop hidden">
```
2. JS: при открытии — `lastFocused = document.activeElement; modal.querySelector('button').focus();`
3. Trap Tab внутри modal:
```javascript
modal.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    const focusable = modal.querySelectorAll('button, [href], input, select, textarea');
    if (e.shiftKey && document.activeElement === focusable[0]) {
        e.preventDefault(); focusable[focusable.length-1].focus();
    } else if (!e.shiftKey && document.activeElement === focusable[focusable.length-1]) {
        e.preventDefault(); focusable[0].focus();
    }
});
```
4. На закрытие — `lastFocused.focus()`.

**Ожидаемый результат:** Modal доступен с клавиатуры и скринридером.

---

### 🟡 СРЕДНЯЯ — 3.4. Нет «Профиль» в мобильной нижней навигации

**Файл:** `templates/base.html:770-862`

**Шаги:** Добавить 5-й (или 6-й) элемент в bottom-nav со ссылкой на `/profile`.

**Ожидаемый результат:** Профиль доступен с мобильной навигации.

---

### 🟡 СРЕДНЯЯ — 3.5. Desktop-поиск `name="city"` с placeholder про «Поиск заданий, трудников»

**Файл:** `templates/base.html:582-593`

**Шаги:** Заменить placeholder на «Поиск по городу...» или реализовать полноценный поиск (задания + трудники + работодатели).

---

### 🟡 СРЕДНЯЯ — 3.6. Нет валидации «passwords match» в profile.html

**Файл:** `templates/profile.html:192-200`

**Шаги:** Добавить JS:
```javascript
const newPassword = document.getElementById('new_password');
const confirmPassword = document.getElementById('confirm_password');
confirmPassword.addEventListener('input', () => {
    if (newPassword.value !== confirmPassword.value) {
        confirmPassword.setCustomValidity('Пароли не совпадают');
    } else {
        confirmPassword.setCustomValidity('');
    }
});
```

Также добавить поле «Текущий пароль» для подтверждения.

**Ожидаемый результат:** Пользователь видит несоответствие паролей до отправки.

---

### 🟡 СРЕДНЯЯ — 3.7. Empty states без CTA

**Файлы:** `templates/notifications.html:71-79`, `templates/chat.html:36-46`

**Шаги:** Добавить кнопку:
```html
<a href="/" class="mt-4 inline-block px-4 py-2 bg-primary-500 text-white rounded-lg">К заданиям</a>
```

---

### 🟡 СРЕДНЯЯ — 3.8. Skill-чипы: разделитель запятая ломается при запятой в имени

**Файл:** `templates/profile.html:138`

**Шаги:** Использовать JSON вместо comma-separated:
```html
<input type="hidden" id="skills-hidden" name="skills" value='{{ profile_user.get("skills", [])|tojson }}'>
```
JS: `JSON.parse(document.getElementById('skills-hidden').value)`.

---

### 🟢 НИЗКАЯ — 3.9. Bottom-nav labels `text-[10px]` — мелко

**Шаги:** Заменить на `text-[11px]` или `text-xs`.

---

### 🟢 НИЗКАЯ — 3.10. PWA-скриншоты могут не существовать

**Файл:** `static/manifest.json:31-44`

**Шаги:** Проверить существование `/static/screenshots/screen-jobs.png` и `screen-chat.png`. Если нет — создать или удалить ссылки.

---

## РАЗДЕЛ 4. ИНФРАСТРУКТУРА И РАЗВЁРТЫВАНИЕ

### 🔴 КРИТИЧЕСКАЯ — 4.1. Branch mismatch: scripts push `main`, Amvera watches `master`

**Файлы:** `scripts/amvera_full_cycle.sh:93,108`, git reflog `.git/logs/refs/remotes/amvera/master`

**Проблема:** Deploy-скрипты делают `git push amvera main`, но Amvera-remote `HEAD -> amvera/master`. Push в `main` не обновляет `master`. Подтверждено в reflog: `8a9b65d → 914c451 → 8564c14`. Локальный `main` уже на `46ad1e7`, но `amvera/master` застрял на `8564c14`. Это причина «deploя устаревшей версии 914c451».

**Шаги (вариант A — предпочтительный):**
1. В Amvera web UI изменить default branch с `master` на `main`.
2. После этого `git push amvera main` будет триггерить rebuild.

**Шаги (вариант B — если нельзя изменить в UI):**
В `scripts/amvera_full_cycle.sh` и `scripts/amvera_deploy.sh` заменить:
```bash
git push amvera main
```
на:
```bash
git push amvera main:master
```

**Ожидаемый результат:** Push в `main` триггерит deploy актуального коммита.

---

### 🔴 КРИТИЧЕСКАЯ — 4.2. `/health` маршрутизируется в FastAPI, не проверяет БД

**Файлы:** `asgi.py:41-43`, `app/__init__.py:425-453`, `websocket_server/main.py:270-291`

**Проблема:** При запуске через `uvicorn asgi:application` маршрут `/health` перехватывается FastAPI `ws_app`, который проверяет только Redis и количество WS-соединений. Если БД упала, `/health` возвращает 200.

**Шаги:** В `asgi.py:41-43` направить `/health` во Flask:
```python
elif scope["type"] == "http" and scope.get("path") == "/health":
    await self.flask_asgi(scope, receive, send)
```
Или добавить проверку PostgREST в FastAPI healthcheck:
```python
@app.get("/health")
async def healthcheck():
    import httpx, os
    try:
        r = await httpx.AsyncClient().get(
            f"{os.environ.get('POSTGREST_URL')}/profiles?select=id&limit=1",
            timeout=3
        )
        db_ok = r.status_code in (200, 401)
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "error"}
```

**Ожидаемый результат:** `/health` отражает реальное состояние БД.

---

### 🔴 КРИТИЧЕСКАЯ — 4.3. Реальные пароли в `archive/env_trudnik_*.env`

**Файлы:** `archive/env_trudnik_db.env:21-22`, `archive/env_trudnik_pgadmin.env:20`

**Проблема:** В комментариях:
- `# App: postgresql://trudnikapp:***REMOVED***@...`
- `# Admin: postgresql://postgres:hyperstls@...`
- `# Password: ***REMOVED***`

Это реальные продакшен-пароли. Любой с доступом к репозиторию видит их.

**Шаги:**

1. Сначала ротировать ВСЕ пароли на Amvera:
   - PostgreSQL user `trudnikapp`: новый пароль через Amvera UI.
   - PostgreSQL superuser `postgres`: новый пароль.
   - pgAdmin: новый пароль.
   - `PGRST_JWT_SECRET`: `python -c "import secrets; print(secrets.token_hex(32))"`.
   - `SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`.
   - `SMTP_PASSWORD`: сменить в Yandex-аккаунте.
   - `ADMIN_API_TOKEN`: `python -c "import secrets; print(secrets.token_hex(32))"`.
   - Admin-пароль `admin@test.ru`: сменить через `change_password` RPC.

2. Очистить комментарии в env-файлах:
```bash
sed -i 's/***REMOVED***/PLACEHOLDER_DB_PASSWORD/g; s/hyperstls/PLACEHOLDER_SU_PASSWORD/g' archive/env_trudnik_db.env
sed -i 's/***REMOVED***/PLACEHOLDER_PG_PASSWORD/g' archive/env_trudnik_pgadmin.env
```

3. Добавить в `.gitignore`:
```
archive/env_trudnik_*.env
scripts/env_trudnik_app.env
```

4. `git rm --cached archive/env_trudnik_*.env scripts/env_trudnik_app.env`

5. Очистить git history:
```bash
pip install git-filter-repo
cat > /tmp/patterns.txt <<EOF
***REMOVED***==>REDACTED_DB_PASS
hyperstls==>REDACTED_SU_PASS
***REMOVED***==>REDACTED
Step@1986==>REDACTED
lvszpkuthmspixnv==>REDACTED_SMTP
EOF
git filter-repo --replace-text /tmp/patterns.txt --force
git push origin main --force --tags
git push amvera main:master --force
```

6. Включить GitHub Push Protection: Repo Settings → Code security → Secret scanning → Push protection = Enable.

**Ожидаемый результат:** В git-истории и текущих файлах нет реальных секретов. Push Protection блокирует будущие утечки.

---

### 🔴 КРИТИЧЕСКАЯ — 4.4. Хардкоженный админ-пароль в migration 067

**Файл:** `migrations/067_bootstrap_amvera.sql:2314-2325`

**Проблема:** `crypt('Step@1986', gen_salt('bf'))` — захардкожен. `ON CONFLICT DO UPDATE` сбрасывает пароль при повторном применении миграции.

**Шаги:**

1. В `migrations/067_bootstrap_amvera.sql:2314-2325` заменить на:
```sql
INSERT INTO profiles (id, email, password_hash, full_name, role, created_at)
VALUES (
    gen_random_uuid(),
    'admin@test.ru',
    crypt(current_setting('app.admin_init_password', true), gen_salt('bf', 12)),
    'Администратор',
    'admin',
    now()
)
ON CONFLICT (email) DO NOTHING;  -- НЕ сбрасывать пароль
```
2. Перед применением миграции:
```sql
SET app.admin_init_password = '<strong_random_password>';
```
3. В `migrations/075_audit_remediation.sql` принудительно сменить пароль admin@test.ru:
```sql
UPDATE profiles SET password_hash = crypt(current_setting('app.admin_new_password', true), gen_salt('bf', 12))
WHERE email = 'admin@test.ru';
```

**Ожидаемый результат:** Пароль admin не в репозитории, при повторном применении миграции не сбрасывается.

---

### 🟠 ВЫСОКАЯ — 4.5. `admin.py:143` — неверный путь к VERSION

**Файл:** `app/blueprints/admin.py:141-153`

**Проблема:** `os.path.join(current_app.root_path, 'VERSION')` = `app/VERSION` (не существует). Fallback `git log` тоже не работает (`git` не установлен в slim Docker). В prod админка показывает `'dev'`.

**Шаги:**
```python
import pathlib
version_file = pathlib.Path(current_app.root_path).parent / 'VERSION'
if version_file.exists():
    actual_version = version_file.read_text(encoding='utf-8').strip()
else:
    # Fallback на env-переменную, установленную при сборке
    actual_version = os.environ.get('GIT_VERSION', 'dev')
```

Дополнительно в `Dockerfile` добавить build-time инъекцию:
```dockerfile
ARG GIT_VERSION=dev
ENV GIT_VERSION=$GIT_VERSION
```
В `scripts/amvera_deploy.sh`:
```bash
GIT_VERSION=$(git rev-parse --short HEAD)
docker build --build-arg GIT_VERSION="$GIT_VERSION" ...
```

**Ожидаемый результат:** В prod админка показывает реальный коммит.

---

### 🟠 ВЫСОКАЯ — 4.6. Pre-commit hook VERSION отстаёт на 1 коммит

**Файлы:** `scripts/update_version.py`, `scripts/install_hooks.py:13-17`

**Проблема:** Pre-commit hook запускает `git log -1` ДО создания коммита → в VERSION попадает хэш родителя. После commit VERSION оказывается в новом коммите, но описывает предыдущий.

**Шаги:** Переключить на post-commit hook:

1. `scripts/install_hooks.py` — установить `post-commit` вместо `pre-commit`:
```python
hook_path = repo_root / '.git' / 'hooks' / 'post-commit'
hook_content = '''#!/bin/sh
python scripts/update_version.py
git add VERSION
git commit --amend --no-edit
'''
```
2. `scripts/update_version.py` — использовать `git rev-parse HEAD` (после commit) вместо `git log -1`.

**Ожидаемый результат:** VERSION содержит хэш текущего HEAD.

---

### 🟠 ВЫСОКАЯ — 4.7. Нет HEALTHCHECK в Dockerfile

**Файл:** `Dockerfile:33`

**Шаги:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)" || exit 1
```
Изменить CMD на exec-форму:
```dockerfile
CMD ["uvicorn", "asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-ping-interval", "20", "--ws-ping-timeout", "20"]
```

**Ожидаемый результат:** Docker видит health-статус контейнера, корректно перезапускает при зависании.

---

### 🟠 ВЫСОКАЯ — 4.8. Нет автоматических backup'ов БД

**Файлы:** `scripts/amvera_db_backup.sh`, `docs/AMVERA_CLI_AUTOMATION.md:131`

**Шаги:**

1. Включить scheduled backups:
```bash
amvera psql scheduled --slug trudnik-db --enable
```
2. Или создать Amvera Cron Job: schedule `0 3 * * *` (ежедневно 03:00 MSK), команда `cd /app && amvera psql backup create --slug trudnik-db`.
3. Тестировать restore раз в квартал.

**Ожидаемый результат:** Ежедневный backup, возможность восстановления.

---

### 🟠 ВЫСОКАЯ — 4.9. Celery не развёрнут в prod

**Файлы:** `Dockerfile:33`, `docker-compose.yml:90-148`

**Проблема:** Dockerfile CMD запускает только uvicorn. `celery_worker` и `celery_beat` определены в docker-compose, но Amvera запускает один контейнер. Email/push/maintenance фоновые таски **не выполняются в prod**.

**Шаги:**

Вариант 1 (рекомендуемый): развернуть отдельный Amvera-проект `trudnik-celery` с тем же образом, но CMD:
```dockerfile
# В Dockerfile добавить:
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info"]
# И второй контейнер для beat:
CMD ["celery", "-A", "app.tasks.celery_app", "beat", "--loglevel=info"]
```

Вариант 2: запускать Celery в том же контейнере через supervisor:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends supervisor
COPY supervisord.conf /etc/supervisor/conf.d/trudnik.conf
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
```

`supervisord.conf`:
```ini
[program:uvicorn]
command=uvicorn asgi:application --host 0.0.0.0 --port 8000 --workers 1
[program:celery_worker]
command=celery -A app.tasks.celery_app worker --loglevel=info
[program:celery_beat]
command=celery -A app.tasks.celery_app beat --loglevel=info
```

**Ожидаемый результат:** Email-уведомления, push и запланированные задачи работают.

---

### 🟠 ВЫСОКАЯ — 4.10. `wait_for_prod.py` проверяет `/api/health` вместо `/health`

**Файл:** `scripts/wait_for_prod.py:9`

**Шаги:** Заменить:
```python
HEALTH_URL = URL.rstrip("/") + "/health"
```

**Ожидаемый результат:** Smoke-test после deploy работает.

---

### 🟠 ВЫСОКАЯ — 4.11. Нет psycopg2 connection pool

**Файлы:** `app/blueprints/auth.py:119`, `app/blueprints/admin.py:736,867`

**Шаги:** Создать `app/utils/db_pool.py`:
```python
from psycopg2 import pool
from flask import current_app
import os

_pool = None

def get_db_connection():
    global _pool
    if _pool is None:
        dsn = os.environ.get('DATABASE_URL')
        if not dsn:
            raise RuntimeError('DATABASE_URL not set')
        _pool = pool.SimpleConnectionPool(minconn=1, maxconn=5, dsn=dsn, connect_timeout=10)
    return _pool.getconn()

def return_db_connection(conn):
    if _pool and conn:
        _pool.putconn(conn)
```

Использовать в auth.py и admin.py:
```python
from app.utils.db_pool import get_db_connection, return_db_connection
conn = get_db_connection()
try:
    with conn.cursor() as cur:
        cur.execute(...)
    return_db_connection(conn)
except Exception:
    return_db_connection(conn)
    raise
```

**Ожидаемый результат:** Меньше latency на DB-соединениях, нет утечки коннектов.

---

### 🟡 СРЕДНЯЯ — 4.12. Миграции не применяются автоматически при deploy

**Шаги:** Создать entrypoint-скрипт `scripts/entrypoint.sh`:
```bash
#!/bin/sh
set -e
echo "Applying migrations..."
python scripts/apply_migrations.py || echo "Migration warning (may already be applied)"
echo "Starting uvicorn..."
exec uvicorn asgi:application --host 0.0.0.0 --port 8000 --workers 1
```

В `Dockerfile`:
```dockerfile
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
```

**Ожидаемый результат:** При каждом deploy миграции применяются автоматически.

---

### 🟡 СРЕДНЯЯ — 4.13. `apply_new_migrations.py` — мёртвый код (Supabase)

**Файл:** `scripts/apply_new_migrations.py`

**Шаги:** Удалить файл или переместить в `archive/`.

---

### 🟡 СРЕДНЯЯ — 4.14. Windows-пути в amvera_*.sh скриптах

**Файлы:** `scripts/amvera_deploy.sh:12`, `amvera_full_cycle.sh:24`, `amvera_monitor.sh:12`, `amvera_env_manager.sh:21`, `amvera_db_backup.sh:14`

**Шаги:** Заменить:
```bash
AMVERA="C:/Users/s.prokopenko/AppData/Local/Amvera/amvera.exe"
```
на:
```bash
AMVERA="${AMVERA_CLI:-amvera}"
```

**Ожидаемый результат:** Скрипты работают на Linux/macOS/CI.

---

### 🟡 СРЕДНЯЯ — 4.15. Resource limits не заданы в docker-compose

**Шаги:** В `docker-compose.yml` для каждого сервиса:
```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '0.5'
```

---

### 🟡 СРЕДНЯЯ — 4.16. Структурированные логи

**Шаги:** Создать `app/utils/logging_config.py`:
```python
import json, logging, os

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'ts': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'msg': record.getMessage(),
            'request_id': getattr(record, 'request_id', None),
        }, ensure_ascii=False)

def setup_logging(app):
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    app.logger.handlers = [handler]
    app.logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
```

Вызвать в `create_app()`. Добавить middleware для request_id (UUID на запрос, прокидывается в логи).

**Ожидаемый результат:** Логи в JSON-формате, легко парсятся.

---

### 🟡 СРЕДНЯЯ — 4.17. `.dockerignore` не исключает `.git/`

**Файл:** `.dockerignore`

**Шаги:** Добавить:
```
.git
.github
.idea
.vscode
scripts/screenshots
trash
uploads/avatars
```

Но! Это сломает fallback `git log` в `admin.py:148`. Поэтому сначала применить фикс 4.5 (env-переменная `GIT_VERSION`).

**Ожидаемый результат:** Меньше размер образа, нет утечки git-истории в image.

---

### 🟢 НИЗКАЯ — 4.18. requirements.txt не пиннует версии

**Шаги:** Заменить `>=` на `==` (или создать `requirements.lock.txt` через `pip freeze`).

---

### 🟢 НИЗКАЯ — 4.19. `amvera_agent.py` (81 KB Playwright) — maintenance liability

**Шаги:** Заменить на direct Amvera CLI calls. Если не используется в CI/CD — переместить в `archive/`.

---

### 🟢 НИЗКАЯ — 4.20. `amvera_full_cycle.sh:142` — naive grep для ошибок

**Шаги:** Заменить grep на структурированный парсинг JSON-ответа Amvera API.

---

## РАЗДЕЛ 5. ГОТОВНОСТЬ К МОНЕТИЗАЦИИ

### 🟡 СРЕДНЯЯ — 5.1. Нет UI-элементов для платных функций

**Шаги:**

1. В `templates/index.html` добавить badge для продвигаемых заданий:
```html
{% if job.tariff == 'pro' or job.tariff == 'premium' %}
<span class="bg-warning text-white text-[10px] font-bold px-2 py-0.5 rounded">★ ТОП</span>
{% endif %}
```
2. В `templates/my_jobs.html` показать квоту:
```html
{% if remaining_free_jobs is defined %}
<p class="text-xs text-neutral-500">Осталось бесплатных заданий: {{ remaining_free_jobs }}</p>
{% endif %}
```
3. В `templates/profile.html` для employer — badge тарифа (Basic/Pro/Enterprise).
4. Создать страницу `/pricing` с тарифами.

---

### 🟡 СРЕДНЯЯ — 5.2. Нет интеграции с платёжным провайдером

**Шаги:**

1. Выбрать провайдера (YooKassa для РФ — нативная интеграция с российскими банками).
2. Добавить `yookassa` в requirements.txt.
3. Создать `app/services/payment_service.py` с методами `create_payment(amount, description, return_url)` и `verify_webhook(payload, signature)`.
4. Создать webhook `/api/payments/yookassa/webhook` (без CSRF, с проверкой IP/подписи).
5. После успешной оплаты — `UPDATE jobs SET is_paid = true WHERE id = ...`.

---

### 🟡 СРЕДНЯЯ — 5.3. Нет таблицы подписок работодателей

**Шаги:** В `migrations/075_audit_remediation.sql`:
```sql
CREATE TABLE employer_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    plan TEXT NOT NULL CHECK (plan IN ('basic','pro','enterprise')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    yookassa_subscription_id TEXT,
    UNIQUE(employer_id, expires_at)
);
CREATE INDEX idx_employer_subscriptions_employer ON employer_subscriptions(employer_id) WHERE is_active = TRUE;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_promoted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS promoted_until TIMESTAMPTZ;
CREATE INDEX idx_jobs_promoted ON jobs(promoted_until) WHERE is_promoted = TRUE AND promoted_until > NOW();
```

В `app/blueprints/jobs.py:build_job_query` добавить boost для продвигаемых:
```python
query += '&order=promoted_until.desc.nullslast,created_at.desc'
```

---

### 🟢 НИЗКАЯ — 5.4. Модель данных готова к pay-per-job

Текущая схема (`tariff_settings`, `job_payments`, `is_paid`, `tariff` на `jobs`) уже поддерживает разовую оплату за публикацию. Достаточно:

1. Включить `MONETIZATION_ENABLED=true` (фикс 1.26).
2. Реализовать payment flow перед созданием задания.
3. Добавить страницу `/employer/billing` с историей платежей.

---

## ЗАВЕРШЕНИЕ

После внесения всех изменений:

1. Запустить полный набор тестов: `pytest tests/ -v`.
2. Запустить e2e-тесты: `pytest tests_e2e/ -v`.
3. Применить миграцию `075_audit_remediation.sql` к staging, затем к prod.
4. Ротировать все секреты (фикс 4.3, 4.4).
5. Очистить git history (фикс 4.3).
6. Обновить `VERSION` через post-commit hook (фикс 4.6).
7. Сделать deploy на Amvera (фикс 4.1 — убедиться, что push идёт в правильную ветку).
8. Проверить `/health` в prod — должен возвращать `{"status":"ok","database":"ok",...}`.
9. Проверить `/admin` — кнопка «Текущая версия» показывает актуальный коммит.
10. Включить GitHub Push Protection.

**Финальный коммит:** `chore: apply comprehensive audit remediation (security, performance, monetization readiness)`.

Все критические и высокие пункты (🔴 + 🟠) должны быть выполнены до deploy в production. Средние и низкие (🟡 + 🟢) могут быть вынесены в отдельные PR.
