# 🔍 Финальная сверка New_logic.md / New_logic2.md с текущим кодом

**Дата анализа:** 2026-06-13  
**Цель:** Сравнить КАЖДОЕ требование из New_logic.md и New_logic2.md с ТЕКУЩИМ состоянием кода  
**Легенда:** ✅ сделано | ❌ не сделано | ⚠️ частично | 🚫 нецелесообразно | 💀 удалить (легаси)

---

## 1. New_logic.md — Статусы заданий (раздел «Статусы задания»)

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 1.1 | Статус `open` | ✅ | Используется везде |
| 1.2 | Статус `in_progress` | ✅ | Используется везде |
| 1.3 | Статус `active` | ✅ | Автопереход реализован в [`jobs.py:509-530`](app/blueprints/jobs.py:509) |
| 1.4 | Статус `completed` | ✅ | force-complete в [`jobs.py:663-701`](app/blueprints/jobs.py:663) |
| 1.5 | Статус `cancelled` | ✅ | cancel-job в [`jobs.py:593-616`](app/blueprints/jobs.py:593) |
| 1.6 | Статус `expired` удалён из модели | ❌ | **Всё ещё используется** в [`jobs.py:79`](app/blueprints/jobs.py:79) — `open → expired` |
| 1.7 | Статус `draft` удалён из модели | ❌ | **Всё ещё используется** в [`jobs.py:438`](app/blueprints/jobs.py:438) при создании задания |
| 1.8 | Статусы `payment_pending`, `paid`, `disputed` исключены | ⚠️ | Удалены из основного кода, но остались в шаблонах и админке |

---

## 2. New_logic.md — Действия работодателя (раздел «Действия работодателя»)

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 2.1 | Редактировать задание (если current=0) | ✅ | Проверка accepted в [`jobs.py:901-925`](app/blueprints/jobs.py:901) |
| 2.2 | Принять / отклонить отклики | ✅ | [`applications.py:241-367`](app/blueprints/applications.py:241) |
| 2.3 | Отозвать задание → cancelled | ✅ | [`jobs.py:593-616`](app/blueprints/jobs.py:593) |
| 2.4 | Отозвать принятого работника (>12ч) | ✅ | [`applications.py:430-494`](app/blueprints/applications.py:430) |
| 2.5 | Принудительно завершить → completed | ✅ | [`jobs.py:663-701`](app/blueprints/jobs.py:663) |
| 2.6 | Оценить работников (1-5 звёзд) | ✅ | [`ratings.py:56-183`](app/blueprints/ratings.py:56) |
| 2.7 | Восстановить из cancelled → open | ✅ | [`jobs.py:619-660`](app/blueprints/jobs.py:619) |
| 2.8 | Удалить задание (архивировать) | ✅ | [`jobs.py:704-740`](app/blueprints/jobs.py:704) |

---

## 3. New_logic.md — Действия работника (раздел «Действия работника»)

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 3.1 | Отозвать pending отклик в любое время | ✅ | [`applications.py:180-182`](app/blueprints/applications.py:180) |
| 3.2 | Откликнуться снова после rejection | ✅ | reopen в [`applications.py:361-365`](app/blueprints/applications.py:361) |
| 3.3 | Отозвать accepted (>12ч до начала) | ✅ | [`applications.py:144-158`](app/blueprints/applications.py:144) |
| 3.4 | Написать в чат (accepted) | ✅ | [`chat.py:81-110`](app/blueprints/chat.py:81) |
| 3.5 | Оценить работодателя (completed) | ✅ | [`ratings.py:109-114`](app/blueprints/ratings.py:109) |

---

