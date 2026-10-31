# UI inventory — jobs / applications

Статусы: ✅ есть; ⚠️ есть, но упрощено/отличается; ❌ отсутствует.

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
| Скрыть cancelled | default open/completed | `Job.objects.public()` + cancelled | ❌ JOB-P1-06 |
| Blacklist-фильтр | есть | — | ❌ JOB-P1-06 |

## Создание/редактирование задания

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Название/описание/адрес/дата/оплата/работники/город | `job_new.html` | `job_form.html` | ✅ |
| Work type | есть | есть | ✅ |
| Навыки | есть | есть | ✅ |
| Фото (≤3, до сабмита) | `/jobs/photo` + `photo_urls[]` | только после создания (`JobPhoto`) | ⚠️ JOB-P1-11 |
| Lat/lng/карта | есть | — | ❌ JOB-P2-01 |
| Stop-words | сервер | — | ❌ JOB-P1-01 |
| Дата в прошлом | сервер | — | ❌ JOB-P1-02 |
| Оплата 0..1M / работники 1..100 | сервер | только widget min/max | ❌ JOB-P1-03 |
| `preferred_religion` | удалён | есть | ❌ JOB-P0-01 |
| `expires_at` 30 дней | сервер | — | ❌ JOB-P1-04 |

## Мои задания

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Табы all/open/completed/cancelled | есть | — | ❌ JOB-P1-09 |
| Bulk cancel/restore/delete/duplicate | есть | — | ❌ JOB-P1-09 |
| Per-job duplicate | есть | — | ❌ JOB-P1-09 |
| Per-job cancel/restore/force-complete/delete | есть | есть | ✅ |
| Application count | есть | — | ❌ JOB-P1-09 |
| Edit/rate-workers | есть | edit + rate-workers | ✅/⚠️ |
| Копировать ID | есть | — | ⚠️ |

## Мои отклики / отклики на задания

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Табы received/sent | есть | sent; received — отдельная | ⚠️ JOB-P1-10 |
| Пагинация | есть | — | ❌ JOB-P1-10 |
| Фильтр навыков | есть | — | ❌ JOB-P1-10 |
| Bulk accept/reject/reopen | есть | — | ❌ JOB-P1-10 |
| Per-app accept/reject/reopen | есть | `job_applicants` | ✅/⚠️ |
| Чат по отклику | есть | ? (проверить) | ⚠️ |
| Контакты работника | есть | ? | ⚠️ |

## Деталь задания

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Поделиться | есть | — | ❌ JOB-P2-02 |
| Пожаловаться на работодателя | есть | — | ❌ JOB-P2-02 |
| Избранный работодатель | есть | — | ❌ JOB-P2-02 |
| Application count (owner) | есть | — | ❌ JOB-P2-02 |
| Withdraw window | `can_withdraw` | — | ❌ JOB-P1-05 |
| Apply/unapply | есть | есть | ✅ |
| Edit/cancel/restore/delete/force-complete | есть | есть | ✅ |
| Rate workers | есть | есть | ✅/⚠️ |
| Ratings-секция | есть | ? | ⚠️ |
| Legacy photo_urls | есть | detail — JobPhoto only | ❌ JOB-P1-11 |
