# План реализации FINAL_NEW_UXUI.md

## Текущий статус
Редизайн уже применён коммитом `29693cb`. Мои исправления: `b0cd936` (floating-label, search, JSON parsing) и `c22b32c` (bottom nav).

## План действий

### 1. Проверить пустые состояния (Empty States) на всех страницах
- [ ] `templates/favorites.html` — ✅ есть (строка 83-91)
- [ ] `templates/blacklist.html` — ? 
- [ ] `templates/notifications.html` — ✅ есть
- [ ] `templates/my_jobs.html` — ✅ есть
- [ ] `templates/my_applications.html` — ? 
- [ ] `templates/shifts.html` — ✅ есть
- [ ] `templates/workers.html` — ✅ есть
- [ ] `templates/chats_list.html` — ? 
- [ ] `templates/jobs.html` — ? 
- [ ] `templates/error.html` — ? (отмечено в ревью как минимальные изменения)

### 2. Проверить адаптивность на всех страницах
- [ ] Проверить отсутствие `md:hidden` на ключевых элементах
- [ ] Проверить grid-сетки (1 колонка mobile, 2-3 desktop)
- [ ] Проверить safe-area-inset-bottom

### 3. Проверить A11y
- [ ] ARIA-атрибуты на модальных окнах
- [ ] focus-visible:ring-2 на всех интерактивных элементах
- [ ] Контраст 4.5:1

### 4. Проверить JS-совместимость
- [ ] Селекторы favorites.js сохранены
- [ ] Селекторы applications.js сохранены
- [ ] showToast глобально доступен

### 5. Комплексное тестирование
- [ ] 106 unit-тестов проходят
- [ ] Browser test for login
- [ ] Ручная проверка форм (валидация, отправка, ошибки)
- [ ] Проверка навигации (десктоп + мобильная)
- [ ] Проверка обработки ошибок (404, 500)
- [ ] Проверка API-запросов

### 6. Фиксация
- [ ] Коммит с осмысленным сообщением
- [ ] Пуш в ветку redesign-uxui
