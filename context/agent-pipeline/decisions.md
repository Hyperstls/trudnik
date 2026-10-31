# Decisions — agent pipeline

Append-only: решения и измерения. Числа, команды, причины.

## 2026-10-31 15:13:39 — T1: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/T1.review.prompt.md

## 2026-10-31 15:13:39 — T1: заметка

**Кто:** Hyperstls

Измерение: verify T1 = 3/3 check exit 0; review-packet = 3607 bytes; новых файлов 2; ревьюер независимый: PASS; attempts=0/3.

## 2026-10-31 15:13:59 — T2: ручной перевод статуса

**Кто:** Hyperstls

**Почему:** честное исправление: удалён demo/scope_drift.py (вне контракта)

**Переход:** fixing → fixing

## 2026-10-31 15:14:01 — T2: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/T2.review.prompt.md

## 2026-10-31 15:14:12 — T3: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/T3.review.prompt.md

## 2026-10-31 15:14:19 — T4: BLOCKED: лимит механических попыток

**Измерение:** attempts=3/3, scope=ok, checks=always_fail=1.

**Решение:** остановка. Третья вариация той же ошибки дороже вопроса человеку.

**Вопрос человеку:** что чинить — код, контракт или проверку? После ответа: `pipeline.py set T4 --status fixing --reason '...' --reset-attempts`.

## 2026-10-31 15:14:26 — T5: ревью: FAIL

**Раунд:** 1/2

**Вердикт ревьюера:** фикстура: содержательный блокер №1

**Действие:** fixing — раунд исправлений

## 2026-10-31 15:14:27 — T5: ревью: FAIL

**Раунд:** 2/2

**Вердикт ревьюера:** фикстура: содержательный блокер №2

**Действие:** blocked — вопрос человеку

## 2026-10-31 15:14:41 — T6: контракт обновлён

**Причина:** liar_ok — фикстура, доказавшая столп 1; после фиксации FAIL она удалена из проверок, критерий перенесён в историю

**Проверки до:** ['compile', 'liar_ok', 'liar_error']

**Проверки после:** ['compile', 'liar_error']

## 2026-10-31 15:14:43 — T6: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/T6.review.prompt.md

## 2026-10-31 15:14:51 — T7: verify --skip-scope (обход scope)

**Кто:** selftest

**Почему:** selftest п.13: демонстрация обязательного следа обхода scope

**Дрейф, который обойдён:** ['demo/skip_drift.py']

## 2026-10-31 15:14:58 — T7: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/T7.review.prompt.md

## 2026-10-31 15:41:21 — CONFIG: конфигурация изменена

**Кто:** Hyperstls

**Новое значение:** max_attempts=3, max_review_rounds=2, check_timeout=600, spill_patterns=['/packs/', '/logs/', '/tasks/', 'state\\.json$', 'progress\\.md$', 'decisions\\.md$', '__pycache__/', '\\.pyc$', '\\.pytest_cache/', '\\.mypy_cache/', '\\.ruff_cache/', 'C:/Program Files/Git/_uploads/']

## 2026-10-31 15:45:42 — P001: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P001.review.prompt.md

## 2026-10-31 15:45:42 — P001: заметка

**Кто:** Hyperstls

Два гейта: contract verify 3/3 exit 0 (compile, captcha_tests, auth_regression); functional review PASS; pattern review PASS (XSS/fail-open/N+1; fail-closed сохранён). Исполнитель дополнительно передал captcha_client_key в render сброса пароля.

## 2026-10-31 15:52:10 — P002: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P002.review.prompt.md

## 2026-10-31 15:52:10 — P002: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, upload_tests 9/9); functional review PASS; pattern review PASS (XSS/fail-open/N+1; ACL по каноническому пути, alias avatars/../verification-docs покрыт тестом, private/no-store).

## 2026-10-31 15:55:40 — P003: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P003.review.prompt.md

## 2026-10-31 15:55:40 — P003: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, public_tests 10/10); functional review PASS; pattern review PASS (XSS/fail-open/N+1; contact/email_public/religion удалены из PUBLIC_PROFILE_FIELDS и шаблона, тест проверяет реальные значения). Примечание: правка шаблона требует npm run build:css перед коммитом (release step, вне контракта).

