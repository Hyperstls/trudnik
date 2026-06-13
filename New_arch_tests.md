# 🚀 MASTER QA PROMPT v3.0: Полное покрытие архитектуры «Трудник» (v2.0)

**РОЛЬ:** Ты — Lead QA Automation Engineer, Security Auditor и Frontend Specialist в одном лице. Твоя задача — провести **исчерпывающий аудит** приложения «Трудник» по архитектуре v2.0 (13.06.2026), покрыв 100% бизнес-логики, безопасности, UI/UX и архитектурных изменений.

**КОНТЕКСТ:** Приложение перешло на упрощённую модель: удалены `shifts`/`reviews`/`hires`, чат перенесён на `application_id`, 5 статусов задания, новый статус отклика `withdrawn`, принудительное завершение, локализация статусов в UI.

---

## 🎯 КЛЮЧЕВЫЕ АРХИТЕКТУРНЫЕ ИЗМЕНЕНИЯ v2.0 (обязательно проверить)

| # | Изменение | Как проверить |
|---|-----------|---------------|
| 1 | ❌ Удалены таблицы `shifts`, `reviews`, `hires` | SQL: `SELECT * FROM information_schema.tables WHERE table_name IN ('shifts','reviews','hires')` — должно вернуть 0 |
| 2 | ❌ Удалён blueprint `shifts_bp` | HTTP: `/shifts/*`, `/shift/<id>/checkin` должны вернуть **404** |
| 3 | ✅ Новый статус отклика `withdrawn` | API: `POST /api/applications/<id>/withdraw` работает для `pending` и `accepted` |
| 4 | ✅ 5 статусов задания: `open/in_progress/active/completed/cancelled` | SQL: `CHECK` constraint в `jobs.status` |
| 5 | ❌ Убраны `draft`/`paid`/`expired` из CHECK constraint | Задание создаётся сразу в `open` с `is_paid=false` |
| 6 | ✅ `POST /api/jobs/<id>/force-complete` | Принудительное завершение + массовый reject `pending` |
| 7 | ✅ `POST /restore-job/<id>` | Восстановление + сброс `accepted` → `rejected` |
| 8 | ✅ Чат через `application_id` | SQL: `messages.application_id` FK→`applications.id`, RLS через участников заявки |
| 9 | ✅ 14 типов уведомлений (вместо 18) | Удалены: `shift_*`, `payment_confirmed`, `payment_received`, `dispute_started` |
| 10 | ✅ UI локализация: 3 статуса = "Идёт набор" | `open`/`in_progress`/`active` → один фильтр |
| 11 | ✅ Автопереход `in_progress → active` | `_auto_transition_in_progress_to_active()` при `date_time <= now()` |

---

## 🛠 ИНСТРУМЕНТАРИЙ

### Учётные данные (пароль `Step@1986` для всех):
- 👑 Админ: `admin@test.ru`
- 🏢 Работодатель: `org@test.ru`
- 👷 Трудники: `trud3@test.ru`, `trud4@test.ru`, `trud5@test.ru`

### Инструменты:
- **Playwright** (E2E + API + Device Emulation)
- **SQL-клиент Supabase** (прямые запросы к БД, обход RLS через `service_role_key`)
- **Playwright Clock API** (симуляция `date_time` для автопереходов)
- **Geolocation Mocking** (больше не нужен — check-in удалён)

---

## 📊 БЛОК 1: STATE MACHINE ЗАДАНИЯ (5 статусов)

### 1.1 Переходы и бизнес-логика

```
[sоздание] ──POST /job/new──> open ──accept отклика──> in_progress ──date_time──> active
                                │                        │                        │
                                │ cancel                 │ force-complete         │ force-complete
                                ▼                        ▼                        ▼
                            cancelled ◄──restore──   completed ◄──────────────────┘
                                │
                                └──restore──> open (сброс всех accepted → rejected)
```

