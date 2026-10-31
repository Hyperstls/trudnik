# UI inventory — jobs / applications

Статусы: ✅ есть; ⚠️ есть, но упрощено/отличается; ❌ отсутствует.
Обновлено 2026-10-31 после J001–J010 (см. [JOBS_RESULTS.md](JOBS_RESULTS.md)).

## Каталог заданий

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Поиск q | `index.html` | `jobs_list.html` | ✅ |
| Город | `index.html` | `jobs_list.html` | ✅ |
| Оплата min/max | `index.html` | только min | ⚠️ JOB-P2-01 |
| Навыки | `index.html` | — | ❌ JOB-P2-01 |
| Сортировка | newest/price | newest/price_asc/price_desc | ✅/⚠️ |
| Фильтр «Новые/Откликнулся» | `index.html` | — | ❌ JOB-P2-01 |
| Карта/гео | `index.html` | — | ❌ JOB-P2-01 |
| Откликнуться/отозвать | карточка/деталь | `job_detail.html` | ✅ |
| Избранное | карточка | `job_detail.html` | ✅ |
| Пагинация | есть | есть | ✅ |
| Скрыть cancelled | default open/completed | `PUBLIC_STATUSES` | ✅ J004 |
| Blacklist-фильтр | есть | `Blacklist` exclude | ✅ J004 |

## Создание/редактирование задания

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Название/описание/адрес/дата/оплата/работники/город | `job_new.html` | `job_form.html` | ✅ |
| Work type | есть | есть | ✅ |
| Навыки | есть | есть | ✅ |
| Фото (≤3) | `/jobs/photo` + `photo_urls[]` | `JobPhoto` после создания, лимит 3 | ✅/⚠️ J007 |
| Lat/lng/карта | есть | — | ❌ JOB-P2-01 |
| Stop-words | сервер | `validators_jobs` | ✅ J002 |
| Дата в прошлом | сервер | `clean_date_time` | ✅ J002 |
| Оплата 0..1M / работники 1..100 | сервер | `validate_payment/workers` | ✅ J002 |
| `preferred_religion` | удалён | удалён | ✅ J001 |
| `expires_at` 30 дней | сервер | create/edit/repost | ✅ J003/J006 |

## Мои задания

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Табы all/open/completed/cancelled | есть | `?status=` | ✅ J008 |
| Bulk cancel/restore/delete | есть | `/my-jobs/action` + панель | ✅ J009/J010 |
| Bulk duplicate | есть | — | ❌ (нужен вынос repost-хелпера) |
| Per-job duplicate | есть | `repost_job` (кнопки в UI нет) | ⚠️ |
| Per-job cancel/restore/force-complete/delete | есть | есть | ✅ |
| Application count | есть | `annotation Count` | ✅ J008 |
| Edit/rate-workers | есть | edit + rate-workers | ✅/⚠️ |
| Копировать ID | есть | — | ⚠️ |

## Мои отклики / отклики на задания

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Табы received/sent | есть | `?tab=received|sent` | ✅ J008 |
| Пагинация | есть | 20/страница | ✅ J008 |
| Фильтр навыков | есть | — | ❌ JOB-P2-01 |
| Bulk accept/reject/reopen | есть | `/my-applications/action` + панель | ✅ J009/J010 |
| Per-app accept/reject/reopen | есть | `job_applicants` + received-таб | ✅ |
| Чат по отклику | есть | `chat_room` | ✅ |
| Контакты работника | есть | ? (проверить) | ⚠️ |

## Деталь задания

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Поделиться | есть | — | ❌ JOB-P2-02 |
| Пожаловаться на работодателя | есть | — | ❌ JOB-P2-02 |
| Избранный работодатель | есть | — | ❌ JOB-P2-02 |
| Application count (owner) | есть | — | ❌ JOB-P2-02 |
| Withdraw window | `can_withdraw` | `can_withdraw` (12 ч, accepted) | ✅ J003 |
| Apply/unapply | есть | есть | ✅ |
| Edit/cancel/restore/delete/force-complete | есть | есть | ✅ |
| Rate workers | есть | есть | ✅/⚠️ |
| Ratings-секция | есть | ? | ⚠️ |
| Legacy photo_urls | есть | unified `job_photo_urls` | ✅ J007 |
