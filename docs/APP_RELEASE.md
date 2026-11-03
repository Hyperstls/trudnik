# Android APK / TWA — сборка и релиз

**Версия:** 1.2 (`versionCode 3`)
**Package:** `ru.trudnik.app`
**Канонический host:** `xn--d1aigknli.xn--p1ai` (трудник.рф)
**Страница установки:** `/app` → `/app/download`

## Что уже собрано

- `static/apk/trudnik.apk` — подписанный release APK 1.2 (TWA, `customtabs` fallback).
  Launcher/adaptive/splash-иконки сгенерированы из `static/icons/icon-512x512.png`
  (фирменный логотип); versionCode 3 устанавливается поверх 1.1.
- `static/icons/og-preview.png` — OG/Twitter превью 1200×630.
- `static/.well-known/assetlinks.json` — Digital Asset Links для TWA:
  - package `ru.trudnik.app`;
  - SHA-256 release-ключа `08:AD:60:85:3B:8A:99:F8:CF:C6:E4:99:3D:A8:CE:F8:62:10:94:C4:6A:BD:2C:95:04:9D:E0:CD:3C:67:C8:8C`.
- `twa-config.json` — конфиг для CI/bubblewrap (host, startUrl `/?utm_source=twa`).
- `twa-project/` — сгенерированный Android-проект (в `.gitignore`, собирается локально/CI).

## Локальная сборка

```bash
# JDK 17 + Android SDK 36
export ANDROID_HOME="$LOCALAPPDATA/Android/Sdk"
cd twa-project
./gradlew assembleRelease
cp app/build/outputs/apk/release/app-release.apk ../static/apk/trudnik.apk
```

APK подписывается `twa-project/trudnik-release.keystore` (alias `trudnik`).
Пароли не хранятся в git: локально — `twa-project/keystore.properties`
(gitignored), в CI — GitHub Secrets. Пример `keystore.properties`:

```properties
storeFile=../trudnik-release.keystore
storePassword=<пароль>
keyAlias=trudnik
keyPassword=<пароль>
```

Либо переменные окружения `ANDROID_KEYSTORE_PATH`,
`ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
Проверка подписи:

```bash
keytool -printcert -jarfile static/apk/trudnik.apk | grep SHA256
```

## CI

`.github/workflows/apk-release.yml` (manual dispatch; также запускается
при изменении самого workflow):

1. JDK 17 + Android SDK 36 на preinstalled SDK раннера;
2. keystore из `ANDROID_KEYSTORE_BASE64`;
3. `./gradlew assembleRelease` с `ANDROID_KEYSTORE_PASSWORD`,
   `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`;
4. подписанный `app-release.apk` в artifact `trudnik-apk`.

Секреты GitHub: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
`ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`. Значения в чат/репозиторий не
добавлять.

Исходники TWA (`twa-project/`) теперь в git без keystore, `keystore.properties`
и build-артефактов; `.dockerignore` по-прежнему исключает каталог из образа.

## Обновление assetlinks

После смены release-ключа обязательно обновить `sha256_cert_fingerprints`
в `static/.well-known/assetlinks.json` — иначе Chrome не подтвердит TWA
и откроет сайт с адресной строкой.

Проверка на проде:

```bash
curl -s https://xn--d1aigknli.xn--p1ai/.well-known/assetlinks.json
```

## CI

`.github/workflows/build-apk.yml` (manual dispatch):
1. JDK 17 + Node 20 + bubblewrap;
2. keystore из `KEYSTORE_PASSWORD`;
3. `twa-config.json` → `scripts/generate_twa_ci.js`;
4. `bubblewrap build`;
5. APK/AAB в artifacts.

Workflow требует `twa-config.json` в корне (добавлен) и секрет `KEYSTORE_PASSWORD`.

## PWA-install баннер

- На всех страницах, кроме `/app`, подключён `static/js/install-prompt.js`.
- Chromium: `beforeinstallprompt` → кнопка «Установить» вызывает системный prompt.
- iOS Safari: через 1.5 с — кнопка «Как установить» с инструкцией «Поделиться → На экран Домой».
- «Не сейчас» скрывает баннер на 30 дней (`trudnik-install-dismissed`), `appinstalled` — навсегда.
- В standalone-режиме и без JS баннер не показывается.

## Страница установки

- `/app` — карточки Android (APK), iPhone/iPad (Safari → «На экран Домой»),
  ПК (Chrome/Edge install), версия/размер/SHA-256.
- `/app/download` — `FileResponse` с `application/vnd.android.package-archive`,
  `Content-Disposition: attachment`, `Cache-Control: public, max-age=3600`.
- Ссылки: футер «Приложение» и профильное меню «Установить приложение».

## iOS

- Сейчас iOS покрыт PWA: Safari → «Поделиться» → «На экран Домой». Иконка,
  splash-фон, standalone-режим и push через Web Push (iOS 16.4+) работают без
  App Store.
- Нативная сборка (Swift/Capacitor) требует Apple Developer Program (99 $/год),
  macOS с Xcode и подписи; до появления аккаунта она не входит в релизный цикл.

## Чек-лист релиза

1. `npm run build:css`, `pre_deploy_check`, `manage.py test core`.
2. Собрать APK, проверить `versionCode/versionName`, host и подпись.
3. Обновить `assetlinks.json` при смене ключа.
4. Задеплоить APK/OG/assetlinks, проверить `/app/download` и `/.well-known/assetlinks.json`.
5. Проверить установку на Android: приложение открывает трудник.рф без адресной строки.
6. Google Play не публикуется (по текущему решению); APK — прямая установка.