| Тест | Сценарий | Проверка |
|------|----------|----------|
| 1.1.1 | Создание задания | `POST /job/new` → статус `open`, `is_paid=false`. Задание **не видно** в ленте `/` (RLS: только `is_paid=true`) |
| 1.1.2 | Оплата публикации | `POST /api/jobs/<id>/publish` → `is_paid=true`, `expires_at=now+30d`, уведомление `job_published`, чек в `receipts` |
| 1.1.3 | Задание появляется в ленте | После оплаты — видно всем в `/` |
| 1.1.4 | `open → in_progress` | Работодатель принимает первый отклик → `current_workers=1`, статус `in_progress` |
| 1.1.5 | `in_progress → open` (отзыв) | Трудник отзывает `accepted` отклик → `current_workers=0`, статус `open` |
| 1.1.6 | `in_progress → active` (автоматически) | Мокаем время: `date_time <= now()` → `_auto_transition_in_progress_to_active()` меняет статус при просмотре |
| 1.1.7 | `in_progress → completed` (force-complete) | `POST /api/jobs/<id>/force-complete` → все `pending` → `rejected`, `accepted` остаются, уведомление `job_completed` |
| 1.1.8 | `active → completed` (force-complete) | Аналогично, но из `active` |
| 1.1.9 | `open → cancelled` | `POST /cancel-job/<id>` → все `pending` → `cancelled`, статус `cancelled` |
| 1.1.10 | `in_progress → cancelled` | Блокировка если есть `accepted`? Проверить логику |
| 1.1.11 | **Блокировка cancel для active** | `POST /cancel-job/<id>` для `active` → **403** (только force-complete) |
| 1.1.12 | `cancelled → open` (restore) | `POST /restore-job/<id>` → `status=open`, `current_workers=0`, все `accepted` → `rejected` |
| 1.1.13 | Блокировка restore из других статусов | `restore` для `completed`/`active` → **403** |

### 1.2 Автопереход `in_progress → active` (критично!)

```javascript
// Playwright Clock API
await page.clock.install();
await page.clock.setSystemTime(new Date('2026-06-14T09:00:00Z'));

// Создаём задание с date_time = 10:00
const jobId = await createJob({ date_time: '2026-06-14T10:00:00Z' });
await expectJobStatus(jobId, 'in_progress'); // После принятия отклика

// Мотаем время вперёд
await page.clock.setSystemTime(new Date('2026-06-14T10:01:00Z'));

// Заходим на страницу задания — должен сработать автопереход
await page.goto(`/jobs/${jobId}`);
await expectJobStatus(jobId, 'active'); // _auto_transition_in_progress_to_active()
```

---

## 📊 БЛОК 2: STATE MACHINE ОТКЛИКА (4 статуса)

```
pending ──accept──> accepted ──withdraw──> withdrawn
   │                  │
   ├──reject──> rejected ──reopen──> pending
   │
   └──withdraw──> withdrawn (в любое время)
```

| Тест | Сценарий | Проверка |
|------|----------|----------|
| 2.1 | Трудник откликается | `POST /apply/<job_id>` → `status=pending`, уведомление `application_received` |
| 2.2 | Работодатель принимает | `POST /api/applications/<id>/accept` (корневой маршрут!) → `accepted`, `current_workers+=1` |
| 2.3 | Работодатель отклоняет | `POST /api/applications/<id>/reject` → `rejected`, уведомление `application_rejected` |
| 2.4 | Работодатель переоткрывает | `POST /api/applications/<id>/reopen` → `pending` |
| 2.5 | **Трудник отзывает `pending`** | `POST /api/applications/<id>/withdraw` → `withdrawn` (в любое время) |
| 2.6 | **Трудник отзывает `accepted`** | `POST /api/applications/<id>/withdraw` → `withdrawn`, `current_workers-=1` |
| 2.7 | Массовый отклик | `POST /apply-selected` → несколько `pending` за одну транзакцию |
| 2.8 | Массовое принятие | JS `applications.js` → чекбоксы → `POST` на корневые маршруты |
| 2.9 | Массовое отклонение | Аналогично |
| 2.10 | **Дубликат отклика** | Повторный `POST /apply/<job_id>` от того же трудника → **400** или UPSERT |
| 2.11 | Отклик на `cancelled` | **400**: "Задание отменено" |
| 2.12 | Отклик на `completed` | **400**: "Задание завершено" |
| 2.13 | Отклик при `current == max` | **400**: "Нет свободных мест" |
| 2.14 | Отклик от заблокированного | **403**: "Вы в чёрном списке" |

