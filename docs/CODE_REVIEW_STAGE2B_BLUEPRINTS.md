# Этап 2-B: Ревью admin и applications blueprint

> **Дата:** 2026-06-22 | **Контекст:** [CODE_REVIEW_CONTEXT.md](docs/CODE_REVIEW_CONTEXT.md), [STAGE1_INFRA.md](docs/CODE_REVIEW_STAGE1_INFRA.md), [STAGE2A_BLUEPRINTS.md](docs/CODE_REVIEW_STAGE2A_BLUEPRINTS.md)
> **Охват:** 2 файла: [admin.py](app/blueprints/admin.py) (~23K, 540 строк), [applications.py](app/blueprints/applications.py) (~28K, 637 строк)
> **Метод:** Статический анализ с выборочной верификацией через [decorators.py](app/decorators.py), [__init__.py](app/__init__.py), [config.py](app/config.py)

---

## 1. [app/blueprints/admin.py](app/blueprints/admin.py)

### Найдено проблем: 14

| # | Серьёзность | Категория | Проблема | Строка | Рекомендация |
|---|------------|-----------|----------|--------|--------------|
| 1 | **HIGH** | Безопасность | Администратор может изменить собственную роль на `worker`/`employer` через [update_user_role()](app/blueprints/admin.py:100) — нет проверки `user_id != session["user_id"]`. Само-лок-аут: если единственный админ понизит себя, доступ к админке потерян навсегда без прямого вмешательства в БД | [app/blueprints/admin.py:100-107](app/blueprints/admin.py) | Добавить защиту: `if user_id == session["user_id"]: flash("Нельзя изменить собственную роль", "danger"); return redirect(...)` |
| 2 | **HIGH** | Безопасность | Дублирование эндпоинтов верификации: [approve_employer()](app/blueprints/admin.py:465) использует `supabase_request` (anon key), а [verify_employer()](app/blueprints/admin.py:491) — `supabase_admin_request` (service_role). Функционально идентичны, но разные уровни привилегий | [app/blueprints/admin.py:462-494](app/blueprints/admin.py) | Оставить один метод (`verify_employer` с `supabase_admin_request`), удалить дубликат |
| 3 | **MEDIUM** | Корректность | [update_user_role()](app/blueprints/admin.py:103) и [update_job_status()](app/blueprints/admin.py:141) не проверяют результат `supabase_request` — всегда flash success, даже если PATCH не удался | [app/blueprints/admin.py:103](app/blueprints/admin.py), [app/blueprints/admin.py:141](app/blueprints/admin.py) | Проверять `resp.ok`, показывать ошибку при неудаче |
| 4 | **MEDIUM** | Корректность | [delete_skill()](app/blueprints/admin.py:300-308) — три неатомарных DELETE: user_skills, job_skills, skills. При сбое третьего — навык-сирота | [app/blueprints/admin.py:301-308](app/blueprints/admin.py) | Создать RPC `delete_skill_cascade` |
| 5 | **MEDIUM** | Корректность | Статистика дашборда limit=1000 ([admin_panel()](app/blueprints/admin.py:27,35)). При >1000 пользователей — неверные цифры | [app/blueprints/admin.py:27,35](app/blueprints/admin.py) | Использовать count без limit или RPC |
| 6 | **MEDIUM** | Производительность | [reorder_skills()](app/blueprints/admin.py:282-283) и [reorder_religions()](app/blueprints/admin.py:402-403) — N PATCH-запросов | [app/blueprints/admin.py:282-283](app/blueprints/admin.py) | Батчевый PATCH через `id=in.(...)` |
| 7 | **MEDIUM** | Производительность | [job_stats()](app/blueprints/admin.py:528-537) fallback загружает ВСЕ jobs в память | [app/blueprints/admin.py:528-537](app/blueprints/admin.py) | Использовать агрегацию на стороне БД |
| 8 | **MEDIUM** | Производительность | [admin_panel()](app/blueprints/admin.py:27-44) — dashboard делает ~3 HTTP-запроса к PostgREST при каждом рендере | [app/blueprints/admin.py:27-44](app/blueprints/admin.py) | Кэшировать статистику в Redis с TTL 60 сек |
| 9 | **MEDIUM** | Безопасность | [approve_employer()](app/blueprints/admin.py:466) использует anon key вместо service_role для PATCH профиля другого пользователя | [app/blueprints/admin.py:466](app/blueprints/admin.py) | Заменить на `supabase_admin_request` |
| 10 | **LOW** | Качество | Неиспользуемый импорт `cache_for` | [app/blueprints/admin.py:6](app/blueprints/admin.py) | Удалить неиспользуемый импорт |
| 11 | **LOW** | Качество | [bulk_delete_users()](app/blueprints/admin.py:184-201) — нет валидации UUID для user_ids | [app/blueprints/admin.py:184-201](app/blueprints/admin.py) | Добавить проверку `uuid.UUID(user_id)` |
| 12 | **LOW** | Качество | [bulk_delete_skills()](app/blueprints/admin.py:329-330) — строковая интерполяция без санитизации | [app/blueprints/admin.py:329-330](app/blueprints/admin.py) | Валидировать UUID перед интерполяцией |
| 13 | **LOW** | Качество | [admin_panel()](app/blueprints/admin.py:26-87) — загружает данные для всех вкладок, даже неактивных | [app/blueprints/admin.py:26-87](app/blueprints/admin.py) | Загружать только для активной вкладки |
| 14 | **LOW** | Качество | Листинг пользователей limit=100 без пагинации | [app/blueprints/admin.py:51](app/blueprints/admin.py) | Добавить offset параметр |

