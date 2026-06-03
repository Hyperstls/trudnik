# ИНСТРУКЦИЯ ПО ОБНОВЛЕНИЮ ЧЕРЕЗ GIT

**Дата:** 2026-06-03  
**Статус:** Изменения закоммичены и отправлены на GitHub ✅

---

## 🚀 БЫСТРАЯ ЗАГРУЗКА ЧЕРЕЗ GIT (3 минуты)

### На PythonAnywhere (в Bash Console):

1. **Открыть Bash Console** на PythonAnywhere:
   - https://www.pythonanywhere.com/consoles/

2. **Выполнить команды:**
   ```bash
   cd /home/hyperstls/trudnik
   git pull origin main
   cp app.py app.py.backup.20260603
   touch app.py.wsgi
   ```

3. **Проверить статус:**
   ```bash
   curl -s https://hyperstls.pythonanywhere.com | head -5
   ```

---

## ✅ ПРОВЕРКА РАБОТЫ

После загрузки:

1. **Открыть:** https://hyperstls.pythonanywhere.com/
2. **Войти как:** `test_employer_final@test.com`
3. **Перейти:** `/create-job`
4. **Заполнить форму и отправить**

### Ожидаемый результат:

- ✅ Сообщение: "Задание опубликовано"
- ✅ Перенаправление на `/my-jobs`
- ❌ НЕ должно быть ошибки 500

---

## 📊 ЧТО ИЗМЕНИЛОСЬ

- ✅ Добавлен `import traceback`
- ✅ Улучшена функция `supabase_request()` с try/except
- ✅ Обновлён маршрут `/create-job` с логированием

---

## 📞 КОНТАКТЫ

**PythonAnywhere:**
- https://www.pythonanywhere.com/consoles/
- https://www.pythonanywhere.com/domains/logs/

**GitHub:**
- https://github.com/Hyperstls/trudnik

---

**Готово к обновлению! 🚀**