---

## 📊 БЛОК 3: ЧАТ (новая модель через `application_id`)

### 3.1 Архитектурный аудит

```sql
-- Проверка удаления shift_id из messages
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'messages' AND column_name = 'shift_id';
-- Должно вернуть 0 строк

-- Проверка наличия application_id
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'messages' AND column_name = 'application_id';
-- Должно быть UUID, NOT NULL

-- RLS для messages (участники заявки)
SELECT * FROM pg_policies WHERE tablename = 'messages';
-- Должны быть политики: "Application participants can view/insert messages"
```

### 3.2 Функциональные тесты

| Тест | Сценарий | Проверка |
|------|----------|----------|
| 3.2.1 | Создание чата | После `accept` отклика автоматически доступна страница `/chat/<application_id>` |
| 3.2.2 | Отправка сообщения | `POST /api/send_message` с `application_id` → `messages` запись, уведомление `new_message` |
| 3.2.3 | Polling новых сообщений | `GET /api/messages/<application_id>/poll?since_id=X` — только новые сообщения |
| 3.2.4 | Чат для `pending` отклика | **403**: чат доступен только после `accepted` |
| 3.2.5 | Чат для `rejected` отклика | **403** |
| 3.2.6 | **RLS: чужой чат** | Трудник пытается прочитать чат чужого `application_id` → 0 строк (RLS блокирует) |
| 3.2.7 | Список чатов | `/chats` — все `accepted`-заявки текущего пользователя |
| 3.2.8 | Удаление чатов | `POST /api/delete-chats` — удаление сообщений по `application_id` |
| 3.2.9 | Чат после `force-complete` | Должен оставаться доступным (история) |
| 3.2.10 | Чат после `withdraw` | Зависит от политики: сохранение или удаление |

---

## 📊 БЛОК 4: МОНЕТИЗАЦИЯ (плата за публикацию)

| Тест | Сценарий | Проверка |
|------|----------|----------|
| 4.1 | Тарифы | `tariff_settings`: `standard` = 490₽, 30 дней, продление 290₽ |
| 4.2 | Создание платежа | `PaymentService.create_job_payment()` → `job_payments` (status=`pending`) |
| 4.3 | Эмуляция оплаты | `PaymentService.process_job_payment()` → `status=paid`, `jobs.is_paid=true` |
| 4.4 | Чек самозанятого | `ReceiptService.issue_job_publication_receipt()` → `receipts` с `owner_inn` из `monetization_settings` |
| 4.5 | Продление публикации | `POST /api/jobs/<id>/renew` → `expires_at += 30d`, новый платёж 290₽ |
| 4.6 | **Архивные таблицы** | `_archive_contact_payments` существует, но активный код её не использует |
| 4.7 | Старая модель pay-per-contact | Нет paywall при отклике, контакты видны сразу после `accepted` |
| 4.8 | Двойная оплата (race condition) | 3 одновременных `POST /api/jobs/<id>/publish` → только одна запись `job_payments` |
| 4.9 | Динамические цены | Изменить `tariff_settings.price` → UI на `/job/<id>/publish` показывает новую цену |

---

## 📊 БЛОК 5: БЕЗОПАСНОСТЬ (CSRF, RLS, Rate Limiting)

### 5.1 CSRF-защита

```javascript
// Playwright тест CSRF
test('CSRF protection on mutating requests', async ({ page }) => {
    // Без CSRF-токена
    const response = await page.evaluate(() => 
        fetch('/api/applications/123/accept', { method: 'POST' })
    );
    expect(response.status).toBe(400); // или 403
    
    // С токеном
    const csrfToken = await page.locator('input[name="_csrf_token"]').inputValue();
    const response2 = await page.evaluate((token) => 
        fetch('/api/applications/123/accept', { 
            method: 'POST',
            headers: { 'X-CSRF-Token': token }
        })
    );
    expect(response2.status).toBe(200);
});
```

### 5.2 Rate Limiting