## 4. New_logic.md — Автоматические переходы (раздел «Автоматические переходы и ограничения»)

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 4.1 | open → in_progress (current = max) | ✅ | Атомарный PATCH в [`applications.py:283-288`](app/blueprints/applications.py:283) |
| 4.2 | in_progress → open (отзыв accepted, current < max) | ✅ | [`applications.py:165-166`](app/blueprints/applications.py:165), [`applications.py:480-481`](app/blueprints/applications.py:480) |
| 4.3 | in_progress → active (по date_time) | ✅ | [`jobs.py:509-530`](app/blueprints/jobs.py:509) |
| 4.4 | active → completed (force-complete) | ✅ | [`jobs.py:663-701`](app/blueprints/jobs.py:663) |
| 4.5 | 12-часовой лимит на отзыв accepted | ✅ | [`applications.py:154-158`](app/blueprints/applications.py:154), [`applications.py:467-471`](app/blueprints/applications.py:467) |
| 4.6 | Массовый reject pending при force-complete | ✅ | [`jobs.py:683-684`](app/blueprints/jobs.py:683) |
| 4.7 | Сброс accepted→pending при restore | ⚠️ | Сбрасывает в `pending` ([`jobs.py:639-640`](app/blueprints/jobs.py:639)), но New_logic.md:49 требует «удалить или пометить неактивными», а не pending |

---

## 5. New_logic.md — Изменения в БД (раздел «Изменения в базе данных»)

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 5.1 | Таблица `shifts` удалена | ✅ | Миграция 027, код не использует |
| 5.2 | `messages.application_id` добавлен | ✅ | [`chat.py:49`](app/blueprints/chat.py:49) использует |
| 5.3 | `shifts` в каскадном удалении админа | ❌ | **admin.py:137-138** — всё ещё удаляет `shifts` |
| 5.4 | `shifts` в `_delete_job_cascade` | ❌ | **admin.py:211** — всё ещё удаляет `shifts` |
| 5.5 | `hires` в каскадном удалении админа | ❌ | **admin.py:139-140** — всё ещё удаляет `hires` (старая таблица) |
| 5.6 | `is_paid` флаг для заданий | ✅ | Используется в новой модели pay-per-job |

---

## 6. New_logic.md — Архитектурный аудит (раздел «Архитектурный аудит»)

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 6.1 | Удалён `/shift/<id>/checkin` | ✅ | Маршрута нет в коде |
| 6.2 | Удалён `/shift/<id>/complete` | ✅ | Маршрута нет в коде |
| 6.3 | Удалён `/api/shifts/<id>/confirm-payment` | ✅ | Маршрута нет в коде |
| 6.4 | Удалён `/api/shifts/<id>/confirm-receipt` | ✅ | Маршрута нет в коде |
| 6.5 | Удалён `/api/disputes/*` | ✅ | Маршрутов нет в коде |
| 6.6 | Новый `/api/jobs/<id>/force-complete` | ✅ | [`jobs.py:663`](app/blueprints/jobs.py:663) |
| 6.7 | Чат по `application_id` | ✅ | [`chat.py:29-57`](app/blueprints/chat.py:29) |
| 6.8 | Новый `/api/applications/<id>/withdraw` | ✅ | [`applications.py:108`](app/blueprints/applications.py:108) |

---

## 7. New_logic.md — Типы уведомлений (раздел «Проверка уведомлений»)

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 7.1 | Деактивированы: `shift_checkin`, `shift_complete`, `payment_confirmed`, `payment_received`, `dispute_started` | ✅ | Нет в [`notification_service.py:8-21`](app/services/notification_service.py:8) |
| 7.2 | Активен: `application_received` | ✅ | Используется |
| 7.3 | Активен: `application_accepted` | ✅ | Используется |
| 7.4 | Активен: `application_rejected` | ✅ | Используется |
| 7.5 | Активен: `application_cancelled` | ✅ | Используется |
| 7.6 | Активен: `new_message` | ✅ | Используется |
| 7.7 | Активен: `new_rating` | ✅ | Есть в словаре |
| 7.8 | Активен: `job_filled` | ✅ | Есть в словаре |
| 7.9 | Активен: `job_completed` | ✅ | Используется |
| 7.10 | Активен: `job_cancelled` | ✅ | Есть в словаре |
| 7.11 | Активен: `hire_limit_warning` | ✅ | Используется |
| 7.12 | Активен: `system` | ✅ | Есть в словаре |
| 7.13 | `shift_id` в параметрах уведомлений | ❌ | **[`notification_service.py:81-82`](app/services/notification_service.py:81)** — всё ещё поддерживает `shift_id` в optional_fields |
| 7.14 | `shift_id` в ответах API | ❌ | **[`applications.py:344`](app/blueprints/applications.py:344)** и **:414** — возвращают `shift_id` в JSON |
| 7.15 | `hires` таблица в коде | ❌ | **[`monetization.py:63-76`](app/blueprints/monetization.py:63)** — ссылается на таблицу `hires` |

