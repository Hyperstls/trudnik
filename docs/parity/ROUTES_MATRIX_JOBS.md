# Routes matrix — jobs / applications

Обновлено 2026-10-31 после J001–J010 (см. [JOBS_RESULTS.md](JOBS_RESULTS.md)).
Статусы: ✅ паритет; ⚠️ есть отличия/упрощения; ❌ отсутствует.

| Flask | Django | Статус | Комментарий |
|---|---|---|---|
| `GET /` — `jobs.index` | `GET /jobs` — `views.jobs_list` | ⚠️ | Нет map/geo/skills/payment_max/filter new-applied. cancelled скрыт, blacklist учтён (J004). |
| `GET/POST /job/new` — `jobs.job_new` | `GET/POST /jobs/new` — `views_flow.job_create` | ✅/⚠️ | Stop-words/date/ranges/expires_at есть (J002/J003), `preferred_religion` удалён (J001); фото — после создания. |
| `GET /jobs/<id>` — `jobs.job_detail` | `GET /jobs/<uuid>` — `views.job_detail` | ⚠️ | can_withdraw и legacy-фото есть (J003/J007); нет application_count, employer verification, share/report/favorite employer. |
| `GET/POST /jobs/<id>/edit` — `jobs.job_edit` | `GET/POST /jobs/<uuid>/edit` — `views_flow.job_edit` | ✅/⚠️ | Валидации и expires_at есть; фото через отдельный upload. |
| `POST /apply/<id>` + `/api/jobs/<id>/apply` | `POST /jobs/<uuid>/apply` | ✅/⚠️ | RPC, error-коды и employer outbox есть (J004/J005); JSON-API маршрута нет. |
| `POST /unapply/<id>` + API | `POST /jobs/<uuid>/unapply` | ✅ | RPC + withdraw-window для accepted (J003). |
| `GET /my-applications?tab=sent` | `GET /my-applications?tab=sent` | ✅/⚠️ | Табы, пагинация (J008); фильтра навыков нет. |
| `GET /my-applications?tab=received` | `GET /my-applications?tab=received` | ✅ | Отклики на свои задания + bulk (J008–J010). |
| `POST /api/applications/<id>/accept|reject|reopen` | `POST /applications/<uuid>/<action>` | ✅ | reopen делегирует в accept-RPC (J006). |
| `POST /api/applications/batch` | `POST /my-applications/action` | ✅ | accept/reject/reopen, ≤50 (J009), UI-панель (J010). |
| `GET /my-jobs` | `GET /my-jobs` | ✅/⚠️ | Табы и application_count есть (J008); duplicate отсутствует. |
| `POST /my-jobs/action` | `POST /my-jobs/action` | ✅/⚠️ | bulk cancel/restore/delete + UI (J009/J010); duplicate отсутствует. |
| `POST /cancel-job/<id>` | `POST /jobs/<uuid>/cancel` | ✅ | RPC `cancel_job_atomic`. |
| `POST /restore-job/<id>` | `POST /jobs/<uuid>/restore` | ✅ | RPC `restore_job_atomic`. |
| `POST /api/jobs/<id>/force-complete` | `POST /jobs/<uuid>/force_complete` | ✅ | RPC `force_complete_job`. |
| `POST /delete-job/<id>` | `POST /jobs/<uuid>/delete` | ✅/⚠️ | RPC `delete_job_cascade`; файлы фото при удалении задания не чистятся (P2-06). |
| `POST /repost-job/<id>` | `POST /jobs/<uuid>/repost` | ✅ | Копирует фото/навыки, expires_at +30d, транзакция (J006). |
| `POST /jobs/photo` | `POST /jobs/<uuid>/photos` | ✅ | Лимит 3, unified массив, refcount-удаление (J007). |
| `POST /favorite-job/<id>`, `/unfavorite-job/<id>` | `POST /jobs/<uuid>/favorite` | ✅ | Toggle. |
| `GET /favorites` | `GET /favorite-jobs` + `/favorite-people` | ⚠️ | Разделено на две страницы. |
| `GET /workers` | `GET /workers` | ⚠️ | Нет skills/карты/бейджей invited/reliable. |
| `GET /employers` | `GET /employers` | ⚠️ | Упрощено. |
| `GET /jobs/<id>/rate-workers` | `GET /jobs/<uuid>/rate-workers` | ⚠️ | Упрощено; нет API ratings. |
| `GET /ratings/user/<id>` | `GET /ratings/user/<uuid>` | ⚠️ | Упрощено; нет API ratings/completed-jobs/details. |
| `POST /apply-selected`, `/unapply-selected` | same | ⚠️ | Нет per-job try/except, detailed counts, notifications (P2-05). |