```python
# 11 POST /login за 60 секунд
for i in range(11):
    response = requests.post('/login', data={'email': 'bad@test.ru', 'password': 'wrong'})
    if i < 10:
        assert response.status_code == 401
    else:
        assert response.status_code == 429  # Too Many Requests
```

### 5.3 RLS-политики (SQL-аудит)

```sql
-- Критические RLS-проверки
-- 1. Трудник не видит чужие applications
SET ROLE authenticated; -- trud3@test.ru
SELECT COUNT(*) FROM applications WHERE worker_id != auth.uid();
-- Должно быть 0

-- 2. Работодатель видит только свои jobs
SELECT COUNT(*) FROM jobs WHERE employer_id != auth.uid() AND status != 'open';
-- Должно быть 0 (open видны всем)

-- 3. Чат только для участников заявки
SELECT * FROM messages 
WHERE application_id NOT IN (
    SELECT id FROM applications WHERE worker_id = auth.uid()
);
-- Должно быть 0

-- 4. Админ видит всё (через service_role)
-- supabase_admin_request() обходит RLS
```

### 5.4 PostgREST инъекции

```javascript
// Тест sanitize_postgrest()
const maliciousUrls = [
    '/api/search/workers?city=eq.Moscow",or("1","eq","1")',
    '/api/search/jobs?work_type=like.*%25*',
    '/api/search/workers?id=in.(1,2,3))--'
];
for (const url of maliciousUrls) {
    const response = await fetch(url);
    expect(response.status).not.toBe(500); // Не должно быть SQL-ошибки
    // И не должно вернуть всю таблицу
}
```

---

## 📊 БЛОК 6: UI/UX И ЛОКАЛИЗАЦИЯ (критично для v2.0)

### 6.1 Локализация статусов в `/my-jobs`

| Технический статус | UI-отображение | Фильтр |
|--------------------|----------------|--------|
| `open` | «Идёт набор» | «Идёт набор» |
| `in_progress` | «Идёт набор» | «Идёт набор» |
| `active` | «Идёт набор» | «Идёт набор» |
| `completed` | «Набор окончен» | «Набор окончен» |
| `cancelled` | «Отозвано» | «Отозванные» |

**Тест:** Создать по одному заданию каждого статуса → проверить, что все 3 (`open`/`in_progress`/`active`) попадают в фильтр «Идёт набор», а не разделяются.

### 6.2 Матрица кнопок в `my_jobs.html`

| Статус | Кнопки работодателя |
|--------|---------------------|
| `open` | Изменить, Отменить, Дублировать, Удалить |
| `in_progress` | Изменить, Отменить, Дублировать, Удалить |
| `active` | **Завершить (force-complete)**, Дублировать |
| `completed` | Дублировать, Удалить |
| `cancelled` | **Восстановить**, Дублировать, Удалить |

**Тест:** Для каждого статуса проверить:
- Кнопки **физически присутствуют** в DOM
- Запрещённые кнопки **отсутствуют** (не просто disabled)
- Клик по кнопке вызывает нужный endpoint

### 6.3 Фильтры на главной `/` (для трудника)

| Кнопка | Что показывает |
|--------|----------------|
| «Все» | `open` + `in_progress` + `active` |
| «Новые» | Задания, на которые трудник **ещё не откликался** |
| «Откликнулся» | Задания с откликом (`pending`/`accepted`/`rejected`/`withdrawn`) |

**Тест:** Трудник откликается на задание → оно перемещается из «Новые» в «Откликнулся», но не исчезает из «Все».

### 6.4 Toast-уведомления

| Действие | Toast |
|----------|-------|
| Успешный отклик | `success`: "Отклик отправлен" |
| Отзыв отклика | `info`: "Отклик отозван" |
| Принятие работодателем | `success`: "Кандидат принят" |
| Force-complete | `success`: "Задание завершено, непринятые отклики отклонены" |
| Restore | `success`: "Задание восстановлено" |
| Cancel | `info`: "Задание отменено" |
| Ошибка сети | `error` + откат оптимистичного UI |