---

## 8. New_logic2.md — 10.1. Матрица видимости UI

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 8.1 | Статус `open`: Бейдж, кнопки Edit/Withdraw/Accept/Reject | ⚠️ | Требует проверки в шаблонах |
| 8.2 | Статус `in_progress`: Бейдж «Все места заняты» | ⚠️ | Требует проверки |
| 8.3 | Статус `active`: Кнопка «Завершить задание» (красная) | ⚠️ | Требует проверки |
| 8.4 | Статус `completed`: Оценить, Избранное, Удалить | ⚠️ | Требует проверки |
| 8.5 | Статус `cancelled`: Восстановить, Удалить | ⚠️ | Требует проверки |

**Проблемы шаблонов:**

| # | Файл | Проблема |
|---|------|----------|
| 8.6 | [`templates/shifts.html`](templates/shifts.html) | 💀 **ДОЛЖЕН БЫТЬ УДАЛЁН** — легаси-шаблон для удалённой функциональности. Содержит `payment_pending`, `paid`, `checkin`, `complete`, `confirm_payment`, `dispute` |
| 8.7 | [`templates/my_jobs.html:23-40`](templates/my_jobs.html:23) | ❌ Использует `active_count`, `payment_pending_count`, `paid_count`. Статусы `payment_pending` и `paid` должны быть убраны |
| 8.8 | [`templates/my_jobs.html:68-74`](templates/my_jobs.html:68) | ❌ Фильтры по `payment_pending` и `paid` |
| 8.9 | [`templates/my_jobs.html:146-158`](templates/my_jobs.html:146) | ❌ Бейджи для `payment_pending` и `paid` |
| 8.10 | [`templates/my_jobs.html:234-237`](templates/my_jobs.html:234) | ❌ Ссылка на `/shifts?job_id=` для payment_pending |
| 8.11 | [`templates/my_jobs.html:243-245`](templates/my_jobs.html:243) | ❌ Кнопка «Оплатить и опубликовать» для `draft` (draft убран из New_logic, но используется при создании) |
| 8.12 | [`templates/my_jobs.html:252-253`](templates/my_jobs.html:252) | ❌ Кнопка «Продлить» для `expired` |
| 8.13 | [`templates/my_jobs.html:261-262`](templates/my_jobs.html:261) | ❌ Кнопка «Оценить» для `paid` (должно быть `completed`) |
| 8.14 | [`templates/my_applications.html:208-209`](templates/my_applications.html:208) | ❌ Ссылка на чат через `app.shift_id` вместо `application_id` |
| 8.15 | [`templates/base.html:333-340`](templates/base.html:333) | ❌ CSS-стили `.status-payment-pending` и `.status-paid` |
| 8.16 | [`templates/base.html:796-798`](templates/base.html:796) | ❌ Ссылка на `/shifts` в навигации |
| 8.17 | [`templates/notifications.html:22-27`](templates/notifications.html:22) | ❌ Старые типы уведомлений: `shift_checkin`, `shift_complete`, `shift_created`, `shift_reminder`, `payment_confirmed` |
| 8.18 | [`templates/chats_list.html:57-68`](templates/chats_list.html:57) | ❌ Использует `shiftIds` вместо `application_ids` |
| 8.19 | [`templates/chat.html:68`](templates/chat.html:68) | ❌ JS: `const shiftId = "{{ shift_id }}"` — теперь должно быть `application_id` |
| 8.20 | [`templates/chat.html:104`](templates/chat.html:104) | ❌ JS: `/api/messages/${shiftId}/poll` |
| 8.21 | [`templates/chat.html:131`](templates/chat.html:131) | ❌ JS: `JSON.stringify({ shift_id: shiftId, ... })` |
| 8.22 | [`templates/admin.html:152`](templates/admin.html:152) | ❌ Фильтр «Оплачено» (`paid`) в админке |
| 8.23 | [`templates/admin.html:179`](templates/admin.html:179) | ❌ Бейдж для `paid` |
| 8.24 | [`templates/admin.html:192`](templates/admin.html:192) | ❌ Опция `paid` в `<select>` статуса |

---

