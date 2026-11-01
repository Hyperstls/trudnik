# Jobs / applications — результаты паритета (J001–J063)

**Дата:** 2026-11-01
**Ветка:** `feat/agent-pipeline` (Django `main` не менялся)
**Метод:** контракт → dispatch → verify (exit-код) → независимый pattern-review → done.
**Итог:** P0 и P1 закрыты; P2-01/02/03/05/06/08/10/11/12/13 закрыты; P2-04/P2-07/P2-09 — осознанные решения; открытых UX-пунктов нет.
Полный `manage.py test core` — **429 OK**; `pre_deploy_check` — 7/7.

## Контракты

| ID | Что сделано | Verify | Review |
|---|---|---|---|
| **J001** | `preferred_religion` удалён из формы/админки/шаблона (ТК РФ ст.3, 152-ФЗ) | PASS | PASS |
| **J002** | Stop-words, дата в прошлом, оплата 0..1M, работники 1..100 — field-level | PASS | PASS |
| **J003** | `expires_at=now+30d` при create/edit; окно отзыва 12 ч для accepted | PASS | PASS |
| **J004** | Каталог `open/completed`, blacklist-exclude; `call_rpc` разворачивает jsonb/boolean; русские коды apply | PASS | PASS |
| **J004T** | `test_rpc` выровнен под boolean-контракт `call_rpc` | PASS | PASS |
| **J005** | Outbox `application_received/accepted/rejected`, savepoint + fail-open | PASS | PASS |
| **J006** | `reopen` через `accept_application` (слоты/FOR UPDATE); repost копирует фото/expires_at в транзакции | PASS | PASS |
| **J006T** | Старый тест reopen(pending) выровнен под accept-семантику | PASS | PASS |
| **J007** | Единый массив JobPhoto+legacy, лимит 3, фото в ленте, refcount-удаление файла | PASS | PASS |
| **J008** | my-jobs табы + `application_count`; my-applications received/sent + пагинация | PASS | PASS |
| **J009** | Bulk cancel/restore/delete и accept/reject/reopen, ≤50, ownership, UUID-валидация | PASS | PASS |
| **J010** | UI-панели массовых действий (HTML5 `form=`, CSRF, только received) | PASS | PASS |
| **J011** | P2-06: удаление файлов фото при single/bulk delete задания, refcount для общих файлов | PASS | PASS |
| **J012** | P2-05: bulk apply — групповые уведомления работодателю, applied/skipped/failed, open-redirect fix | PASS | PASS |
| **J013** | P2-01 (часть): payment_max, фильтр по навыку, Новые/Откликнулся | PASS | PASS |
| **J014** | P2-02 (часть): application_count владельцу, избранный работодатель, жалоба, share | PASS | PASS |
| **J015** | Косметика: label «Принять повторно» + недостающие CSS-утилиты | PASS | PASS |
| **J016** | P2-02 (ratings): рейтинг, число отзывов и 3 последних отзыва работодателя | PASS | PASS |
| **J017** | Bulk duplicate через общий `duplicate_job` (фото/навыки/expires_at) | PASS | PASS |
| **J018** | P2-02 (verification): бейдж «✓ Подтверждён» у approved-работодателя | PASS | PASS |
| **J019** | P2-01 (multi-skills): фильтр по нескольким навыкам | PASS | PASS |
| **J020** | P2-08: поиск q по object_description | PASS | PASS |
| **J021** | P2-12 (часть): навыки/рейтинг/оплата/сортировка в каталоге трудников | PASS | PASS |
| **J022** | P2-03: лимиты названия 255 / описания 5000 | PASS | PASS |
| **J023** | P2-12 (badges): Надёжный и Приглашён в каталоге трудников | PASS | PASS |
| **J024** | P2-01 (гео): radius-фильтр, distance-sort, geolocation, расстояние в карточке | PASS | PASS |
| **J025** | P2-01 (карта): Yandex Maps с метками заданий (опционально по ключу) | PASS | PASS |
| **J027** | P2-01 (координаты): карта-пикер в форме задания, lat/lng сохраняются | PASS | PASS |
| **J028** | P2-01: на карте только офлайн-задания (address+coords) | PASS | PASS |
| **J029** | P2-11: уникальность (rater, job, rated_user), точечный upsert, accepted-гейт, отзывы по target_type | PASS | PASS |
| **J030** | P2-11 UI: prefill оценки в rate_workers, подписи «От работодателя/работника» | PASS | PASS |
| **J031** | P2-13: каталог работодателей по open-заданиям, фильтры/сортировки, blacklist, избранное | PASS | PASS |
| **J032** | P2-13: карточка работодателя — open-only, blacklist 404, избранное, метка отклика | PASS | PASS |
| **J033** | P2-10: после accepted меняется только описание задания | PASS | PASS |
| **J034** | SmartCaptcha validate: JSON → form-urlencoded | PASS | PASS |
| **J035** | SMTP_USER + resend-страница с prefill email | PASS | PASS |
| **J036** | Service worker v15: не кэширует и не синтезирует 503 | PASS | PASS |
| **J037** | Мобильный UX: дубли «Создать», табы/кнопки, навыки | PASS | PASS |
| **J038** | Контакты трудника в полученных откликах | PASS | PASS |
| **J039** | `/chats` только accepted-отклики | PASS | PASS |
| **J040** | «Отклонить все ожидающие» приглашения | PASS | PASS |
| **J041** | «Удалить все» уведомления + настройки | PASS | PASS |
| **J042** | Панель навыков не выходит за viewport | PASS | PASS |
| **J043–J044** | Единое `/favorites` с табами, bulk и приглашениями | PASS | PASS |
| **J045** | Push-уведомления: скрипты, кнопка, CSRF | PASS | PASS |
| **J046** | «Мои отклики»: received-дефолт, карточки, select-all | PASS | PASS |
| **J047** | `/search`→`/jobs`, чат accepted, trust-блок | PASS | PASS |
| **J048** | Чат: пустое состояние, автоскролл, даты | PASS | PASS |
| **J049–J050** | Гео: автозаполнение формы, адрес/карта/маршрут | PASS | PASS |
| **J052** | Уведомления: типы и deep-links | PASS | PASS |
| **J053** | 152-ФЗ: гео POST+сессия, round(3), без координат в URL | PASS | PASS |
| **J054** | FAQ: 5 групп/14 вопросов, rel=noopener | PASS | PASS |
| **J055** | Фильтр навыков в «Моих откликах» | PASS | PASS |
| **J056** | Жалоба в `<dialog>` | PASS | PASS |
| **J057** | Мультирольное избранное: явный тип | PASS | PASS |
| **J058** | `/chats`: Subquery вместо N+1 | PASS | PASS |
| **J059** | A11Y: focus-visible + aria-labelledby модалок | PASS | PASS |
| **J060** | Канонический домен 301/308 + OG/Twitter | PASS | PASS |
| **J061** | `/app` и безопасная отдача APK | PASS | PASS |
| **J062** | Ссылки на приложение, фон «Изменить» | PASS | PASS |
| **J063** | APK v1.1, assetlinks, OG 1200×630, PWA manifest | PASS | PASS |

