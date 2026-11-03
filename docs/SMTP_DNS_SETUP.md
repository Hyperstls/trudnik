# Почта: SMTP, SPF, DKIM, DMARC

## Текущая настройка (Вариант A, 2026-11-03)

В Amvera настроено:

- `SMTP_HOST=smtp.yandex.ru`
- `SMTP_PORT=465`, `SMTP_USE_SSL=true`, `SMTP_USE_TLS=false`
- `SMTP_USER=trudnik-app@yandex.ru`
- `SMTP_FROM_EMAIL=trudnik-app@yandex.ru`
- `SMTP_FROM_NAME=Трудник`
- `SMTP_PASSWORD` — пароль приложения Яндекс.Почты (секрет, в репозитории нет)

Проверено: SMTP login через `smtp.yandex.ru:465` успешен, тестовое письмо
отправлено. Дубликатов (`SMTP_USERNAME`, второго From и т.п.) в Amvera нет.

DNS менять не нужно: письма уходят с домена `yandex.ru`, у которого уже есть
SPF/DKIM/DMARC. Брендовый `@trudnik.ru` — отдельный Вариант B ниже.

## Что было

Изначально использовался `SMTP_FROM_EMAIL=notifications@trudnik.ru`, но домен
`trudnik.ru` припаркован (`ns1.snparking.ru`, `MX = void.blackhole.mx`), без
SPF/DKIM/DMARC. Письма с такого адреса не проходили проверку подлинности.
Поэтому выбран Вариант A — отправка с реального ящика Яндекса.
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
