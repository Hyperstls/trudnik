# Расхождения Flask → Django: jobs / applications

**Severity:** P0 — блокер/закон; P1 — высокий; P2 — средний/UX.
**Статус:** P0 и часть P1 закрыты контрактами; остальное — open.
**Обновление 2026-10-31:** JOB-P0-01 исправлен контрактом J001
(verify PASS, functional PASS, pattern PASS). JOB-P1-01/02/03 исправлены J002
(stop-words/дата/диапазоны, field-level ошибки; 11 JobCrudTests + 26 test_flows OK).
JOB-P1-04/05 исправлены J003 (expires_at=now+30d, окно отзыва 12 ч для accepted).
JOB-P1-06/08 исправлены J004 (каталог open/completed + blacklist; call_rpc
разворачивает jsonb/boolean, русские коды ошибок).
JOB-P1-07 исправлен J005 (outbox: application_received/accepted/rejected,
savepoint + fail-open). Полный core-набор — 252 OK.
Остальные пункты открыты.

## P0

| ID | Расхождение | Flask | Django | Влияние |
|---|---|---|---|---|
| JOB-P0-01 | **`preferred_religion` в форме задания.** | `jobs.py:725` — «убран: дискриминация при найме (ТК РФ ст.3)» | `core/forms.py:11,34`; `job_form.html:13` рендерит все поля | Дискриминационный признак при найме; нарушение ТК РФ ст.3 и риск 152-ФЗ (спецкатегория). |

## P1

| ID | Расхождение | Flask | Django | Влияние |
|---|---|---|---|---|
| JOB-P1-01 | Нет stop-words проверки (ТК РФ ст.15). | `jobs.py:77,672-682` | `core/forms.py` — нет | Риск переквалификации разовой услуги в трудовые отношения. |
| JOB-P1-02 | Нет серверной проверки даты в прошлом. | `jobs.py:44,684-689` | `core/forms.py` — нет `clean_date_time` | Задание можно создать/сохранить в прошлом; apply RPC отсечёт, но данные уже созданы. |
| JOB-P1-03 | Нет диапазонов оплаты/работников. | `jobs.py:697-710` (0..1 000 000; 1..100) | `core/forms.py:32-33` — только widget min/max (клиент) | Обход через POST: 0 работников, отрицательная/огромная оплата. |
| JOB-P1-04 | `expires_at` не устанавливается. | `jobs.py:729` — now+30 дней | `views_flow.py:138-149`; `views_public_ext.py:191+` — не задаётся | Задания без срока; `apply_job_atomic` не отсекает по expires; каталог засоряется. |
| JOB-P1-05 | Нет withdraw-window 12 ч. | `utils/business.py:37-55`; `jobs.py:556` | `views_flow.py:213-222` | Можно отозвать отклик в последний момент; паритет бизнес-правила нарушен. |
| JOB-P1-06 | Каталог: cancelled виден по умолчанию; нет blacklist-фильтра. | `jobs.py:164-166,202-210` (open/completed; applied — +cancelled; blacklist exclude) | `views.py:61-109` — `Job.objects.public()` (open/completed/cancelled), без blacklist | Отменённые задания в ленте; задания работодателей, заблокировавших пользователя, видны. |
| JOB-P1-07 | Нет уведомлений apply/accept/reject. | `applications.py:1-88,518-641` — `enqueue_notification` | `views_flow.py:201-208,249-286` — только RPC | Работодатель/работник не получают outbox-уведомления. |
| JOB-P1-08 | Не映射 error-коды apply. | `applications.py:99-110,160-170` (blacklisted/own_job/duplicate/no_slots/job_expired/job_in_past) | `views_flow.py:29-43` — нет этих кодов | Пользователь видит английский код/RPC-текст вместо понятного сообщения. |
| JOB-P1-09 | my-jobs упрощён. | `jobs.py:759-788`; табы all/open/completed/cancelled; bulk cancel/restore/delete/duplicate; application_count | `views_flow.py:171-173`; `my_jobs.html` 44 строки | Нет фильтров, bulk, duplicate, счётчика откликов. |
| JOB-P1-10 | my-applications упрощён. | `applications.py:390-518`; received/sent, skills, пагинация, bulk accept/reject/reopen | `views_flow.py:226-231`; `my_applications.html` 51 строка; received — отдельный `job_applicants` (59 строк) | Нет табов, bulk, пагинации; работодатель не видит полноценный список откликов. |
| JOB-P1-11 | Фото задания раздвоены. | `jobs.py:579-613` — `photo_urls[]`, ≤3, `/jobs/photo`; detail/list используют один массив | `views_public_ext.py:140-168` — `JobPhoto`; `_job_card.html:8` — `photo_urls`; `job_detail.html:68-72` — `photos` | Новые фото не видны в списке, legacy — в detail; нет лимита 3; delete не удаляет файл. |
| JOB-P1-12 | `reopen` через ORM. | `applications.py:534-641` — reopen делегирует в accept RPC (слоты/FOR UPDATE) | `views_flow.py:277-284` — rejected→pending напрямую | Обход проверки слотов/гонок; расхождение семантики «reopen». |
| JOB-P1-13 | `repost_job` теряет фото/срок. | `utils/business.py` copy_job (проверить) | `views_public_ext.py:191+` — не копирует фото, `expires_at` None | Перепубликация неполная; задание без срока. |