---

## 2. [app/blueprints/applications.py](app/blueprints/applications.py)

### Найдено проблем: 16

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **CRITICAL** | Безопасность | [apply_selected()](app/blueprints/applications.py:187-243) — массовая подача заявок обходит RPC `apply_job_atomic`: не проверяются blacklist, слоты, собственное задание. Заблокированный трудник может обойти блокировку | [app/blueprints/applications.py:199-219](app/blueprints/applications.py) | Заменить на вызов `supabase_rpc("apply_job_atomic")` в цикле |
| 2 | **HIGH** | Корректность | [api_withdraw_application()](app/blueprints/applications.py:280-362) — полностью неатомарна: 6 HTTP-запросов (GET app -> GET job -> PATCH workers -> NOTIFY -> PATCH status -> DELETE). current_workers может уйти в минус | [app/blueprints/applications.py:290-356](app/blueprints/applications.py) | Создать RPC `withdraw_application_atomic` |
| 3 | **HIGH** | Корректность | [cancel_application()](app/blueprints/applications.py:571-637) — неатомарна: GET->GET->GET->PATCH->PATCH. Двойная отмена -> current_workers уходит в минус | [app/blueprints/applications.py:573-626](app/blueprints/applications.py) | Создать RPC `cancel_worker_atomic` |
| 4 | **HIGH** | Корректность | [api_handle_application()](app/blueprints/applications.py:435-438) — при accept rejected делает PATCH rejected->pending ПЕРЕД RPC accept_application. Если RPC падает, заявка в pending вместо rejected — потеря данных | [app/blueprints/applications.py:437-441](app/blueprints/applications.py) | Перенести rejected->pending внутрь RPC accept_application |
| 5 | **HIGH** | Корректность | [cancel_application()](app/blueprints/applications.py:571-637) — не проверяет статус заявки. Можно отменить уже rejected/withdrawn, повторно уведомив работника | [app/blueprints/applications.py:571-637](app/blueprints/applications.py) | Проверять: if status != accepted: reject |
| 6 | **MEDIUM** | Безопасность | [my_applications()](app/blueprints/applications.py:397-402) — копирует worker целиком в worker_contacts, включая phone. Поле может быть не предназначено для раскрытия | [app/blueprints/applications.py:397-402](app/blueprints/applications.py) | Явный whitelist полей: full_name, photo_url, rating |
| 7 | **MEDIUM** | Безопасность | [api_handle_application()](app/blueprints/applications.py:416) и маршруты в [__init__.py:335-350](app/__init__.py) без @role_required | [app/blueprints/applications.py:416-433](app/blueprints/applications.py) | Добавить @employer_required, убрать ручную проверку |
| 8 | **MEDIUM** | Производительность | [my_applications()](app/blueprints/applications.py:376-378) — запрашивает ВСЕ отклики без пагинации | [app/blueprints/applications.py:376-378](app/blueprints/applications.py) | Добавить limit/offset |
| 9 | **MEDIUM** | Производительность | [apply_selected()](app/blueprints/applications.py:199-219) — N+1 запросов: GET jobs + GET applications + POST для каждого job_id. До 60 запросов при 20 заданиях | [app/blueprints/applications.py:201-212](app/blueprints/applications.py) | Заменить на RPC apply_job_atomic в цикле |
| 10 | **MEDIUM** | Корректность | [api_batch_applications()](app/blueprints/applications.py:544-549) — fragile: проверка isinstance(result, tuple) зависит от Flask internals | [app/blueprints/applications.py:544-549](app/blueprints/applications.py) | Добавить проверку статус-кода |
| 11 | **MEDIUM** | Корректность | [api_withdraw_application()](app/blueprints/applications.py:351-356) — для pending: PATCH withdrawn + DELETE (статус теряется). Для accepted: PATCH withdrawn без DELETE. Несогласованно | [app/blueprints/applications.py:351-356](app/blueprints/applications.py) | Унифицировать: всегда withdrawn или всегда delete |
| 12 | **MEDIUM** | Корректность | [api_withdraw_application()](app/blueprints/applications.py:338-341) — PATCH current_workers затем PATCH статуса заявки — неатомарная пара. Между ними accept -> перезапись устаревшим значением | [app/blueprints/applications.py:338-352](app/blueprints/applications.py) | Объединить в RPC |
| 13 | **LOW** | Качество | [api_handle_application()](app/blueprints/applications.py:416) — смешение ролей: route handler + внутренняя функция для batch | [app/blueprints/applications.py:416](app/blueprints/applications.py) | Вынести бизнес-логику в сервис |
| 14 | **LOW** | Безопасность | [api_reopen_application()](app/__init__.py:347-350) без @rate_limit — вектор DoS | [app/__init__.py:347-350](app/__init__.py) | Добавить @rate_limit |
| 15 | **LOW** | Качество | [apply_selected()](app/blueprints/applications.py:240) — при applied==0 всегда одно сообщение, даже при ошибках | [app/blueprints/applications.py:240](app/blueprints/applications.py) | Добавить счётчик ошибок |
| 16 | **LOW** | Качество | [unapply_job()](app/blueprints/applications.py:248-255) использует DELETE, а [api_withdraw_application()](app/blueprints/applications.py:278-362) — PATCH->withdrawn. Два механизма отзыва | [app/blueprints/applications.py:250,268](app/blueprints/applications.py) | Унифицировать механизм отзыва |

