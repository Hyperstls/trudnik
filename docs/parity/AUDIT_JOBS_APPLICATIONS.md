# AUDIT — jobs / applications

**Дата:** 2026-10-31
**Flask:** `origin/main-flask` @ `9b3ed42` (worktree `../trudnik-flask`)
**Django:** `main` @ `3f4aa40` (+ незакоммиченные P0/P1 auth-правки)
**Статус:** первая область после auth/profile. Только аудит; код не менялся.
**Обновление 2026-10-31:** JOB-P0-01 исправлен контрактом J001
(verify 2/2, functional PASS, pattern PASS; `preferred_religion` удалён из JobForm/JobAdmin,
колонка dormant). JOB-P1-01/02/03 исправлены J002: stop-words, дата в прошлом,
оплата 0..1 000 000, работники 1..100 — серверные field-level ошибки; JobCrudTests 11/11,
test_flows 26/26. Остальные JOB-пункты закрыты контрактами J004–J033
(см. [JOBS_RESULTS.md](JOBS_RESULTS.md)); открытых пунктов нет, полный `core` — 412 OK.

## Главное

- **P0:** `preferred_religion` снова в форме создания/редактирования задания. Flask убрал его
  как дискриминацию при найме (ТК РФ ст.3): `app/blueprints/jobs.py:725`.
  Django `JobForm` включает поле (`core/forms.py:11,34`), шаблон рендерит все поля
  (`core/templates/core/job_form.html:13`).
- **P1:** отсутствуют серверные проверки Flask: дата в прошлом, stop-words (ТК РФ ст.15),
  диапазоны оплаты/работников, `expires_at=+30 дней`.
- **P1:** нет withdraw-window (Flask — 12 ч до начала), нет уведомлений на apply/accept/reject,
  нет фильтра заблокированных работодателей и исключения `cancelled` из каталога по умолчанию.
- **P1:** my-jobs/my-applications сильно упрощены: нет статус-табов, bulk cancel/restore/delete/duplicate,
  нет received/sent-табов, bulk accept/reject/reopen, пагинации.
- **P1:** фото задания раздвоены: `JobPhoto` (detail, upload) vs `photo_urls` (list card);
  новые фото не видны в списке, legacy — в detail; нет лимита 3; delete не удаляет файл.
- **P1:** `reopen` в Django делает ORM-переход rejected→pending, Flask делегирует в accept RPC
  (проверка слотов/FOR UPDATE). `repost_job` не копирует фото и `expires_at`.
- **P2:** каталог без карты/гео/навыков/payment_max/filter new-applied; job detail упрощён;
  каталог трудников без skills/карты/бейджей; employer/ratings-страницы упрощены.

## Что совпало

- `apply_job_atomic` RPC: проверки status/expires/date_time/own_job/blacklist/duplicate —
  общие для Flask и Django; Django вызывает тот же RPC.
- `accept_application`/`reject_application`/`cancel_worker_atomic`/`withdraw_application_atomic`
  RPC — те же; `accept_application` атомарно проверяет слоты и статус.
- `cancel_job_atomic`/`restore_job_atomic`/`force_complete_job`/`delete_job_cascade` — те же.
- `Job.objects.public()` (open/completed/cancelled) и `JobForm` ownership в `job_edit`.
- `job_applicants` ограничен владельцем/админом; `job_action` — владельцем.
- `jobs_list` фильтры q/city/status/payment_min/sort и `applied_ids` — есть.
- `bulk_apply`/`bulk_unapply` используют тот же RPC и лимит количества.

## Доказательства

- Django: `core/forms.py`, `core/views.py`, `core/views_flow.py`, `core/views_public_ext.py`,
  `core/models.py`, `core/templates/core/{job_form,job_detail,_job_card,my_jobs,my_applications}.html`.
- Flask: `app/blueprints/jobs.py`, `applications.py`, `app/utils/business.py`,
  `templates/{job_new,job_detail,my_jobs,my_applications}.html`.
- БД: `apply_job_atomic`, `accept_application`, `reject_application` — фактические сигнатуры
  и тела (MCP read-only).

## Полный реестр

См. [DISCREPANCIES_JOBS.md](DISCREPANCIES_JOBS.md). Матрицы:
[ROUTES_MATRIX_JOBS.md](ROUTES_MATRIX_JOBS.md), [UI_INVENTORY_JOBS.md](UI_INVENTORY_JOBS.md).

## Рекомендуемый порядок контрактов

1. **JOB-P0-01** — убрать `preferred_religion` из формы/шаблона; колонка dormant.
2. **JOB-P1-01/02/03** — портировать stop-words, past-date, payment/max_workers ranges.
3. **JOB-P1-04** — `expires_at=+30 дней` при create/repost.
4. **JOB-P1-05** — withdraw-window 12 ч + UI.
5. **JOB-P1-06/08** — каталог: исключить cancelled по умолчанию, blacklist-фильтр; error-коды apply.
6. **JOB-P1-07** — уведомления apply/accept/reject через outbox.
7. **JOB-P1-09/10** — my-jobs/my-applications: табы, bulk, duplicate.
8. **JOB-P1-11/12/13** — фото (единый источник, лимит 3, удаление файла), reopen через accept RPC, repost.
9. **P2** — карта/гео/навыки, job detail, workers/employers/ratings.