## 2026-10-31 15:58:29 — P004: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P004.review.prompt.md

## 2026-10-31 15:58:29 — P004: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, profile_tests 6/6); functional review PASS; pattern review PASS (XSS/fail-open/N+1; religion удалён из формы и fieldsets, POST не меняет religion_id).

## 2026-10-31 16:13:35 — P101: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P101.review.prompt.md

## 2026-10-31 16:13:35 — P101: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, auth_tests 20/20); functional review PASS; pattern review PASS (XSS/fail-open/N+1; worker-only поля, skills sync с логом, savepoint для IntegrityError).

## 2026-10-31 16:18:32 — P102: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P102.review.prompt.md

## 2026-10-31 16:18:32 — P102: заметка

**Кто:** Hyperstls

Два гейта: contract verify 3/3 exit 0 (compile, auth_tests 24/24, profile_tests 8/8); functional review PASS; pattern review PASS (XSS/fail-open/N+1; ИНН checksum, contact format, ASCII/no-space password, skip только post_jobs).

## 2026-10-31 16:23:24 — P106: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P106.review.prompt.md

## 2026-10-31 16:23:24 — P106: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, profile_tests 9/9); functional review PASS; pattern review PASS (XSS/fail-open/N+1; auth-hash только после успешного RPC, текущая сессия жива, другие разлогинены).

## 2026-10-31 16:44:19 — P103: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P103.review.prompt.md

## 2026-10-31 16:44:19 — P103: заметка

**Кто:** Hyperstls

Два гейта: contract verify 3/3 exit 0 (compile, login_tests 35/35, auth_regression 24/24); functional PASS; pattern PASS (XSS/fail-open/N+1; per-IP 20/ч, cache lockout, fail-closed, обход глушения PermissionDenied через lock_remaining).

## 2026-10-31 16:52:16 — P104: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P104.review.prompt.md

## 2026-10-31 16:52:17 — P104: заметка

**Кто:** Hyperstls

Два гейта: contract verify 3/3 exit 0 (compile, auth_tests 26/26, login_regression 35/35); functional PASS; pattern PASS (XSS/fail-open/N+1; cooldown в cache, IP-лимиты, fail-closed, _COOLDOWNS удалён).

## 2026-10-31 17:01:05 — P107: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P107.review.prompt.md

## 2026-10-31 17:01:05 — P107: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, upload_tests 11/11); functional PASS; pattern PASS (XSS/fail-open/N+1; PDF только по magic bytes для verification-docs, avatars/jobs reject).

## 2026-10-31 17:03:37 — P108: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P108.review.prompt.md

## 2026-10-31 17:03:37 — P108: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, public_tests 14/14); functional PASS; pattern PASS (XSS/fail-open/N+1; fallback photo_url на /profile,/workers/<id>,/workers, avatar_url приоритет).

## 2026-10-31 17:08:08 — P114: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P114.review.prompt.md

## 2026-10-31 17:08:08 — P114: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, upload_tests 12/12); functional PASS; pattern PASS (XSS/fail-open/N+1; сбор URL до RPC, удаление после успеха, path traversal закрыт resolve_upload_url, ошибки логируются).

## 2026-10-31 17:10:43 — B001: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/B001.review.prompt.md

## 2026-10-31 17:10:44 — B001: заметка

**Кто:** Hyperstls

Два гейта: contract verify 3/3 exit 0 (build_css, pre_deploy 7/7, compile); functional PASS; pattern PASS (XSS/fail-open/N+1; content/scan включают djadmin/core/templates, CSS пересобран, другие проверки не тронуты).

## 2026-10-31 17:17:11 — T001: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/T001.review.prompt.md

## 2026-10-31 17:17:11 — T001: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, task_tests 8/8); functional PASS; pattern PASS (XSS/fail-open/N+1; dict/скаляр/None, RPC count учтён, warning при сбое). Найдено полным прогоном core (TypeError int(dict)).

## 2026-10-31 18:01:12 — P112: ревью: FAIL

**Раунд:** 1/2

**Вердикт ревьюера:** Pattern FAIL: self-report test can be masked by the one-per-hour report rate limit; cache.clear() only at test start. Fix: clear cache immediately before self-report POST (or use a fresh reporter) and assert the self-report rejection cause.

