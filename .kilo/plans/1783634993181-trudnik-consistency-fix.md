# Plan — «Трудник» Consistency Fix (GLM-5.2 Contract, T1–T70)

> Status: **Planning complete.** Scope confirmed with user: Iteration 1 execution-ready + Iterations 2–4 outlined.
> Target branch: `fix/trudnik-consistency` (currently checked out).
> Interpreter for local checks: `py -3` (Python 3.14.2; `python`/`python.exe` on PATH is a broken Store stub). Project targets 3.12; full-suite collection crashes on 3.14 — run **targeted** test files locally, full suite in Docker/CI.

---

## 0. Verified situation (cross-checked against actual code, not just the contract)

A prior run executed **~85% of Iteration 1 correctly** but **committed and logged nothing**. The working tree is dirty:

- ~44 tracked files modified, `app/blueprints/admin.py` staged-deleted, 4 new untracked files (`templates/password_reset_request.html`, `templates/password_reset_confirm.html`, `IMPLEMENTATION_LOG.md`, `CHANGELOG.md`).
- Backup tags present: `backup/pre-iteration-1`, stale `backup/temp-action-T1-20260709` (temp tag never cleaned up).
- Branch origin is `refactor/iteration-1-2-combined`, **not** `main` (contract said from `main`).

### Per-task status (Iter 1) — VERIFIED

| Task | Status | Evidence |
|------|--------|----------|
| T1 | ✅ done (uncommitted) | `admin.py` deleted; `test_all_functions.py` references new admin bps |
| T2 | ✅ done | routes removed from `__init__.py`, correctly re-added to `applications_bp` replacing test endpoint |
| T3 | ✅ done | `/api/applications/test` removed; `test_critical_gaps.py` now asserts 404 |
| T4 | ✅ done | `/job-stats`, `/migrations-status`, `/reset-circuit-breaker`; middleware whitelist; `test_b1` updated |
| T5 | ✅ done | `/admin/health`; 3 scripts updated |
| T6 | ✅ done | `applications.js`: `shift_id`→`appId`/`chatAppId` throughout |
| T7 | ✅ done | `base.html`: `userId` added to `TRUDNIK_CONFIG` |
| T8 | ✅ done | `notifications.html` `id="notifications-list"`; `notifications-init.js` `'messages'` |
| T9 | ✅ done | `sw.js`: `X-CSRF-Token` |
| T10 | ✅ done | `chat.html`: `client_message_id` generated |
| T11 | ✅ done | `rate_limit_decorator.py`: `logger` defined |
| T12 | ✅ done | `admin_service.py`/`postgrest_client.py`: `session.get('user_id')` |
| T13 | ⚠️ partial | templates + `login.html` "Забыли пароль?" done; **no test written** |
| T14 | ✅ done | env vars unified (`YANDEX_GEOCODER_KEY`, `SMTP_USERNAME`, `TEST_USER_PASSWORD`, `PG*`) |
| T15 | ✅ done | `base.html`: both `sendBeacon` use `Blob(application/json)` + `_csrf_token` |
| T16 | ✅ done | nav `('jobs.index',)` |
| T17 | ✅ done | `profile.profile_edit` removed (3 sites) |
| T18 | ⚠️ mostly | CSRF in **all 33** form sites ✅; but `<noscript>` still `fixed inset-0` fullscreen overlay ❌ |
| T19 | ✅ done | logout → POST form + `@rate_limit(fail_open=True)` (no `@login_required`, correct) |
| T20 | ✅ done | `profile.py`: `current_password` |
| T21 | ✅ done | `minlength="8"` (register/profile); login `minlength` removed |
| T22 | ❌ pending | `auth.py:113-116` logs `secret[:8]`; `config.py:36-37` logs `PGRST_JWT_SECRET[:16]` |
| T23 | ❌ pending | `base.html:37` still embeds `jwtToken`; `context_processors.inject_ws_config` still generates JWT; no `/api/ws/token` |
| T24 | ❌ pending | `entrypoint.sh:9-11` migrations still commented (see §B risk) |

