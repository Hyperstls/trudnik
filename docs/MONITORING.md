# Мониторинг и алерты (J135)

## Что уже есть

| Проверка | Где | Что означает |
|---|---|---|
| `GET /health` | прод | `{"status":"ok","db":true}` — приложение и БД живы |
| `GET /metrics` | прод | Prometheus-текст, нужен `X-Metrics-Token` = env `METRICS_TOKEN`; без токена на проде 404 |
| `Uptime` workflow | `.github/workflows/uptime.yml` | каждые 30 минут проверяет `/health`, `/jobs`, `/login` и статику |
| Amvera build/run logs | MCP `getBuildLogs` / `getRunLogs`, панель Amvera | ошибки сборки, рестарты, Celery |
| UX quality workflow | `.github/workflows/ux-quality.yml` | Lighthouse + axe по живому проду; запускать вручную после стабилизации деплоя |

## Uptime-алерт

`scripts/uptime_check.py` не требует секретов. Локально:

```bash
python scripts/uptime_check.py
```

В GitHub Actions workflow `Uptime` падает с exit 1 при:
- недоступности любого из URL;
- не-200 ответе;
- `/health` без `status=ok` или `db=true`.

Уведомление приходит по правилам GitHub (email/watchers). При падении workflow
открывает issue `Uptime: production probe failed` (или комментирует уже открытую),
а после восстановления закрывает её — так инцидент не теряется в логах.
Проверить вручную: Actions → Uptime → Run workflow. Расписание (`*/30 * * * *`)
действует только на дефолтной ветке (`main`), поэтому после merge в `main`
включится автоматически.

## Деплой и мониторинг

1. Пуш в `amvera-msk1/master` запускает сборку.
2. Дождаться `Status: RUNNING` (`getProject`) и `/health` 200.
3. Проверить `getRunLogs`: не должно быть `ModuleNotFoundError`, `FATAL`,
   повторяющихся `exited ... not expected` (Celery).
4. Только после стабильного прода запускать `UX quality` вручную — иначе
   Lighthouse ловит окно рестарта (`NO_NAVSTART`).

## Staging и restore

- Отдельный staging-проект Amvera не создан: это платное решение владельца.
  Локальный аналог — dev-БД + `scripts/e2e/run_critical_flows.sh`.
- Restore drill проверен локально: `scripts/restore_drill.py --drop-target`
  (counts, PostGIS, RLS, RPC — PASSED). Safety-правила и процедура восстановления
  прода — в [RESTORE_DRILL.md](RESTORE_DRILL.md). На проде drill не выполнять.
