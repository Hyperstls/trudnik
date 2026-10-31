# Jobs / applications — результаты паритета (J001–J010)

**Дата:** 2026-10-31
**Ветка:** `feat/agent-pipeline` (Django `main` не менялся)
**Метод:** контракт → dispatch → verify (exit-код) → независимый pattern-review → done.
**Итог:** P0 закрыт, все P1 jobs/applications закрыты, кроме bulk duplicate.
Полный `manage.py test core` — **270 OK**; `pre_deploy_check` — 7/7.

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
| Bulk duplicate заданий | ❌ требует выноса repost-хелпера в сервис |
| P2-01 каталог (карта/гео/навыки/payment_max/filter new-applied) | open |
| P2-02 detail (application_count, share/report/favorite employer) | open |
| P2-05 bulk apply (per-job counts/уведомления) | open |
| P2-06 удаление файлов при удалении задания | open |
| P2-09..P2-13 ratings/employers/workers UI | open |

## Доказательства

- Контракты: `context/agent-pipeline/tasks/J001.json` … `J010.json`.
- Логи проверок: `context/agent-pipeline/logs/J00*.verify.log`.
- Решения/заметки: `context/agent-pipeline/decisions.md`.
- Матрицы: [ROUTES_MATRIX_JOBS.md](ROUTES_MATRIX_JOBS.md),
  [UI_INVENTORY_JOBS.md](UI_INVENTORY_JOBS.md),
  [DISCREPANCIES_JOBS.md](DISCREPANCIES_JOBS.md).
