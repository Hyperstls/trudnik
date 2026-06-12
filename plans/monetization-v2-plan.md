# План: Переход на модель «Плата за публикацию задания»

**Актуально на:** 12.06.2026
**Предыдущая модель:** плата за раскрытие контакта каждого исполнителя
**Новая модель:** плата за публикацию задания

---

## Оглавление

1. [Сравнительный анализ моделей](#1-сравнительный-анализ-моделей)
2. [Обратная связь по требованиям](#2-обратная-связь-по-требованиям)
3. [Новая схема БД](#3-новая-схема-бд)
4. [Новый жизненный цикл задания](#4-новый-жизненный-цикл-задания)
5. [План внедрения (этапы)](#5-план-внедрения-этапы)
6. [Детальные шаги по каждому файлу](#6-детальные-шаги-по-каждому-файлу)
7. [Что удалить/заархивировать](#7-что-удалитьзаархивировать)
8. [Риски и ограничения](#8-риски-и-ограничения)

---

## 1. Сравнительный анализ моделей

| Аспект | Старая модель (pay-per-contact) | Новая модель (pay-per-job) |
|--------|-------------------------------|---------------------------|
| **Триггер оплаты** | Каждый раз при желании увидеть контакт исполнителя | Один раз при публикации задания |
| **Цена** | 290 руб. за контакт (настраиваемая) | 490 руб. за публикацию (настраиваемая по тарифам) |
| **Видимость контактов** | Скрыты до оплаты | Видны сразу после публикации |
| **Срок действия** | Бессрочно (пока задание открыто) | 30 дней (с возможностью продления) |
| **UX для работодателя** | Paywall на каждом отклике -> friction | Одна оплата при создании -> простота |
| **Модель дохода** | Переменная (зависит от числа раскрытий) | Фиксированная за задание + продления |
| **Юридическая модель** | Плата за «информационную услугу» | Плата за «размещение объявления» |

**Вывод:** Новая модель проще для пользователя, убирает friction в воронке найма, предсказуемее для бизнеса.

---

## 2. Обратная связь по требованиям

### Согласовано и будет реализовано:

| # | Требование | Комментарий |
|---|-----------|-------------|
| 1 | Поля `is_paid`, `paid_at`, `expires_at`, `tariff` в jobs | Добавляем в jobs |
| 2 | Модальное окно с ценой перед публикацией | Вместо немедленной публикации |
| 3 | Статус `draft` для неоплаченных заданий | Черновики с кнопкой «Оплатить и опубликовать» |
| 4 | Отклики с полными контактами без paywall | Упрощает воронку |
| 5 | Удаление ContactPaywall и логики сокрытия | Полная очистка старой модели |
| 6 | Авто-снятие с публикации по истечении срока | Проверка при загрузке ленты |
| 7 | Уведомление за 3 дня до истечения | При проверке истечения |
| 8 | Кнопка «Продлить на 30 дней» | С вызовом оплаты |
| 9 | Админ-панель: статистика по заданиям | Новый раздел |
| 10 | Админ-панель: настройки тарифов | Замена текущих настроек contact_price |
| 11 | Платёжный модуль: type: 'task_publication' | Рефакторинг PaymentService |
| 12 | Чеки с услугой «Публикация задания» | Обновление ReceiptService |
| 13 | Уведомления (in-app) при оплате, истечении, найме | Через существующий NotificationService |
| 14 | Сохранение стоп-слов, предупреждений, актов ГПХ | Без изменений |

### Требуют уточнения или адаптации:

| # | Требование | Моя рекомендация |
|---|-----------|-----------------|
| 1 | **Тарифы standard/urgent/vip** | Начать с **одного тарифа** `standard` (490 руб.). VIP/urgent добавляют сложность без явной бизнес-ценности на текущем этапе. Структуру БД заложим с поддержкой тарифов, но UI сделаем только для standard. |
| 2 | **Push-уведомления** | В текущей архитектуре нет push-уведомлений (только in-app через NotificationService). Push (FCM/Web Push) — отдельный проект. Используем in-app уведомления. |
| 3 | **Cron-задача для истечения** | На Render нет cron. Два варианта: (а) проверка при каждой загрузке ленты — дёшево, но не мгновенно; (б) внешний ping-сервис (cron-job.org) дёргает эндпоинт `/api/jobs/expire-check` раз в час. Реализуем (а) + (б) опционально. |
| 4 | **«Возврат не предусмотрен»** | Добавим текст в модальное окно. Юридически требует оферты — пока только UI. |
| 5 | **Удаление contact_payments** | **Не удалять**, а переименовать в `_archive_contact_payments`. Юридически значимые записи должны сохраняться. |

---

## 3. Новая схема БД

### 3.1 Изменения в таблице `jobs`

```sql
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS tariff VARCHAR(20) DEFAULT 'standard';

-- Новые статусы: draft, expired
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check 
    CHECK (status IN ('draft', 'open', 'in_progress', 'completed', 'cancelled', 'paid', 'expired'));
```

### 3.2 Новая таблица `job_payments`

```sql
CREATE TABLE IF NOT EXISTS job_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE NOT NULL,
    employer_id UUID REFERENCES auth.users(id) NOT NULL,
    amount INTEGER NOT NULL,
    tariff VARCHAR(20) DEFAULT 'standard',
    type VARCHAR(30) DEFAULT 'publication',
    status VARCHAR(20) DEFAULT 'pending',
    transaction_id VARCHAR(255),
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.3 Новая таблица `tariff_settings`

```sql
CREATE TABLE IF NOT EXISTS tariff_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tariff_key VARCHAR(30) UNIQUE NOT NULL,
    price INTEGER NOT NULL,
    duration_days INTEGER NOT NULL DEFAULT 30,
    renewal_price INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO tariff_settings (tariff_key, price, duration_days, renewal_price)
VALUES ('standard', 490, 30, 290)
ON CONFLICT (tariff_key) DO NOTHING;
```

### 3.4 Архивация старых данных

```sql
ALTER TABLE IF EXISTS contact_payments RENAME TO _archive_contact_payments;
```

### 3.5 Индексы

```sql
CREATE INDEX IF NOT EXISTS idx_jobs_expires ON jobs(expires_at) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_job_payments_job ON job_payments(job_id);
CREATE INDEX IF NOT EXISTS idx_job_payments_employer ON job_payments(employer_id);
```

---

## 4. Новый жизненный цикл задания

```
draft ──оплата──> open ──принят_отклик──> in_progress ──смены_завершены──> completed
                     │                                                         │
                     │ истечение_30_дней                                       │ оплата_подтверждена
                     ▼                                                         ▼
                  expired ──продление──> open                                paid ──оценки──> completed
```

**Новые статусы:**
- `draft` — задание создано, но не оплачено (не видно в публичной ленте)
- `expired` — срок публикации истёк (снято с публикации, можно продлить)

**Новые переходы:**
- `draft -> open`: после успешной оплаты (is_paid=true, expires_at=now+30d)
- `open -> expired`: при истечении expires_at < now()
- `expired -> open`: после оплаты продления

---

## 5. План внедрения (этапы)

### Этап 1 — Миграция БД
- [ ] Создать `migrations/022_new_monetization_model.sql`
- [ ] Добавить поля в jobs, обновить CHECK
- [ ] Создать job_payments, tariff_settings
- [ ] Создать индексы
- [ ] Переименовать contact_payments -> _archive_contact_payments
- [ ] Применить на Supabase

### Этап 2 — Рефакторинг PaymentService и ReceiptService
- [ ] `PaymentService.create_job_payment()` — создание платежа за публикацию
- [ ] `PaymentService.process_job_payment()` — обработка успешного платежа + публикация задания
- [ ] `PaymentService.get_tariffs()` — получение тарифов
- [ ] `ReceiptService.issue_job_publication_receipt()` — чек за публикацию

### Этап 3 — Обновление jobs.py (создание/публикация)
- [ ] `POST /job/new`: сохранять как `draft`
- [ ] `POST /api/jobs/<id>/publish`: оплата и публикация
- [ ] `POST /api/jobs/<id>/renew`: продление
- [ ] `GET /api/jobs/expire-check`: проверка истечения
- [ ] Фильтр ленты: только `open` + `is_paid=true` + `expires_at > now()`

### Этап 4 — Обновление monetization.py
- [ ] Заменить `/api/payments/create` и `/api/payments/confirm` на модель job
- [ ] Удалить `/api/payments/status/<application_id>`
- [ ] Обновить `/api/admin/monetization-settings` для тарифов
- [ ] Добавить `/api/admin/job-stats`

### Этап 5 — Упрощение applications.py
- [ ] Удалить логику contact_paid/contact_payment_id
- [ ] Показывать полные контакты сразу

### Этап 6 — Шаблоны
- [ ] `job_new.html`: модальное окно с ценой
- [ ] `my_jobs.html`: кнопки «Оплатить» (draft), «Продлить» (expired)
- [ ] `my_applications.html`: убрать paywall
- [ ] `admin.html`: вкладки «Тарифы», «Статистика»

### Этап 7 — Уведомления
- [ ] «Задание опубликовано» после оплаты
- [ ] «Срок публикации истекает» за 3 дня
- [ ] «Не забудьте чек из Мой налог» после найма

### Этап 8 — Очистка
- [ ] Удалить неиспользуемые маршруты
- [ ] Удалить JS/CSS paywall

---

## 6. Детальные шаги по ключевым файлам

### 6.1 `app/services/payment_service.py`

**Новые методы:**

```python
@staticmethod
def get_tariffs():
    """Получить список активных тарифов."""
    resp = supabase_request('GET', 'tariff_settings?is_active=eq.true&order=price.asc')
    return resp.json() if resp.ok else [
        {'tariff_key': 'standard', 'price': 490, 'duration_days': 30, 'renewal_price': 290}
    ]

@staticmethod
def create_job_payment(employer_id, job_id, tariff='standard'):
    """Создать платёж за публикацию задания."""
    tariffs = {t['tariff_key']: t for t in PaymentService.get_tariffs()}
    tariff_info = tariffs.get(tariff, {'price': 490, 'duration_days': 30})
    amount = tariff_info['price']
    
    resp = supabase_request('POST', 'job_payments', json={
        'job_id': job_id, 'employer_id': employer_id,
        'amount': amount, 'tariff': tariff,
        'type': 'publication', 'status': 'pending',
    })
    if resp.ok and resp.json():
        payment = resp.json()[0] if isinstance(resp.json(), list) else resp.json()
        return {'payment_id': payment['id'], 'amount': amount}
    return None

@staticmethod
def process_job_payment(payment_id, employer_id):
    """Обработать платёж и опубликовать задание."""
    # Получить платёж
    payment_resp = supabase_request('GET',
        f'job_payments?id=eq.{payment_id}&select=*,job:jobs(organization_name)')
    payment = payment_resp.json()[0]
    
    # Эмуляция эквайринга (в будущем — реальный API)
    transaction_id = f"txn_{int(time.time() * 1000)}"
    
    now = datetime.now(timezone.utc).isoformat()
    tariffs = {t['tariff_key']: t for t in PaymentService.get_tariffs()}
    tariff_info = tariffs.get(payment['tariff'], {'duration_days': 30})
    expires_at = (datetime.now(timezone.utc) + timedelta(days=tariff_info['duration_days'])).isoformat()
    
    # Обновить платёж
    supabase_request('PATCH', f'job_payments?id=eq.{payment_id}', json={
        'status': 'paid', 'transaction_id': transaction_id, 'paid_at': now
    })
    
    # Опубликовать задание
    job_id = payment['job_id']
    supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={
        'status': 'open', 'is_paid': True, 'paid_at': now, 'expires_at': expires_at
    })
    
    # Чек
    employer = supabase_request('GET', f'profiles?id=eq.{employer_id}&select=full_name,inn')
    employer_data = employer.json()[0] if employer.ok and employer.json() else {}
    ReceiptService.issue_job_publication_receipt(
        employer_name=employer_data.get('full_name', ''),
        employer_inn=employer_data.get('inn', ''),
        job_id=job_id, tariff=payment['tariff'], amount=payment['amount']
    )
    
    # Уведомление
    from app.services.notification_service import create as notify
    notify(employer_id, 'job_published', 'Задание опубликовано',
           f'Задание опубликовано! Ожидайте откликов.',
           data={'job_id': job_id})
    
    return {'success': True, 'transaction_id': transaction_id}
```

### 6.2 `app/blueprints/jobs.py` — ключевые изменения

**POST /job/new:**
```python
# Вместо status='open':
job_data['status'] = 'draft'
job_data['is_paid'] = False
# После сохранения — редирект на страницу оплаты
return redirect(url_for('jobs.publish_job', job_id=resp.json()[0]['id']))
```

**Новый роут — страница оплаты:**
```python
@jobs_bp.route('/job/<job_id>/publish')
@login_required
@role_required('employer')
def publish_job(job_id):
    # Проверить владельца
    job = _get_job_or_404(job_id)
    if job['employer_id'] != session['user_id']:
        flash('Нет доступа', 'danger')
        return redirect(url_for('jobs.my_jobs'))
    if job['status'] != 'draft':
        flash('Задание уже опубликовано', 'warning')
        return redirect(url_for('jobs.my_jobs'))
    tariffs = PaymentService.get_tariffs()
    return render_template('job_publish.html', job=job, tariffs=tariffs)
```

**Фильтр в ленте (GET /):**
```python
# Только оплаченные, открытые, не истёкшие
query = "jobs?status=eq.open&is_paid=eq.true"
# Проверка expires_at происходит в коде:
jobs = [j for j in jobs if not j.get('expires_at') or j['expires_at'] > datetime.now(timezone.utc).isoformat()]
```

### 6.3 `app/blueprints/applications.py` — упрощение

Удалить все проверки:
```python
# Было:
if app.get('contact_paid'):
    worker_info = {...}
else:
    worker_info = {'full_name': worker['full_name']}  # скрыто

# Стало:
worker_info = worker  # полные данные всегда
```

---

## 7. Что удалить/заархивировать

| Компонент | Действие |
|-----------|----------|
| `contact_payments` таблица | Переименовать в `_archive_contact_payments` |
| `contact_paid`, `contact_payment_id` в applications | Прекратить использование (колонки оставить) |
| `PaymentService.create_payment_intent()` | Заменить на `create_job_payment()` |
| `PaymentService.process_contact_payment()` | Заменить на `process_job_payment()` |
| `GET /api/payments/status/<app_id>` | Удалить маршрут |
| Логика paywall в applications.py | Удалить |
| Кнопка «Раскрыть контакт за N руб.» | Удалить из шаблонов |
| `contact_price` в monetization_settings | Заменить на tariff_settings |

---

## 8. Риски и ограничения

| Риск | Мера |
|------|------|
| Потеря юридически значимых записей | Архивация таблиц вместо удаления |
| Сложность возврата к старой модели | Код в Git-истории |
| Отсутствие cron на Render | Проверка при загрузке + внешний ping (cron-job.org) |
| Существующие open-задания без is_paid | Миграция: проставить is_paid=true, expires_at=now+30d |
| Увеличение времени загрузки ленты | Индекс idx_jobs_expires |
