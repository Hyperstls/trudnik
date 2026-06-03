# ИНСТРУКЦИЯ ПО ОБНОВЛЕНИЮ FLASK-ПРИЛОЖЕНИЯ НА PYTHONANYWHERE

## Дата: 2026-06-03

---

## 📋 ПРОВЕРКА ФАЙЛА LOCAL

✅ **Файл app.py локально обновлён:**
- Добавлен `import traceback` для обработки ошибок
- Улучшена функция `supabase_request()` с обработкой исключений
- Обновлён маршрут `/create-job` сtry/except и логированием

---

## 🔧 СПОСОБЫ ОБНОВЛЕНИЯ НА PYTHONANYWHERE

### СПОСОБ 1: Через PythonAnywhere Web Console (РЕКОМЕНДУЕТСЯ)

1. **Перейти на PythonAnywhere:**
   ```
   https://www.pythonanywhere.com/
   ```

2. **Войти в аккаунт:** `hyperstls`

3. **Открыть Console (вкладка):**
   - Выбрать: `Bash` console
   - Или создать новый console

4. **Скопировать файл через веб-редактор:**
   - Перейти во вкладку `Files`
   - Открыть `/home/hyperstls/app.py`
   - Скопировать содержимое (на всякий случай)
   - Вставить обновлённую версию

5. **ИЛИ через paste в console:**
   ```bash
   cd /home/hyperstls
   cp app.py app.py.backup.20260603
   # Затем редактировать через nano или vim
   ```

### СПОСОБ 2: Через Web Files Editor

1. **Войти на PythonAnywhere**
2. **Вкладка: Files**
3. **Путь:** `/home/hyperstls/app.py`
4. **Нажать: Edit**
5. **Заменить содержимое на обновлённую версию**
6. **Нажать: Save**

### СПОСОБ 3: Через Web Console + curl

Если у вас есть доступ к локальному файлу:

```bash
# На PythonAnywhere console:
cd /home/hyperstls

# Скачать обновлённый файл (если он доступен по URL)
curl -o app.py https://ваш-сайт.com/app.py

# ИЛИ вставить через heredoc:
cat > app.py << 'EOF'
# Вставить содержимое app.py здесь
EOF
```

---

## 🔁 ПЕРЕЗАПУСК ПРИЛОЖЕНИЯ

После обновления файла:

### Вариант 1: Через веб-интерфейс
1. Перейти во вкладку **Web**
2. Нажать кнопку **Reload** (перезапуск)
   - Адрес: `https://www.pythonanywhere.com/user/hyperstls/webapps/hyperstls_pythonanywhere_com`

### Вариант 2: Через консоль
```bash
cd /home/hyperstls
source .venv/bin/activate
# Если используется Flask через WSGI
touch app.py.wsgi
# ИЛИ перезапустить весь веб-сервер
# Перейти в Web и нажать Reload
```

---

## ✅ ПРОВЕРКА ОБНОВЛЕНИЯ

После перезапуска:

1. **Открыть приложение в браузере:**
   ```
   https://hyperstls.pythonanywhere.com
   ```

2. **Протестировать создание задания:**
   - Войти как `test_employer_final@test.com`
   - Перейти в `/create-job`
   - Заполнить форму и отправить

3. **Проверить логи:**
   - Вкладка Web → Error log
   - Искать записи за текущую дату
   - Если ошибок нет - всё работает!

---

## 🐛 ДЕБАГГИНГ

Если ошибка 500 сохраняется:

### 1. Включить DEBUG режим:
```python
# В app.py добавить:
app.config['DEBUG'] = True
app.config['TESTING'] = True
```

### 2. Проверить логи PythonAnywhere:
```
https://www.pythonanywhere.com/domains/logs/
```

### 3. Проверить Supabase connection:
```python
# Добавить тестовый маршрут:
@app.route('/test-supabase')
def test_supabase():
    try:
        resp = supabase_request('GET', 'jobs?limit=1')
        return f"Status: {resp.status_code}, Text: {resp.text}"
    except Exception as e:
        return f"Error: {e}"
```

### 4. Проверить права доступа:
- Убедиться, что `SUPABASE_ANON_KEY` имеет права на INSERT в `jobs`
- Проверить RLS policies для таблицы `jobs`

---

## 📝 ЧЕК-ЛИСТ

- [ ] Файл `app.py` обновлён на PythonAnywhere
- [ ] Приложение перезапущено (Reload)
- [ ] Создание задания работает без ошибок 500
- [ ] Логи PythonAnywhere чисты
- [ ] Форма `/create-job` отправляется успешно
- [ ] Задания появляются в `/my-jobs`

---

## 📞 КОНТАКТЫ

Если проблема не решена:

1. **Проверить логи PythonAnywhere:**
   - https://www.pythonanywhere.com/domains/logs/

2. **Проверить Supabase Dashboard:**
   - https://supabase.com/dashboard
   - Таблица: `jobs`
   - RLS policies

3. **Протестировать API напрямую:**
   ```bash
   curl -X POST https://***REMOVED***.supabase.co/rest/v1/jobs \
     -H "apikey: ваш-anon-key" \
     -H "Authorization: Bearer ваш-anon-key" \
     -H "Content-Type: application/json" \
     -d '{"employer_id": "test", "organization_name": "Test"}'
   ```

---

**Обновление выполнено 2026-06-03**
