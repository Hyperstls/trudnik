Топ-9 критических проблем (с указанием конкретных файлов/строк в документе):
admin_panel — 8 последовательных count=exact запросов (нужен 1 RPC с GROUP BY)
cache_for — in-memory dict, не работает между gunicorn-воркерами
active_connections в WebSocket-сервере — блокирует горизонтальное масштабирование WS
threading.Thread в apply_job — fire-and-forget потоки теряются при деплое (нужен transactional outbox)
JWT mint на каждый PostgREST-запрос (CPU + Redis SETEX на каждый HTTP)
Циклические импорты через from app import _redis_cache_*
Глобальный app = create_app() на уровне модуля — side-effects при импорте, блокирует --preload
Отсутствие Unit of Work — fallback-пути с TOCTOU race condition
50+ bare except Exception как культурный паттерн
Дорожная карта: 6 фаз, 13 недель при одном инженере. Фаза 0 (1 нед., инфра-уборка) и Фаза 1 (2 нед., исключения + error handler) — низкий риск, быстрый выигрыш. Фазы 2–3 — Repository + Use Cases, основная переработка. Фаза 4 — multi-replica WS. Фаза 5 — DI и Config dataclass.

Бонус — библиотеки. Must: Pydantic 2 (Command-объекты для Use Cases), pytest-flask. Should: Marshmallow, Tenacity, structlog. Could: Flask-Smorest/APIFlask (только для новых API-route), Redis Streams. SQLAlchemy 2 — не внедрять (PostgREST покрывает 95% сценариев).
 
