# Stage 3: Service Layer Review

Date: 2026-06-22  |  Branch: main  |  Files: 5 services
Context: Flask + Supabase + Celery + Redis, Trudnik project

---

## 1. app/services/email_service.py

### Issues found: 8

1. HIGH [Reliability] Daily limit in instance memory -- each Celery worker counts from 0
   Line 45-46. Fix: Redis INCR with TTL until midnight.

2. HIGH [Reliability] send_batch() -- sync loop with time.sleep blocks worker for minutes
   Line 212. Fix: Celery group/chord for parallel send.

3. HIGH [Reliability] SMTP connection not closed on exception -- quit() not in finally
   Line 141-142. Fix: try/finally for server.quit().

4. HIGH [Performance] Each send_email() opens new SMTP connection
   Line 124-131. Fix: Connection pooling in instance.

5. MEDIUM [Code Quality] create_unsubscribe_token() reads SECRET_KEY from os.environ
   Line 285. Fix: Accept as parameter from current_app.config.

6. MEDIUM [Code Quality] Settings read from os.environ directly, ignoring Config class
   Line 32-42. Fix: Constructor parameters.

7. LOW [Code Quality] send_email() returns False without distinguishing error types
   Line 148-154. Fix: Custom exception or error code.

8. LOW [Security] Default SSL context -- not self-documenting
   Line 125-127. Fix: Explicit ssl.create_default_context().


### Detailed Findings

**Finding 1 -- Daily limit broken in multi-process (HIGH, 95%)**
- File: app/services/email_service.py:45-46
- Problem: _daily_count and _last_reset_date are instance attributes. Celery workers each have their own EmailService. The 1000/day limit is not enforced across workers.
- Fix: Use Redis INCR email:daily:YYYY-MM-DD with EXPIRE at midnight.

**Finding 2 -- Blocking batch loop (HIGH, 90%)**
- File: app/services/email_service.py:179-212
- Problem: send_batch() sequentially calls send_email() with time.sleep(). Blocks Celery worker. For 1000 recipients at 1s pause, that is 16+ minutes of blocked worker.
- Fix: Celery group -- each email as separate task for parallel execution.

**Finding 3 -- SMTP connection leak (HIGH, 90%)**
- File: app/services/email_service.py:141-142
- Problem: If send_message() raises, server.quit() on line 142 is never reached. SMTP connection leaks until GC.
- Fix: Wrap in try/finally: server.send_message(msg) ... server.quit().

**Finding 4 -- No connection pooling (HIGH, 85%)**
- File: app/services/email_service.py:124-142
- Problem: Every send_email() creates new connection (TCP + TLS handshake + AUTH). 200-500ms overhead per email. SMTP servers may rate-limit frequent connections.
- Fix: Lazy connection as instance attribute, reconnect on SMTPServerDisconnected.

---

## 2. app/services/job_service.py

### Issues found: 9

1. HIGH [Reliability] search_jobs() pagination broken with client-side geo-filtering -- total from DB (pre-filter), results after radius filtering. Pages may be empty. Line 196-243. Fix: nearby_jobs RPC on DB side.

2. HIGH [Performance] check_job_visibility() -- HTTP request to blacklist for EACH job (N+1). 20 jobs = 20 extra DB round-trips. Line 393-396. Fix: Load blacklist once before the loop.

3. HIGH [Performance] enrich_job_with_references() -- 2 HTTP requests per job for UUID resolution (N+1). Line 52-64. Fix: PostgREST embedded resources: select=*,work_type:skills(name).

4. MEDIUM [Security] get_job_by_id() always uses supabase_admin_request -- bypasses RLS for all callers. Line 35-38. Fix: Add use_admin=False parameter.

5. MEDIUM [Code Quality] search_jobs() and search_workers() have ~80% duplicated geo-filtering logic. Lines 202-225 and 266-287. Fix: Extract _apply_geo_filters() helper.

6. MEDIUM [Reliability] build_job_query() constructs URL by concatenation without URL-encode. Lines 84-131. Fix: urllib.parse.quote() for all values.

7. MEDIUM [Performance] search_jobs() loads ALL matching jobs from DB, then filters by geo in Python. Line 194-221. Fix: Use nearby_jobs RPC for DB-side geo-filtering.

8. LOW [Reliability] apply_skill_filter() -- substring matching is fragile (skill name may match part of another word). Line 320-330. Fix: Use job_skills table with exact UUID comparison.

9. LOW [Code Quality] from flask import current_app inside functions (lazy import). Lines 223, 286. Fix: Import at top of file.

### Detailed Findings