### Confirmed decisions (from user)
1. **Existing work**: keep & commit in logical task-grouped chunks; back-fill `IMPLEMENTATION_LOG.md`.
2. **Scope**: Iter 1 detailed + iters 2–4 outlined.
3. **Tests**: high-value subset only (not all ~15 the contract lists).

---

## A. Phase A — Reconcile existing uncommitted work (do FIRST)

Goal: turn the dirty tree into clean, atomic, logged commits **without changing any code** (only `git add`/`commit` + write logs).

### A.1 Pre-flight
- Confirm still on `fix/trudnik-consistency`; confirm `backup/pre-iteration-1` exists.
- Run a targeted green check (proves the uncommitted state is sound before committing):
  ```
  $env:POSTGREST_MOCK_MODE='1'; $env:SECRET_KEY='test-secret'; $env:PGRST_JWT_SECRET='test-jwt-secret'
  $env:WEBSOCKET_JWT_SECRET='test-ws-secret'; $env:FLASK_CONFIG='testing'
  py -3 -m pytest tests/test_b1_admin_diagnostics_token.py tests/test_rate_limit.py -q
  ```
- Clean up stale temp tag: `git tag -d backup/temp-action-T1-20260709` (yellow — record in log).

### A.2 Commit grouping (each file assigned to exactly ONE commit — no hunk-splitting needed)

| # | Commit msg | Files |
|---|-----------|-------|
| 1 | `[T1] Remove dead admin.py blueprint` | `app/blueprints/admin.py` (del), `tests/test_all_functions.py` |
| 2 | `[T2,T3] Move accept/reject/reopen to applications_bp; drop debug endpoint` | `app/__init__.py`, `app/blueprints/applications.py`, `tests/test_critical_gaps.py` |
| 3 | `[T4,T5] Fix admin diagnostics/dashboard route prefixes` | `app/blueprints/admin_diagnostics.py`, `app/blueprints/admin_dashboard.py`, `app/middleware.py`, `templates/admin.html`, `scripts/test_buttons.py`, `scripts/smoke_test_prod.py`, `scripts/fix_prod_complete.py`, `tests/test_b1_admin_diagnostics_token.py` |
| 4 | `[T6] Fix chat button after batch accept/reject (shift_id→appId)` | `static/js/applications.js` |
| 5 | `[T8,T9] Fix WS realtime DOM ids and SW CSRF header` | `templates/notifications.html`, `static/sw.js` |
| 6 | `[T10] Add client_message_id for chat idempotency` | `templates/chat.html` |
| 7 | `[T11,T12] Define rate_limit logger; fix session keys in audit/postgrest_client` | `app/utils/rate_limit_decorator.py`, `app/services/admin_service.py`, `app/utils/postgrest_client.py` |
| 8 | `[T13] Add password-reset templates and login link` | `templates/password_reset_request.html`, `templates/password_reset_confirm.html`, `templates/login.html` |
| 9 | `[T14] Unify env var names with .env.example` | `app/config.py`, `app/utils/captcha.py`, `app/utils/db_pool.py`, `app/services/email_service.py`, `app/testing/mock_postgrest.py`, `docker-compose.yml`, `.env.example` |
| 10 | `[T7,T15,T16,T17] base.html: WS userId, sendBeacon CSRF, nav active states` | `templates/base.html` |
| 11 | `[T18,T19,T20,T21] Profile/register: CSRF, logout POST, change-password field, pw length` | `app/blueprints/profile.py`, `app/blueprints/auth.py`, `templates/profile.html`, `templates/register.html` |
| 12 | `[T18] Add CSRF tokens to remaining HTML forms` | `templates/index.html`, `templates/job_detail.html`, `templates/employer_detail.html`, `templates/employers.html`, `templates/favorites.html`, `templates/job_new.html`, `templates/my_jobs.html`, `templates/verify_employer.html` |