1. Вердикт
Проект «Трудник» представляет собой функционально завершённый MVP платформы поиска временной подработки, развёрнутый в продакшн на платформе Amvera. Архитектура реализует несколько продвинутых паттернов (Circuit Breaker, transactional outbox, atomic RPC в PostgreSQL, PWA, WebSocket-уведомления), что говорит об опытной команде. Однако текущая кодовая база не готова к 10-кратному росту ни нагрузки, ни размера команды: критическая масса технического долга сосредоточена в трёх зонах — толстые Blueprints с замешанной в них бизнес-логикой, отсутствие Unit of Work над PostgREST, и состояние в памяти процесса, которое не переживает горизонтальное масштабирование.
Ключевые количественные индикаторы долга: файл app/blueprints/jobs.py содержит 1019 строк кода и 56 одновременных вызовов PostgREST и render_template в одном модуле; admin_panel() при tab=dashboard делает 8 последовательных HTTP-запросов count=exact к PostgREST; в кодовой базе встречается свыше 50 конструкций bare except Exception, которые маскируют ошибки вместо их обработки; декоратор cache_for использует in-memory dict, который не разделяется между gunicorn-воркерами и бесполезен при масштабировании. Эти проблемы не критичны при текущей нагрузке, но станут блокерами на следующих этапах роста.
Хорошая новость: основная «большая тройка» архитектурных решений (PostgREST как data-access слой, Celery для фоновых задач, отдельный FastAPI-процесс для WebSocket) выбрана корректно и не требует пересмотра. Рефакторинг сводится к перераспределению ответственности между существующими слоями (View → Use Case → Repository), введению нескольких недостающих инфраструктурных абстракций (Unit of Work, Redis-backed cache, кастомные исключения) и устранению нескольких циклических зависимостей. Всё это можно выполнить инкрементально, без больших взрывных миграций.
2. Контекст аудита
Аудит проводился по исходному коду проекта, переданному в виде RAR-архива (trudnik.rar). Анализ охватывает Python-кодовую базу объемом около 10 400 строк (без учёта тестов, архивов и сгенерированных артефактов), структуру директорий, конфигурацию Docker Compose, точки входа app.py / asgi.py и вспомогательный скриптовый слой. Вне зоны аудита остались: SQL-миграции (migrations/*.sql), security-аудит RLS-политик PostgreSQL, инфраструктура деплоя Amvera, а также фронтенд-часть (templates/, static/js/).
Технологический стек проекта характерен и важен для интерпретации находок. Backend построен на Flask 3.1 с Application Factory; в качестве data-access слоя выступает PostgREST v12.2.3 — HTTP-фасад над PostgreSQL, который заменяет традиционный ORM. Это означает, что в проекте нет SQLAlchemy, нет ORM-моделей, нет Unit of Work в его классическом виде; все обращения к данным — HTTP-вызовы к PostgREST с JWT-аутентификацией. Брокер сообщений — Redis; фоновые задачи — Celery 5.6; WebSocket-сервер вынесен в отдельный процесс на FastAPI и общается с Flask через Redis Pub/Sub. Деплой — Amvera (российский PaaS) с docker-compose для локальной разработки.
2.1. Метрики кодовой базы
| Метрика | Значение | Комментарий |
|---|---|---|
| Python LOC (app/) | ≈ 10 400 | Без учёта tests/, archive/, scripts/ |
| Blueprints | 14 | auth, profile, jobs, jobs_api, applications, chat, favorites, blacklist, notifications, admin, ratings, seo, employers |
| Services | 10 | notification, job, application, invitation, ratings, payment, push, email, storage, redis_publisher |
| Celery tasks | 4 модуля | email_tasks, push_tasks, maintenance_tasks, celery_app |
| Tests LOC | ≈ 21 000 | tests/ + tests_e2e/ — значительный объём, но много Selenium/E2E |
| SQL-миграция | 75+ | migrations/ + migrations/archive/ — большая история эволюции схемы |
| Routes (app-level) | ≈ 70 | Включая редиректы, API, health-checks |
| Bare except Exception | 50+ | Сосредоточены в blueprints/auth.py (13), admin.py (13), services/email_service.py (11) |
Объём тестов (21 000 строк) значительно превышает объём основного кода — это типично для проектов, где E2E/Selenium-тесты заменяют юнит-тесты из-за сильной связанности кода. Большая часть тестов — интеграционные (test_critical_gaps.py — 2159 строк, test_buttons_backend.py — 3230 строк), что косвенно подтверждает гипотезу о слабой изоляции слоёв: протестировать отдельный сервис без поднятия всего стека затруднительно.
3. Критические проблемы
В этом разделе перечислены проблемы в порядке, в котором они проявят себя при росте нагрузки или команды. Каждая проблема сопровождается указанием конкретного файла и строки, а также описанием сценария, при котором она приведёт к инциденту в продакшене. Это не полный список недостатков, а приоритизированный список «что сломается первым».
3.1. admin_panel: 8 последовательных count=exact запросов
Файл app/blueprints/admin.py, строки 47–103. При переходе администратора на вкладку dashboard маршрут admin_panel() выполняет восемь последовательных HTTP-запросов к PostgREST для подсчёта количества пользователей по ролям (worker, employer, admin), заданий по статусам (open, completed, cancelled) и ожидающих верификаций. Каждый запрос — отдельный round-trip к PostgREST, который в свою очередь делает отдельный SQL COUNT(*) в PostgreSQL. При текущем объёме данных это работает мгновенно, но при росте до 100 000 пользователей каждый COUNT начнёт занимать заметное время, а сумма восьми последовательных запросов — тем более. Кроме того, этот маршрут кешируется через cache_for, но кеш in-memory, поэтому каждый gunicorn-воркер выполняет свой набор из восьми запросов.
admin.py:47-103 — 8 count=exact запросов в одном route; должен быть один RPC get_admin_stats() с GROUP BY в PostgreSQL.
3.2. cache_for: in-memory кеш, не работающий между воркерами
Файл app/utils/postgrest_client.py, строки 249–275. Декоратор @cache_for(seconds=N) использует локальный словарь внутри замыкания. Это означает, что при запуске приложения через gunicorn с N воркерами каждый воркер имеет свой собственный кеш, и запросы к /api/skills и /api/religions (файл app/blueprints/jobs_api.py, строки 34 и 44) выполнят N раз полный HTTP-вызов к PostgREST вместо одного. При 4 воркерах и TTL 300 секунд это 4 запроса вместо 1 каждые 5 минут — не катастрофа, но паттерн «in-memory cache в WSGI-приложении» является антипаттерном и будет тиражироваться. Уже сейчас в jobs.py:79 (Redis-кеш для application_count) используется правильный подход через Redis; нужно лишь унифицировать.
3.3. active_connections: состояние в памяти WebSocket-сервера
Файл websocket_server/main.py, строка 54. Глобальный словарь active_connections: dict[str, WebSocket] = {} хранит все активные WS-соединения в памяти одного процесса. Это означает: (1) при рестарте WebSocket-сервера все пользователи теряют соединение и должны переподключиться; (2) при горизонтальном масштабировании (запуск двух реплик WS-сервера за load balancer) уведомление, опубликованное в Redis Pub/Sub, будет получено обеими репликами, но доставлено только тому пользователю, чьё соединение живо на конкретной реплике — то есть только половина пользователей получит пуш. Это блокирует масштабирование WebSocket-сервера. Решение — хранить соответствие user_id → server_id в Redis и маршрутизировать сообщения через Redis Streams или Redis Pub/Sub с шаблоном канала по server_id.
3.4. threading.Thread в apply_job: fire-and-forget в WSGI-процессе
Файл app/blueprints/applications.py, строки 80, 179, 251. В маршрутах apply_job, _apply_job_fallback и apply_selected для отправки уведомлений работодателю используется threading.Thread(target=_notify_employer, daemon=True).start(). Это работает, но имеет три проблемы: (1) при деплое новой версии процесса потоки убиваются вместе с процессом, и уведомления теряются; (2) при высокой нагрузке количество потоков растёт неконтролируемо, что увеличивает потребление памяти и риск GIL-конфликтов; (3) нет ретраев и нет observability. Правильное решение — использовать уже существующий transactional outbox (функция enqueue_notification, которая пишет в таблицу notification_outbox и обрабатывается Celery-воркером). В коде уже есть этот паттерн, но он не применяется в apply_job.
3.5. JWT mint на каждый PostgREST-запрос
Файл app/utils/postgrest_client.py, строки 319–339. Функция get_user_headers() вызывается при каждом postgrest_request() и заново подписывает JWT-токен через pyjwt.encode(), а также делает синхронный SETEX в Redis (utils/auth.py:103–108) для хранения jti. При типичной странице job_detail, которая делает 4–5 запросов к PostgREST, это 4–5 signing operations и 4–5 Redis-запросов только на аутентификацию. CPU-cost HS256-подписи невелик, но он суммируется. Решение — кешировать сгенерированный токен в session с TTL 4 минуты (при exp=300 секунд), обновлять только при истечении.
3.6. Циклические импорты через lazy import
В коде есть несколько мест, где для обхода циклических зависимостей используется локальный импорт внутри функций. Файл app/services/notification_service.py, строки 222 и 331: from app import _redis_cache_delete. Файл app/services/notification_service.py, строки 154–155: from app.tasks.email_tasks import send_email_notification. Файл app/blueprints/jobs.py, строка 79: from app import _redis_cache_get, _redis_cache_set. Эти конструкции не ломают продакшн, но они сигнализируют об архитектурной проблеме: модули нижнего уровня (services, tasks) зависят от модуля верхнего уровня (app), что инвертирует естественное направление зависимостей. Правильное решение — вынести _redis_cache_* в отдельный модуль app/cache.py, от которого зависит и app, и services.
3.7. Глобальный app = create_app() на уровне модуля
Файл app/__init__.py, строка 513. На уровне модуля выполняется app = create_app(), что приводит к side-effects при импорте модуля app: запускается _wait_for_postgrest, который блокирует поток до 30 секунд; происходит проверка PGRST_JWT_SECRET и логирование; инициализируется Redis-клиент. Это затрудняет тестирование (импорт app запускает приложение) и мешает горизонтальному масштабированию через gunicorn --preload, потому что _wait_for_postgrest выполняется в master-процессе и блокирует fork воркеров. Решение — убрать глобальный app, использовать фабрику с явным вызовом в app.py и asgi.py.
3.8. Отсутствие Unit of Work над PostgREST
PostgREST не предоставляет транзакций через REST API. Для обхода этого в проекте реализованы атомарные RPC-функции в PostgreSQL (apply_job_atomic, withdraw_application_atomic, accept_invitation_atomic), которые выполняют несколько операций в одной SQL-транзакции. Однако при недоступности RPC (например, миграция не применена) срабатывает fallback на неатомарный путь, что явно признаётся в комментариях как TOCTOU race condition (файл app/blueprints/applications.py, строки 86–182). Файл app/services/application_service.py, строки 73–96, содержит откровенный комментарий: «при сетевом сбое между PATCH задания и PATCH заявки возможна рассинхронизация». Это не теоретическая проблема — это инциденты, которые уже могут происходить и не диагностироваться из-за bare except Exception.
3.9. 50+ bare except Exception как культурный паттерн
Конструкция except Exception: pass или except Exception as e: logger.warning(...) встречается более 50 раз в кодовой базе приложения (без учёта тестов). Наиболее проблемные файлы: app/blueprints/auth.py (13 вхождений), app/blueprints/admin.py (13), app/services/email_service.py (11), app/utils/postgrest_client.py (10). Этот паттерн маскирует ошибки: если postgrest_request вернёт None из-за network timeout, последующий resp.ok выбросит AttributeError, который будет проглочен, и пользователь увидит «произошла непредвиденная ошибка» без возможности диагностики. Решение — ввести иерархию кастомных исключений (PostgrestError, CircuitBreakerOpenError, ValidationError) и централизованный errorhandler, который логирует stack trace и возвращает предсказуемый HTTP-ответ.
4. Рефакторинг (по пунктам)
Для каждой проблемы из раздела 3 ниже приводится конкретное решение с примером кода «Было → Стало». Примеры минимальны и иллюстрируют паттерн, а не полную реализацию. Все «Стало»-фрагменты совместимы с существующим стеком (Flask + PostgREST + Celery) и не требуют ввода новых тяжёлых зависимостей, если явно не указано обратное.
4.1. Структура проекта и циклические зависимости
Текущая структура app/utils/__init__.py — это god-module, который реэкспортирует ~40 функций из 10 подмодулей. Это создаёт два класса проблем: (1) любой импорт from app.utils import X тянет инициализацию mock-механизма (mock_postgrest.py), что замедляет запуск тестов; (2) сервисы и tasks используют from app.utils import postgrest_request, что затрудняет внедрение зависимостей. Цель рефакторинга — разделить модули по слоям (cache, db, auth, http) и устранить циклические импорты через выделение app/cache.py.
Было
# app/__init__.py — текущий код (строки 21-69)
def _redis_cache_get(key: str):
    try:
        client = get_redis_client()
        if client is None:
            return None
        value = client.get(key)
        if value is not None:
            return int(value)
    except Exception:
        pass
    return None
 
# app/services/notification_service.py — lazy import из-за цикла
def mark_read(notification_id, user_id=None):
    ...
    try:
        from app import _redis_cache_delete  # ← циклический импорт
        _redis_cache_delete(f'unread:{user_id}')
    except Exception:
        pass
Стало
# app/cache.py — новый модуль, зависит только от redis_client
from app.utils.redis_client import get_redis_client
 
_DEFAULT_TTL = 30
 
def cache_get(key: str, *, as_int: bool = False):
    client = get_redis_client()
    if client is None:
        return None
    try:
        value = client.get(key)
        if value is None:
            return None
        return int(value) if as_int else value
    except RedisError as e:
        current_app.logger.warning('cache_get(%s) failed: %s', key, e)
        return None
 
def cache_set(key: str, value, ttl: int = _DEFAULT_TTL) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.setex(key, ttl, value)
    except RedisError as e:
        current_app.logger.warning('cache_set(%s) failed: %s', key, e)
 
def cache_delete(key: str) -> None:
    client = get_redis_client()
    if client is not None:
        try:
            client.delete(key)
        except RedisError:
            pass
 
# app/services/notification_service.py — прямой импорт, без цикла
from app.cache import cache_delete
 
def mark_read(notification_id, user_id=None):
    ...
    if user_id:
        cache_delete(f'unread:{user_id}')
Дополнительно следует убрать глобальный app = create_app() из app/__init__.py (строка 513) и оставить только функцию-фабрику. Точки входа app.py и asgi.py должны явно вызывать create_app(). Это уберёт side-effects при импорте, ускорит запуск тестов и сделает gunicorn --preload безопасным.
4.2. Толстые Blueprints → тонкие Views + Use Cases
Текущий файл app/blueprints/jobs.py содержит 1019 строк и 16 маршрутов, каждый из которых смешивает четыре ответственности: парсинг request.args, валидацию, построение PostgREST-запроса и рендеринг шаблона. Это нарушает SRP и затрудняет тестирование. Цель — вынести бизнес-логику в Use Case-объекты (Command pattern), оставляя Blueprint тонкой HTTP-обёрткой. Пример ниже показывает рефакторинг маршрута apply_job.
Было
# app/blueprints/applications.py — текущий код (701 строка)
@applications_bp.route('/apply/<job_id>', methods=['GET', 'POST'])
@login_required
@validate_uuid('job_id')
@rate_limit
def apply_job(job_id):
    user_id = session['user_id']
    check = postgrest_request('GET', f'applications?job_id=eq.{job_id}&worker_id=eq.{user_id}')
    if check.ok and check.json():
        flash('Вы уже откликались на это задание', 'info')
        return redirect(url_for('jobs.index'))
    rpc_result = postgrest_rpc('apply_job_atomic', {...}, use_admin=True)
    if not rpc_result.ok:
        if rpc_result.status_code == 404:
            return _apply_job_fallback(job_id, user_id)
        flash('Ошибка при отправке отклика', 'danger')
        return redirect(url_for('jobs.index'))
    # ... ещё 40 строк бизнес-логики ...
    threading.Thread(target=_notify_employer, daemon=True).start()
    flash('Отклик отправлен', 'success')
    return redirect(url_for('jobs.index'))
Стало
# app/use_cases/apply_job.py — новый модуль Use Case
from dataclasses import dataclass
from app.services import notification_service
from app.errors import ApplyJobError, DuplicateApplication, NoSlotsAvailable
from app.repositories import ApplicationRepository, JobRepository
 
@dataclass
class ApplyJobCommand:
    job_id: str
    worker_id: str
 
@dataclass
class ApplyJobResult:
    application_id: str
    employer_id: str
    job_id: str
 
class ApplyJobUseCase:
    def __init__(self, applications: ApplicationRepository,
                 jobs: JobRepository,
                 notifications: NotificationService):
        self._applications = applications
        self._jobs = jobs
        self._notifications = notifications
 
    def execute(self, cmd: ApplyJobCommand) -> ApplyJobResult:
        # Атомарная операция через RPC (PostgREST не даёт транзакций)
        result = self._applications.apply_atomic(cmd.job_id, cmd.worker_id)
        if not result.success:
            raise _map_error(result.code, result.message)
        # Уведомление через transactional outbox (НЕ threading.Thread)
        self._notifications.enqueue(
            user_id=result.employer_id,
            notification_type='application_received',
            title='Новый отклик',
            body='На ваше задание поступил новый отклик',
            data={'job_id': cmd.job_id},
        )
        return ApplyJobResult(
            application_id=result.application_id,
            employer_id=result.employer_id,
            job_id=cmd.job_id,
        )
 
    def _map_error(code: str, message: str) -> ApplyJobError:
        return {
            'duplicate': DuplicateApplication(message),
            'no_slots': NoSlotsAvailable(message),
            'blacklisted': BlacklistedByEmployer(message),
        }.get(code, ApplyJobError(message))
 
# app/blueprints/applications.py — тонкая обёртка
@applications_bp.route('/apply/<job_id>', methods=['POST'])
@login_required
@validate_uuid('job_id')
@rate_limit
def apply_job(job_id):
    cmd = ApplyJobCommand(job_id=job_id, worker_id=session['user_id'])
    use_case = current_app.container.apply_job_use_case()
    try:
        result = use_case.execute(cmd)
    except DuplicateApplication:
        flash('Вы уже откликались на это задание', 'info')
        return redirect(url_for('jobs.index'))
    except NoSlotsAvailable as e:
        flash(str(e), 'info')
        return redirect(url_for('jobs.index'))
    except ApplyJobError as e:
        flash(str(e), 'danger')
        return redirect(url_for('jobs.index'))
    flash('Отклик отправлен', 'success')
    return redirect(url_for('jobs.index'))
Ключевая идея: Use Case не знает про Flask (никаких session, request, flash). Он принимает типизированную команду и возвращает типизированный результат или выбрасывает типизированное исключение. Blueprint сводится к маппингу HTTP ↔ Use Case. Это позволяет переиспользовать Use Case в Celery-задачах, WebSocket-обработчиках и тестах без поднятия Flask-контекста.
4.3. Repository над PostgREST + N+1 + Unit of Work
Все 14 Blueprints напрямую вызывают postgrest_request и postgrest_admin_request — около 80 точек вызова в кодовой базе. Это нарушает DIP (Dependency Inversion Principle): бизнес-логика зависит от конкретной реализации data-access. Рефакторинг вводит Repository-интерфейс, который можно подменять в тестах. Параллельно решается проблема N+1 в admin_panel через один batched RPC.
Было
# app/blueprints/admin.py — 8 count=exact запросов
if tab == 'dashboard':
    users_resp = postgrest_admin_request('GET', 'profiles?select=role&limit=0',
        headers={'Prefer': 'count=exact'})
    total_users = int(users_resp.headers.get('Content-Range', '').split('/')[-1])
    for role_key in ['worker', 'employer', 'admin']:
        role_resp = postgrest_admin_request('GET',
            f'profiles?role=eq.{role_key}&select=id&limit=0',
            headers={'Prefer': 'count=exact'})
        # ... ещё 5 аналогичных запросов ...
Стало
-- migrations/076_get_admin_stats.sql (один RPC вместо 8 запросов)
CREATE OR REPLACE FUNCTION get_admin_stats()
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'total_users', (SELECT COUNT(*) FROM profiles),
        'by_role', (SELECT json_object_agg(role, cnt)
                    FROM (SELECT role, COUNT(*) cnt FROM profiles GROUP BY role) s),
        'total_jobs', (SELECT COUNT(*) FROM jobs),
        'jobs_by_status', (SELECT json_object_agg(status, cnt)
                          FROM (SELECT status, COUNT(*) cnt FROM jobs GROUP BY status) s),
        'pending_verifications', (SELECT COUNT(*) FROM profiles WHERE verification_status = 'pending')
    ) INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;
 
# app/repositories/admin_repository.py
class AdminRepository:
    def __init__(self, client: PostgrestClient):
        self._client = client
 
    def get_stats(self) -> AdminStats:
        resp = self._client.rpc('get_admin_stats', {}, use_admin=True)
        if not resp.ok:
            raise PostgrestError(f'get_admin_stats failed: {resp.status_code}')
        return AdminStats.from_dict(resp.json())
 
# app/blueprints/admin.py — одна строка вместо 8 запросов
if tab == 'dashboard':
    stats = current_app.container.admin_repo().get_stats()
Для Unit of Work над PostgREST: поскольку PostgREST не даёт транзакций, паттерн реализуется через PostgreSQL-функции (atomic RPC), которые уже есть в проекте. Задача — устранить fallback-пути с TOCTOU, потребовав миграцию 048+ как обязательную, и удалить неатомарный _apply_job_fallback. Это значительно упрощает код и устраняет целый класс инцидентов.
4.4. Кастомные исключения и централизованный error handler
Сейчас в проекте нет ни одного кастомного исключения (поиск class.*Exception|class.*Error не находит ни одного в app/). Все ошибки возвращаются через flash() + redirect() или jsonify(), что приводит к дублированию логики в каждом маршруте и 50+ bare except Exception. Рефакторинг вводит иерархию DomainError + InfrastructureError и один централизованный errorhandler.
Стало
# app/errors.py — новый модуль с иерархией исключений
class DomainError(Exception):
    """Базовый класс для всех бизнес-ошибок."""
    http_status: int = 400
    user_message: str = 'Ошибка операции'
 
class NotFoundError(DomainError):
    http_status = 404
    user_message = 'Объект не найден'
 
class PermissionDeniedError(DomainError):
    http_status = 403
    user_message = 'Доступ запрещён'
 
class ValidationError(DomainError):
    http_status = 422
 
class ApplyJobError(DomainError): pass
class DuplicateApplication(ApplyJobError):
    user_message = 'Вы уже откликались на это задание'
class NoSlotsAvailable(ApplyJobError):
    user_message = 'Все места заняты'
class BlacklistedByEmployer(ApplyJobError):
    http_status = 403
    user_message = 'Работодатель добавил вас в чёрный список'
 
class InfrastructureError(Exception):
    """Ошибки внешних сервисов."""
    http_status: int = 503
class PostgrestError(InfrastructureError): pass
class CircuitBreakerOpenError(InfrastructureError):
    user_message = 'Сервис временно недоступен. Попробуйте позже.'
class RedisUnavailableError(InfrastructureError): pass
 
# app/error_handlers.py — регистрируется в create_app()
def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(DomainError)
    def handle_domain_error(e: DomainError):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': e.user_message, 'code': type(e).__name__}), e.http_status
        flash(e.user_message, 'warning' if e.http_status < 500 else 'danger')
        return redirect(request.referrer or url_for('jobs.index'))
 
    @app.errorhandler(InfrastructureError)
    def handle_infra_error(e: InfrastructureError):
        app.logger.exception('Infrastructure error: %s', e)
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': e.user_message}), e.http_status
        flash(e.user_message, 'warning')
        return redirect(url_for('jobs.index'))
 
    @app.errorhandler(Exception)
    def handle_unexpected(e: Exception):
        app.logger.exception('Unhandled exception: %s', e)
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
        return render_template('error.html', error_code='500',
                               error='Произошла непредвиденная ошибка'), 500
В комбинации с Use Cases (раздел 4.2) это даёт предсказуемый контракт: любой маршрут может выбросить DomainError, и errorhandler превратит его в корректный HTTP-ответ без дублирования логики в каждой view-функции.
4.5. Состояние вне процесса: Redis-backed cache и multi-replica WS
Две проблемы — in-memory cache_for (раздел 3.2) и active_connections dict (раздел 3.3) — имеют общую природу: состояние хранится в памяти процесса, что блокирует горизонтальное масштабирование. Решение в обоих случаях — вынести состояние в Redis, который уже используется в проекте как брокер и кеш.
Было
# app/utils/postgrest_client.py — текущий in-memory кеш
def cache_for(seconds: int = 30):
    cache_store: Dict[str, tuple] = {}  # ← в памяти процесса
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (func.__name__, repr(args), repr(sorted(kwargs.items())))
            now = time.time()
            if key in cache_store:
                result, expiry = cache_store[key]
                if now < expiry:
                    return result
            result = func(*args, **kwargs)
            cache_store[key] = (result, now + seconds)
            return result
        return wrapper
    return decorator
Стало
# app/cache.py — Redis-backed кеш с pickle-сериализацией
import pickle, hashlib, json
from typing import Callable, TypeVar
from app.utils.redis_client import get_redis_client
 
F = TypeVar('F', bound=Callable)
 
def _make_key(func_name: str, args: tuple, kwargs: dict) -> str:
    payload = json.dumps({'a': repr(args), 'k': repr(sorted(kwargs.items()))},
                         sort_keys=True, ensure_ascii=False)
    return f'cache:{func_name}:{hashlib.sha256(payload.encode()).hexdigest()[:16]}'
 
def cache_for(seconds: int = 30) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            client = get_redis_client()
            if client is None:
                return func(*args, **kwargs)  # graceful degradation
            key = _make_key(func.__name__, args, kwargs)
            try:
                cached = client.get(key)
                if cached is not None:
                    return pickle.loads(cached)
            except Exception:
                pass
            result = func(*args, **kwargs)
            try:
                client.setex(key, seconds, pickle.dumps(result, protocol=4))
            except Exception:
                pass
            return result
        return wrapper
    return decorator
Для WebSocket-сервера решение сложнее. Глобальный active_connections должен быть заменён на схему с регистрацией соединений в Redis: при подключении пользователь публикует ws:register:{user_id} = {server_id, connection_id}; при отправке уведомления издатель отправляет в Redis Pub/Sub канал ws:server:{server_id}, а каждый WS-сервер слушает свой канал. Альтернатива — Redis Streams с consumer groups, что даёт лучшую гарантию доставки, но сложнее в реализации.
Было
# websocket_server/main.py — текущий in-memory dict
active_connections: dict[str, WebSocket] = {}  # ← не переживает рестарт
 
@app.websocket('/ws')
async def websocket_endpoint(websocket, token):
    payload = verify_token(token)
    user_id = str(payload.get('user_id', ''))
    await websocket.accept()
    active_connections[user_id] = websocket  # ← теряется при масштабировании
    # ...
Стало
# websocket_server/registry.py — Redis-backed registry
import os, json, uuid
import redis.asyncio as aioredis
 
SERVER_ID = str(uuid.uuid4())  # уникален для каждого процесса
CHANNEL = f'ws:server:{SERVER_ID}'
 
class ConnectionRegistry:
    def __init__(self, redis_url: str):
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._local: dict[str, WebSocket] = {}  # только локальные соединения
 
    async def register(self, user_id: str, ws: WebSocket) -> None:
        self._local[user_id] = ws
        await self._redis.sadd(f'ws:online:{user_id}', SERVER_ID)
        await self._redis.setex(f'ws:server_id:{SERVER_ID}', 60, '1')
 
    async def unregister(self, user_id: str) -> None:
        self._local.pop(user_id, None)
        await self._redis.srem(f'ws:online:{user_id}', SERVER_ID)
 
    async def send_to_user(self, user_id: str, message: dict) -> None:
        # Находим серверы, где сидит пользователь
        servers = await self._redis.smembers(f'ws:online:{user_id}')
        for server_id in servers:
            # Публикуем в канал конкретного сервера
            await self._redis.publish(
                f'ws:server:{server_id}',
                json.dumps({'user_id': user_id, 'message': message}),
            )
 
    async def listen_local(self) -> None:
        # Слушаем свой канал и отправляем локальным соединениям
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        async for msg in pubsub.listen():
            if msg['type'] != 'message':
                continue
            payload = json.loads(msg['data'])
            ws = self._local.get(payload['user_id'])
            if ws:
                await ws.send_json(payload['message'])
4.6. Тестируемость: DI и mock-инжекция
Текущий mock-механизм (app/testing/mock_postgrest.py — 837 строк) работает через monkey-patching атрибутов модуля postgrest_client в app/utils/__init__.py. Это хрупко: порядок инициализации имеет значение, и любой новый импорт может сломать тесты. Рефакторинг — ввести простейший DI-контейнер (без фреймворков) и передавать Repository в Use Case конструктором.
Стало
# app/container.py — минимальный DI-контейнер
from functools import lru_cache
from app.repositories import ApplicationRepository, JobRepository, AdminRepository
from app.services import NotificationService
from app.use_cases import ApplyJobUseCase, WithdrawApplicationUseCase
 
class Container:
    def __init__(self, postgrest_client, redis_client):
        self._pg = postgrest_client
        self._redis = redis_client
 
    def application_repo(self) -> ApplicationRepository:
        return ApplicationRepository(self._pg)
 
    def job_repo(self) -> JobRepository:
        return JobRepository(self._pg)
 
    def admin_repo(self) -> AdminRepository:
        return AdminRepository(self._pg)
 
    def notification_service(self) -> NotificationService:
        return NotificationService(self._pg, self._redis)
 
    def apply_job_use_case(self) -> ApplyJobUseCase:
        return ApplyJobUseCase(
            applications=self.application_repo(),
            jobs=self.job_repo(),
            notifications=self.notification_service(),
        )
 
# app/__init__.py — регистрация контейнера в app
def create_app():
    app = Flask(__name__)
    # ...
    app.container = Container(
        postgrest_client=PostgrestClient(Config),
        redis_client=get_redis_client(),
    )
    return app
 
# tests/test_apply_job.py — тест без поднятия Flask
def test_apply_job_rejects_duplicate():
    fake_repo = FakeApplicationRepository(duplicates=[('job-1', 'user-1')])
    use_case = ApplyJobUseCase(applications=fake_repo, jobs=FakeJobRepo(),
                               notifications=FakeNotificationService())
    with pytest.raises(DuplicateApplication):
        use_case.execute(ApplyJobCommand(job_id='job-1', worker_id='user-1'))
4.7. Конфигурация как instance, не class attributes
Текущий app/config.py вычисляет все значения на верхнем уровне класса Config при импорте. Это означает: (1) нельзя протестировать приложение с разными конфигурациями в одном pytest-ране; (2) load_dotenv() выполняется как side-effect при импорте; (3) проверка «production requires POSTGREST_URL» выбрасывает RuntimeError при импорте, что ломает dev-окружение. Рефакторинг — превратить Config в dataclass, заполняемый из env в factory-функции.
Было
# app/config.py — текущий код (class attributes, side-effects)
load_dotenv()  # ← side-effect при импорте
 
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')  # ← вычисляется 1 раз
    if not SECRET_KEY:
        raise RuntimeError('SECRET_KEY environment variable is required')
    POSTGREST_URL = os.environ.get('POSTGREST_URL', '').strip()
    # ... 50 строк валидации на верхнем уровне класса ...
Стало
# app/config.py — dataclass + factory
from dataclasses import dataclass, field
 
@dataclass(frozen=True)
class Config:
    secret_key: str
    postgrest_url: str
    pgrst_jwt_secret: str
    redis_url: str = 'redis://localhost:6379/0'
    deployment_env: str = 'development'
    monetization_enabled: bool = False
    testing: bool = False
    # ... остальные поля ...
 
    @classmethod
    def from_env(cls, env: dict | None = None) -> 'Config':
        env = env or os.environ
        deployment = env.get('DEPLOYMENT_ENV', 'development')
        secret = env.get('SECRET_KEY', '')
        if not secret and deployment == 'production':
            raise ConfigError('SECRET_KEY is required in production')
        return cls(
            secret_key=secret or 'dev-secret-not-for-production',
            postgrest_url=cls._normalize_postgrest_url(env.get('POSTGREST_URL', '')),
            pgrst_jwt_secret=env.get('PGRST_JWT_SECRET', ''),
            redis_url=env.get('REDIS_URL', 'redis://localhost:6379/0'),
            deployment_env=deployment,
            monetization_enabled=env.get('MONETIZATION_ENABLED', '').lower() == 'true',
            testing=env.get('TESTING', '').lower() in ('true', '1', 'yes'),
        )
 
    @staticmethod
    def _normalize_postgrest_url(url: str) -> str:
        url = url.strip()
        if not url:
            return 'http://localhost:3000'
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        return url
 
# app/__init__.py
def create_app(config: Config | None = None):
    config = config or Config.from_env()
    app = Flask(__name__)
    app.config.from_mapping(dataclasses.asdict(config))
    app.container = Container(config)
    return app
5. Дорожная карта
Рефакторинг организован в шесть фаз, упорядоченных так, чтобы каждая последующая фаза опиралась на предыдущую и не ломала продакшн. Каждая фаза длится от 1 до 4 недель и заканчивается measurable результатом. Общая длительность — 13 недель (около 3 месяцев) при одном инженере на full-time; при параллельной работе двух инженеров можно сократить до 8–9 недель за счёт совмещения Фазы 1 и Фазы 2.
Принцип упорядочивания: сначала изменения, не затрагивающие поведение (Фаза 0), потом инфраструктурные абстракции (Фазы 1–2), затем перераспределение бизнес-логики (Фазы 3–4), и наконец — устранение антипаттернов масштабирования (Фаза 5). Такой порядок минимизирует риск регрессий: если Фаза 3 ломает что-то, откат — это git revert одного pull request, а не переписывание инфраструктуры.
5.1. План фаз
| Фаза | Длительность | Файлы (ключевые) | Риск отката | Метрика успеха |
|---|---|---|---|---|
| 0. Уборка инфры | 1 неделя | app/__init__.py, app/cache.py (новый) | Низкий | gunicorn --preload работает; нет lazy import из app в services |
| 1. Исключения + error handler | 2 недели | app/errors.py, app/error_handlers.py, 14 blueprints | Средний | 0 новых bare except Exception; все 503 возвращают JSON на /api/* |
| 2. Repository + admin stats RPC | 3 недели | app/repositories/, migrations/076, app/blueprints/admin.py | Средний | admin_panel: 1 RPC вместо 8 запросов; latency < 50ms при 100k users |
| 3. Use Cases + замена threading.Th read | 4 недели | app/use_cases/, app/blueprints/application.py, jobs_api.py | Высокий | 0 threading.Thread в кодовой базе; all mutations через Use Case |
| 4. Redis cache_for + multi-replica WS | 2 недели | app/cache.py, websocket_server/registr y.py, websocket_server/main.py | Средний | 2 реплики WS-сервера доставляют 100% путей; cache hit ratio > 80% |
| 5. DI-контейнер + Config refactor | 1 неделя | app/container.py, app/config.py, tests/conftest.py | Низкий | Юнит-тест Use Case без Flask-контекста запускается < 100ms |

5.2. Пофазное описание
Фаза 0. Уборка инфраструктуры (1 неделя)
Цель: устранить технический долг, не меняющий поведение. Шаги: (1) вынести _redis_cache_get / _redis_cache_set / _redis_cache_delete из app/__init__.py в новый модуль app/cache.py; (2) убрать глобальный app = create_app() из app/__init__.py, оставить только фабрику; (3) обновить app.py и asgi.py, чтобы они явно вызывали create_app(); (4) убрать неиспользуемый import subprocess из app/__init__.py. Риск: могут сломаться скрипты scripts/*, которые делают from app import app. Метрика: gunicorn --preload запускается без блокировки на 30 секунд.
Фаза 1. Кастомные исключения и error handler (2 недели)
Цель: ввести иерархию DomainError + InfrastructureError, зарегистрировать централизованный errorhandler, заменить bare except Exception на конкретные исключения в 50+ местах. Шаги: (1) создать app/errors.py с иерархией; (2) создать app/error_handlers.py с register_error_handlers(app); (3) в каждом blueprint добавить обработку PostgrestError вместо проверки resp.ok; (4) добавить CircuitBreakerOpenError и выбрасывать его из postgrest_request когда CB открыт. Риск: неверное отображение ошибок в UI, если user_message не задан. Метрика: 0 новых bare except Exception в кодовой базе (проверяется ruff линтером).
Фаза 2. Repository-слой и admin stats RPC (3 недели)
Цель: ввести Repository-интерфейсы над PostgREST, устранить N+1 в admin_panel через один batched RPC. Шаги: (1) создать app/repositories/ с модулями job_repository.py, application_repository.py, admin_repository.py, notification_repository.py; (2) написать миграцию 076_get_admin_stats.sql с RPC get_admin_stats() на основе GROUP BY; (3) переписать admin_panel() для использования AdminRepository.get_stats(); (4) постепенно переписать остальные маршруты admin.py на repository-вызовы. Риск: RPC может вернуть не тот формат данных; нужно покрыть интеграционным тестом. Метрика: latency admin_panel при 100k users < 50ms (сейчас оценивается в 500–800ms).
Фаза 3. Use Cases и устранение threading.Thread (4 недели)
Цель: ввести Command/Use Case-паттерн для всех мутаций, заменить fire-and-forget потоки на transactional outbox. Шаги: (1) создать app/use_cases/ с apply_job.py, withdraw_application.py, accept_invitation.py, create_job.py, cancel_job.py; (2) переписать apply_job, _apply_job_fallback, apply_selected, withdraw_application, accept_invitation на Use Case-вызовы; (3) удалить threading.Thread, заменить на enqueue_notification (уже есть в notification_service); (4) удалить _apply_job_fallback, потребовав миграцию 048 как обязательную. Риск: изменения в бизнес-логике при переписывании; нужны E2E-тесты для каждого Use Case. Метрика: 0 вхождений threading.Thread в app/; все Use Case покрыты юнит-тестами (>80% строк).
Фаза 4. Redis cache_for и multi-replica WebSocket (2 недели)
Цель: устранить состояние в памяти процесса. Шаги: (1) переписать cache_for в app/cache.py на Redis-backed реализацию; (2) обновить jobs_api.py — кеш /api/skills и /api/religions теперь разделяется между воркерами; (3) в websocket_server/ создать registry.py с ConnectionRegistry на Redis Sets + Pub/Sub; (4) обновить websocket_server/main.py для использования registry; (5) протестировать с 2 репликами WS-сервера. Риск: при failover Redis теряются кеш и registry; нужно testировать graceful degradation. Метрика: 2 реплики WS-сервера доставляют 100% уведомлений при kill -9 одной реплики.
Фаза 5. DI-контейнер и Config refactor (1 неделя)
Цель: финальная очистка. Шаги: (1) создать app/container.py с минимальным DI-контейнером; (2) обновить create_app() для создания container и регистрации в app.container; (3) переписать Config как dataclass с factory-методом from_env; (4) обновить tests/conftest.py для использования фейковых repository в юнит-тестах. Риск: низкий, так как изменения изолированы. Метрика: юнит-тест ApplyJobUseCase запускается за < 100ms без Flask-контекста.

5.3. Принципы работы в каждой фазе
●	Каждая фаза — отдельный feature branch с pull request и code review. Не сливать несколько фаз в один PR.
●	Перед началом фазы — снимается baseline-метрика (latency, error rate, test coverage). После фазы — та же метрика сравнивается. Regression = фаза не принята.
●	E2E-тесты (Selenium/Playwright) запускаются на каждом PR. Если хотя бы один E2E-тест падает — PR блокируется.
●	На время Фазы 3 (Use Cases) вводится freeze на новые фичи в apply/withdraw/accept-маршрутах. Любая новая фича — через новый Use Case.
●	Деплой после каждой фазы — на staging, минимум 24 часа soak test перед деплоем в production.
6. Бонус — рекомендуемые библиотеки
В этом разделе оценивается целесообразность внедрения библиотек, упомянутых в запросе (Flask-Smorest, APIFlask, Marshmallow, Celery), плюс несколько дополнительных, которые органично дополняют рефакторинг. Для каждой библиотеки указан приоритет (Must / Should / Could), обоснование и ожидаемый эффект. Важно: PostgREST уже берёт на себя часть функций, которые обычно закрывают ORM и schema-библиотеки, поэтому некоторые «классические» рекомендации избыточны.
6.1. Сводная таблица
| Библиотека | Назначение | Приоритет | Эффект |
|---|---|---|---|
| Celery 5.6 (уже есть) | Фоновые задачи, retry, scheduled jobs | — | Уже внедрён, корректно используется; расширить покрытие |
| Marshmallow 4 | Сериализация/валидация схем входных и выходных данных | Should | Заменит ручную валидацию в 14 blueprints; автогенерация OpenAPI |
| Pydantic 2 | Type-safe модели команд для Use Cases | Must | ApplyJobCommand, WithdrawCommand и т.д. — вместо dataclass |
| Flask-Smorest | Blueprint с auto-OpenAPI + Marshmallow-интеграцией | Could | Полезно для /api/*; но требует переписывания всех API-blueprints |
| APIFlask | Альтернатива Flask-Smorest, более декларативная | Could | Выбирать между Smorest и APIFlask — не одновременно |
| Tenacity | Retry с exponential backoff для внешних вызовов | Should | Замена ad-hoc retry-логики в postgresql_client.py и email_tasks.py |
| SQLAlchemy 2 (опционально) | ORM для прямого доступа к PostgreSQL в обход Postgres | Could | ТОЛЬКО если PostgreSQL перестанет справляться; пока не нужен |
| structlog | Structured logging (JSON) для observability | Should | Замена logging.basicConfig; лучше ищется в ELK/Loki |
| pytest-flask + pytest-cov | Тестирование Flask-приложений и coverage | Must | Уже используется pytest; добавить fixtures из pytest-flask |
| Redis Streams (через redis-py) | Гарантированная доставка WS-сообщений | Could | Замена Pub/Sub для multi-replica WS; сложнее, но надёжнее |

6.2. Подробное обоснование
Marshmallow (Should)
Сегодня валидация входных данных в blueprints делается вручную: каждый request.form.get / request.args.get сопровождается if not value: flash(...); return redirect(...). Это дублируется в десятках мест и легко пропускает edge cases. Marshmallow вводит схему как декларативный объект, который одновременно валидирует, сериализует и документирует поле. В комбинации с Use Cases (раздел 4.2) Marshmallow-схема становится контрактом на входе в Use Case. Для API-маршрутов Marshmallow-схема автоматически генерирует OpenAPI-спецификацию через Flask-Smorest или APIFlask.
Pydantic 2 (Must)
Pydantic 2 (выпущен в 2023 году) — это не просто валидатор, это type-safe модели с C-ядром (в 5–50 раз быстрее Pydantic 1). В контексте рефакторинга Pydantic идеален для объявления Command-объектов: ApplyJobCommand(job_id: UUID, worker_id: UUID) автоматически валидирует типы при создании и даёт статическую типизацию в IDE. В отличие от dataclass, Pydantic-модель выбрасывает ValidationError при неверном типе, что ловится на границе HTTP-слоя. Pydantic 2 уже может быть неявной зависимостью через FastAPI (websocket_server), поэтому внедрение не добавит новой тяжёлой библиотеки.
Flask-Smorest или APIFlask (Could)
Обе библиотеки — это надстройки над Flask для построения REST API с auto-OpenAPI. Flask-Smorest более зрелый, APIFlask — более декларативный и современный. Выбор между ними — дело вкуса команды. Внедрение имеет смысл только если в планах есть публичное API для мобильных клиентов или внешних интеграций; для текущего проекта, где 90% маршрутов возвращают HTML, это избыточно. Рекомендация: внедрять только на новых API-маршрутах (app/blueprints/jobs_api.py, notifications API), не переписывая существующие HTML-route.
Celery (уже есть) — расширить покрытие
Celery уже внедрён и корректно настроен (celery_app.py с task_acks_late=True, task_reject_on_worker_lost=True, beat_schedule для maintenance). Однако он используется только для email и push-уведомлений. После Фазы 3 (устранение threading.Thread) Celery должен взять на себя все асинхронные операции: отправку уведомлений из apply_job, генерацию превью изображений при загрузке фото, инкрементальный пересчёт рейтингов. Дополнительная рекомендация — добавить Flower (flower-celery) для мониторинга воркеров в реальном времени.
Tenacity (Should)
Сейчас retry-логика реализована ad-hoc в нескольких местах: postgrest_client.py (401 → refresh → retry), email_tasks.py (self.retry с countdown). Tenacity даёт декларативный @retry декоратор с exponential backoff, jitter, condition-based retry. Это унифицирует retry-паттерн и сделает его тестируемым. Особенно полезно для внешних вызовов (Yandex Maps API, SMTP, Web Push).
SQLAlchemy 2 (Could — не внедрять сейчас)
SQLAlchemy — стандартный Python ORM, но в проекте с PostgREST его внедрение создаст два параллельных data-access слоя, что ухудшит поддерживаемость. PostgREST покрывает 95% случаев (CRUD, фильтры, joins, RPC); оставшиеся 5% (сложные аналитические запросы, batch-операции) лучше закрывать через RPC-функции PostgreSQL, как уже сделано с apply_job_atomic. SQLAlchemy стоит рассматривать только если PostgREST станет узким местом — но для этого нужны profiling-данные, которых сейчас нет.
structlog (Should)
Текущее логирование — стандартный logging модуль с format-строкой. Это работает, но в distributed-сценариях (много gunicorn-воркеров, Celery, WebSocket-сервер) искать ошибки в логах тяжело. structlog выводит логи как JSON с structured fields (request_id, user_id, latency_ms), что отлично ищется в ELK/Loki/Datadog. Миграция на structlog — один-два дня работы, эффект значительный.
Redis Streams (Could — для Фазы 4)
Если multi-replica WebSocket (Фаза 4) покажет, что Pub/Sub теряет сообщения при failover, следует рассмотреть Redis Streams с consumer groups. Streams дают guaranteed delivery и at-least-once семантику, но сложнее в настройке. Рекомендация — начать с Pub/Sub (как описано в разделе 4.5), и переходить на Streams только если метрики доставки покажут потери.
7. Резюме и следующие шаги
Архитектура проекта «Трудник» функционально завершена и пригодна для текущей нагрузки. Однако она не готова к 10-кратному росту ни по трафику, ни по размеру команды. Главные точки приложения силы для рефакторинга: (1) Repository-слой над PostgREST с устранением N+1 в admin_panel; (2) Use Cases с типизированными командами и результатами, замещающие бизнес-логику в Blueprints; (3) Redis как единый источник shared-state для кеша и WebSocket-registry; (4) кастомные исключения и централизованный errorhandler, замещающие 50+ bare except Exception.
Рекомендуемая последовательность — начать с Фазы 0 (инфраструктурная уборка, 1 неделя) и Фазы 1 (исключения + error handler, 2 недели). Это даёт быстрый выигрыш при минимальном риске: кодовая база становится более предсказуемой, появляются первые юнит-тесты на новую инфраструктуру, и команда получает тактический опыт рефакторинга перед более крупными Фазами 2 и 3. После Фазы 1 можно принимать решение о приоритизации Фазы 2 (Repository) vs Фазы 3 (Use Cases) — они независимы и могут выполняться параллельно разными инженерами.
Метрика успеха всего аудита: через 2 месяца после начала рефакторинга вы должны суметь удалить маршрут admin_panel и переписать его за один день, используя AdminRepository.get_stats() из Фазы 2 и один из новых Use Cases из Фазы 3. Если это получается — аудит сделал свою работу: кодовая база стала достаточно модульной, чтобы крупные изменения были рутинной операцией, а не проектом на квартал.
Параллельно с рефакторингом следует investировать в observability: structured logging через structlog (рекомендация из раздела 6), tracing через OpenTelemetry для PostgREST-вызовов, метрики через Prometheus. Без observability любой рефакторинг превращается в ходьбу вслепую: вы не знаете, стало лучше или хуже. Минимальный набор — логи в JSON, метрика latency p95 на каждый маршрут, alert на Circuit Breaker OPEN события. Это можно внедрить за неделю параллельно с Фазой 0.
