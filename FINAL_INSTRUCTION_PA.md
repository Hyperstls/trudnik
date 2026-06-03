# ИТОГОВАЯ ИНСТРУКЦИЯ ПО ЗАГРУЗКЕ

**Дата:** 2026-06-03  
**Статус:** Локальный файл готов, осталось загрузить на PythonAnywhere

---

## 🚀 САМЫЙ ПРОСТОЙ СПОСОБ (5 минут)

### Через веб-интерфейс PythonAnywhere:

1. **Открыть:** https://www.pythonanywhere.com/
2. **Войти как:** `Hyperstls`
3. **Вкладка:** `Files`
4. **Путь:** `/home/hyperstls/app.py`
5. **Нажать:** `Edit`
6. **Выделить весь код** (`Ctrl+A`)
7. **Удалить** (`Delete`)
8. **Вставить обновлённый код** (`Ctrl+V`)
9. **Нажать:** `Save`
10. **Вкладка:** `Web` → нажать: `Reload`

---

## ✅ ПРОВЕРКА РАБОТЫ

После загрузки и перезапуска:

1. **Открыть:** https://hyperstls.pythonanywhere.com/
2. **Войти как:** `test_employer_final@test.com`
3. **Перейти:** `/create-job`
4. **Заполнить форму и отправить**

### Ожидаемый результат:

- ✅ Сообщение: "Задание опубликовано"
- ✅ Перенаправление на `/my-jobs`
- ❌ НЕ должно быть ошибки 500

---

## 📊 ЛОГИ ПОСЛЕ ЗАГРУЗКИ

После обновления в логах PythonAnywhere (Web → Error log) должны появиться записи:

```
INFO: Creating job: {...}
INFO: Supabase response: 201 - {...}
```

---

## 📁 ЧТО ИЗМЕНИЛОСЬ В app.py

### 1. Добавлен импорт traceback
```python
import traceback
```

### 2. Улучшена функция `supabase_request()`
- Добавлен try/except для обработки исключений
- Логирование ошибок для диагностики
- Безопасный возврат при ошибках

### 3. Обновлён маршрут `/create-job`
- try/except обработка всех ошибок
- Логирование данных для диагностики
- Улучшенные сообщения об ошибках

---

## 🔧 ПРОБЛЕМЫ

Если ошибка 500 осталась после загрузки:

1. **Проверить логи:**
   - https://www.pythonanywhere.com/domains/logs/
   - Искать записи за текущую дату

2. **Проверить Supabase API ключи:**
   - `SUPABASE_ANON_KEY` имеет права на INSERT?
   - RLS policies для таблицы `jobs`

3. **Проверить debug режим:**
   - Добавить в `app.py`: `app.config['DEBUG'] = True`

---

## 📞 КОНТАКТЫ

**PythonAnywhere:**
- https://www.pythonanywhere.com/
- https://www.pythonanywhere.com/domains/logs/

**Supabase:**
- https://supabase.com/dashboard
- Project: ***REMOVED***

---

**Готов к обновлению! 🎉**
