# Инструкция по деплою системы избранного

## Проблема

Кнопка "В избранное" на странице трудников не реагирует на клик.

## Причина

Функция `toggleFavorite` была объявлена внутри блока `DOMContentLoaded`, что делала её недоступной для вызова из HTML.

## Решение

Сделана функция `toggleFavorite` глобальной, чтобы она была доступна для вызова из HTML.

## Выполненные изменения

1. **templates/workers.html:**
   - Сделана функция `toggleFavorite` глобальной
   - Изменен вызов: `toggleFavorite(event, this, workerId)`
   - Добавлено `e.stopPropagation()` в начале функции
   - Добавлено alert при успехе добавления в избранное

2. **templates/favorites.html:**
   - Обновлена логика удаления трудника
   - Добавлена проверка статуса избранного перед удалением
   - Добавлено отображение полных данных (город, навыки, оплата)

3. **migrations/setup_rls.sql:**
   - Добавлены RLS политики для favorites, blacklists, profiles

## Инструкция по деплою

### 1. Git - уже выполнено
```bash
git add .
git commit -m "fix: оптимизация кнопки избранного..."
git push
```

### 2. PythonAnywhere - обновить сервер

В консоли PythonAnywhere выполнить:
```bash
cd ~/mysite
git pull
touch /var/www/hyperstls_pythonanywhere_com_wsgi.py
```

### 3. Supabase - применить RLS политики

1. Открыть https://***REMOVED***.supabase.co
2. Перейти в SQL Editor
3. Скопировать содержимое `migrations/apply_rls_policies.sql`
4. Выполнить SQL запрос

## Проверка после деплоя

1. Открыть https://hyperstls.pythonanywhere.com/workers
2. Найти трудника
3. Кликнуть на кнопку "В избранное"
4. Проверить:
   - Кнопка стала красной с ❤️
   - Текст "Удалить из избранного"
   - Не происходит переход в профиль
5. Кликнуть повторно
6. Проверить:
   - Кнопка стала желтой с ⭐
   - Текст "В избранное"

## Консоль браузера (F12)

При клике на кнопку должны появиться сообщения:
```
toggleFavorite called for workerId: <uuid>
Current status (from data): not-favorited isFavorited: False
Add response: {...}
Successfully added to favorites
```
