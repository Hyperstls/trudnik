# Полное код-ревью приложения Трудник

**Дата:** 2026-06-12
**Версия:** текущая (uncommitted changes)
**Анализ:** Flask 3.1 + Supabase REST API, 11 blueprintов, 3 сервиса, 23 HTML-шаблона, 28 миграций

---

## Сводка

Приложение успешно прошло рефакторинг от standalone-режима (original_app.py) к модульной blueprint-архитектуре. Удалена таблица shifts, чат мигрирован на application_id, модель монетизации переведена на pay-per-job.

Обнаружено 7 критических проблем (включая баг с запросом чатов работодателя), 15 предупреждений и 14 предложений.

**Рекомендация:** NEEDS CHANGES — баг в chat.py:19 требует обязательного исправления перед деплоем.

---

## Сводная таблица проблем

| # | Severity | File:Line | Issue |
|---|----------|-----------|-------|
| 1 | CRITICAL | chat.py:16-20 | Баг: неверный фильтр employer-чатов (AND вместо OR). Employer не видит свои чаты. |
| 2 | CRITICAL | admin.py:35 | statuses.get("paid",0) — статус paid удалён миграцией 027/028. |
| 3 | CRITICAL | jobs.py:776 | Дублирующий локальный импорт notify внутри invite_worker (уже на строке 7). |
| 4 | CRITICAL | jobs.py:861 | Ещё один дублирующий импорт notify внутри respond_invitation. |
| 5 | CRITICAL | __init__.py:93 | log.warning на каждый запрос для всех пользователей. |
| 6 | CRITICAL | receipt_service.py:80-85,108,169-174 | print() вместо logger в продакшн-коде. |
| 7 | CRITICAL | chat.py:19 | Дублирует #1: employer-чаты сломаны. |
| 8 | WARNING | utils.py:161 | Мёртвый код: add_notification() — не вызывается. |
| 9 | WARNING | decorators.py:37 | Мёртвый код: generate_csrf_token(). |
| 10 | WARNING | decorators.py:44 | Мёртвый код: csrf_protect(). |
| 11 | WARNING | config.py:2 | Неиспользуемый импорт warnings. |
| 12 | WARNING | monetization.py:349 | Мёртвый код: _check_hire_limit(). |
| 13 | WARNING | notifications.py:28,41 | Двойной import re. |
| 14 | WARNING | jobs.py:889 | Устаревший комментарий про draft. |
| 15 | WARNING | __init__.py:29-115 | N+1 context processors (3 шт). |
| 16 | WARNING | templates/jobs.html | Мёртвый шаблон. |
| 17 | WARNING | templates/profile_edit.html | Мёртвый шаблон. |
| 18 | WARNING | test_selenium_v2.py:259 | Тесты /shifts. |
| 19 | WARNING | tests/test_selenium_browser.py:398 | Тесты shifts. |
| 20 | WARNING | tests/test_job_lifecycle*.py | Тесты shifts. |
| 21 | WARNING | tests/test_all_functions.py:382 | Тесты shifts. |
| 22 | WARNING | tests/test_job_lifecycle_api.py:153 | API-тесты shifts. |
| 23 | SUGGESTION | blueprints/__init__.py | ratings_bp не экспортирован. |
| 24 | SUGGESTION | jobs.py:100,214 | Дублирование фильтрации по навыкам. |
| 25 | SUGGESTION | admin.py:200 / jobs.py:720 | Дублирование _delete_job_cascade. |
| 26 | SUGGESTION | applications.py:246 | Длинная функция api_handle_application. |
| 27 | SUGGESTION | ratings.py:134 | Ручной UPSERT. |
| 28 | SUGGESTION | jobs.py:435 | Хардкод координат Москвы. |
| 29 | SUGGESTION | .env.example:11 | DEEPSEEK_API_KEY не используется. |
| 30 | SUGGESTION | requirements.txt:5-6,8 | supabase, postgrest, openai не импортируются. |
| 31 | SUGGESTION | jobs.py:507 | _auto_transition с побочным PATCH. |
| 32 | SUGGESTION | utils.py:237 | my_query хрупкий API. |
| 33 | SUGGESTION | applications.py:208 | INNER JOIN на profiles. |
| 34 | SUGGESTION | monetization.py:22 | url_prefix=/api нестандартно. |
| 35 | SUGGESTION | utils.py:135 | Хардкод URL Storage. |
| 36 | SUGGESTION | jobs.py:384 | Длинная функция job_new. |

---

## Файлы для переноса в archive/

### Устаревшие миграции (перекрыты 028)
| Файл | Причина |
|------|---------|
| migrations/FINAL_FIX.sql | Агрегирован в 028 |
| migrations/FINAL_FIX_2.sql | Агрегирован в 028 |
| migrations/FINAL_FIX_3.sql | Агрегирован в 028 |
| migrations/ALL_PENDING.sql | Сборная миграция |

### Дублирующиеся тесты
| Файл | Причина |
|------|---------|
| test_full.py | Дублирует tests/test_all_functions.py |
| test_new_routes.py | Дублирует test_new_routes_v2.py |

### Пустые файлы (0 байт)
| Файл | Причина |
|------|---------|
| Boundary | Пустой файл без расширения |
| RLS | Пустой файл без расширения |
| page_404_test.html | Пустой HTML |

### Скриншоты в корне (13 файлов .png)
| Файл | Размер |
|------|--------|
| 404_error_page.png | 41 KB |
| Admin_dashboard.png | 45 KB |
| Applications_no_paywall.png | 44 KB |
| Create_job_flow.png | 44 KB |
| Employer_access__my-jobs.png | 45 KB |
| Favorites_page.png | 37 KB |
| Invitations_page.png | 44 KB |
| Job_detail_page.png | 44 KB |
| Login_admin.png | 45 KB |
| Login_employer.png | 45 KB |
| Login_worker.png | 49 KB |
| Worker_access__.png | 45 KB |
| Workers_page_+_invite.png | 45 KB |

### Устаревшие .md и отчёты
| Файл | Причина |
|------|---------|
| selenium_test.md | Устаревший план |
| Supabase_warnings.md | Warnings исправлены |
| selenium_report.txt | Устаревший отчёт |
| matrix_jobs.md | План реализован |
| New_logic.md | План рефакторинга выполнен |
| New_logic2.md | План рефакторинга v2 выполнен |

### Всего файлов для archive: 28

---

## Итоговая статистика

| Категория | Количество |
|-----------|------------|
| CRITICAL | 7 |
| WARNING | 15 |
| SUGGESTION | 14 |
| Всего проблем | 36 |
| Файлов для archive/ | 28 |

---

## Рекомендация: NEEDS CHANGES

Обязательно исправить до деплоя:
1. Баг в chat.py:19 — неверный запрос чатов работодателя
2. Устаревший статус paid в admin.py:35
3. Дублирующие локальные импорты в jobs.py:776, 861

Рекомендуется исправить в этом PR:
4. Мёртвый код (add_notification, generate_csrf_token, csrf_protect, _check_hire_limit)
5. Неиспользуемый импорт warnings в config.py
6. print() -> logger в receipt_service.py
7. Устаревший комментарий про draft в jobs.py:889
8. Двойной import re в notifications.py

Можно отложить:
9. Удаление 28 файлов (archive/)
10. N+1 context processors
11. Устаревшие тесты shifts
12. Рефакторинг длинных функций
