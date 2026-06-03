# Читаем файл и удаляем дубликаты
with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим строки с дубликатом
dup_line = 969 - 1  # Строка 969 (0-indexed)

# Оставляем только первые 968 строк
with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines[:dup_line])

print(f"Удалено строк: {len(lines) - dup_line}")
