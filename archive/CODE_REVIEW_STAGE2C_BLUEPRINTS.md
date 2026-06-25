# Этап 2-C: Ревью оставшихся blueprint'ов

> **Дата:** 2026-06-22 | **Контекст:** [`CODE_REVIEW_CONTEXT.md`](docs/CODE_REVIEW_CONTEXT.md), [`STAGE1_INFRA.md`](docs/CODE_REVIEW_STAGE1_INFRA.md), [`STAGE2A_BLUEPRINTS.md`](docs/CODE_REVIEW_STAGE2A_BLUEPRINTS.md), [`STAGE2B_BLUEPRINTS.md`](docs/CODE_REVIEW_STAGE2B_BLUEPRINTS.md)  
> **Охват:** 8 файлов — [`profile.py`](app/blueprints/profile.py) (~9K), [`chat.py`](app/blueprints/chat.py) (~10K), [`notifications.py`](app/blueprints/notifications.py) (~9K), [`ratings.py`](app/blueprints/ratings.py) (~14K), [`employers.py`](app/blueprints/employers.py) (~10K), [`favorites.py`](app/blueprints/favorites.py) (~6K), [`blacklist.py`](app/blueprints/blacklist.py) (~2.7K), [`seo.py`](app/blueprints/seo.py) (~0.6K)  
> **Метод:** Статический анализ с выборочной верификацией через [`utils.py`](app/utils.py), [`notification_service.py`](app/services/notification_service.py), [`decorators.py`](app/decorators.py)

---

## 1. [`app/blueprints/profile.py`](app/blueprints/profile.py)

### Найдено проблем: 5

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **MEDIUM** | Безопасность | `change_password()` валидирует пароль только на `len >= 6`, без требований к сложности (цифры, спецсимволы, регистр). Аналогично проблеме auth.py #2 | [`profile.py:148`](app/blueprints/profile.py) | Добавить проверку: минимум 1 цифра, 1 заглавная, 1 спецсимвол, длина >= 8 |
| 2 | **MEDIUM** | Корректность | `update_profile()` строка 58-59: `except ValueError: pass` — молча игнорирует некорректный `desired_payment`. Пользователь не узнает, что поле не сохранено | [`profile.py:58-59`](app/blueprints/profile.py) | `flash('Некорректная сумма желаемой оплаты', 'warning')` в except-блоке |
| 3 | **LOW** | Корректность | `delete_photo()` не проверяет `resp.ok` после PATCH — всегда flash success, даже при ошибке БД | [`profile.py:112`](app/blueprints/profile.py) | Добавить `if resp.ok: flash('Фото удалено', 'success') else: flash('Ошибка удаления', 'danger')` |
| 4 | **LOW** | Корректность | `verify_employer()` строка 207: не проверяет `resp.ok` после PATCH — всегда flash success | [`profile.py:207`](app/blueprints/profile.py) | Аналогично #3: проверить `resp.ok` перед flash |
| 5 | **LOW** | Качество | `verify_employer()` строка 204: `flash(f'Ошибка при загрузке: {str(e)}')` — раскрывает внутреннее исключение пользователю (утечка информации) | [`profile.py:204`](app/blueprints/profile.py) | `flash('Ошибка при загрузке документа. Попробуйте позже.', 'danger')` |

---

## 2. [`app/blueprints/chat.py`](app/blueprints/chat.py)

