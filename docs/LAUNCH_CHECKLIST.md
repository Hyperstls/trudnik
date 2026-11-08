# Launch-readiness checklist (J138)

**Дата проверки:** 2026-11-03
**Скрипт:** `python scripts/launch_check.py`
**Прод:** https://xn--d1aigknli.xn--p1ai (деплой `01c24d2`)

## Автоматическая проверка

Скрипт проверяет без секретов:

- `/health` (JSON `status=ok`, `db=true`);
- публичные страницы `/jobs`, `/login`, `/privacy`, `/terms`, `/safety`, `/faq`;
- `/sitemap.xml`, `/robots.txt`, `/static/manifest.json`, `/sw.js`, статику;
- security-заголовки: CSP, HSTS, XCTO, Referrer-Policy, Permissions-Policy;
- срок TLS-сертификата;
- email-DNS: SPF, DMARC, MX, DKIM для `trudnik.ru` и `xn--d1aigknli.xn--p1ai`.

Exit code 1 — только ошибки приложения/TLS/заголовков. Email-DNS — предупреждения
для владельца.

## Результат 2026-11-03

| Блок | Статус |
|---|---|
| Приложение и страницы | PASS |
| Security-заголовки | PASS на всех проверенных страницах |
| TLS | PASS, истекает через 83 дня |
| `robots.txt` | исправлено: добавлены `Disallow: /admin/` и `Sitemap:` |
| `manifest.json` | PASS по фактическому пути `/static/manifest.json` |
| SPF `trudnik.ru` | **MISSING** |
| DMARC `trudnik.ru` | **MISSING** |
| MX `trudnik.ru` | **void.blackhole.mx** (домен паркуется) |
| DKIM `trudnik.ru` | не найден по типовым селекторам |
| SPF/DMARC/DKIM `xn--d1aigknli.xn--p1ai` | **MISSING** |

## Критично перед запуском

### 1. Почта — проверить `SMTP_FROM_EMAIL`

В Amvera задан секрет `SMTP_FROM_EMAIL`. Нужно убедиться, что адрес отправителя
использует домен с настроенными SPF, DKIM и DMARC.

Сейчас `trudnik.ru` припаркован (`MX = void.blackhole.mx`), TXT/SPF/DMARC/DKIM
отсутствуют. Если письма уходят с `@trudnik.ru`, они будут попадать в спам или
отклоняться. Варианты:

1. настроить DNS домена отправителя (SPF + DKIM + DMARC) у регистратора/почтового
   провайдера;
2. использовать From-домен провайдера SMTP, у которого уже есть SPF/DKIM;
3. использовать `xn--d1aigknli.xn--p1ai` только после настройки его почтовых
   записей (IDN-адреса требуют проверки у провайдера).

После изменения — отправить тестовые письма на Gmail/Яндекс/Mail.ru и проверить
заголовки `spf=pass`, `dkim=pass`, `dmarc=pass`.

### 2. Бэкапы и restore

- Уточнить в панели Amvera retention/частоту бэкапов PostgreSQL.
- Один раз восстановить временный кластер по [RESTORE_DRILL.md](RESTORE_DRILL.md).
- Зафиксировать RTO/RPO.

### 3. Юридическое

- Проверить статус уведомления РКН (`docs/rkn_notification_fill.md`).
- **Решение по push-каналу (владелец):** задекларировать трансграничную
  передачу (ст. 12, Google/Mozilla) или отключить push; политика v1.3
  (08.11.2026) признаёт передачу явно и допускает оба варианта.
- Актуальность политики (теперь v1.3) и согласий; обновить `site_pages`
  в проде через админку до текста v1.3 (4.2/9.1/9.2/10.7/10.8/14.5).

### 4. Алерты

Сейчас есть GitHub Uptime-workflow: при падении он открывает issue
`Uptime: production probe failed` и закрывает её после восстановления. Для
запуска желательно добавить внешний канал (Telegram/email), чтобы падение не
осталось только в GitHub. Нужны токен/чат владельца.

### 5. Нагрузка

- Проверить лимиты тарифа Amvera: CPU/RAM, соединения PostgreSQL, Redis.
- Прогнать нагрузочный сценарий на `/jobs` и `/health` (100 req, P=8) после
  запуска staging.

### 6. Монетизация и APK — если входят в запуск

- Платежи/чеки/возвраты — протестировать на тестовом провайдере.
- APK: подпись и CI готовы; публикация в RuStore/Google Play, assetlinks,
  скриншоты и описание — по необходимости.

## После запуска

- Следить за `Uptime` и `getRunLogs` первые 24 часа.
- Проверить воронку `/admin/analytics/` и ошибки `/api/client-error`.
- Запустить `UX quality` вручную после стабилизации деплоя.