After each commit: `git status` (MODULE 1 step 4). After commit 12 the tree must be clean except `IMPLEMENTATION_LOG.md`/`CHANGELOG.md` (still untracked).

### A.3 Back-fill logs
- Append `<log_entry>` blocks to `IMPLEMENTATION_LOG.md` for T1–T21 (status COMPLETED, `rollback_plan` → `backup/pre-iteration-1`).
- Populate `CHANGELOG.md` with T1–T21 entries.
- Commit 13: `[DOCS] Back-fill IMPLEMENTATION_LOG and CHANGELOG for T1–T21`.
- **Note (deviation, record as EXTRA/escalation L1):** contract's T4/T5 asked for 301 deprecated-redirects. Not needed — those endpoints were already 404 (broken), so there is no live caller to redirect. Implemented fix (correct URLs) is correct and safe.

---

## B. Phase B — Finish remaining Iteration 1 tasks

### B.1 T22 — stop leaking JWT secret prefix
- `app/utils/auth.py:113-116` (inside `generate_jwt`, after secret validation):
  replace the `current_app.logger.info('JWT: signing with secret prefix=%s... (%d bytes)', secret[:8], ...)` block with:
  ```python
  logger.debug('JWT signed for user_id=%s, exp=%d sec', user_id, exp_seconds)
  ```
  (`logger` already exists in the file; `user_id` and `exp_seconds` are params of `generate_jwt`.)
- `app/config.py:36-37`: replace with:
  ```python
  logger.debug('PGRST_JWT_SECRET loaded: length=%d', len(PGRST_JWT_SECRET))
  ```
- Criterion: `rg "secret\[:8\]|PGRST_JWT_SECRET\[:16\]" app/` → 0.

### B.2 T23 — stop embedding WS JWT in HTML (fetch on demand)
**Riskiest task.** Three coordinated edits; the `.on()` handlers must still register even though `connect()` becomes async.

1. `app/context_processors.py:48-78` `inject_ws_config()`: delete the JWT-generation block (lines ~62-76). Keep `wsUrl`, `wsPort`, `pushEnabled`; leave `jwtToken` key removed or set to `''`. Return `{'trudnik_ws_config': config}`.
2. `templates/base.html:37`: remove the `jwtToken: '{{ trudnik_ws_config.jwtToken }}',` line (keep `userId` from T7).
3. `static/js/notifications-init.js:12-15`: replace the synchronous `const token = window.TRUDNIK_CONFIG?.jwtToken; if (token ...) connect(token)` with: register the `.on('notification')`/`.on('new_message')` handlers **unconditionally on `window.NotificationsWS`**, then connect via async token fetch:
   ```js
   if (window.TRUDNIK_CONFIG?.userId && window.NotificationsWS) {
       window.NotificationsWS.on('notification', function(data){ /* existing body */ });
       window.NotificationsWS.on('new_message', function(data){ /* existing body */ });
       (async () => {
           try {
               const r = await fetch('/api/ws/token');          // GET — no CSRF needed
               if (!r.ok) return;
               const d = await r.json();
               if (d.token) window.NotificationsWS.connect(d.token);
           } catch (e) { console.error('WS token fetch failed:', e); }
       })();
   }
   ```
4. New endpoint in `app/blueprints/notifications.py` (after line 14 bp def; `login_required`, `jsonify`, `session` already imported):
   ```python
   @notifications_bp.route('/api/ws/token')
   @login_required
   def get_ws_token():
       from datetime import datetime, timedelta, timezone
       import jwt as pyjwt, uuid
       from app.config import Config
       token = pyjwt.encode(
           {'user_id': str(session['user_id']),
            'exp': datetime.now(timezone.utc) + timedelta(minutes=5),
            'jti': str(uuid.uuid4())},
           Config.WEBSOCKET_JWT_SECRET or Config.SECRET_KEY, algorithm='HS256')
       return jsonify({'token': token, 'wsUrl': Config.WEBSOCKET_PUBLIC_URL})
   ```
   (`Config.WEBSOCKET_PUBLIC_URL` and `Config.WEBSOCKET_JWT_SECRET` both confirmed to exist.)