## 9. New_logic2.md — 10.5. Бейджи и цвета

| # | Требование | Статус | Где/Комментарий |
|---|-----------|--------|----------------|
| 9.1 | Бейдж `open` (зелёный) | ⚠️ | Требует проверки в шаблонах |
| 9.2 | Бейдж `in_progress` (жёлтый) | ⚠️ | Требует проверки |
| 9.3 | Бейдж `active` (синий) | ⚠️ | Требует проверки |
| 9.4 | Бейдж `completed` (фиолетовый) | ⚠️ | Требует проверки |
| 9.5 | Бейдж `cancelled` (красный) | ⚠️ | Требует проверки |
| 9.6 | Отсутствие бейджей `paid`, `payment_pending`, `expired`, `draft` в UI | ❌ | См. пункты 8.9, 8.22, 8.23 |

---

## 10. Тесты — ссылки на удалённое

| # | Файл | Проблема |
|---|------|----------|
| 10.1 | [`tests/test_selenium_browser.py:397-408`](tests/test_selenium_browser.py:397) | ❌ `test_SH01_shifts_employer` / `test_SH02_shifts_worker` |
| 10.2 | [`tests/test_selenium_browser.py:537-538`](tests/test_selenium_browser.py:537) | ❌ Навигация на `/shifts` |
| 10.3 | [`tests/test_selenium_browser.py:602-604`](tests/test_selenium_browser.py:602) | ❌ Вызов удалённых тестов |
| 10.4 | [`tests/test_job_lifecycle_api.py:5`](tests/test_job_lifecycle_api.py:5) | ❌ Весь файл — старый lifecycle: `open → in_progress → active → payment_pending → paid → completed` |
| 10.5 | [`tests/test_job_lifecycle_api.py:153-282`](tests/test_job_lifecycle_api.py:153) | ❌ Создание смен, checkin, payment_pending, paid, shifts |
| 10.6 | [`tests/test_job_lifecycle.py:7`](tests/test_job_lifecycle.py:7) | ❌ Весь файл — старый lifecycle |
| 10.7 | [`tests/test_job_lifecycle.py:203-257`](tests/test_job_lifecycle.py:203) | ❌ shift_id, checkin, complete, confirm-payment |
| 10.8 | [`tests/test_all_functions.py:382-384`](tests/test_all_functions.py:382) | ❌ Импортирует `app.blueprints.shifts` |
| 10.9 | [`tests/test_all_functions.py:664-665`](tests/test_all_functions.py:664) | ❌ Использует `shift_id` в моках |
| 10.10 | [`tests/test_all_functions.py:786-821`](tests/test_all_functions.py:786) | ❌ Тесты shifts, checkin, confirm-payment, dispute |
| 10.11 | [`tests/test_all_functions.py:910-911`](tests/test_all_functions.py:910) | ❌ `/api/send_message` с `shift_id` |
| 10.12 | [`test_selenium_v2.py:259-261`](test_selenium_v2.py:259) | ❌ `/shifts` страница |
| 10.13 | [`test_selenium_v2.py:441-442`](test_selenium_v2.py:441) | ❌ Вызов `t_shifts_page` |
| 10.14 | [`test_rls.py:156-161`](test_rls.py:156) | ❌ Тест `shifts` таблицы |
| 10.15 | [`test_rls.py:214`](test_rls.py:214) | ❌ Вызов `t_shifts_endpoint` |

---

## 11. New_logic2.md — Прочие проверки

| # | Требование | Статус | Комментарий |
|---|-----------|--------|-------------|
| 11.1 | Toast при open→in_progress | ⚠️ | Требует верификации в JS |
| 11.2 | Toast при in_progress→open | ⚠️ | Требует верификации в JS |
| 11.3 | Toast при in_progress→active | ⚠️ | Требует верификации в JS |
| 11.4 | Модальное окно при force-complete | ⚠️ | Требует верификации |
| 11.5 | Модальное окно при restore из cancelled | ⚠️ | Требует верификации |
| 11.6 | Smart hints (бейдж «Осталось 2 дня», tooltip <12ч) | ⚠️ | Требует проверки |
| 11.7 | Оптимистичные обновления UI | ⚠️ | Требует проверки JS |
| 11.8 | Адаптивность (мобильные 360x800) | ⚠️ | Требует визуальной проверки |
| 11.9 | `cheque_reminder` тип уведомления | ⚠️ | Не в списке NOTIFICATION_TYPES, но используется в [`monetization.py:252`](app/blueprints/monetization.py:252) — может вызвать warning |

