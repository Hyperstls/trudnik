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

**J115 (2026-11-02) — степпер регистрации СДЕЛАНО:**
- шаги «Аккаунт» → «О себе» → «Контакты»; прогресс, aria-current, aria-live;
- Next валидирует только текущий шаг, submit открывает шаг с ошибкой;
- без JS — одна длинная форма + `<noscript>` submit;
- sessionStorage-черновик только `intent` и навыков (TTL 7 дней), очищается на `/login?email=`;
- `intent` сохраняется при серверной ошибке формы.

## P2 — Дизайн-система (P3 из ревью)

**Порядок, чтобы не рефакторить всё сразу:**
1. **Токены** в `app.css`: primary/neutral/status, spacing, radius, shadow,
   duration/easing; заменить только новые компоненты, затем карточки.
2. **Иконки:** один набор (Lucide-подобные SVG) + `icon` template tag/include;
   размеры 16/20/24; постепенно заменить emoji/разнородные SVG.
   - J109–J110: sprite (`static/icons/sprite.svg`) + `_ui_icon.html`, звёзды/галочки на ключевых страницах;
   - J113–J116 (2026-11-02): emoji ★/✓/✕ заменены на sprite во всех шаблонах (`employer_detail`, `user_ratings`, `favorites`, `worker_detail`, `job_applicants`, `my_applications`, `rate_workers`, `job_form`, `legal_fallback`); emoji в шаблонах не осталось.
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
- J121 (2026-11-02): axe-аудит 5 страниц (`/jobs`, `/login`, `/workers`, `/register`, `/search`) desktop+mobile — **0 critical/serious**; `primary-600` для кнопок/ссылок, доступные имена логотипа и ссылки Яндекса; в отчёт добавлены serious-warnings.
- J125 (2026-11-03): Inter self-hosted (cyrillic/latin), Google Fonts удалён — Lighthouse mobile: performance 70→**96**, LCP 4.5→**1.9 s**, FCP 4.5→**1.4 s**, CLS 0; нет трансграничной передачи в Google;
- публиковать отчёт в artifacts; порог: 0 critical axe, LCP < 2.5s.

## P3 — Прочее

- `YANDEX_SUGGEST_API_KEY` добавлен в env Amvera (2026-11-01); J079: серверный POST-прокси `/api/geo/suggest`, ключ не в HTML; fallback Geocoder;
- J119 (2026-11-02): глобальный поиск `/search` по заданиям, трудникам и работодателям; форма в шапке видна и гостям, мобильная иконка поиска; работодатели — только авторизованным;
- J111 (2026-11-02): серверный Geocoder-прокси `/api/geo/geocode` (`YANDEX_GEOCODER_KEY`), клик по карте/поиск адреса не зависят от прав JavaScript-ключа; встроенный `searchControl` убран;
- J117–J118 (2026-11-02): per-job OG-картинка 1200×630 генерируется на сервере (Pillow + DejaVu, заголовок/оплата/город/дата), кэш 1 час, `/jobs/<id>/og.png`; фото и брендовый fallback больше не нужны;
- PWA-install баннер на `/app` не показывается (страница сама установочная);
- J120 (2026-11-02): чат — новый `client_message_id` на каждое сообщение, отправка без перезагрузки, offline-очередь в sessionStorage (TTL 1ч), flush по online/WS, дедуп WS+poll, свои сообщения справа;
- offline-очередь чата и «отправить при появлении сети» — СДЕЛАНО J120;
- J123 (2026-11-03): first-party аналитика воронки — агрегаты в Redis (просмотры/отклики/публикации/установки), без cookies/IP, `/admin/analytics/` за 7/30 дней;
- J124 (2026-11-03): публичная политика 1.2 — серверный черновик, сохранённые поиски, localStorage/sessionStorage, геокодер Яндекс.Карт, обезличенная статистика;
- метрики воронки: просмотр → отклик, создание → публикация, install — СДЕЛАНО J123;
