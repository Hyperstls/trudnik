# Почта: SMTP, SPF, DKIM, DMARC

## Что сейчас

Прод отправляет письма через **smtp.yandex.ru** (видно в run-logs Amvera).
Адрес отправителя задан секретом `SMTP_FROM_EMAIL`; по умолчанию в коде —
`notifications@trudnik.ru`.

Проблема: домен `trudnik.ru` сейчас **припаркован** (`ns1.snparking.ru`,
`MX = void.blackhole.mx`), у него нет SPF, DKIM и DMARC. Если письма уходят
с `@trudnik.ru`, они не проходят проверку подлинности и попадают в спам или
отклоняются.

## Вариант A — быстро и без DNS (рекомендую для запуска)

Использовать реальный ящик Яндекс.Почты как отправителя, например
`trudnik-app@yandex.ru`:

1. В Amvera выставить:
   - `SMTP_HOST=smtp.yandex.ru`
   - `SMTP_PORT=465` и `SMTP_USE_SSL=true` (или 587 + `SMTP_USE_TLS=true`)
   - `SMTP_USER=trudnik-app@yandex.ru`
   - `SMTP_FROM_EMAIL=trudnik-app@yandex.ru`
   - `SMTP_PASSWORD` — **пароль приложения** Яндекс.Почты, не обычный пароль
     (включите 2FA и создайте «Пароль приложения» для почты).
2. Пересобрать/перезапустить проект Amvera, чтобы env применились.
3. Отправить тестовую регистрацию/сброс пароля на Gmail, Яндекс и Mail.ru.
4. В полученном письме открыть «Показать оригинал» и проверить:
   `spf=pass`, `dkim=pass`, `dmarc=pass`.

Плюс: ничего не нужно менять в DNS, Яндекс сам подписывает письма своего
домена. Минус: адрес отправителя будет `@yandex.ru`, а не брендовый.

## Вариант B — брендовый `notifications@trudnik.ru`

Нужен доступ к DNS домена `trudnik.ru` (сейчас NS — `ns1.snparking.ru`;
записи добавляются у регистратора/в панели snparking, либо делегируйте домен
в Яндекс 360).

1. Подключить `trudnik.ru` в Яндекс 360 (или Яндекс.Почте для домена).
2. Подтвердить владение доменом: добавить выданную Яндексом TXT-запись
   `yandex-verification: ...` на `@`.
3. Прописать почтовые записи (значения уточняются в панели Яндекс 360):
   - `@ MX 10 mx.yandex.net`
   - `@ TXT "v=spf1 redirect=_spf.yandex.net"` (или `include:_spf.yandex.net ~all`)
   - `mail._domainkey TXT "v=DKIM1; k=rsa; p=..."` — публичный ключ DKIM
     из панели Яндекс 360
   - `_dmarc TXT "v=DMARC1; p=none; rua=mailto:dmarc@trudnik.ru"` —
     начать с `p=none`, после проверки можно `quarantine`
4. Создать ящик `notifications@trudnik.ru` и пароль приложения.
5. В Amvera: `SMTP_USER=notifications@trudnik.ru`,
   `SMTP_FROM_EMAIL=notifications@trudnik.ru`, `SMTP_PASSWORD=<пароль приложения>`.
6. Дождаться DNS (обычно минуты, максимум 24 часа) и проверить:

```bash
python scripts/launch_check.py
nslookup -q=TXT trudnik.ru 8.8.8.8
nslookup -q=TXT _dmarc.trudnik.ru 8.8.8.8
nslookup -q=TXT mail._domainkey.trudnik.ru 8.8.8.8
```

7. Отправить тестовое письмо на https://www.mail-tester.com/ — цель 10/10,
   и проверить `spf=pass dkim=pass dmarc=pass` в Gmail.

## Важно

- Пароли приложений и SMTP-секреты — только в env Amvera, не в репозитории.
- `TRUDNIK.RU` в punycode — `xn--d1aigknli.xn--p1ai`; для почты используйте
  ASCII-домен `trudnik.ru`, IDN-адреса поддерживаются не всеми провайдерами.
- Пока DNS не настроен, `scripts/launch_check.py` будет показывать
  предупреждения `SPF/DMARC missing` и `MX blackhole` — это ожидаемо.
- После настройки писем проверить регистрацию, подтверждение email и сброс
  пароля на реальных ящиках.