**Тест через мокинг `window.showToast`:**
```javascript
await page.addInitScript(() => {
    window.__toasts = [];
    const original = window.showToast;
    window.showToast = (msg, type) => {
        window.__toasts.push({ msg, type, ts: Date.now() });
        original?.(msg, type);
    };
});
// После действия:
const toasts = await page.evaluate(() => window.__toasts);
expect(toasts.some(t => t.msg.includes('Завершено'))).toBeTruthy();
```

### 6.5 Оптимистичные обновления (favorites.js, applications.js)

| Сценарий | Ожидаемое поведение |
|----------|---------------------|
| Клик "В избранное" | Кнопка мгновенно меняется → запрос → при ошибке откат |
| Клик "Принять" | Кнопка → `✓ Принято`, счётчик +1 → при ошибке откат |
| Массовое принятие | Все выделенные меняются одновременно |

**Тест отката:**
```javascript
await page.route('**/api/favorites/add', route => 
    route.fulfill({ status: 500, body: 'Server Error' })
);
await page.click('[data-favorite-btn]');
await expect(page.locator('[data-favorite-btn]')).toHaveText('В избранное'); // Откат
const toasts = await page.evaluate(() => window.__toasts);
expect(toasts.some(t => t.type === 'error')).toBeTruthy();
```

### 6.6 Система приглашений (с `prompt()`)

```javascript
// Критично: Playwright должен обработать диалог
page.on('dialog', async dialog => {
    if (dialog.type() === 'prompt') {
        await dialog.accept('123'); // ID задания
    }
});
await page.click('text=Пригласить');
// Проверка: кнопка → "✓ Приглашён" (disabled)
// Кросс-страничная синхронизация: на /favorites тот же трудник уже с бейджем
```

---

## 📊 БЛОК 7: АРХИТЕКТУРНЫЙ АУДИТ (удаление старых сущностей)

### 7.1 Проверка удаления `shifts_bp`

Следующие URL должны возвращать **404**:
- `GET /shifts`
- `POST /shift/<id>/checkin`
- `POST /shift/<id>/complete`
- `POST /api/shifts/<id>/confirm-payment`
- `GET /api/messages/<shift_id>/poll` (старый формат)

### 7.2 Проверка удаления `reviews` и `hires`

```sql
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name IN ('reviews', 'hires')
); -- false
```

### 7.3 Проверка старого статуса `draft`

- Создание задания должно сразу давать `status='open'` (не `draft`)
- `draft` исключён из CHECK constraint (миграция 028)
- UI не должен показывать "Оплатить черновик"

### 7.4 Проверка уведомлений (14 вместо 18)

```python
# Следующие типы НЕ должны создаваться
deprecated_types = [
    'shift_checkin', 'shift_complete', 'shift_created', 'shift_reminder',
    'payment_confirmed', 'payment_received', 'dispute_started'
]
# При любом действии проверить, что уведомления этих типов не создаются
```

### 7.5 Проверка полей `contact_paid` и `contact_payment_id`

```sql
-- В applications этих полей больше нет (или они NULL)
SELECT contact_paid, contact_payment_id FROM applications;
-- Все NULL или поля физически удалены
```

---

## 📊 БЛОК 8: PWA И INFRASTRUCTURE

### 8.1 PWA компоненты

| Компонент | Проверка |
|-----------|----------|
| `manifest.json` | `display: "standalone"`, `theme_color: "#d97706"`, иконки 48-512px |
| `sw.js` | Network First для HTML, Cache First для статики |
| `offline.html` | Отображается при отключённой сети |
| `.well-known/assetlinks.json` | Валидный JSON для TWA |
| Установка PWA | `beforeinstallprompt` event срабатывает |

### 8.2 Service Worker стратегии

```javascript
// Тест 1: Network First для HTML
await page.goto('/jobs/123'); // Прогреть кэш
await context.setOffline(true);
await page.reload();
// Должна загрузиться offline.html (Network First не кэширует HTML агрессивно)

// Тест 2: Cache First для статики
await page.goto('/'); // Прогреть кэш
await context.setOffline(true);
await page.goto('/profile');
// tailwind.min.css, default-avatar.png должны загрузиться из кэша
```

### 8.3 Кросс-браузерность

Запустить все E2E в:
- **Chromium** (основной)
- **Firefox**
- **WebKit** (Safari)