- Criterion: `rg "jwtToken" templates/base.html` → 0; GET `/api/ws/token` (authed) returns JSON token; HTML source has no JWT.

### B.3 T24 — enable migrations on deploy (⚠️ more than the contract states)
**Contract is incomplete here.** Two blockers found in `scripts/apply_migrations.py`:
- Line 275: early-exit unless env `MIGRATIONS_ENABLED` ∈ {true,1,yes}. Uncommenting `entrypoint.sh` alone does nothing.
- Lines 255-258: selects **every** `*.sql` in `migrations/` — would attempt the 3 ad-hoc files `manual_fix_all.sql`, `run_all_safe.sql`, `apply_manual_pgadmin.sql` (not idempotent → may fail).

**Recommended approach (green edits, avoids moving tracked SQL):**
1. `scripts/apply_migrations.py:255-258`: add a numeric-prefix filter so only `NNN_*.sql` are applied:
   ```python
   import re
   _MIG_RE = re.compile(r'^\d{3}_.*\.sql$', re.IGNORECASE)
   all_files = sorted(
       f for f in migrations_dir.iterdir()
       if f.is_file() and f.suffix.lower() == ".sql" and _MIG_RE.match(f.name)
   )
   ```
   (Ad-hoc files stay in place but are ignored — they are tracked, so no destructive move.)
2. `scripts/entrypoint.sh`: uncomment lines 9-11 **and** ensure the env gate is satisfied. Two options — pick one (recommend option (a)):
   - (a) Pass the flag inline: `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py`
   - (b) Set `MIGRATIONS_ENABLED=true` in `docker-compose.yml` environment for the web service and Amvera env.
3. Verify dry-run locally (needs a reachable DB; in Docker): `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py --dry-run`.
- **Risk flag:** auto-applying migrations at every container start can mask drift and run DDL under load. Consider a dedicated one-shot `migrate` step rather than inline in `entrypoint.sh`. If the user prefers caution, leave migrations as an explicit manual/Cron step (the existing `MIGRATIONS_ENABLED` gate already supports this) and document it in `docs/MIGRATION_PLAN.md` instead of auto-running. → **This is a real decision; default to option (a) but note the safer alternative.**

### B.4 T13 — finish: noscript banner + close-out
- `templates/base.html:48-56`: replace the fullscreen `<noscript>` overlay (`fixed inset-0 z-[200] ...`) with a non-blocking banner:
  ```html
  <noscript>
  <div class="bg-warning text-neutral-800 px-4 py-3 text-center text-sm">
      JavaScript отключён. Некоторые функции (уведомления, чат) будут недоступны.
  </div>
  </noscript>
  ```
  (Satisfies T18 step 4 and T55.)
- T13 test: see §C.

---

## C. Phase C — High-value new tests (subset)

Create under `tests/`, using the existing `client` + `mock_postgrest_client` fixtures (conftest auto-sets `POSTGREST_MOCK_MODE=1`). Run each with `py -3 -m pytest tests/<file> -q`.

