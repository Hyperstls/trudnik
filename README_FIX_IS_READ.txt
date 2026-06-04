# Инструкция по исправлению ошибки with is_read

## Ошибка:
```
Error: Failed to run sql query: ERROR: 42703: column "is_read" does not exist
```

## Причина:
Таблица `notifications` уже существует в базе данных Supabase, но без столбца `is_read`.

## Решение:

### Выполнить миграцию add_is_read_column.sql

1. Открыть Supabase Dashboard → SQL Editor
2. Скопировать содержимое файла `migrations/add_is_read_column.sql`
3. Вставить и выполнить

Эта миграция добавит столбец `is_read` в существующую таблицу `notifications`.

## Если возникнут ошибки:

### Проверить существующую таблицу:
```sql
SELECT * FROM notifications LIMIT 5;
```

### Вручную добавить столбец через Table Editor:
1. Перейти в Dashboard → Table Editor
2. Открыть таблицу `notifications`
3. Нажать "Add column"
4. Назвать `is_read`, тип `Boolean`, Default `false`
5. Сохранить

### Проверить добавление:
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'notifications' AND column_name = 'is_read';
```