### 8.4 Адаптивность (Mobile-First)

| Viewport | Проверка |
|----------|----------|
| 1920x1080 (desktop) | Сетки grid/flex работают |
| 393x852 (iPhone 15) | Бургер-меню, карточки в 1 колонку |
| 360x800 (Android) | Кнопки ≥44x44px, нет горизонтальной прокрутки |
| Landscape ориентация | Макет адаптируется, нет обрезки |

---

## 📊 БЛОК 9: EDGE CASES И PRODUCTION READINESS

### 9.1 Race Conditions

| Сценарий | Ожидаемое поведение |
|----------|---------------------|
| 3 одновременных `accept` при `max-current=1` | Принимается только первый, остальные **400** |
| Трудник `withdraw` + работодатель `force-complete` одновременно | Транзакционная изоляция, побеждает первое |
| 2 трудника откликаются на последнее место | Принимается первый, второй получает "Нет мест" |
| Auto-transition `in_progress→active` во время `force-complete` | Проверка статуса атомарна |

### 9.2 Supabase Downtime (отказоустойчивость)

```javascript
await page.route('**/rest/v1/**', route => 
    route.fulfill({ status: 503, body: 'Service Unavailable' })
);
await page.goto('/');
// НЕ должен быть 500 со stack trace
// Должна быть error.html с "Сервис временно недоступен"
```

### 9.3 JWT Auto-Refresh

```python
# Подменить access_token на невалидный, refresh_token оставить валидным
# Сделать запрос к Supabase
# Ожидаем: бэкенд автоматически обновит токен и вернёт 200
# Пользователь не должен быть разлогинен
```

### 9.4 Кэширование контекст-процессоров (30 секунд)

```javascript
// 1. Создать новое приглашение для трудника
await createInvitation(workerId);
// 2. Сразу обновить страницу
await page.reload();
// 3. Счётчик pending_invitations НЕ должен обновиться мгновенно (это фича, не баг)
// 4. Подождать 31 секунду, обновить снова → счётчик обновился
```

### 9.5 30-дневное истечение публикации

```python
# Создать задание, оплатить
# Вручную изменить expires_at на вчера
# Проверить:
# 1. Задание не видно в ленте /
# 2. Работодатель видит кнопку "Продлить за 290₽"
# 3. POST /api/jobs/<id>/renew → expires_at += 30d
```

---

## 📊 БЛОК 10: ИНТЕГРАЦИИ

### 10.1 Яндекс.Карты

- На `/job/new` карта инициализируется
- Выбор точки сохраняет `lat`/`lng` в `jobs`
- Поиск трудников использует `calculate_distance()` (haversine)

### 10.2 AI-помощник (DeepSeek на localhost:11434)

```javascript
// Тест 1: AI доступен
await page.click('[data-ai-chat]');
await page.fill('[data-ai-input]', 'Как опубликовать задание?');
await page.click('[data-ai-send]');
await expect(page.locator('[data-ai-response]')).toBeVisible();

// Тест 2: AI недоступен (fallback)
await page.route('**/localhost:11434/**', route => 
    route.abort('connectionrefused')
);
// Спиннер исчезает через таймаут, показывается фоллбэк-сообщение
// Консоль не забита ошибками
```

---

## 🎭 БЛОК 11: РОЛЕВАЯ МОДЕЛЬ И RBAC

### 11.1 Доступ к маршрутам

| Маршрут | Гость | Трудник | Работодатель | Админ |
|---------|-------|---------|--------------|-------|
| `/` (лента) | ✅ (ограниченно) | ✅ | ✅ | ✅ |
| `/my-jobs` | ❌ (→ /login) | ❌ | ✅ | ✅ |
| `/my-applications` | ❌ | ✅ | ✅ | ✅ |
| `/admin` | ❌ | ❌ | ❌ | ✅ |
| `/job/new` | ❌ | ❌ | ✅ | ✅ |
| `/verify-employer` | ❌ | ❌ | ✅ | ✅ |
| `/chats` | ❌ | ✅ | ✅ | ✅ |

### 11.2 Нижнее меню (разное для ролей)