---

## 12. 🚫 Нецелесообразное (отфильтровано)

| # | Предложение | Причина исключения |
|---|------------|-------------------|
| 12.1 | pg_cron для автопереходов | Недоступен на бесплатном Supabase. Реализована альтернатива в [`jobs.py:509-530`](app/blueprints/jobs.py:509) |
| 12.2 | PostgreSQL триггер `AFTER UPDATE ON applications` для автоперехода `jobs.status` | Избыточно — уже реализовано на уровне приложения с атомарными PATCH |
| 12.3 | Playwright Clock API для тестов | Сложная инфраструктура, не требуется для MVP |
| 12.4 | Индекс на `messages.application_id` | Может быть добавлен в миграциях, но не критичен для MVP |

---

## 📋 ИТОГОВЫЙ СПИСОК ЗАДАЧ ДЛЯ CODE MODE

### 🔴 КРИТИЧЕСКИЕ (нарушают целостность архитектуры)

#### Бэкенд — удаление легаси-ссылок

1. **[`app/blueprints/admin.py:137-138`](app/blueprints/admin.py:137)** — удалить `shifts` из `cascade_tables` в `delete_user()`
2. **[`app/blueprints/admin.py:139-140`](app/blueprints/admin.py:139)** — удалить `hires` из `cascade_tables` в `delete_user()`
3. **[`app/blueprints/admin.py:211`](app/blueprints/admin.py:211)** — удалить `shifts` из `_delete_job_cascade()`
4. **[`app/blueprints/admin.py:189`](app/blueprints/admin.py:189)** — убрать `'paid'` из допустимых статусов в `update_job_status()`
5. **[`app/blueprints/jobs.py:79`](app/blueprints/jobs.py:79)** — удалить строку с переводом `open → expired` (статус `expired` исключён)
6. **[`app/blueprints/jobs.py:438`](app/blueprints/jobs.py:438)** — изменить `'status': 'draft'` на `'status': 'open'` при создании (либо оставить `draft` как внутренний статус до оплаты)
7. **[`app/services/notification_service.py:81-82`](app/services/notification_service.py:81)** — удалить поддержку `shift_id` из optional_fields
8. **[`app/blueprints/applications.py:344`](app/blueprints/applications.py:344)** и **:414** — удалить `'shift_id'` из возвращаемых JSON
9. **[`app/blueprints/jobs.py:639-640`](app/blueprints/jobs.py:639)** — при restore сбрасывать accepted в `rejected` (или удалять), а не в `pending` (согласно New_logic.md:49)

#### Шаблоны — удаление легаси

10. **[`templates/shifts.html`](templates/shifts.html)** — **УДАЛИТЬ ФАЙЛ ПОЛНОСТЬЮ**
11. **[`templates/my_jobs.html`](templates/my_jobs.html)** — убрать все упоминания `payment_pending`, `paid`, `expired`:
    - Строки 23-25: убрать `payment_pending_count`, `paid_count`
    - Строки 37-40: убрать отображение payment_pending и paid
    - Строки 68-74: убрать фильтры payment_pending, paid
    - Строки 146-158: убрать бейджи payment_pending, paid
    - Строки 234-237: убрать ссылку на `/shifts`
    - Строки 252-253: убрать кнопку «Продлить» для expired
    - Строки 261-262: заменить `paid` на `completed` для кнопки «Оценить»
12. **[`templates/base.html`](templates/base.html)**:
    - Строки 333-340: удалить CSS `.status-payment-pending` и `.status-paid`
    - Строки 796-798: удалить ссылку на `/shifts` в навигации
13. **[`templates/my_applications.html:208-209`](templates/my_applications.html:208)** — заменить `app.shift_id` на `app.id` (application_id)
14. **[`templates/notifications.html:22-27`](templates/notifications.html:22)** — удалить старые типы: `shift_checkin`, `shift_complete`, `shift_created`, `shift_reminder`, `payment_confirmed`
15. **[`templates/chat.html`](templates/chat.html)** — заменить `shiftId` на `applicationId` везде в JS:
    - Строка 68: `const applicationId = "{{ application_id }}"`
    - Строка 104: `/api/messages/${applicationId}/poll`
    - Строка 131: `JSON.stringify({ application_id: applicationId, content: content })`