---

## Общая сводка

| Файл | CRITICAL | HIGH | MEDIUM | LOW | Всего |
|------|----------|------|--------|-----|-------|
| [admin.py](app/blueprints/admin.py) | 0 | 2 | 7 | 5 | **14** |
| [applications.py](app/blueprints/applications.py) | 1 | 4 | 7 | 4 | **16** |
| **ИТОГО** | **1** | **6** | **14** | **9** | **30** |

---

## Топ-10 проблем

| Ранг | Серьёзность | Файл:Строка | Проблема |
|------|------------|-------------|----------|
| 1 | **CRITICAL** | [applications.py:187](app/blueprints/applications.py) | apply_selected() обходит RPC apply_job_atomic — blacklist, слоты, своё задание |
| 2 | **HIGH** | [applications.py:280](app/blueprints/applications.py) | api_withdraw_application() — 6 запросов без транзакции, current_workers в минус |
| 3 | **HIGH** | [applications.py:571](app/blueprints/applications.py) | cancel_application() — неатомарна: race condition на current_workers |
| 4 | **HIGH** | [applications.py:437](app/blueprints/applications.py) | accept: rejected->pending PATCH вне RPC — потеря данных при сбое |
| 5 | **HIGH** | [applications.py:571](app/blueprints/applications.py) | cancel_application() не проверяет статус — повторная отмена |
| 6 | **HIGH** | [admin.py:100](app/blueprints/admin.py) | Админ может понизить свою роль — само-лок-аут |
| 7 | **HIGH** | [admin.py:462](app/blueprints/admin.py) | Дублирование эндпоинтов верификации с разными привилегиями |
| 8 | **MEDIUM** | [applications.py:397](app/blueprints/applications.py) | my_applications() раскрывает phone работодателям |
| 9 | **MEDIUM** | [admin.py:27](app/blueprints/admin.py) | Статистика дашборда limit=1000 — неверные данные |
| 10 | **MEDIUM** | [applications.py:376](app/blueprints/applications.py) | my_applications() без пагинации |

---

## Общие паттерны проблем (cross-cutting concerns)

### 1. Неатомарные операции — доминирующий паттерн (6 проблем)

Самая критичная группа. Неатомарные последовательности HTTP-запросов к PostgREST без транзакционной защиты:

- [applications.py:280-362](app/blueprints/applications.py) — `api_withdraw_application()`: 6 запросов
- [applications.py:571-637](app/blueprints/applications.py) — `cancel_application()`: 5 запросов
- [applications.py:437-441](app/blueprints/applications.py) — accept rejected: PATCH вне RPC
- [admin.py:301-308](app/blueprints/admin.py) — `delete_skill()`: 3 DELETE без транзакции
- [admin.py:103,141](app/blueprints/admin.py) — `update_user_role/job_status` без проверки результата

**Рекомендация:** Создать RPC: `withdraw_application_atomic`, `cancel_worker_atomic`, `delete_skill_cascade`. Проект уже использует RPC для accept/reject/apply — распространить паттерн.

### 2. Обход бизнес-правил через альтернативные эндпоинты (3 проблемы)