**Finding 1 -- Broken pagination with geo-filtering (HIGH, 95%)**
- File: app/services/job_service.py:196-243
- Problem: total is taken from Content-Range header (line 198) -- count BEFORE client-side radius filtering. After filtering (line 216), results count may be less than per_page. Pages can be empty or incomplete. total is always overestimated.
- Fix: Use nearby_jobs RPC (migrations/056) -- DB-side geo-filtering with correct pagination.

**Finding 2 -- N+1 for blacklist checks (HIGH, 90%)**
- File: app/services/job_service.py:393-396
- Problem: check_job_visibility() makes a separate HTTP request for each job. 20 jobs on a page = 20 extra round-trips to the database.
- Fix: Load the user blacklist with ONE request before the loop. Pass blocked_user_id set to template context.

**Finding 3 -- N+1 for UUID resolution (HIGH, 85%)**
- File: app/services/job_service.py:52-64
- Problem: enrich_job_with_references() makes 2 HTTP requests per job to resolve UUIDs to names.
- Fix: Use PostgREST embedded resources: select=*,work_type:skills(name) in the original query -- one request.

---

## 3. app/services/notification_service.py

### Issues found: 9

1. HIGH [Security] mark_read() does not check user_id -- anyone can mark any notification as read. Line 246-249. Fix: Add user_id=eq.{user_id} filter.

2. HIGH [Reliability] get_unread_count() uses limit=100 -- undercounts when more than 100 unread notifications. Line 235. Fix: Use Prefer: count=exact header with limit=0.

3. MEDIUM [Reliability] create() returns True even when email/push dispatch fails. Caller cannot distinguish partial success. Line 213. Fix: Return dict with flags: {in_app, email_dispatched, push_dispatched}.

4. MEDIUM [Performance] Double profile fetch: get_user_prefs() (line 68) + second query for email/username (line 160). Two HTTP requests to same table. Fix: Merge into one: select=notification_prefs,email,username.

5. MEDIUM [Code Quality] Circular import: notification_service -> app.tasks.email_tasks -> app.services.email_service. Lazy imports (lines 148-149) work but are fragile. Fix: Move Celery dispatch to blueprint level or use signals.

6. MEDIUM [Security] get_user_prefs() always uses supabase_admin_request -- bypasses RLS for all contexts. Line 68. Fix: Use supabase_request for owner context, admin only for system calls.

7. MEDIUM [Security] title and message not sanitized before DB insertion -- potential XSS if rendered without escaping. Lines 99-105. Fix: Sanitize HTML tags with bleach or markupsafe.escape.

8. LOW [Code Quality] mark_all_read() and mark_read() do not return result -- caller cannot verify success. Lines 241-249. Fix: Return bool or resp.ok.

9. LOW [Code Quality] NOTIFICATION_TYPES (line 30) and DEFAULT_ENABLED_TYPES (line 47) duplicate keys. Line 30-62. Fix: DEFAULT_ENABLED_TYPES = {k: True for k in NOTIFICATION_TYPES}.

### Detailed Findings

**Finding 1 -- mark_read without owner check (HIGH, 85%)**
- File: app/services/notification_service.py:246-249
- Problem: PATCH only by notification id, no user_id filter. If RLS is misconfigured or disabled, any user can modify other users notifications. Defense should be multi-layered.
- Fix: Add user_id parameter and filter: notifications?id=eq.{id}&user_id=eq.{user_id}.

**Finding 2 -- Undercount of unread notifications (HIGH, 85%)**
- File: app/services/notification_service.py:234-236
- Problem: limit=100 means at 150 unread, user sees 100 instead of 150. Misleading count in UI.
- Fix: Use select=id&limit=0 with header Prefer: count=exact, parse Content-Range for accurate count without loading data.

---

## 4. app/services/push_service.py

### Issues found: 9

1. HIGH [Security] delete_subscription() deletes by endpoint only, no user_id check. Any user can delete another user subscription if they know the endpoint URL. Line 326-330. Fix: Add user_id=eq.{user_id} filter.

2. HIGH [Reliability] vapid_claims[exp] is string 24h instead of Unix timestamp (int). RFC 8292 requires int. pywebpush may silently ignore, causing push server rejection. Line 157. Fix: int(time.time()) + 86400.

3. HIGH [Performance] get_all_subscriptions() loads ALL subscriptions into memory -- OOM risk with many users. Line 359-366. Fix: Add pagination with limit/offset or use streaming.

4. HIGH [Performance] send_to_user() -- sync loop sending to all subscriptions. Blocks Celery worker. Line 222-235. Fix: asyncio.gather or Celery group for parallel send.