**Действие:** fixing — раунд исправлений

## 2026-10-31 18:04:45 — P112: verify --skip-scope (обход scope)

**Кто:** orchestrator

**Почему:** orchestrator added P110 contract source and docs/parity/MIGRATION_LEDGER.md after P112 dispatch; unrelated to P112 test change

**Дрейф, который обойдён:** ['context/agent-pipeline/selftest/contracts/P110.json', 'docs/parity/MIGRATION_LEDGER.md']

## 2026-10-31 18:07:23 — P112: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P112.review.prompt.md

## 2026-10-31 18:07:23 — P112: заметка

**Кто:** Hyperstls

Два гейта после исправления: contract verify 2/2 (skip-scope trace для оркестраторских файлов P110/MIGRATION_LEDGER), functional PASS, pattern PASS. Первый pattern-review FAIL (self-report masked by rate-limit) -> fixing -> cache.clear + различение RPC/rate-limit -> PASS. 50 тестов OK, IDOR не найден.

## 2026-10-31 18:11:55 — P110: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P110.review.prompt.md

## 2026-10-31 18:11:55 — P110: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, auth_tests 42/42); functional PASS; pattern PASS (XSS/fail-open/N+1; ORM default False, create_superuser True, make_profile verified, DB default не тронут).

## 2026-10-31 19:06:45 — P105: ревью: FAIL

**Раунд:** 1/2

**Вердикт ревьюера:** Pattern FAIL: import of send_transactional_email is outside try in views_auth._send_mail (views_auth.py:75-77); ImportError/Celery config error bypasses sync fallback and breaks registration. Move import inside try; add test that simulates import failure (sys.modules['core.tasks']=None) and asserts sync fallback + user created.

**Действие:** fixing — раунд исправлений

## 2026-10-31 19:10:47 — P105: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/P105.review.prompt.md

## 2026-10-31 19:10:47 — P105: заметка

**Кто:** Hyperstls

Два гейта после fixing: contract verify 3/3 (compile, auth_tests 29/29, task_tests 8/8), functional PASS, pattern PASS. Первый pattern FAIL (import вне try -> обход fallback) исправлен: импорт внутри try + тест с sys.modules['core.tasks']=None; async/sync/fallback/retry покрыты.

## 2026-10-31 19:41:22 — J001: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J001.review.prompt.md

## 2026-10-31 19:41:22 — J001: заметка

**Кто:** Hyperstls

Два гейта: contract verify 2/2 exit 0 (compile, JobCrudTests 7/7); functional PASS; pattern PASS (XSS/fail-open/N+1; preferred_religion удалён из JobForm/JobAdmin, POST игнорируется, колонка dormant).

## 2026-10-31 20:08:25 — L001: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/L001.review.prompt.md

## 2026-10-31 20:08:26 — L001: заметка

**Кто:** Hyperstls

Два гейта: verify 2/2 (compile, public_tests 19/19); functional PASS; pattern PASS (XSS/fail-open/N+1; fallback только privacy/terms/safety, SitePage override, 404 unknown). E2E smoke выявил 404 при пустом site_pages.

## 2026-10-31 20:24:12 — J002: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J002.review.prompt.md

## 2026-10-31 20:24:12 — J002: заметка

**Кто:** Hyperstls

Два гейта: verify 2/2 (compile, JobCrudTests 11/11; test_flows 26/26); functional PASS; pattern PASS (XSS/fail-open/N+1; stop-words/date/ranges field-level, invalid job not created).

## 2026-10-31 20:50:37 — E001: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/E001.review.prompt.md

## 2026-10-31 20:50:37 — E001: заметка

**Кто:** Hyperstls

Два гейта: verify 2/2 (compile, admin_tests 8/8); functional PASS; pattern PASS (XSS/fail-open/N+1; все secret-маркеры маскируются, несекретные видны, staff-only сохранён).

## 2026-10-31 21:20:59 — J003: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J003.review.prompt.md

## 2026-10-31 21:20:59 — J003: заметка

**Кто:** Hyperstls

Ревьюер PASS. Некритичные замечания: (1) assertNotContains('disabled') page-wide — сузить до кнопки; (2) can_withdraw=True при date_time=None — fail-open, но RPC 084 серверно блокирует; (3) pending-тест проверяет отсутствие note, не disabled. Принято без блокировки.

