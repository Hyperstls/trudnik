# Routes matrix — jobs / applications

| Flask | Django | Статус | Комментарий |
|---|---|---|---|
| `GET /` — `jobs.index` | `GET /jobs` — `views.jobs_list` | ⚠️ | Django: нет map/geo/skills/payment_max/filter new-applied; cancelled виден по умолчанию; нет blacklist-фильтра. |
| `GET/POST /job/new` — `jobs.job_new` | `GET/POST /jobs/new` — `views_flow.job_create` | ❌/⚠️ | Нет stop-words, past-date, ranges, expires_at; `preferred_religion`; фото только после создания. |
| `GET /jobs/<id>` — `jobs.job_detail` | `GET /jobs/<uuid>` — `views.job_detail` | ⚠️ | Нет application_count, can_withdraw, employer verification, share/report/favorite employer; legacy `photo_urls` не видны. |
| `GET/POST /jobs/<id>/edit` — `jobs.job_edit` | `GET/POST /jobs/<uuid>/edit` — `views_flow.job_edit` | ⚠️ | Те же поля/валидация; фото через отдельный upload. |
| `POST /apply/<id>` + `/api/jobs/<id>/apply` | `POST /jobs/<uuid>/apply` | ⚠️ | RPC тот же; нет error-кодов blacklisted/own_job/duplicate/job_expired/job_in_past; нет employer notification. |
| `POST /unapply/<id>` + API | `POST /jobs/<uuid>/unapply` | ⚠️ | Нет withdraw-window 12 ч. |
| `GET /my-applications?tab=sent` | `GET /my-applications` | ⚠️ | Django — только sent; нет пагинации/skills. |
| `GET /my-applications?tab=received` | `GET /jobs/<uuid>/applicants` | ⚠️ | Отдельная простая страница; нет bulk accept/reject/reopen, пагинации, чата. |
| `POST /api/applications/<id>/accept|reject|reopen` | `POST /applications/<uuid>/<action>` | ⚠️ | accept/reject RPC те же; reopen — ORM rejected→pending, Flask — accept RPC. |
| `POST /api/applications/batch` | — | ❌ | Нет bulk accept/reject/reopen. |
| `GET /my-jobs` | `GET /my-jobs` | ⚠️ | Нет status-табов, bulk, duplicate, application_count. |
| `POST /my-jobs/action` (cancel/restore/delete/duplicate) | `POST /jobs/<uuid>/<action>` | ⚠️ | Нет bulk и duplicate; restore/cancel/force_complete/delete — есть. |
| `POST /cancel-job/<id>` | `POST /jobs/<uuid>/cancel` | ✅ | RPC `cancel_job_atomic`. |
| `POST /restore-job/<id>` | `POST /jobs/<uuid>/restore` | ✅ | RPC `restore_job_atomic`. |
| `POST /api/jobs/<id>/force-complete` | `POST /jobs/<uuid>/force_complete` | ✅ | RPC `force_complete_job`. |
| `POST /delete-job/<id>` | `POST /jobs/<uuid>/delete` | ✅ | RPC `delete_job_cascade`; файлы фото не удаляются. |
| `POST /repost-job/<id>` | `POST /jobs/<uuid>/repost` | ⚠️ | Не копирует фото, `expires_at` None. |
| `POST /jobs/photo` | `POST /jobs/<uuid>/photos` | ⚠️ | JobPhoto vs `photo_urls`; нет лимита 3; delete не удаляет файл. |
| `POST /favorite-job/<id>`, `/unfavorite-job/<id>` | `POST /jobs/<uuid>/favorite` | ✅ | Toggle. |
| `GET /favorites` | `GET /favorite-jobs` + `/favorite-people` | ⚠️ | Разделено на две страницы; проверить UI-паритет. |
| `GET /workers` | `GET /workers` | ⚠️ | Нет skills/карты/бейджей invited/reliable. |
| `GET /employers` | `GET /employers` | ⚠️ | Упрощено. |
| `GET /jobs/<id>/rate-workers` | `GET /jobs/<uuid>/rate-workers` | ⚠️ | Упрощено; нет API ratings. |
| `GET /ratings/user/<id>` | `GET /ratings/user/<uuid>` | ⚠️ | Упрощено; нет API ratings/completed-jobs/details. |
| `POST /apply-selected`, `/unapply-selected` | same | ⚠️ | Нет per-job try/except, detailed counts, notifications. |