### Найдено проблем: 6

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **MEDIUM** | Корректность | `send_message()` — проверка статуса задания `!= 'completed'` (стр. 126) блокирует отправку сообщений для заданий в статусе `accepted`, `in_progress` и любых других, кроме `completed`. Бизнес-правило спорное: чат нужен ДО завершения задания, а не после. Но статус заявки `accepted` уже проверен (стр. 119). Сейчас чат работает только для `completed`-заданий | [`chat.py:122-132`](app/blueprints/chat.py) | Пересмотреть: разрешить чат для accepted-заявок независимо от статуса задания. Либо добавить `in_progress` в список разрешённых статусов |
| 2 | **MEDIUM** | Производительность | `send_message()` делает 3 последовательных HTTP-запроса к PostgREST перед отправкой (applications GET + jobs GET + messages POST) + Redis publish + notification create. Суммарно 5+ внешних вызовов на одно сообщение | [`chat.py:108-175`](app/blueprints/chat.py) | Кэшировать проверку доступа (applications GET) с TTL 5 сек. Объединить проверку applications + jobs в один запрос через `select=worker_id,job_id,status,job:jobs(employer_id,status)` |
| 3 | **LOW** | Корректность | `delete_chats()` удаляет только сообщения (`DELETE messages`), но не затрагивает саму заявку (`applications`). Название вводит в заблуждение: функция очищает историю чата, а не удаляет чат | [`chat.py:239`](app/blueprints/chat.py) | Переименовать в `clear_chat_history` или добавить документирующий комментарий |
| 4 | **LOW** | Производительность | `delete_chats()` — цикл с индивидуальным `DELETE messages?application_id=eq.{aid}` для каждого чата. При 10 чатах — 10 запросов | [`chat.py:224-240`](app/blueprints/chat.py) | Батчевый DELETE: `messages?application_id=in.({ids})` |
| 5 | **LOW** | Качество | `chat_new()` строка 81: фильтр `job.employer_id=eq.{user_id}` — PostgREST embedded resource фильтрация. Если `job` join возвращает null (нет задания у заявки), фильтр молча не сработает, пользователь получит «Чат недоступен» | [`chat.py:81-83`](app/blueprints/chat.py) | Добавить явную проверку на null после запроса |
| 6 | **LOW** | Качество | `send_message()` строка 170: `session.get('username', 'Пользователь')` — поле `username` отсутствует в таблице `profiles` согласно модели данных. Может всегда быть «Пользователь» | [`chat.py:170`](app/blueprints/chat.py) | Использовать `session.get('full_name')` или `profile['full_name']` |

---

## 3. [`app/blueprints/notifications.py`](app/blueprints/notifications.py)

### Найдено проблем: 6

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **HIGH** | Корректность | `notifications()` — при загрузке страницы все непрочитанные уведомления автоматически помечаются как прочитанные (стр. 44-46). Пользователь может открыть страницу, не успеть прочитать все уведомления, но они уже будут `is_read=True`. Потеря visibility | [`notifications.py:43-46`](app/blueprints/notifications.py) | Убрать автоматическую отметку. Отмечать прочитанными только при явном действии (клик, scroll, или отдельный API-вызов) |
| 2 | **MEDIUM** | Корректность | `notifications()` — очистка orphaned-приглашений через `message=ilike.*{job_id}*` (стр. 41). Поиск подстроки в тексте уведомления хрупкий: job_id `abc123` совпадёт с `abc1234`. Аналогично проблеме jobs.py #3 | [`notifications.py:41`](app/blueprints/notifications.py) | Добавить колонку `job_id` в таблицу `notifications`, использовать `DELETE notifications?job_id=eq.{job_id}` |
| 3 | **MEDIUM** | Производительность | `notifications()` — при наличии приглашений делает `supabase_admin_request` для проверки существования заданий (стр. 38) и потенциально DELETE для каждого осиротевшего (стр. 41). Замедляет загрузку страницы уведомлений | [`notifications.py:36-41`](app/blueprints/notifications.py) | Вынести очистку в фоновую задачу Celery (запускать раз в час) |
| 4 | **LOW** | Качество | `push_vapid_public_key()` строка 178: `import os as _os` внутри функции — нестандартный паттерн, дублирование импорта | [`notifications.py:178`](app/blueprints/notifications.py) | Перенести `import os` на уровень модуля |
| 5 | **LOW** | Качество | `api_save_preference()` строка 157: `from app.services.notification_service import get_user_prefs` — дублирующий импорт внутри функции (уже импортирован на уровне модуля через `notification_service`, хотя и не напрямую) | [`notifications.py:157`](app/blueprints/notifications.py) | Добавить `get_user_prefs` в импорт на строке 8-11, убрать локальный импорт |
| 6 | **LOW** | Безопасность | `push_vapid_public_key()` возвращает `VAPID_PUBLIC_KEY` любому аутентифицированному пользователю. Публичный ключ предназначен для раскрытия, но эндпоинт не имеет практического ограничения — OK для VAPID | [`notifications.py:176-180`](app/blueprints/notifications.py) | Оставить как есть (VAPID public key — не секрет) |