## 2026-10-31 21:28:57 — J004: ручной перевод статуса

**Кто:** Hyperstls

**Почему:** Contract gap found by tests: call_rpc jsonb wrapper breaks all RPC messages; change_password bool wrapped gives false success. Expanding contract with rpc.py.

**Переход:** implementing → fixing

## 2026-10-31 21:28:57 — J004: контракт обновлён

**Причина:** Added call_rpc contract fix; tests consolidated in test_flows.py (4-file limit).

**Проверки до:** ['compile', 'flow_tests', 'public_tests']

**Проверки после:** ['compile', 'flow_tests', 'public_tests']

## 2026-10-31 21:35:36 — J004: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J004.review.prompt.md

## 2026-10-31 21:35:36 — J004: заметка

**Кто:** Hyperstls

Ревьюер PASS. Некритично: (1) jobs_list мог бы сохранять .public() в цепочке; (2) call_rpc_rows/as_user пока без _decode_json; (3) неизвестный code даёт generic-текст. Вынести в отдельную задачу по унификации RPC-хелперов.

## 2026-10-31 21:41:52 — J004T: ревью: FAIL

**Раунд:** 1/2

**Вердикт ревьюера:** Empty diff: baseline captured after the test edit; re-dispatch with pre-edit baseline.

**Действие:** fixing — раунд исправлений

## 2026-10-31 21:41:52 — J004T: ручной перевод статуса

**Кто:** Hyperstls

**Почему:** Re-dispatch with pre-edit baseline (process fix).

**Переход:** fixing → planned

## 2026-10-31 21:42:31 — J004T: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J004T.review.prompt.md

## 2026-10-31 21:55:05 — J005: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J005.review.prompt.md

## 2026-10-31 21:55:06 — J005: заметка

**Кто:** Hyperstls

Ревью PASS. Некритично: assertLogs для ветки логирования; идемпотентность reject→reopen→reject (каждая строка = реальный переход) — вынести при необходимости exactly-once.

## 2026-10-31 22:11:57 — J006: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J006.review.prompt.md

## 2026-10-31 22:11:57 — J006T: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J006T.review.prompt.md

## 2026-10-31 22:11:57 — J006: заметка

**Кто:** Hyperstls

Ревью PASS. Некритично: direct POST /reopen/ для pending разрешён RPC (как Flask), шаблон показывает кнопку только для rejected; повторный reopen даёт bad_status без роста счётчика.

## 2026-10-31 22:16:30 — J007: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J007.review.prompt.md

## 2026-10-31 22:16:30 — J007: заметка

**Кто:** Hyperstls

Ревью PASS. Некритично: дедуп только между JobPhoto и legacy; _job_card используется только в jobs_list; delete_upload_url уже защищён от traversal/не-/uploads.

## 2026-10-31 22:25:39 — J008: verify --skip-scope (обход scope)

**Кто:** Hyperstls

**Почему:** static/css/tailwind.min.css rebuilt by npm run build:css after my_jobs/my_applications template classes; generated artifact, not business code

**Дрейф, который обойдён:** ['static/css/tailwind.min.css']

## 2026-10-31 22:27:27 — J008: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J008.review.prompt.md

## 2026-10-31 22:27:27 — J008: заметка

**Кто:** Hyperstls

Ревью PASS. CSS-дрейф обойдён штатным --skip-scope (сгенерированный tailwind.min.css после правки шаблонов), след в state/progress/decisions. Bulk-операции остаются на J009.

## 2026-10-31 22:37:03 — J009: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J009.review.prompt.md

## 2026-10-31 22:37:03 — J009: заметка

**Кто:** Hyperstls

Ревью PASS. Bulk duplicate не входит (нужен вынос repost-хелпера); UI-панель массовых действий — J010.

## 2026-10-31 22:43:12 — J010: ревью пройдено

**Вердикт:** PASS

**Кто:** Hyperstls

**Пакет:** context/agent-pipeline/packs/J010.review.prompt.md

## 2026-10-31 22:43:12 — J010: заметка

**Кто:** Hyperstls

Ревью PASS. Остаётся только bulk duplicate (требует вынос repost-хелпера) — отдельная задача при необходимости.