- [applications.py:187-243](app/blueprints/applications.py) — `apply_selected()` без RPC
- [applications.py:248-275](app/blueprints/applications.py) — `unapply` используют DELETE вместо withdraw
- [admin.py:462-494](app/blueprints/admin.py) — два эндпоинта верификации

**Рекомендация:** Все мутации через единые RPC-процедуры. Никакой альтернативной бизнес-логики.

### 3. Раскрытие конфиденциальных данных (2 проблемы)

- [applications.py:397-402](app/blueprints/applications.py) — `worker_contacts` включает phone
- [applications.py:376-378](app/blueprints/applications.py) — запрос включает phone в select

**Рекомендация:** Whitelist-подход: явно перечислять раскрываемые поля.

### 4. Отсутствие пагинации (3 проблемы)

- [admin.py:51](app/blueprints/admin.py) — пользователи: limit=100
- [admin.py:65](app/blueprints/admin.py) — задания: limit=100
- [applications.py:376-378](app/blueprints/applications.py) — отклики: без limit

**Рекомендация:** Стандартная пагинация `?page=N&per_page=50`.

### 5. Непоследовательные декораторы vs ручные проверки (3 проблемы)

- [applications.py:369](app/blueprints/applications.py) — ручная проверка роли
- [applications.py:416](app/blueprints/applications.py) — ручная проверка владения
- [__init__.py:335-350](app/__init__.py) — accept/reject/reopen без @role_required

**Рекомендация:** Использовать @employer_required, убрать ручные проверки.

### 6. Смешение бизнес-логики и route-обработчиков (2 проблемы)

- [applications.py:416-504](app/blueprints/applications.py) — `api_handle_application()` и route handler и внутренняя функция
- [applications.py:85-182](app/blueprints/applications.py) — `_apply_job_fallback()`: 100 строк в blueprint

**Рекомендация:** Вынести в `app/services/application_service.py`.

### 7. Избыточное @login_required + @admin_required

[admin_required](app/decorators.py:103-115) уже включает проверку `_is_authenticated()`. Двойная проверка сессии и лишний запрос к БД.

**Рекомендация:** Убрать @login_required где есть @admin_required/@employer_required.

---

## Рекомендация

**NEEDS CHANGES** — 1 CRITICAL и 6 HIGH проблем требуют обязательного исправления.

### Ключевые приоритеты:

1. **CRITICAL — Обход бизнес-правил массовым откликом** [applications.py:187](app/blueprints/applications.py) — `apply_selected()` позволяет заблокированным пользователям подавать заявки. Немедленное исправление.

2. **HIGH — Неатомарный withdraw** [applications.py:280](app/blueprints/applications.py) — 6-шаговая операция без транзакции. Требует RPC `withdraw_application_atomic`.

3. **HIGH — Неатомарный cancel** [applications.py:571](app/blueprints/applications.py) — двойная отмена -> отрицательный current_workers. Требует RPC `cancel_worker_atomic`.

4. **HIGH — Потеря rejected-статуса при accept** [applications.py:437](app/blueprints/applications.py) — rejected->pending вне RPC с риском потери данных.

5. **HIGH — Само-лок-аут админа** [admin.py:100](app/blueprints/admin.py) — отсутствие защиты от изменения собственной роли.

### Позитивные моменты:

- Все админские эндпоинты защищены @admin_required (кроме /api/health)
- Проект использует атомарные RPC: accept_application, reject_application, delete_user_cascade, delete_job_cascade
- [bulk_delete_skills()](app/blueprints/admin.py:313-362) — хороший пример батчевых операций через in.()
- Хорошее логирование ошибок RPC с контекстом (user_id, status_code, text)

### Сравнение с предыдущими этапами:

| Этап | Файлов | CRITICAL | HIGH | MEDIUM | LOW | Всего |
|-------|--------|----------|------|--------|-----|-------|
| Stage 1 (Infra) | 15 | 2 | 13 | 31 | 17 | 63 |
| Stage 2-A (Auth/Jobs) | 3 | 0 | 4 | 13 | 13 | 30 |
| **Stage 2-B (Admin/Apps)** | **2** | **1** | **6** | **14** | **9** | **30** |
| **Всего** | **20** | **3** | **23** | **58** | **39** | **123** |

Stage 2-B показывает схожий профиль со Stage 2-A: доминируют неатомарные операции и обход бизнес-правил. Паттерн системный — требуется создание недостающих RPC-процедур и унификация route-обработчиков.

Stage 2-B показывает схожий профиль проблем со Stage 2-A: доминируют неатомарные операции и обход бизнес-правил. Паттерн системный — требуется создание недостающих RPC-процедур и унификация route-обработчиков.
