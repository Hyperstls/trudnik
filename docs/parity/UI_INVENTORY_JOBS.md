# UI inventory — jobs / applications

**Обновлено:** 2026-11-01 после J001–J058.
**Статус:** все элементы реализованы; открытых UX-пунктов нет.
**Шаблоны:** `djadmin/core/templates/core/` (корневые `templates/` — legacy Flask).

## Каталог заданий (`/jobs`)

| Элемент | Django | Статус |
|---|---|---|
| Поиск q (работа/организация/город/описания) | `jobs_list.html` | ✅ J020 |
| Город | форма фильтров | ✅ |
| Оплата от/до | `payment_min`/`payment_max` | ✅ J013 |
| Навыки (multi, чекбоксы) | `<details>`-панель | ✅ J019/J037/J042 |
| Сортировка | newest/price/distance | ✅ J013/J024 |
| «Рядом со мной», радиус | POST `/jobs/geo`, сессия | ✅ J024/J053 |
| Карта заданий (только офлайн) | Yandex Maps | ✅ J025/J028 |
| Откликнуться/отозвать | карточка/деталь | ✅ |
| Массовые отклики | чекбоксы + панель | ✅ |
| Избранное | деталь/карточка | ✅ |
| Пагинация с сохранением фильтров | есть | ✅ |
| Скрыть cancelled / blacklist | `PUBLIC_STATUSES`, exclude | ✅ J004 |

## Создание/редактирование (`/jobs/new`, `/jobs/<id>/edit`)

| Элемент | Django | Статус |
|---|---|---|
| Все поля задания | `job_form.html` | ✅ |
| Валидации (stop-words, дата, оплата, работники, длины) | формы | ✅ J002/J022 |
| Карта-пикер | Yandex Maps | ✅ J027 |
| «Моё местоположение» | `navigator.geolocation` | ✅ J049 |
| «Найти по адресу» / «Адрес по метке» | Yandex Geocoder | ✅ J049 |
| «Очистить метку» | JS | ✅ J049 |
| Блокировка условий после accepted | только описание | ✅ J033 |
| Фото ≤3 | `JobPhoto` | ✅ J007 |

## Карточка задания (`/jobs/<id>`)

| Элемент | Django | Статус |
|---|---|---|
| Адрес/город | секция «Адрес» | ✅ J050 |
| Карта + «Открыть на карте»/«Маршрут» | detail map | ✅ J050 |
| Отклик/отзыв, 12-часовое окно | detail | ✅ J003 |
| Чат для accepted | кнопка | ✅ J047 |
| Жалоба | `<dialog>` | ✅ J056 |
| Избранное работодателя/задания | формы | ✅ J014/J057 |
| Отзывы/рейтинг/верификация | detail | ✅ J016/J018 |
| Trust-блок | detail | ✅ J047 |

## Мои задания (`/my-jobs`)

| Элемент | Django | Статус |
|---|---|---|
| Табы Все/Открытые/Завершённые/Отменённые | есть | ✅ J008 |
| Bulk cancel/restore/delete/duplicate | панель | ✅ J009/J010/J017 |
| application_count, edit/cancel/complete/delete | карточка | ✅ |
| Мобильные переносы действий | flex-wrap | ✅ J037 |

## Мои отклики (`/my-applications`)

| Элемент | Django | Статус |
|---|---|---|
| Табы received/sent, default received для работодателя | есть | ✅ J008/J046 |
| Фильтр навыков (трудник/задание) | `<details>` | ✅ J055 |
| Рейтинг/навыки/оплата | карточка received | ✅ J046 |
| Контакты трудника | received/applicants | ✅ J038 |
| Выбрать все | JS | ✅ J046 |
| Bulk accept/reject/reopen | панель | ✅ J009/J010 |

## Избранное (`/favorites`)

| Элемент | Django | Статус |
|---|---|---|
| Задания/трудники/работодатели | секции + табы | ✅ J043 |
| Массовое удаление | bulk-формы | ✅ J043 |
| Приглашение трудника | select открытых заданий | ✅ J043 |
| Корректный тип worker/employer | `as` | ✅ J057 |
| Навигация в шапке/bottom-nav | `/favorites` | ✅ J044 |

## Работодатели/трудники/оценки

| Элемент | Django | Статус |
|---|---|---|
| `/employers`: open-jobs, фильтры, blacklist, избранное | `employers.html` | ✅ J031 |
| `/employers/<id>`: open-only, 404 blacklist, отклик | detail | ✅ J032 |
| `/workers`: навыки/рейтинг/оплата/сортировка | `workers_list.html` | ✅ J021 |
| Бейджи «Надёжный»/«Приглашён» | workers | ✅ J023 |
| `/jobs/<id>/rate-workers` | prefill/обновление | ✅ J029/J030 |
| `/ratings/user/<id>` | типы отзывов, job-link | ✅ J030 |

## Уведомления/приглашения/чат

| Элемент | Django | Статус |
|---|---|---|
| `/notifications`: read/delete, delete-all, настройки | `notifications.html` | ✅ J041 |
| Типы и deep-links уведомлений | `notifications.html` | ✅ J052 |
| `/invitations`: accept/decline, reject-all | `invitations.html` | ✅ J040 |
| `/chats`: только accepted, последнее сообщение | `chats.html` | ✅ J039/J058 |
| `/chat/<id>`: empty state, autoscroll, даты | `chat.html` | ✅ J048 |

## Legacy

`/favorite-jobs`, `/favorite-people` сохранены для старых ссылок; основной вход —
`/favorites`. Корневые `templates/` и `app/` — архив Flask, UI не используется.
