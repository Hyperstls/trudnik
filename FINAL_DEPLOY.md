# Финальная инструкция по деплою

## Проблемы

1. Кнопка "В избранное" на странице `/workers` вызывала переход в профиль вместо добавления в избранное
2. На странице `/favorites` трудник не появлялся после добавления

## Решения

### 1. Исправление workers.html

**До:**
```html
<div class="worker-card" onclick="window.location.href='/profile/{{ worker.id }}'">
    ...
    <button onclick="toggleFavorite(this, '{{ worker.id }}')">
```

**После:**
```html
<div class="worker-card" 
     onclick="event.stopPropagation(); window.location.href='/profile/{{ worker.id }}'">
    ...
    <button onclick="toggleFavorite(event, this, '{{ worker.id }}')">
```

**Изменения:**
- `onclick` на карточке теперь вызывает `event.stopPropagation()` ДО перехода
- `toggleFavorite` теперь получает `event` как первый параметр
- В функции добавлены `e.stopPropagation()` и `e.preventDefault()`

### 2. Исправление profile_worker.html

Файл использовал функцию `addToFavorites`, которая только добавляла и не проверяла статус.

**Добавлено:**
- Проверка статуса избранного при загрузке страницы
- Показ правильной кнопки (⭐ или ❤️)
- Правильный текст кнопки

## Инструкция по деплою

### 1. Git - уже выполнено
```bash
git add templates/workers.html
git commit --file=.git_commit_msg
git push
```

### 2. PythonAnywhere

В консоли PythonAnywhere:
```bash
cd ~/mysite
git pull
touch /var/www/hyperstls_pythonanywhere_com_wsgi.py
```

### 3. Supabase

Применить RLS политики из `migrations/apply_rls_policies.sql`

## Проверка

1. Открыть `/workers`
2. Кликнуть на кнопку "В избранное"
3. Проверить консоль (F12) на наличие:
   ```
   toggleFavorite called for workerId: ...
   After stopPropagation - should not navigate
   Add response: {success: true, ...}
   Successfully added to favorites
   ```
4. Проверить, что НЕ произошел переход в профиль
5. Кнопка должна стать красной с ❤️

## Дополнительно

### Если трудник не появляется в избранном:

1. Проверить консоль браузера на ошибки
2. Проверить, что API возвращает `success: true`
3. Проверить, что вызывается `/api/favorites/add` а не `/api/favorites/check`
4. Обновить страницу `/favorites` и проверить

### Если кнопка всё ещё вызывает переход:

1. Проверить, что `e.stopPropagation()` вызывается в функции `toggleFavorite`
2. Проверить, что `onclick` на карточке вызывает `event.stopPropagation()` ДО `window.location.href`

## Статус

✅ Готово к деплою
✅ Изменения отправлены на GitHub
