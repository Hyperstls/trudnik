# Routes matrix — auth / registration / profile

**Flask:** `origin/main-flask` @ `9b3ed42`; **Django:** `main` @ `3f4aa40`.
Статусы: ✅ паритет; ⚠️ частично; ❌ отсутствует/сломано/изменено.

| Flask | Flask handler | Django | Django handler | Статус | Комментарий |
|---|---|---|---|---|---|
| `GET/POST /login` | `auth.login` (`auth.py:63`) | `GET/POST /login` | `views_flow.login_view` (`urls.py:76`) | ⚠️ | Нет per-IP rate-limit; lockout in-process; `PermissionDenied` → 403; нет сообщения «подтвердите email»; редирект всем на `/`. |
| `GET/POST /register` | `auth.register` (`auth.py:147`) | `GET/POST /register` | `views_auth.register` (`urls.py:78`) | ⚠️ | Упрощённая форма; потеряны ИНН/самозанятость/контакт/портфолио/опыт/оплата/навыки; капча по имени поля не работает. |
| `POST /logout` | `auth.logout` (`auth.py:375`) | `POST /logout` | `views_flow.logout_view` (`urls.py:77`) | ⚠️ | Django не ставит `Cache-Control: no-store`; нет jti-blacklist (сессия Django). |
| `GET/POST /password-reset/request` | `auth.password_reset_request` (`auth.py:486`) | same | `views_auth.password_reset_request` (`urls.py:81`) | ⚠️ | Капча (P0-01), cooldown in-process, синхронная почта. |
| `GET/POST /password-reset/confirm/<token>` | `auth.password_reset_confirm` (`auth.py:551`) | same | `views_auth.password_reset_confirm` (`urls.py:82`) | ✅/⚠️ | RPC `change_password(text,text)` есть, `password_changed_at` двигается; остаточный риск формата `isoformat()` vs токен — нужен runtime-тест. |
| `GET /verify-email/<token>` | `auth.verify_email` (`auth.py:626`) | same | `views_auth.verify_email` (`urls.py:80`) | ⚠️ | Невалидный токен: Django → resend, Flask → register. |
| `GET/POST /verify-email/resend` | `auth.resend_verification` (`auth.py:642`) | same | `views_auth.verify_email_resend` (`urls.py:79`) | ⚠️ | Django шлёт письмо уже подтверждённым; cooldown in-process. |
| `GET /profile` | `profile.profile` (`profile.py:59`) | `GET /profile` | `views_profile.profile_edit` (`urls.py:33`) | ⚠️ | Django-форма содержит `religion`; нет удаления фото/логаута; UI упрощён. |
| `POST /profile/update` | `profile.update_profile` (`profile.py:92`) | `POST /profile` (`action=profile`) | same | ⚠️ | Маршрут слит; поля профиля есть, но валидация ИНН/контакта отсутствует. |
| `POST /profile/delete-photo` | `profile.delete_photo` (`profile.py:205`) | — | — | ❌ | Нет маршрута и кнопки. |
| `POST /profile/delete-account` | `profile.delete_account` (`profile.py:236`) | same | `views_profile_ext.delete_account` (`urls.py:46`) | ✅/⚠️ | RPC + logout; файлы на диске не удаляются (P1-14). |
| `GET /profile/export-data` | `profile.export_data` (`profile.py:275`) | same | `views_profile_ext.export_data` (`urls.py:45`) | ✅ | Django исключает `password` (улучшение). |
| `POST /profile/change-password` | `profile.change_password` (`profile.py:336`) | `POST /profile` (`action=password`) | same | ⚠️ | Нет ротации сессии/инвалидации других сессий; нет rate-limit. |
| `GET/POST /verify-employer` | `profile.verify_employer` (`profile.py:400`) | `GET /verify-employer` + `POST /profile/verification-doc` | `views_profile_ext.verify_employer` / `upload_verification_doc` (`urls.py:49-50`) | ⚠️ | Нет PDF; упрощённый шаблон; доступ к файлам (P0-02). |
| `GET /profile/<uuid>` | `profile.public_profile` (`profile.py:439`) | `GET /workers/<uuid>` | `views.worker_detail` (`urls.py:26`) | ❌/⚠️ | URL изменён, редиректа нет; публичный `contact` (P0-03). |
| `POST /profile/<uuid>/report` | `profile.report_user` (`profile.py:469`) | `POST /profile/<uuid>/report` | `views_profile_ext.report_user` (`urls.py:47`) | ✅/⚠️ | `call_rpc_as_user` — корректно; Django всегда redirect (Flask AJAX → JSON). |
| `GET /notifications/settings` | `notifications.settings` (`notifications.py:151`) | same | `views_profile_ext.notification_prefs` (`urls.py:51`) | ⚠️ | Flask — динамический JS/AJAX; Django — статичные чекбоксы. |
| `GET/POST /api/notifications/preferences` | `notifications.*` (`notifications.py:160,182`) | `GET /api/notifications/preferences` | `views_profile_ext.notification_prefs_api` (`urls.py:52`) | ⚠️ | Django API POST не обновляет prefs (только возвращает текущие). |
| `GET /uploads/avatars/<file>` | `core.uploaded_avatar` (`core.py:228`) | `GET /uploads/<path>` | `views_profile_ext.serve_upload` (`urls.py:53`) | ✅ | Публично, cache 86400. |
| `GET /uploads/verification-docs/<file>` | `core.uploaded_verification_doc` (`core.py:246`) | `GET /uploads/verification-docs/<path>` | same | ❌ | Flask: owner/admin; Django: любой авторизованный (P0-02). |
| `GET /uploads/jobs/<file>` | `core.uploaded_job_photo` (`core.py:238`) | `GET /uploads/jobs/<path>` | same | ✅ | Публично. |

## Сводка

- Полный паритет: reset confirm (с оговоркой), export, delete account (с оговоркой по файлам),
  report, avatars/jobs uploads.
- Частично: login, register, logout, reset request, resend, profile edit, change password,
  verify employer, public profile, notifications.
- Отсутствует/сломано: delete photo, verification-doc ACL, captcha field, public contact PII.