5. MEDIUM [Reliability] send_notification() has no timeout for WebPusher.send() -- risk of hanging forever. Line 151. Fix: Add timeout=10 parameter.

6. MEDIUM [Code Quality] VAPID keys read from os.environ instead of Config class. Lines 49-56. Fix: Accept keys via constructor parameters.

7. MEDIUM [Security] vapid_claims[aud] set to full endpoint URL instead of origin (scheme+host). Line 156. Fix: urlparse(endpoint) to extract {scheme}://{netloc}.

8. MEDIUM [Reliability] cleanup_expired_subscriptions() sends real push to every subscriber for healthcheck -- wasteful resource usage. push_tasks.py:86. Fix: Use TTL column or HEAD request without push payload.

9. LOW [Code Quality] generate_vapid_keys() has ImportError inside method body instead of module top. Lines 83-88. Fix: Import at top of file.

### Detailed Findings

**Finding 1 -- Deleting other users subscription (HIGH, 90%)**
- File: app/services/push_service.py:326-330
- Problem: delete_subscription(endpoint) does DELETE ...?endpoint=eq.{endpoint} without user_id filter. An attacker who knows another users endpoint URL can unsubscribe them from push notifications.
- Fix: Change signature to delete_subscription(user_id, endpoint) and add &user_id=eq.{user_id} to URL.

**Finding 2 -- Invalid VAPID expiration format (HIGH, 90%)**
- File: app/services/push_service.py:157
- Problem: exp: 24h is a string. RFC 8292 section 2.1 requires Unix timestamp (int). pywebpush may silently ignore, leading to push server rejection with uninformative errors.
- Fix: Use str(int(time.time()) + 86400) or pywebpush internal mechanism.

**Finding 3 -- OOM risk from loading all subscriptions (HIGH, 85%)**
- File: app/services/push_service.py:359-366
- Problem: get_all_subscriptions() fetches all records without pagination. 50K users x 2 devices = 100K records in memory. Can cause OOM in Celery worker.
- Fix: Add pagination with limit/offset or range headers.

**Finding 4 -- Blocking push send loop (HIGH, 85%)**
- File: app/services/push_service.py:222-235
- Problem: send_to_user() loops synchronously, each push waiting for HTTP response. 5 devices x 2 sec = 10 seconds of blocked worker.
- Fix: Use asyncio + aiohttp for parallel push delivery.

---

## 5. app/services/redis_publisher.py

### Issues found: 8

1. HIGH [Reliability] Dead connection never recovered -- self._client stays non-None after errors, blocking all future publishes. Lines 33-73. Fix: Set self._client = None in except block of publish().

2. HIGH [Reliability] _reconnect_interval = 60 seconds -- notifications lost for up to 1 minute after Redis restart. Line 26. Fix: Reduce to 5-10 seconds with exponential backoff.

3. HIGH [Reliability] _get_client() only catches ConnectionError -- ValueError and RedisError from redis.from_url() crash the process. Lines 46-48. Fix: Catch Exception during client initialization.

4. MEDIUM [Code Quality] Pseudo-singleton: _instance declared but __init__ does not use it. Any code can create a second instance. Lines 25, 114. Fix: Implement __new__ for real singleton or remove _instance.

5. MEDIUM [Reliability] publish_chat_message() returns result1 or result2 -- masks partial failure (recipient fail + sender ok = True). Line 101. Fix: Return dict {recipient_ok, sender_ok} or all([result1, result2]).

6. MEDIUM [Reliability] No health-check method -- caller cannot verify Redis availability before publishing. Fix: Add is_available() -> bool method.

7. LOW [Code Quality] close() not called automatically -- no __del__ or context manager support. Lines 103-110. Fix: Add __enter__/__exit__ for context manager usage.

8. LOW [Reliability] json.dumps errors masked as Redis unavailable -- caller cannot distinguish serialization failures from connection failures. Lines 71-73. Fix: Log error types separately.

### Detailed Findings

**Finding 1 -- Dead connection never recovered (HIGH, 90%)**
- File: app/services/redis_publisher.py:33-73
- Problem: After successful _get_client(), self._client stays non-None forever. If Redis restarts, the stored client is dead. publish() will get ConnectionError but self._client is not reset to None. Next _get_client() returns the same dead client. Notifications lost indefinitely.
- Fix: Set self._client = None in the except block of publish() to force reconnection on next call.

**Finding 2 -- Long reconnect interval (HIGH, 85%)**
- File: app/services/redis_publisher.py:26
- Problem: _reconnect_interval = 60 seconds. When Redis drops, all real-time notifications (chat messages, status updates) are silently lost for up to 1 minute.
- Fix: Reduce to 5 seconds with exponential backoff: 5, 10, 20, 40, 60.

