# A11Y-аудит шаблонов «Трудник»

Дата: 2026-08-15 (исправления: 2026-08-16)

## ✅ СТАТУС ИСПРАВЛЕНИЙ (2026-08-16)

Исправлены ВСЕ находки аудита (атрибутные правки, без изменения структуры):
- **C-1, C-2, I-2** (chat.html): aria-label «Назад к чатам»; `role="log" aria-live="polite" aria-label="История сообщений"`; aria-label формы
- **W-1, W-2**: rating-star кнопки `aria-label="Оценка {{ i }}"` (workers.html, employer_detail.html)
- **W-3, W-4, W-5, W-6**: aria-label на всех textarea (workers, rate_workers, profile_worker, job_detail JS-строка)
- **W-7, W-8, W-9, W-14**: связь label for/id (admin_edit_content, employer_detail select, profile bio, admin_test_user)
- **W-10..W-13**: aria-label на 4 select в admin.html (фильтры + per-row с именем пользователя/ID задания)
- **I-1**: register.html декоративный SVG aria-hidden

Осталось (info, при следующем рефакторинге): I-3 (контраст placeholder neutral-400), I-4 (title → aria-label дублирование).
Верификация: pre_deploy_check 0 проблем; f-серия (aria_labels, input_labels) зелёная.

---

## Исходный отчёт

Метод: статический анализ всех 44 .html файлов в `templates/` (включая `email/`, partials `_*.html`).
Стандарт: WCAG 2.1 AA. Severity: **critical** (блокирует использование скринридером) → **warning** (нарушение WCAG A/AA, есть workaround) → **info** (рекомендация).

> Примечание: это аудит-отчёт. Шаблоны НЕ модифицировались. Часть базовых проверок (html lang, skip-link, flash aria, tabindex, page titles) также покрыта автотестами `tests/test_f1..f29*.py`.

---

## Общая картина

Общее состояние — **хорошее**. В `base.html` есть `lang="ru"`, skip-link, aria-label на навигации, `aria-hidden` на декоративных SVG, `aria-live` на бейджах. Формы login/register/job_new/password_reset имеют корректные `<label for>`. Найдено **2 critical**, **13 warning**, **4 info** проблемы.

---

## CRITICAL

### C-1. chat.html:14 — иконочная ссылка «назад» без доступного имени

```html
<a href="/chats" class="w-9 h-9 rounded-full flex items-center justify-center hover:bg-neutral-100 transition-colors -ml-1">
    {{ chevron_left(22) }}
</a>
```

- **Проблема**: ссылка содержит только SVG-стрелку. Скринридер объявляет «ссылка» без назначения. Нарушение WCAG 2.4.4 / 4.1.2.
- **Исправление**: добавить `aria-label="Назад к чатам"`.

### C-2. chat.html:27 — контейнер сообщений без ARIA live region

```html
<div id="messages" class="flex-1 overflow-y-auto px-4 py-3 space-y-3">
```

- **Проблема**: сообщения добавляются динамически (polling/WebSocket, `addMessage()`), но новые сообщения не объявляются скринридеру. Нарушение WCAG 4.1.3 (Status Messages).
- **Исправление**: `role="log"` + `aria-live="polite"` (полезно также `aria-label="История сообщений"`).

---

## WARNING

### W-1. workers.html:161 — кнопки выбора оценки без aria-label

```html
<button type="button" class="rating-star ..." data-value="{{ i }}">★</button>
```

- **Проблема**: доступное имя — символ «★», объявляется нестабильно («star»/тишина). 5 одинаковых кнопок неотличимы. WCAG 4.1.2.
- **Исправление**: `aria-label="Оценка {{ i }}"`.
- **Эталон**: в `rate_workers.html:114` сделано правильно (`aria-label="Оценка {{ s }}"`) — консистентность нарушена.

### W-2. employer_detail.html:233 — то же самое

`<button type="button" class="rating-star ..." data-value="{{ i }}">★</button>` — без aria-label. Исправление аналогично W-1.

### W-3. workers.html:167-169 — textarea комментария без label

`<textarea id="rating-comment" ... placeholder="Комментарий (необязательно)">` — только placeholder. WCAG 3.3.2. Исправление: `aria-label="Комментарий к оценке"`.

### W-4. rate_workers.html:121-126 — textarea отзыва без label

`<textarea id="comment-{{ w.worker_id }}" ... placeholder="Ваш отзыв (необязательно)">` — только placeholder. Исправление: `aria-label="Ваш отзыв"`.

### W-5. profile_worker.html:95-97 — textarea жалобы без label

`<textarea name="reason" ... placeholder="Причина жалобы…">` — только placeholder. Исправление: `aria-label="Причина жалобы"`.

### W-6. job_detail.html:582 — JS-генерируемая textarea без label

Строка в JS-шаблоне `addRatingForm()`: `<textarea id="rating-comment" ... placeholder="Ваш отзыв (необязательно)">`. Исправление: добавить `aria-label` в JS-строку.

### W-7. admin_edit_content.html:17-18 — label не ассоциирован с textarea

```html
<label class="block ...">Содержимое (HTML)</label>
<textarea name="content" rows="20" ...>
```

- **Проблема**: видимый label есть, но нет `for`/`id` — программной связи нет. WCAG 1.3.1 / 3.3.2.
- **Исправление**: `<label for="content-field">` + `<textarea id="content-field">`.

### W-8. employer_detail.html:225-226 — label не ассоциирован с select

```html
<label class="block ...">Выберите завершённое задание:</label>
<select id="rating-job-select" ...>
```

- **Исправление**: `<label for="rating-job-select">` (id у select уже есть).