- **Трудник:** Главная, Отклики, Чаты, Избранное, Профиль
- **Работодатель:** Мои задания, Отклики, Чаты, Трудники, Профиль

**Тест:** Проверить, что пункты меню **физически различаются** в DOM для разных ролей.

---

## 🏁 ФОРМАТ ОТЧЁТА АГЕНТА

После выполнения всех тестов предоставить Markdown-отчёт:

```markdown
# ОТЧЁТ: Комплексное тестирование «Трудник» v2.0

## 📊 Сводка по блокам
| Блок | Пройдено | Провалено | Покрытие |
|------|----------|-----------|----------|
| 1. State Machine задания | X/Y | Z | N% |
| 2. State Machine отклика | X/Y | Z | N% |
| 3. Чат (application_id) | X/Y | Z | N% |
| 4. Монетизация | X/Y | Z | N% |
| 5. Безопасность | X/Y | Z | N% |
| 6. UI/UX и локализация | X/Y | Z | N% |
| 7. Архитектурный аудит | X/Y | Z | N% |
| 8. PWA | X/Y | Z | N% |
| 9. Edge Cases | X/Y | Z | N% |
| 10. Интеграции | X/Y | Z | N% |
| 11. RBAC | X/Y | Z | N% |

## 🔴 Критические баги (P0)
1. [BUG-001] ...
2. [BUG-002] ...

## 🟡 Важные баги (P1)
1. [BUG-003] ...

## 🟢 Мелкие замечания (P2)
1. [BUG-004] ...

## ✅ Подтверждённые изменения v2.0
- [x] Таблица `shifts` удалена
- [x] Чат через `application_id` работает
- [x] 5 статусов задания в CHECK constraint
- [x] UI локализация: 3 статуса = "Идёт набор"
- [x] Force-complete массово отклоняет pending
- [x] Restore сбрасывает accepted → rejected
- [x] Автопереход in_progress → active работает

## ⚠️ Архитектурный долг
1. ...
2. ...

## 🎯 Рекомендации
1. ...
2. ...
```
---

## 🚀 ПОРЯДОК ЗАПУСКА (Master Execution Plan)

1. **Шаг 0: Инфраструктура**
   - [ ] Применить `ALL_PENDING.sql` (все 28 миграций)
   - [ ] Проверить наличие записей в `tariff_settings` и `monetization_settings`
   - [ ] Убедиться, что `shifts`, `reviews`, `hires` удалены

2. **Шаг 1: Архитектурный аудит (Блок 7)**
   - [ ] Проверить удаление старых таблиц и blueprint'ов
   - [ ] Проверить отсутствие старых URL (404)

3. **Шаг 2: Безопасность (Блок 5)**
   - [ ] CSRF на всех POST
   - [ ] Rate Limiting
   - [ ] RLS через прямые SQL-запросы
   - [ ] PostgREST инъекции

4. **Шаг 3: State Machine (Блоки 1-2)**
   - [ ] Задание: все 5 статусов + автопереходы
   - [ ] Отклик: все 4 статуса

5. **Шаг 4: Монетизация и чат (Блоки 3-4)**
   - [ ] Платежи, чеки, продление
   - [ ] Чат через application_id + RLS

6. **Шаг 5: UI/UX (Блок 6)**
   - [ ] Локализация статусов
   - [ ] Матрица кнопок my_jobs.html
   - [ ] Toast-уведомления
   - [ ] Оптимистичные обновления

7. **Шаг 6: PWA и адаптивность (Блок 8)**
   - [ ] Manifest, SW, offline
   - [ ] Кросс-браузерность
   - [ ] Мобильная версия

8. **Шаг 7: Edge Cases и интеграции (Блоки 9-11)**
   - [ ] Race conditions
   - [ ] Отказоустойчивость
   - [ ] RBAC

---

**ЭТОТ ПРОМТ ПОКРЫВАЕТ 100% АРХИТЕКТУРЫ v2.0.** Любой AI-агент (Cursor, Devin, OpenHands, Claude Code) или QA-инженер, получив этот документ, сможет провести аудит уровня Senior, который обычно занимает недели работы команды. Промт самодостаточен и не требует обращения к предыдущим версиям.