**Finding 3 -- Narrow exception handling (HIGH, 85%)**
- File: app/services/redis_publisher.py:46-48
- Problem: _get_client() only catches redis.ConnectionError. redis.from_url() can raise ValueError (invalid URL) or redis.RedisError -- these propagate unhandled and crash the calling code.
- Fix: Catch Exception during client initialization, log and set self._client = None.

---

## Summary

| File | CRITICAL | HIGH | MEDIUM | LOW | Total |
|------|----------|------|--------|-----|-------|
| email_service.py | 0 | 4 | 2 | 2 | **8** |
| job_service.py | 0 | 3 | 4 | 2 | **9** |
| notification_service.py | 0 | 2 | 5 | 2 | **9** |
| push_service.py | 0 | 4 | 4 | 1 | **9** |
| redis_publisher.py | 0 | 3 | 3 | 2 | **8** |
| **TOTAL** | **0** | **16** | **18** | **9** | **43** |

---

## Top 10 Issues

1. HIGH [job_service.py:196-243] Broken pagination with client-side geo-filtering -- total from DB does not account for radius filtering
2. HIGH [email_service.py:45-46] Daily limit in instance memory -- not enforced across Celery workers
3. HIGH [redis_publisher.py:33-73] Dead Redis connection never recovered after errors
4. HIGH [job_service.py:393-396] N+1 HTTP requests for blacklist check -- one per job
5. HIGH [push_service.py:326-330] delete_subscription() without user_id check -- can delete others subscriptions
6. HIGH [push_service.py:157] vapid_claims[exp] is string 24h instead of Unix timestamp
7. HIGH [email_service.py:124-142] No SMTP connection pooling -- new connection per email
8. HIGH [email_service.py:179-212] send_batch() -- synchronous blocking loop for minutes
9. HIGH [push_service.py:359-366] get_all_subscriptions() loads all records into memory -- OOM risk
10. HIGH [notification_service.py:234-236] get_unread_count() limit=100 undercounts unread notifications

---

## Cross-Cutting Architectural Issues

### 1. Direct os.environ reads instead of current_app.config

Affected files: email_service.py:32-42, push_service.py:49-56

All services read configuration directly from os.environ, ignoring the Config class that already loads the same variables. This creates two sources of truth: os.environ[SMTP_HOST] in EmailService vs current_app.config[SMTP_HOST] in templates/blueprints. When renaming a variable, both places must be updated.

Recommendation: Accept settings via constructor parameters. In Celery tasks, create instances with parameters from current_app.config (if available) or os.environ.

### 2. No unified dependency injection pattern

Affected files: All 5 services

- EmailService() -- new instance per task (email_tasks.py:115)
- PushService() -- new instance per task (push_tasks.py:29)
- RedisPublisher -- module-level singleton (redis_publisher.py:114)
- job_service -- module-level functions, no class

No consistent approach: classes vs functions vs singletons. Makes testing harder (no way to mock without monkey-patching).

Recommendation: Choose one pattern: either classes with DI via __init__ registered in app.extensions, or module-level functions with mock.patch for testing.

### 3. Configuration duplication between services and Config

EmailService (lines 32-42) and Config (lines 41-51) duplicate all SMTP settings. PushService (lines 49-56) and Config (lines 70-73) duplicate VAPID settings. Adding a new environment variable requires changes in 3 places: Config, service, and .env.example.

### 4. Mixed business logic and infrastructure in notification_service.create()

File: notification_service.py:146-211

create() does everything: checks preferences, writes to DB, publishes to Redis, dispatches email task, dispatches push task. This violates Single Responsibility -- notification creation should not know about delivery transports.

Recommendation: Observer pattern -- create() only writes to DB and publishes to Redis. A separate handler (Celery task or signal) listens to Redis and dispatches email/push.

### 5. No dependency inversion

All services directly call supabase_request / supabase_admin_request (concrete HTTP client implementations). Cannot substitute with mock without monkey-patching.

Recommendation: Pass DB client as dependency: class JobService: def __init__(self, db_client): ...

---

## Recommendation

**APPROVE WITH SUGGESTIONS** -- No critical issues (security/data loss) found. 16 HIGH-level issues require attention. Priority fixes:

1. Fix pagination in job_service (use nearby_jobs RPC)
2. Fix dead Redis connection recovery in redis_publisher
3. Add user_id check to push_service.delete_subscription()
4. Move email daily limit to Redis
5. Fix vapid_claims expiration format
6. Add SMTP connection pooling
7. Replace blocking batch loops with Celery groups
