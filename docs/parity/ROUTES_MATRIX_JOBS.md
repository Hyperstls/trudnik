# Routes matrix — jobs / applications

**Обновлено:** 2026-11-01 после J001–J058.
**Статус:** паритет закрыт, открытых пунктов нет (см. [JOBS_RESULTS.md](JOBS_RESULTS.md)).
**Актуальный источник:** `djadmin/core/urls.py`; таблица — карта Flask→Django.

| Flask | Django | Статус | Комментарий |
|---|---|---|---|
| `GET /` — `jobs.index` | `GET /jobs` | ✅ | map/geo/skills/payment_max/filter, blacklist, cancelled скрыт (J004/J013/J019/J024/J025/J028/J053) |
| `GET/POST /job/new` | `GET/POST /jobs/new` | ✅ | валидации, expires_at, preferred_religion удалён, карта + геокодер (J001–J003/J022/J027/J049) |
| `GET /jobs/<id>` | `GET /jobs/<uuid>` | ✅ | detail, can_withdraw, photos, rating/verification, share/report/favorite, чат, trust, адрес/карта/маршрут (J003/J007/J014/J016/J018/J047/J050) |
| `GET/POST /jobs/<id>/edit` | `GET/POST /jobs/<uuid>/edit` | ✅ | после accepted — только описание (J033); фото отдельно |
| `POST /apply/<id>` | `POST /jobs/<uuid>/apply` | ✅ | RPC, русские коды, outbox (J004/J005) |
| `POST /unapply/<id>` | `POST /jobs/<uuid>/unapply` | ✅ | RPC + 12-часовое окно (J003) |
| `GET /my-applications?tab=sent|received` | same | ✅ | default received для работодателя, фильтр навыков, контакты, карточки, select-all (J008/J038/J046/J055) |
| `POST /api/applications/<id>/accept|reject|reopen` | `POST /applications/<uuid>/<action>` | ✅ | reopen через accept-RPC (J006) |
| `POST /api/applications/batch` | `POST /my-applications/action` | ✅ | ≤50, ownership (J009/J010) |
| `GET /my-jobs` | `GET /my-jobs` | ✅ | табы, application_count (J008); duplicate (J017) |
| `POST /my-jobs/action` | `POST /my-jobs/action` | ✅ | bulk cancel/restore/delete/duplicate (J009/J010/J017) |
| `POST /cancel-job/<id>` | `POST /jobs/<uuid>/cancel` | ✅ | RPC `cancel_job_atomic` |
| `POST /restore-job/<id>` | `POST /jobs/<uuid>/restore` | ✅ | RPC `restore_job_atomic` |
| `POST /api/jobs/<id>/force-complete` | `POST /jobs/<uuid>/force_complete` | ✅ | RPC `force_complete_job` |
| `POST /delete-job/<id>` | `POST /jobs/<uuid>/delete` | ✅ | RPC + удаление файлов (J011) |
| `POST /repost-job/<id>` | `POST /jobs/<uuid>/repost` | ✅ | фото/навыки/expires_at (J006/J017) |
| `POST /jobs/photo` | `POST /jobs/<uuid>/photos` | ✅ | лимит 3, unified, refcount (J007) |
| `POST /favorite-job/<id>` | `POST /jobs/<uuid>/favorite` | ✅ | toggle |
| `GET /favorites` | `GET /favorites` | ✅ | единая страница: задания/трудники/работодатели, bulk, приглашения (J043/J044) |
| legacy `/favorite-jobs`, `/favorite-people` | те же URL | ✅ | сохранены для совместимости |
| `GET /workers` | `GET /workers` | ✅ | skills/rating/payment/sort, badges invited/reliable, без карты (J021/J023/J026 n/a) |
| `GET /employers` | `GET /employers` | ✅ | open-jobs каталог без role-гейта, фильтры, blacklist, избранное (J031/J032) |
| `GET /jobs/<id>/rate-workers` | `GET /jobs/<uuid>/rate-workers` | ✅ | уникальность rater/job/rated, prefill (J029/J030) |
| `GET /ratings/user/<id>` | `GET /ratings/user/<uuid>` | ✅ | отзывы, типы, job-link |
| `POST /apply-selected`, `/unapply-selected` | same | ✅ | per-job counts, grouped notifications, safe redirect (J012) |
| `GET /chats` | `GET /chats` | ✅ | только accepted, последнее сообщение Subquery (J039/J058) |
| `GET /notifications` | `GET /notifications` | ✅ | delete-all кроме приглашений, настройки, типы, deep-links (J041/J052) |
| `GET /invitations` | `GET /invitations` | ✅ | поштучно + «Отклонить все ожидающие» (J040) |
| `GET /search` | `GET /search` | ✅ | 302 → `/jobs` с query (J047) |