---

## 4. [`app/blueprints/ratings.py`](app/blueprints/ratings.py)

### Найдено проблем: 7

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **HIGH** | Корректность | `upsert_rating()` — обновление агрегированного рейтинга (`update_rating`, стр. 190) происходит ПОСЛЕ успешного UPSERT, но неатомарно: если `update_rating` упадёт (ошибка сети, таймаут), оценка сохранена, а `profiles.rating` устарел. При этом `update_rating` внутри ([`utils.py:1287-1295`](app/utils.py)) делает GET+PATCH — ещё одна неатомарная пара: между GET и PATCH может добавиться другая оценка | [`ratings.py:190`](app/blueprints/ratings.py) -> [`utils.py:1287-1295`](app/utils.py) | Создать RPC `upsert_rating_atomic`, которая в одной транзакции: вставляет/обновляет ratings + пересчитывает и обновляет profiles.rating |
| 2 | **MEDIUM** | Производительность | `get_job_ratings()` делает 2 запроса для одного и того же задания: ratings с JOIN'ами (стр. 13-15) + ratings для подсчёта среднего (стр. 20-23). Среднее можно вычислить из первого запроса | [`ratings.py:13-27`](app/blueprints/ratings.py) | Убрать второй запрос, вычислять `avg_rating` из `ratings` списка первого запроса |
| 3 | **MEDIUM** | Производительность | `get_completed_jobs_for_rating()` — если RPC `get_completed_jobs_between` не существует (status != 200), fallback делает до 3 запросов: GET applications + GET jobs + batch GET applications. При отсутствии RPC — деградация производительности | [`ratings.py:213-247`](app/blueprints/ratings.py) | Гарантировать наличие RPC через миграцию. Убрать fallback или заменить на упрощённый fallback с одним batch-запросом |
| 4 | **MEDIUM** | Корректность | `upsert_rating()` — проверка существования (GET на стр. 148-151) и последующий INSERT (стр. 164) неатомарны: два конкурентных запроса могут оба увидеть "не существует" и оба попытаться INSERT. Код обрабатывает конфликт уникальности (стр. 168-180) с повторной попыткой, но это добавляет 2 лишних HTTP-запроса в худшем случае | [`ratings.py:148-180`](app/blueprints/ratings.py) | Использовать `Prefer: resolution=merge-duplicates` заголовок PostgREST для UPSERT (если поддерживается), либо RPC `upsert_rating` |
| 5 | **LOW** | Качество | `rate_workers_page()` — проверка `job['employer_id'] != user_id` (стр. 327) дублирует фильтр в запросе `employer_id=eq.{user_id}` (стр. 309). Защита defence-in-depth — ок, но избыточно | [`ratings.py:327`](app/blueprints/ratings.py) | Оставить как defence-in-depth, добавить комментарий |
| 6 | **LOW** | Корректность | `get_user_rating()` строка 52: возвращает полный `resp.json()` в поле `ratings` (все рейтинги пользователя без JOIN'ов). API отдаёт сырые данные без имён оценщиков | [`ratings.py:52`](app/blueprints/ratings.py) | Добавить `select=*,rater:profiles!rater_user_id(full_name)` для консистентности с `get_user_rating_details` |
| 7 | **LOW** | Качество | `upsert_rating()` строка 144: `'updated_at': 'now()'` — строковое значение, а не вызов SQL-функции. PostgREST не интерпретирует строки как SQL. Поле `updated_at` не будет заполнено автоматически | [`ratings.py:144`](app/blueprints/ratings.py) | Убрать `updated_at` из данных (должен обновляться триггером БД) или использовать RPC с `NOW()` |

---

## 5. [`app/blueprints/employers.py`](app/blueprints/employers.py)

### Найдено проблем: 6

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **HIGH** | Корректность | `employers_list()` — фильтрация чёрного списка выполняется в Python (стр. 46-51) после получения страницы из БД с limit/offset. Страница из 20 записей может содержать 0-5 после фильтрации. Пагинация сломана: пользователи видят неполные страницы, часть работодателей пропускается. Аналогично проблеме jobs.py #1 | [`employers.py:46-51`](app/blueprints/employers.py) | Перенести фильтрацию чёрного списка в БД: `profiles?id=not.in.({blocked_ids})` как дополнительный фильтр к основному запросу, либо RPC `get_visible_employers` |
| 2 | **MEDIUM** | Корректность | `employers_list()` — `total_count` и `total_pages` вычисляются ПОСЛЕ Python-фильтрации (строка 77-78) от количества уже отфильтрованных записей, а не от реального общего количества. Пагинация показывает меньше страниц, чем есть на самом деле | [`employers.py:77-78`](app/blueprints/employers.py) | Использовать `content-range` заголовок от PostgREST для общего количества ДО фильтрации |
| 3 | **LOW** | Корректность | `toggle_favorite()` — check-then-act race condition: между проверкой существования (GET, стр. 153-154) и DELETE/POST (стр. 158-166) другой запрос может изменить состояние. Supabase предотвратит дубликат (unique constraint), но DELETE может удалить чужую запись (маловероятно — фильтр по user_id защищает) | [`employers.py:153-166`](app/blueprints/employers.py) | Использовать UPSERT-семантику через `Prefer: resolution=merge-duplicates`, либо RPC `toggle_favorite_atomic` |
| 4 | **LOW** | Производительность | `employer_detail()` строка 133: `job_id=in.({job_ids})` — при большом количестве открытых заданий (>100) URL может превысить лимит PostgREST (~8KB). Аналогично проблеме jobs.py #10 | [`employers.py:133-135`](app/blueprints/employers.py) | Разбивать на батчи по 50 ID при большом количестве |
| 5 | **LOW** | Безопасность | `check_employer_favorite_api()` строка 245: `str(e)` в ответе клиенту — утечка информации об исключении | [`employers.py:245`](app/blueprints/employers.py) | `current_app.logger.error(...)`, вернуть `jsonify({'success': False, 'error': 'Внутренняя ошибка сервера'})` |
| 6 | **LOW** | Качество | `employers_list()` — нет валидации UUID для `skills` (строка 16), но параметр не используется в запросе (нет фильтрации по навыкам работодателей). Мёртвый параметр | [`employers.py:16`](app/blueprints/employers.py) | Удалить параметр `skills` или реализовать фильтрацию через `user_skills` |

---

## 6. [`app/blueprints/favorites.py`](app/blueprints/favorites.py)

### Найдено проблем: 5

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **MEDIUM** | Корректность | `check_favorite_api()` строка 116: запрос `favorites?user_id=eq.{user_id}&target_id=eq.{worker_id}` БЕЗ фильтра `favorite_type`. Вернёт `is_favorited=True` даже если это favourite типа `employer` (для работодателя), а не `worker`. Ложное срабатывание при проверке трудника, если тот же `target_id` есть в избранном другого типа | [`favorites.py:116`](app/blueprints/favorites.py) | Добавить `&favorite_type=eq.worker` в запрос |
| 2 | **LOW** | Корректность | `add_favorite()` — жёстко задан `favorite_type='worker'` (стр. 50). Не работает для добавления работодателей в избранное (для этого есть отдельный эндпоинт в employers.py). Но если вызвать этот эндпоинт с target_id работодателя — создаст запись с неверным типом | [`favorites.py:50`](app/blueprints/favorites.py) | Добавить проверку роли target пользователя или принимать `favorite_type` как параметр |
| 3 | **LOW** | Корректность | `add_favorite()` и `remove_favorite()` не проверяют `resp.ok` для POST/DELETE, не имеют try/except. Ошибка БД — 500 без диагностики | [`favorites.py:50-53`](app/blueprints/favorites.py), [`favorites.py:59`](app/blueprints/favorites.py) | Добавить проверку `resp.ok` и `flash` при ошибке |
| 4 | **LOW** | Безопасность | `add_favorite()` строка 50: нет валидации UUID для `target_id`. Злоумышленник может вставить произвольную строку в URL. Supabase отклонит не-UUID, но ошибка будет некрасивой | [`favorites.py:50`](app/blueprints/favorites.py) | Добавить `uuid.UUID(target_id)` валидацию |
| 5 | **LOW** | Производительность | `favorites()` делает 3 запроса для работодателей (favorites + invitations) и 2 для трудников (favorites + job_favorites). Для страницы с небольшим объёмом данных — приемлемо, но можно объединить batch-запросом | [`favorites.py:17-42`](app/blueprints/favorites.py) | Рассмотреть объединение в 1 batch-запрос через `Accept: application/vnd.pgrst.array+json` (если поддерживается) |

---

## 7. [`app/blueprints/blacklist.py`](app/blueprints/blacklist.py)

### Найдено проблем: 4

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **LOW** | Корректность | `block_user()` строка 49: не проверяет, заблокирован ли уже пользователь. При дубликате Supabase вернёт 409/unique violation, но пользователь увидит "Ошибка блокировки" без пояснения причины | [`blacklist.py:49`](app/blueprints/blacklist.py) | Добавить предварительную проверку: `GET blacklists?user_id=eq.{user_id}&blocked_user_id=eq.{target_id}`. При дубликате: `flash('Пользователь уже в чёрном списке', 'warning')` |
| 2 | **LOW** | Корректность | `unblock_user()` строка 66: не проверяет, существует ли блокировка перед DELETE. DELETE несуществующей записи возвращает 204/200 — пользователь не узнает, что разблокировка не имела эффекта | [`blacklist.py:66`](app/blueprints/blacklist.py) | Проверить `resp.ok` и `content-range` (количество удалённых записей) или предварительно GET |
| 3 | **LOW** | Безопасность | `block_user()` и `unblock_user()` — нет валидации UUID для `user_id` | [`blacklist.py:45`](app/blueprints/blacklist.py), [`blacklist.py:62`](app/blueprints/blacklist.py) | Добавить `uuid.UUID(user_id)` валидацию |
| 4 | **LOW** | Качество | `blacklist()` строка 33: использует `profiles!blacklists_blocked_user_id_fkey` — жёсткая привязка к имени внешнего ключа. При переименовании FK в миграциях — сломается без ошибки компиляции | [`blacklist.py:33`](app/blueprints/blacklist.py) | Использовать алиас `blocked:profiles!blocked_user_id` (без имени FK), если PostgREST поддерживает |

---

## 8. [`app/blueprints/seo.py`](app/blueprints/seo.py)

### Найдено проблем: 2

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **LOW** | Корректность | `sitemap()` — жёстко закодирован список из 3 страниц. Динамический контент (задания, профили) не индексируется поисковиками | [`seo.py:13-17`](app/blueprints/seo.py) | Добавить динамические URL: открытые задания (`/jobs?page=N`), профили публичных работодателей |
| 2 | **LOW** | Качество | `robots()` — жёстко закодирован домен `trudnik.ru`. При деплое на другой домен (staging, preview) sitemap будет указывать на неверный URL | [`seo.py:8`](app/blueprints/seo.py) | Использовать `url_for('seo.sitemap', _external=True)` или `current_app.config['WORKER_SITE_URL']` |

---

## Общая сводка

| Файл | CRITICAL | HIGH | MEDIUM | LOW | Всего |
|------|----------|------|--------|-----|-------|
| [`profile.py`](app/blueprints/profile.py) | 0 | 0 | 2 | 3 | **5** |
| [`chat.py`](app/blueprints/chat.py) | 0 | 0 | 2 | 4 | **6** |
| [`notifications.py`](app/blueprints/notifications.py) | 0 | 1 | 2 | 3 | **6** |
| [`ratings.py`](app/blueprints/ratings.py) | 0 | 1 | 3 | 3 | **7** |
| [`employers.py`](app/blueprints/employers.py) | 0 | 1 | 1 | 4 | **6** |
| [`favorites.py`](app/blueprints/favorites.py) | 0 | 0 | 1 | 4 | **5** |
| [`blacklist.py`](app/blueprints/blacklist.py) | 0 | 0 | 0 | 4 | **4** |
| [`seo.py`](app/blueprints/seo.py) | 0 | 0 | 0 | 2 | **2** |
| **ИТОГО** | **0** | **3** | **11** | **27** | **41** |

---

## Топ-10 проблем (все файлы)

| # | Файл | Серьёзность | Проблема |
|---|------|------------|----------|
| 1 | [`notifications.py:43-46`](app/blueprints/notifications.py) | HIGH | Автоматическая отметка всех уведомлений как прочитанных при загрузке страницы — потеря visibility |
| 2 | [`ratings.py:190`](app/blueprints/ratings.py) -> [`utils.py:1287-1295`](app/utils.py) | HIGH | Неатомарное обновление агрегированного рейтинга: оценка сохранена, profiles.rating может быть устаревшим |
| 3 | [`employers.py:46-51`](app/blueprints/employers.py) | HIGH | Фильтрация чёрного списка в Python ломает пагинацию (страницы неполные, данные пропускаются) |
| 4 | [`profile.py:148`](app/blueprints/profile.py) | MEDIUM | Валидация пароля без требований к сложности (только длина >= 6) |
| 5 | [`chat.py:122-132`](app/blueprints/chat.py) | MEDIUM | Отправка сообщений разрешена только для completed-заданий — чат недоступен во время выполнения |
| 6 | [`notifications.py:41`](app/blueprints/notifications.py) | MEDIUM | Очистка orphaned-уведомлений через ilike по тексту — хрупкий паттерн (ложные срабатывания) |
| 7 | [`ratings.py:13-27`](app/blueprints/ratings.py) | MEDIUM | Дублирующий запрос для подсчёта среднего рейтинга — избыточный HTTP-вызов |
| 8 | [`ratings.py:148-180`](app/blueprints/ratings.py) | MEDIUM | Неатомарный UPSERT с retry-логикой — до 3 HTTP-запросов на одну операцию |
| 9 | [`employers.py:77-78`](app/blueprints/employers.py) | MEDIUM | Неверный подсчёт total_pages из-за пост-фильтрации в Python |
| 10 | [`favorites.py:116`](app/blueprints/favorites.py) | MEDIUM | `check_favorite_api` без фильтра `favorite_type` — ложные срабатывания |

---

## Общие паттерны проблем (cross-cutting concerns)

### 1. Неатомарные операции (3 файла)

Проблема присутствует в [`ratings.py`](app/blueprints/ratings.py), [`employers.py`](app/blueprints/employers.py), [`favorites.py`](app/blueprints/favorites.py). Наиболее критична в ratings — сохранение оценки и обновление агрегированного рейтинга выполняются раздельными запросами. При сбое второго — данные рассинхронизируются.

**Системная рекомендация:** создать набор RPC-процедур для атомарных операций: `upsert_rating_atomic`, `toggle_favorite_atomic`, `toggle_blacklist_atomic`. Это решит проблему во всех blueprint'ах единообразно.

### 2. Отсутствие валидации UUID (5 файлов)

[`employers.py`](app/blueprints/employers.py), [`favorites.py`](app/blueprints/favorites.py), [`blacklist.py`](app/blueprints/blacklist.py), [`chat.py`](app/blueprints/chat.py) не валидируют UUID в параметрах маршрута. Только [`profile.py:217`](app/blueprints/profile.py) делает `uuid.UUID(user_id)`. Непоследовательно.

**Системная рекомендация:** создать декоратор `@validate_uuid` для параметров маршрута или добавить проверку в начало каждого эндпоинта, принимающего user_id/job_id.

### 3. Отсутствие проверки resp.ok (6 файлов)

Множество эндпоинтов не проверяют успешность ответа от PostgREST перед тем как показать flash success или redirect. Пользователь видит подтверждение операции, которая на самом деле не выполнилась.

**Затронутые файлы:** [`profile.py:112,207`](app/blueprints/profile.py), [`favorites.py:50,59`](app/blueprints/favorites.py), [`employers.py:158,162`](app/blueprints/employers.py), [`blacklist.py:49,66`](app/blueprints/blacklist.py), [`chat.py:239`](app/blueprints/chat.py).

**Системная рекомендация:** ввести утилиту `assert_supabase_ok(resp, error_message)` или использовать декоратор/контекстный менеджер для единообразной обработки.

### 4. Бизнес-логика в route-обработчиках

Все 8 файлов реализуют бизнес-логику непосредственно в обработчиках маршрутов. Сервисный слой используется только в [`notifications.py`](app/blueprints/notifications.py) (через `NotificationService`) и частично в [`ratings.py`](app/blueprints/ratings.py) (через `update_rating` из utils).

**Системная рекомендация:** вынести бизнес-логику в сервисы: `ProfileService`, `ChatService`, `RatingsService`, `FavoritesService`, `BlacklistService`. Это улучшит тестируемость и уменьшит дублирование между blueprint'ами (например, проверка владения заявкой в chat.py дублируется 4 раза).

### 5. Утечка информации через сообщения об ошибках

Несколько эндпоинтов возвращают `str(e)` клиенту при исключениях: [`profile.py:204`](app/blueprints/profile.py), [`employers.py:245`](app/blueprints/employers.py), [`favorites.py:87`](app/blueprints/favorites.py), [`favorites.py:103`](app/blueprints/favorites.py).

**Системная рекомендация:** логировать исключение через `current_app.logger.error()`, возвращать клиенту обобщённое сообщение "Внутренняя ошибка сервера".

### 6. Сравнение с предыдущими этапами

| Паттерн | Stage 2A (auth/jobs) | Stage 2B (admin/apps) | Stage 2C (текущий) |
|---------|---------------------|----------------------|---------------------|
| Неатомарные операции | 5 проблем | 8 проблем | 3 проблемы (улучшение) |
| Race conditions | 2 проблемы | 2 проблемы | 1 проблема (улучшение) |
| Python-фильтрация вместо БД | 1 проблема | 0 | 1 проблема (employers) |
| Отсутствие проверки resp.ok | 2 проблемы | 3 проблемы | 7 проблем (хуже) |
| N+1 запросы | 2 проблемы | 2 проблемы | 1 проблема (улучшение) |
| Валидация UUID | 0 (была в jobs) | 1 проблема | 4 проблемы (хуже) |
| Утечка информации | 0 | 1 проблема | 4 проблемы (хуже) |

**Вывод:** группа C показывает меньше критических проблем с атомарностью (урок из Stage 2A/2B усвоен — chat.py использует проверки перед операциями, ratings.py обрабатывает конфликты), но страдает от небрежности в проверке ответов и валидации входных данных. Это объяснимо: эти blueprint'ы писались раньше и не были отрефакторены под стандарты, внедрённые в auth/jobs/admin.

---

## Рекомендация

**APPROVE WITH SUGGESTIONS** — критические проблемы отсутствуют. Три HIGH-проблемы требуют внимания:

1. **Авто-отметка уведомлений прочитанными** ([`notifications.py:43-46`](app/blueprints/notifications.py)) — UX-баг, требующий немедленного исправления
2. **Неатомарное обновление рейтинга** ([`ratings.py:190`](app/blueprints/ratings.py)) — требует RPC, но не критичен (rating можно пересчитать)
3. **Сломанная пагинация работодателей** ([`employers.py:46-51`](app/blueprints/employers.py)) — видимый пользователю баг

Остальные 38 проблем — LOW/MEDIUM, могут исправляться постепенно.