### W-9. profile.html:100-101 — floating-label без ассоциации

```html
<textarea name="bio" rows="3" class="floating-input resize-none" placeholder=" ">...</textarea>
<label class="floating-label">О себе</label>
```

- **Проблема**: паттерн floating-label через CSS, но связи for/id нет. Аналогичные группы в этом же файле стоит проверить.
- **Исправление**: `id="bio"` + `<label for="bio" class="floating-label">`.

### W-10. admin.html:108 — select фильтра ролей без aria-label

`<select name="role" ...><option value="">Все роли</option>` — контекст только визуальный (рядом поле поиска). Исправление: `aria-label="Фильтр по роли"`.

### W-11. admin.html:159 — per-row select смены роли без aria-label

В таблице пользователей: `<select name="role">` — из строки таблицы непонятно, чью роль меняешь. Исправление: `aria-label="Роль пользователя {{ u.full_name }}"`.

### W-12. admin.html:191 — select фильтра статуса заданий без aria-label

`<select name="status">` рядом с поиском заданий. Исправление: `aria-label="Фильтр по статусу"`.

### W-13. admin.html:242 — per-row select статуса задания без aria-label

`<select name="status">` в строке таблицы заданий. Исправление: `aria-label="Статус задания {{ j.id }}"`.

### W-14. admin_test_user.html:33-34 — label «Роль» не ассоциирован с select

```html
<label class="block ...">Роль</label>
<select name="role" ...>
```

Исправление: `for`/`id`.

---

## INFO

### I-1. register.html:8-13 — декоративный SVG без aria-hidden

Иконка в шапке формы регистрации. Для консистентности добавить `aria-hidden="true"` (в login.html:8 — есть).

### I-2. chat.html:62 — форма отправки без aria-label

`<form id="chat-form">` — внутри input имеет `aria-label="Сообщение"`, поэтому некритично. Рекомендуется `aria-label="Отправка сообщения"`.

### I-3. Контраст placeholder'ов (text-neutral-400 на белом)

Широко используется `placeholder:text-neutral-400` и `text-neutral-400` для подсказок — ориентировочно ~2.8:1, ниже WCAG AA 4.5:1 для текста. Placeholder — не единственный источник информации (есть labels), поэтому info. Рекомендация: заменить на `neutral-500`.

### I-4. title= вместо aria-label на кнопках действий

`job_detail.html`, `index.html` используют `title="..."` на кнопках. `title` даёт доступное имя, но не отображается на тач-устройствах и надёжность поддержки скринридерами ниже. Все проверенные кнопки имеют видимый текст — некритично. Рекомендация: дублировать в `aria-label` при рефакторинге.

---

## Полный чеклист шаблонов (44 файла)

| Шаблон | Статус | Находки |
|--------|--------|---------|
| _components.html | ✅ partial | нет standalone-контента |
| _filter_skills.html | ✅ partial | — |
| _icons.html | ✅ macros | SVG-иконки без aria-hidden в некоторых макросах (декоративные, используются с текстом) |
| _sort_panel.html | ✅ partial | — |
| admin.html | ⚠️ warning | W-10, W-11, W-12, W-13 |
| admin_complaints.html | ✅ | — |
| admin_edit_content.html | ⚠️ warning | W-7 |
| admin_test_user.html | ⚠️ warning | W-14 |
| base.html | ✅ | lang="ru", skip-link, aria-label навигации — эталон |
| blacklist.html | ✅ | — |
| chat.html | 🔴 critical | C-1, C-2, I-2 |
| chats_list.html | ✅ | кнопки с текстом |
| email/base_email.html | ✅ | lang="ru" |
| email/chat_message.html | ✅ | email-контент |
| email/notification.html | ✅ | email-контент |
| employers.html | ✅ | кнопки с текстом |
| employer_detail.html | ⚠️ warning | W-2, W-8 |
| error.html | ✅ | — |
| favorites.html | ✅ | кнопки с текстом |
| index.html | ✅ info | I-4 |
| invitations.html | ✅ | — |
| job_detail.html | ⚠️ warning | W-6, I-4 |
| job_new.html | ✅ | labels корректны (work_type: label for ✅) |
| legal_page.html | ✅ | — |
| login.html | ✅ | эталон форм |
| my_applications.html | ✅ | — |
| my_jobs.html | ✅ | — |
| notification_settings.html | ✅ | чекбоксы обёрнуты в label |
| notifications.html | ✅ | aria-label на кнопках удаления |
| offline.html | ✅ | lang="ru" |
| password_reset_confirm.html | ✅ | label for ✅ |
| password_reset_request.html | ✅ | label for ✅ |
| pricing.html | ✅ | — |
| privacy.html | ✅ | — |
| profile.html | ⚠️ warning | W-9 |
| profile_worker.html | ⚠️ warning | W-5 |
| rate_workers.html | ⚠️ warning | W-4 (звёзды — эталон W-1) |
| register.html | ✅ info | I-1; labels/fieldset/legend ✅ |
| resend_verification.html | ✅ | — |
| terms.html | ✅ | — |
| user_ratings.html | ✅ | — |
| verify_email.html | ✅ | — |
| verify_employer.html | ✅ | — |
| workers.html | ⚠️ warning | W-1, W-3 |

## img alt: 12 `<img>` по всем шаблонам — все имеют alt ✅

---

## Приоритет исправления

1. **C-1, C-2** (chat.html) — однострочные правки, максимальный эффект
2. **W-1..W-6** — звёзды и textarea (формы оценки — ключевой user flow)
3. **W-7..W-14** — админ-панель (меньшая аудития)
4. **I-1..I-4** — при следующем рефакторинге