## Ключевая находка контрактной проверки

`call_rpc` возвращал jsonb как `{'apply_job_atomic': '<json>'}`. Из-за этого:
- все сообщения RPC были «Действие не выполнено»;
- `change_password` из-за `bool(dict)` мог показывать успех при неверном пароле.

Исправлено в J004: jsonb-объект → плоский dict, boolean → `bool`, прочие скаляры
сохраняют обёртку для совместимости (`register_user`, `expire_unfilled_jobs`).
Серверные RPC не менялись — это контракт Python-клиента.

## Что осталось

| Пункт | Статус |
|---|---|
| Bulk duplicate заданий | ✅ J017 |
| P2-01 каталог/гео/карта | ✅ J013/J019/J024/J025/J027/J028 |
| P2-02 detail | ✅ J014/J016/J018 |
| P2-03 валидация | ✅ J022 |
| P2-04 redirect после create | ✅ осознанное UX-улучшение (detail вместо my-jobs) |
| P2-07 org/object description в форме | ✅ осознанное UX-улучшение (Flask оставлял пустыми) |
| P2-09 job_applicants для админа | ✅ осознанное админ-исключение (`admin_required` разрешён AGENTS.md) |
| P2-10 edit после accepted | ✅ J033 |
| P2-11 ratings/rate_workers | ✅ J029/J030 |
| P2-12 каталог трудников | ✅ J021/J023; карта n/a — у Profile нет lat/lng (J026 blocked) |
| P2-13 employers/ratings | ✅ J031/J032 |

Открытых пунктов паритета jobs/applications нет.

## Доказательства

- Контракты: `context/agent-pipeline/tasks/J001.json` … `J063.json`.
- **J026 blocked:** карта трудников — у `Profile` нет lat/lng; потребовала бы миграцию/геокодинг.
- Логи проверок: `context/agent-pipeline/logs/J00*.verify.log`.
- Решения/заметки: `context/agent-pipeline/decisions.md`.
- Матрицы: [ROUTES_MATRIX_JOBS.md](ROUTES_MATRIX_JOBS.md),
  [UI_INVENTORY_JOBS.md](UI_INVENTORY_JOBS.md),
  [DISCREPANCIES_JOBS.md](DISCREPANCIES_JOBS.md).
