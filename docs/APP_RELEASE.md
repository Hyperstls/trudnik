# Android APK / TWA — сборка и релиз

**Версия:** 1.1 (`versionCode 2`)
**Package:** `ru.trudnik.app`
**Канонический host:** `xn--d1aigknli.xn--p1ai` (трудник.рф)
**Страница установки:** `/app` → `/app/download`

## Что уже собрано

- `static/apk/trudnik.apk` — подписанный release APK (TWA, `customtabs` fallback).
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

APK подписывается `twa-project/trudnik-release.keystore` (alias `trudnik`);
пароль хранится только в окружении/CI (`KEYSTORE_PASSWORD`), не в git.
Проверка подписи:

```bash
keytool -printcert -jarfile static/apk/trudnik.apk | grep SHA256
```

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

## Страница установки

- `/app` — карточки Android (APK), iPhone/iPad (Safari → «На экран Домой»),
  ПК (Chrome/Edge install), версия/размер/SHA-256.
- `/app/download` — `FileResponse` с `application/vnd.android.package-archive`,
  `Content-Disposition: attachment`, `Cache-Control: public, max-age=3600`.
- Ссылки: футер «Приложение» и профильное меню «Установить приложение».

## Чек-лист релиза

1. `npm run build:css`, `pre_deploy_check`, `manage.py test core`.
2. Собрать APK, проверить `versionCode/versionName`, host и подпись.
3. Обновить `assetlinks.json` при смене ключа.
4. Задеплоить APK/OG/assetlinks, проверить `/app/download` и `/.well-known/assetlinks.json`.
5. Проверить установку на Android: приложение открывает трудник.рф без адресной строки.
6. Google Play не публикуется (по текущему решению); APK — прямая установка.
