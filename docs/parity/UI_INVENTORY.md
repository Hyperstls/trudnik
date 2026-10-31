# UI inventory — кликабельные элементы (auth / registration / profile)

Сверка шаблонов Flask (`templates/*.html`) и Django (`djadmin/core/templates/core/*.html`).
Статусы: ✅ есть и работает по коду; ⚠️ есть, но поведение/набор отличается; ❌ отсутствует.

## Login

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Email | `login.html:23` | `core/login.html:30` | ✅ |
| Пароль | `login.html:35` | `core/login.html:36` | ✅ |
| Показать/скрыть пароль | `login.html:36` | `core/login.html:37` | ✅ |
| Войти | `login.html:19` | `core/login.html:44` | ✅ |
| Забыли пароль? | `login.html:60` | `core/login.html:48` | ✅ |
| Не пришло письмо? | `login.html:64` | `core/login.html:50` | ✅ |
| Зарегистрироваться | `login.html:71` | `core/login.html:55` | ✅ |
| Сообщение о блокировке/неподтверждённом email | flash | общий `messages` | ⚠️ Django не различает причины, lockout → 403 |

## Register

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| ФИО | `register.html:38` | `core/register.html:20` | ✅ |
| Email | `register.html:50` | `core/register.html:25` | ✅ |
| Пароль | `register.html:62` | `core/register.html:30` | ✅ |
| Intent (3 карточки) | `register.html:83-104` | `core/register.html:39-50` | ✅ |
| Город | `register.html:127` | `core/register.html:61` | ✅ |
| Портфолио | `register.html:133` | — | ❌ P1-01 |
| Контакт | `register.html:137` | — | ❌ P1-01 |
| ИНН | `register.html:148` | — | ❌ P1-01 |
| Самозанятый | `register.html:154` | — | ❌ P1-01 |
| Опыт | `register.html:160` | — | ❌ P1-01 |
| Желаемая оплата | `register.html:165` | — | ❌ P1-01 |
| Навыки | `register.html:392` (JS) | — | ❌ P1-01 |
| Согласие 152-ФЗ | `register.html:171` | `core/register.html:65` | ✅ |
| Honeypot | `register.html:31` | `core/register.html:69` | ⚠️ Django показывает ошибку |
| SmartCaptcha | `register.html:175-186` | `core/register.html:72-75` | ❌ P0-01 (поле `smart_token` vs `smart-token`) |
| Зарегистрироваться | `register.html` submit | `core/register.html:77` | ✅ |
| Войти | `register.html` | `core/register.html:82` | ✅ |

## Password reset request / confirm

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Email | `password_reset_request.html` | `core/password_reset_request.html:16` | ✅ |
| SmartCaptcha | `password_reset_request.html:46-53` | `core/password_reset_request.html:19-21` | ❌ P0-01 |
| Отправить ссылку | там же | `core/password_reset_request.html:23` | ✅ |
| Новый пароль | `password_reset_confirm.html` | `core/password_reset_confirm.html:17` | ✅ |
| Повтор пароля | там же | там же | ✅ |
| Сменить пароль | там же | `core/password_reset_confirm.html:24` | ✅ |

## Profile (own)

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Фото/аватар | `profile.html:64-66,86` | `core/profile.html:74-78` | ⚠️ Django только загрузка, нет удаления |
| ФИО | `profile.html:90` | `core/profile.html:46-54` (form) | ✅ |
| Телефон | `profile.html:96` | form field | ✅ |
| О себе | `profile.html:102` | form field | ✅ |
| Город | `profile.html:107` | form field | ✅ |
| Видимость в каталоге | `profile.html:119` | form field `worker_visibility` | ✅ |
| Портфолио | `profile.html:134` | form field | ✅ |
| Опыт | `profile.html:141` | form field | ✅ |
| Желаемая оплата | `profile.html:146` | form field | ✅ |
| Контакт | `profile.html:153` | form field | ⚠️ нет валидации |
| ИНН/самозанятость | нет в шаблоне Flask | form fields | ⚠️ Django добавил, но без checksum |
| Вероисповедание | удалено Flask | form field `religion` | ❌ P0-04 (152-ФЗ) |
| Навыки | `profile.html` | `core/profile.html:57-65` | ✅ |
| Сменить пароль | `profile.html:176-191` | `core/profile.html:107-120` | ⚠️ нет инвалидации сессий |
| Выйти | `profile.html:231-234` | — | ❌ P2-02 |
| Удалить аккаунт | `profile.html:237-241,292-304` | `core/profile.html:89-92` | ⚠️ Django `confirm()` вместо модалки |
| Скачать данные | `profile.html:241` | `core/profile.html:85` | ✅ |
| Настройки уведомлений | (в навигации) | `core/profile.html:86` | ✅/⚠️ |
| Верификация | `profile.html:163` | `core/profile.html:87,99-101` | ⚠️ |
| MAX-верификация (кнопки) | `profile.html:205-218` | ссылка на messenger | ⚠️ |
| Чат/избранное (на чужом профиле) | `profile.html:317-322` | — (на `/workers/<id>`) | ⚠️ |

## Public profile

| Элемент | Flask (`profile_worker.html`) | Django (`core/worker_detail.html`) | Статус |
|---|---|---|---|
| Фото | `:29` | `:13` | ✅ |
| Имя/verified | `:44-48` | `:20-23` | ✅ |
| Рейтинг/отзывы | `:54-57` | `:24-28` | ✅ |
| Ссылка «Все отзывы» | `:57` | — | ❌ P2-03 |
| Счётчик выполненных | `:61-63` | — | ❌ P2-03 |
| Бейдж «Надёжный» | `:48` | — | ❌ P2-03 |
| Чат | `:69-71,221-223` | — | ❌ P2-03 |
| Избранное | `:75-77` | `:66-68` | ✅ |
| Блокировка | `:81-82` | `:69-71` | ✅ |
| Жалоба | `:92-108` | `:72-75` | ✅/⚠️ (inline вместо модалки) |
| Bio/опыт/оплата | `:125-174` | `:33-44` | ✅ |
| Контакты | `:176-179` (фактически не выбраны в Flask) | `:46-47` (реально отдаёт `contact`) | ❌ P0-03 |
| Портфолио | `:203-212` | — | ⚠️ (проверить, есть ли в Django) |
| Навыки | `:191-193` | `:37-41` | ✅ |
| Приглашение | — | `:55-63` | ✅ |

## Verify employer / notification settings

| Элемент | Flask | Django | Статус |
|---|---|---|---|
| Файл документа | `verify_employer.html:42` (PDF/JPG/PNG) | `core/verify_employer.html:12` (JPEG/PNG/WebP) | ❌ P1-07 |
| JS-валидация размера/формата | `verify_employer.html:71+` | — | ⚠️ P2-15 |
| Отправить на проверку | `verify_employer.html:61` | `core/verify_employer.html:14` | ✅ |
| Настройки: чекбоксы | `notification_settings.html` (JS/AJAX) | `core/notification_settings.html:17,26` | ⚠️ API POST не обновляет |
| Сохранить настройки | `notification_settings.html:21` | `core/notification_settings.html:31` | ✅ |
