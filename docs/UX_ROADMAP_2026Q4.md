# UX/продуктовый roadmap — 2026 Q4

**Статус на 2026-11-01:** J074–J076 (APK-логотип, PWA-install, OG заданий) — текущий релиз.
Ниже — следующие этапы в порядке приоритета. Каждый этап — отдельный контракт(ы)
агентного pipeline, без смешивания с текущим релизом.

## Уже сделано

| Задача | Результат |
|---|---|
| J074 | APK 1.2: фирменный логотип на launcher/adaptive/splash, versionCode 3 |
| J075 | PWA-install баннер: Chromium `beforeinstallprompt`, iOS-инструкция, отказ на 30 дней |
| J076 | OG/Twitter-превью задания: работа, оплата, город, фото или брендовый fallback |
| J064–J072 | Мобильные фильтры, карта/радиус/suggest, уведомления, push, CSRF, SW v16 |

## P1 — Черновик и степпер формы задания

**Почему первым:** самый заметный прирост конверсии «начал заполнять → опубликовал»;
длинная форма сейчас теряет данные при случайном уходе.

**Этап 1.1 — локальный черновик (без миграций), 1–2 дня — СДЕЛАНО (J077/J078)**
- `localStorage`-ключ `trudnik-job-draft` с TTL 7 дней;
- сохранять только несекретные поля: work_type, description, payment, date, city, address, skills;
- при возврате — баннер «Продолжить черновик?» / «Начать заново»;
- очищать после успешного POST через `?created=1`; не сохранять фото/координаты без явного согласия.
- реализовано: `static/js/job-draft.js`, TTL 7 дней, баннер восстановления, edit-форма исключена.

**Этап 1.2 — серверный черновик (миграция + RLS), 3–5 дней**
- таблица `job_drafts` (`id`, `employer_id`, `payload jsonb`, `updated_at`, `expires_at`);
- RLS: только владелец; TTL 30 дней; очистка Celery;
- endpoint `POST /jobs/draft` (CSRF, лимит), `DELETE` после публикации;
- риск: дублирование схемы `jobs`; payload версионировать (`schema_version`).

**Этап 1.3 — степпер, 2–3 дня**
- шаги: 1 «Что делать» → 2 «Когда и сколько» → 3 «Где» → 4 «Публикация»;
- прогресс, «Назад/Далее», валидация на шаге, клавиатура/aria-current;
- на мобильном — один столбец, sticky «Далее»;
- без JS — одна длинная форма (progressive enhancement).

**Критерии:** draft restore rate, completion rate, ошибки валидации по шагам;
не хранить ПДн сверх текущей политики.

## P2 — Дизайн-система (P3 из ревью)

**Порядок, чтобы не рефакторить всё сразу:**
1. **Токены** в `app.css`: primary/neutral/status, spacing, radius, shadow,
   duration/easing; заменить только новые компоненты, затем карточки.
2. **Иконки:** один набор (Lucide-подобные SVG) + `icon` template tag/include;
   размеры 16/20/24; постепенно заменить emoji/разнородные SVG.
3. **Компоненты:** Django includes (не Jinja-макросы):
   `_button.html`, `_badge.html`, `_card.html`, `_field.html`,
   `_empty_state.html`, `_modal.html`, `_sheet.html`.
4. **Motion:** 150–250 ms, ease-out, `prefers-reduced-motion` (уже есть глобально).

**Критерии:** нет визуальных регрессий на топ-10 страницах; axe-core 0 critical;
размер CSS не растёт более чем на 10%.

## P2 — Сохранённые поиски и подписка на задания

- таблица `saved_searches` (`user_id`, `query jsonb`, `created_at`, `notify`);
- сохранение текущих фильтров кнопкой «Сохранить поиск»;
- ежедневная Celery-задача: новые open-задания по фильтру → outbox → push/email;
- anti-spam: не больше 1 дайджеста в день, дедупликация по job_id;
- RLS: только владелец; удаление/отключение подписки.
- риск: стоимость запроса по навыкам/гео; использовать индексы и лимит 50 поисков.

## P3 — Core Web Vitals + axe-core в CI — КАРКАС ГОТОВ (J108)

- Playwright + `@axe-core/playwright` на публичных страницах (`/jobs`, `/jobs/<id>`, `/login`);
- Lighthouse CI (mobile) на preview/prod: LCP/CLS/INP, бюджет;
- запуск по расписанию/вручную, не блокировать каждый PR до стабилизации;
- реализовано: `.github/workflows/ux-quality.yml`, `.lighthouserc.json`, `scripts/axe_audit.mjs` (desktop+mobile, critical axe).
- публиковать отчёт в artifacts; порог: 0 critical axe, LCP < 2.5s.

## P3 — Прочее

- `YANDEX_SUGGEST_API_KEY` добавлен в env Amvera (2026-11-01); J079: серверный POST-прокси `/api/geo/suggest`, ключ не в HTML; fallback Geocoder;
- J111 (2026-11-02): серверный Geocoder-прокси `/api/geo/geocode` (`YANDEX_GEOCODER_KEY`), клик по карте/поиск адреса не зависят от прав JavaScript-ключа; встроенный `searchControl` убран;
- per-job OG-картинка с текстом (сейчас фото/брендовый fallback + OG title/description);
- PWA-install баннер на `/app` не показывается (страница сама установочная);
- offline-очередь чата и «отправить при появлении сети»;
- метрики воронки: просмотр → отклик, создание → публикация, install → return.