| File | Covers | Key assertions |
|------|--------|----------------|
| `tests/test_password_reset.py` | T13 | GET `/password-reset/request`→200; POST valid email (mocked existing)→302; GET confirm bad token→redirect; GET confirm good token→200; POST mismatch→stays. Adapt to mock's handling of `profiles?email=eq.` and `rpc/change_password`. |
| `tests/test_logout.py` | T19 | GET `/logout`→405; POST no CSRF→400; POST + CSRF (logged-in session)→302 + session cleared. |
| `tests/test_change_password.py` | T20 | POST `/profile/change-password` with `current_password` (not `old_password`); empty→flash; correct→RPC called with `p_old_password=current_password`. |
| `tests/test_csrf_forms.py` | T18 | Sample a few mutating routes (login/apply/favorite) → POST without `_csrf_token`→400, with→ passes CSRF stage. |
| `tests/test_log_redaction.py` | T22 | `caplog` at INFO; call `generate_jwt`; assert no secret prefix substring appears; assert length-only line present. |
| `tests/test_ws_token.py` | T23 | GET `/api/ws/token` unauth→302/401; authed→JSON has `token`; `base.html` rendered source has no `jwtToken`. |

> Coverage gate `--cov-fail-under=90` for `auth.py`/`profile.py` is a contract criterion; if these tests plus existing ones don't reach it, treat as a non-blocking follow-up rather than blocking Iter 1 merge (note as deviation).

---

## D. Phase D — Iteration 1 verification & commit/PR