## P2

| ID | Расхождение | Evidence |
|---|---|---|
| JOB-P2-01 | Каталог без карты/гео/навыков/payment_max/filter new-applied. | Flask `jobs.py:127-389`, `index.html`; Django `views.py:61-109`, `jobs_list.html` 85 строк |
| JOB-P2-02 | Job detail упрощён: нет application_count, can_withdraw, employer verification, share/report/favorite employer, ratings-секции. | Flask `job_detail.html` 800+; Django 109 строк |
| JOB-P2-03 | Max lengths: organization_name 500 vs 255; detailed_description без max vs 5000. | Flask `jobs.py:659-668`; Django `models.py:254-257` |
| JOB-P2-04 | После create Django ведёт на detail; Flask — в my_jobs. | `views_flow.py:147-148`; `jobs.py:745` |
| JOB-P2-05 | bulk_apply: нет per-job try/except, detailed skipped/error counts, уведомлений. | `views_public_ext.py:88-138`; Flask `applications.py:127-214` |
| JOB-P2-06 | job_photo_delete не удаляет файл с диска. | `views_public_ext.py:161-168` |
| JOB-P2-07 | JobForm содержит org_description/object_description, Flask ставит пустые. | `forms.py:8-12`; Flask `jobs.py:715-716` |
| JOB-P2-08 | q не ищет по object_description. | `views.py:63-66`; Flask `jobs.py:173-176` |
| JOB-P2-09 | job_applicants разрешён админу; Flask — владельцу. | `views_flow.py:235-239`; `applications.py:518+` |
| JOB-P2-10 | job_edit разрешён для любых статусов; Flask — проверить ограничения. | `views_flow.py:153-156`; Flask `jobs.py:1198+` |
| JOB-P2-11 | Ratings/rate_workers упрощены. | Flask `ratings.py` 384; Django `views_public_ext.py:58-86` |
| JOB-P2-12 | Каталог трудников без skills/карты/бейджей invited/reliable. | Flask `jobs.py:389-508`; Django `views.py:147-154` |
| JOB-P2-13 | Employers/ratings pages упрощены. | Flask `employers.py`/`ratings.py`; Django `views_public_ext.py` |

## Что совпало

- `apply_job_atomic`, `accept_application`, `reject_application`, `withdraw_application_atomic`,
  `cancel_worker_atomic`, `cancel_job_atomic`, `restore_job_atomic`, `force_complete_job`,
  `delete_job_cascade` — те же RPC (проверено в БД).
- `accept_application` атомарно проверяет слоты/статус/FOR UPDATE.
- Ownership: job_edit/job_action/job_applicants — по владельцу/админу.
- `jobs_list` фильтры/сортировки и `applied_ids`; bulk RPC-цикл.