16. **[`templates/chats_list.html:57-68`](templates/chats_list.html:57)** — заменить `shiftIds` на `applicationIds`
17. **[`templates/admin.html`](templates/admin.html)**:
    - Строка 152: убрать `<option value="paid">`
    - Строка 179: убрать бейдж для `paid`
    - Строка 192: убрать `<option value="paid">`

### 🟡 ВАЖНЫЕ (чистота кода и тестов)

#### Тесты

18. **[`tests/test_selenium_browser.py`](tests/test_selenium_browser.py)** — удалить/закомментировать `test_SH01_shifts_employer`, `test_SH02_shifts_worker`, навигацию на `/shifts`
19. **[`tests/test_job_lifecycle_api.py`](tests/test_job_lifecycle_api.py)** — **УДАЛИТЬ ФАЙЛ** (полностью устарел: shifts, payment_pending, paid, checkin)
20. **[`tests/test_job_lifecycle.py`](tests/test_job_lifecycle.py)** — **УДАЛИТЬ ФАЙЛ** (полностью устарел)
21. **[`tests/test_all_functions.py`](tests/test_all_functions.py)**:
    - Строка 382: удалить импорт `app.blueprints.shifts`
    - Строки 664-665: заменить `shift_id` моки
    - Строки 786-821: удалить тесты shifts, checkin, confirm-payment, dispute
    - Строки 910-911: заменить `shift_id` на `application_id`
22. **[`test_selenium_v2.py:259-261`](test_selenium_v2.py:259)** — удалить `t_shifts_page` и его вызов
23. **[`test_rls.py:156-161`](test_rls.py:156)** — удалить `t_shifts_endpoint` и его вызов

#### Документация

24. **[`monetization.py:252`](app/blueprints/monetization.py:252)** — тип `cheque_reminder` отсутствует в [`notification_service.py:8-21`](app/services/notification_service.py:8), добавить или заменить на `system`

### 🟢 РЕКОМЕНДУЕМЫЕ (улучшение UX)

25. Проверить Toast-уведомления для всех автопереходов (open↔in_progress, in_progress→active, force-complete, restore)
26. Проверить модальные окна `showConfirm()` для force-complete, restore, массовых операций
27. Проверить Smart hints: tooltip на disabled-кнопке «Отозвать» при <12ч, бейдж «Осталось N дней»
28. Проверить адаптивность на мобильных устройствах (360×800)
29. Проверить оптимистичные обновления в избранном и откликах с откатом при ошибке

---

## 📊 СТАТИСТИКА

| Категория | ✅ Сделано | ❌ Не сделано | ⚠️ Частично |
|-----------|-----------|--------------|-------------|
| Статусы заданий (New_logic.md) | 5 | 3 | 1 |
| Действия (New_logic.md) | 13 | 0 | 0 |
| Автопереходы (New_logic.md) | 7 | 0 | 0 |
| Изменения БД (New_logic.md) | 3 | 3 | 0 |
| Архитектурный аудит (New_logic.md) | 8 | 0 | 0 |
| Уведомления (New_logic.md) | 11 | 3 | 0 |
| Матрица UI (New_logic2.md) | 5 | 0 | 5 |
| Шаблоны (легаси-остатки) | — | 12 | — |
| Тесты (легаси-остатки) | — | 8 | — |
| Прочее (New_logic2.md) | 0 | 0 | 9 |
| **ИТОГО** | **52** | **29** | **15** |

---

**Резюме:** Основной функционал (state machine, статусы, автопереходы, чат по application_id, force-complete, withdraw, restore, ratings) реализован корректно. Основная проблема — **незавершённая чистка**: в шаблонах, админке, notification_service и тестах осталось множество ссылок на старые статусы (`paid`, `payment_pending`, `expired`, `draft`) и удалённую таблицу `shifts`. Это 29 конкретных проблем, которые нужно исправить для полного соответствия New_logic.md/New_logic2.md.