1. Targeted green run (full suite won't collect on Py 3.14; run broad subset, ignore `test_critical_gaps.py` which hits `127.0.0.1:5000`):
   ```
   py -3 -m pytest tests/ -q --ignore=tests/test_critical_gaps.py
   ```
   (Set the `TRUDNIK_*` + `POSTGREST_MOCK_MODE` env block; some e2e modules import-time-require creds — set the 4 `TRUDNIK_*` vars.)
2. Static checks (contract criteria):
   - `rg "app.blueprints.admin " --type py` → 0
   - `rg "logger = logging.getLogger" app/utils/rate_limit_decorator.py` → 1
   - `rg "secret\[:8\]|PGRST_JWT_SECRET\[:16\]" app/` → 0
   - `rg "jwtToken" templates/base.html` → 0
   - `rg "shift_id|shiftId" static/js/applications.js` → 0
   - `rg "X-CSRFToken" static/` → 0
   - `ls templates/password_reset*.html` → 2 files
   - `flask routes` shows `/admin/job-stats`, `/admin/health`, `/admin/migrations-status`, `/admin/reset-circuit-breaker`, `/api/ws/token`
3. Commit B/C work as `[T22]`, `[T23]`, `[T24]`, `[T13,T18,T55] noscript+tests`, `[TESTS] iter-1 high-value tests`, `[DOCS] changelog/log T22–T24`.
4. Tag `backup/post-iteration-1`.
5. Open PR `fix/trudnik-consistency → main` (yellow). Do **not** merge without human approval (red).

---

## E. Iterations 2–4 — outline (verified/challenged, not yet executed)

Each should become its own branch `fix/trudnik-consistency/iteration-N-<name>` off the merged Iter-1, with `backup/pre-iteration-N`.

### Iteration 2 (T25–T45) — architecture / dedup
**Spot-verified claims:**
- T25 ✅ confirmed: `app/__init__.py:88` has module-level `app = create_app()` — remove it; `app.py`/`asgi.py`/`conftest.py` already call `create_app()` correctly.
- T27 ✅ confirmed zero imports for `startup.py`, `payment_gateway.py`, `subscription_service.py`, `feature_flags.py`, `captcha.py`. **Sequencing note:** T14 (Iter 1) already edited `captcha.py`'s env var — deleting it in T27 makes that edit moot (harmless). Verify `app/utils/__init__.py` re-exports before deleting.
- T33 (duplicate `safe_redirect` import in `favorites.py:5-6`) — verify current line numbers before edit.
- T34 (`WTF_CSRF_ENABLED` in conftest) — verify Flask-WTF absent in `requirements.txt` before removing.
- T36 (dead utils funcs) — each needs `rg` confirmation of zero call sites before deletion.

**Contract tasks to treat with care (flag in their own log entries):**
- T26, T38, T53: refactor/extract to services — ensure no behavioral change; add tests.
- T31, T39: large template `url_for` rewrites — mechanical; verify every endpoint name exists via `flask routes` first.
- T40: add `@role_required('employer')` to favorites — confirm `role_required` import path & that worker-flow doesn't legitimately need favorites.
- T44: move mock infra out of `app/utils/__init__.py` into `app/testing/` via conftest fixtures — high blast radius; run full suite after.
- T42: remove duplicate `PERMANENT_SESSION_LIFETIME` — confirm which value (86400) is intended.

### Iteration 3 (T46–T66) — UX / a11y / dedup
- T46 ✅ likely valid (`095_drop_religion_text.sql` exists) — confirm `jobs.py` still filters `religion=eq.`.
- T47: delete `static/css/tailwind.css` — verify not referenced by any template/`<link>` first (yellow, 3.2 protocol).
- T48–T58: Jinja filter / macro extractions (`_components.html`) — additive, low risk.
- T63: `applications.js` `innerHTML` → `escapeHtml`/`textContent` — security; audit all `innerHTML` in `static/js/`.
- T65: tighten CSP `wss://*` → explicit host from `Config.WEBSOCKET_PUBLIC_URL`.
- T50/T51/T52: consolidate job-action JS into `static/js/jobs_actions.js`; unify `js-job-act-btn`→`js-job-action`; single `getCSRFToken` in `base.js`.
- Lighthouse/axe gates (Performance≥80, A11y≥90) are environment-dependent — run via Playwright skill, not assertions.

### Iteration 4 (T67–T70) — dead-code cleanup + final
- T67/T68: drop `photos:job_photos(*)`, `tariff, promoted_until` from SELECTs — confirm no template consumes them.
- T69: icon a11y audit (`aria-hidden`/`aria-label`).
- T70: `supervisord.conf` `--workers 1`→`2` (memory 512M) — yellow; verify mem headroom.
- Final: full regression in Docker (Py 3.12), `--cov-fail-under=80` overall + 90 for auth/profile; update `VERSION`, `README.md`, all `docs/`.

---

## F. Risks & open items

1. **Branch off `refactor/iteration-1-2-combined`, not `main`.** Decide: rebase Iter-1 branch onto current `main` before PR, or PR against `main` as-is (diff will include whatever that refactor branch already had). → Confirm target/base with user before opening PR.
2. **T24 auto-migration policy** (§B.3): inline-on-start vs explicit Cron/manual. Defaulting to inline with `MIGRATIONS_ENABLED=true`; safer alt documented.
3. **Coverage gate 90%** may not be reachable with subset tests alone — treat as non-blocking follow-up, not an Iter-1 blocker.
4. **Local Py 3.14** cannot collect the full suite (pytest capture crash) — all "tests green" verification must use targeted files locally or run in Docker.
5. **`test_critical_gaps.py`** and other `BASE_URL=http://127.0.0.1:5000` smoke tests require a running server — exclude from local CI-equivalent runs; they belong to the prod/e2e stage.
6. **Stale temp tag** `backup/temp-action-T1-20260709` to be deleted in §A.1.

---

## G. Quick reference — env block for local test runs
```powershell
$env:POSTGREST_MOCK_MODE='1'; $env:SECRET_KEY='test-secret'; $env:PGRST_JWT_SECRET='test-jwt-secret'
$env:WEBSOCKET_JWT_SECRET='test-ws-secret'; $env:FLASK_CONFIG='testing'
$env:TRUDNIK_EMPLOYER_EMAIL='org@test.ru'; $env:TRUDNIK_EMPLOYER_PASS='Pass1234!'
$env:TRUDNIK_WORKER_EMAIL='worker@test.ru'; $env:TRUDNIK_WORKER_PASS='Pass1234!'
```
Run with `py -3 -m pytest tests/<file> -q` (full-suite collection broken on 3.14 only).
