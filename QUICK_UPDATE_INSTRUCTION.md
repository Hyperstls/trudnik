# БЫСТРОЕ ОБНОВЛЕНИЕ app.py НА PYTHONANYWHERE

**Дата:** 2026-06-03  
**Статус:** Локальный файл обновлён ✅

---

## 🚀 5-МИНУТНОЕ ОБНОВЛЕНИЕ (Через веб-интерфейс)

### ШАГ 1: Скопировать обновлённый файл (5 сек)

1. Открыть локальный файл:
   ```
   C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py
   ```

2. **Выделить весь код** (Ctrl+A)

3. **Скопировать** (Ctrl+C)

---

### ШАГ 2: Загрузить на PythonAnywhere (2 минуты)

1. **Открыть PythonAnywhere:**
   ```
   https://www.pythonanywhere.com/
   ```

2. **Войти:** `hyperstls`

3. **Вкладка: Files**
   - Путь: `/home/hyperstls/app.py`
   - Нажать: **Edit**

4. **Вставить обновлённый код:**
   - Нажать: **Select All** (или Ctrl+A)
   - Нажать: **Delete** (или Delete)
   - **Вставить** (Ctrl+V)

5. **Сохранить:**
   - Нажать: **Save**
   - Дождаться сообщения "File saved"

---

### ШАГ 3: Перезапустить приложение (1 минута)

1. **Вкладка: Web**
   - Нажать кнопку: **Reload**
   - Дождаться перезапуска

2. **ИЛИ через консоль (альтернатива):**
   ```bash
   cd /home/hyperstls
   source .venv/bin/activate
   touch app.py.wsgi
   ```

---

### ШАГ 4: Проверить (30 сек)

1. **Открыть приложение:**
   ```
   https://hyperstls.pythonanywhere.com
   ```

2. **Протестировать создание задания:**
   - Войти: `test_employer_final@test.com`
   - Перейти: `/create-job`
   - Заполнить форму
   - Отправить

3. **Проверить логи (если ошибка):**
   ```
   https://www.pythonanywhere.com/domains/logs/
   ```

---

## 🔍 ПРОВЕРКА РЕЗУЛЬТАТА

### Что должно работать после обновления:

- ✅ Форма `/create-job` не возвращает 500 ошибку
- ✅ Задания создаются и сохраняются в базу
- ✅ Перенаправление на `/my-jobs` работает
- ✅ В логах нет ошибок

### Если ошибка 500 осталась:

1. **Проверить логи PythonAnywhere:**
   ```
   https://www.pythonanywhere.com/domains/logs/
   ```

2. **Проверить Supabase API ключи:**
   - Убедиться, что `SUPABASE_ANON_KEY` имеет права на INSERT
   - Проверить RLS policies для таблицы `jobs`

3. **Добавить DEBUG режим:**
   ```python
   app.config['DEBUG'] = True
   ```

---

## 📊 СВОЙСТВА ОБНОВЛЁННОГО КОДА

### Изменения в `app.py`:

1. **Добавлен импорт traceback:**
   ```python
   import traceback
   ```

2. **Улучшенная функция `supabase_request()`:**
   ```python
   def supabase_request(method, endpoint, **kwargs):
       try:
           resp = _make_request()
           # ...
           return resp
       except requests.RequestException as e:
           app.logger.error(f"Supabase request error: {e}")
           return type('obj', (object,), {'ok': False, ...})()
   ```

3. **Обновлён маршрут `/create-job`:**
   ```python
   @app.route('/create-job', methods=['GET', 'POST'])
   def create_job():
       if request.method == 'POST':
           try:
               job_data = {...}
               app.logger.info(f"Creating job: {job_data}")
               resp = supabase_request('POST', 'jobs', json=job_data)
               app.logger.info(f"Supabase response: {resp.status_code}")
               if resp.ok:
                   flash('Задание опубликовано', 'success')
                   return redirect(url_for('my_jobs'))
               else:
                   flash(f'Ошибка: {resp.text}', 'danger')
           except Exception as e:
               error_details = traceback.format_exc()
               app.logger.error(f"Error creating job: {error_details}")
               flash(f'Ошибка сервера: {str(e)}', 'danger')
   ```

---

## 🛠️ ДЕБАГГИНГ (если нужно)

### Добавить тестовый маршрут:
```python
@app.route('/debug-create-job', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def debug_create_job():
    if request.method == 'POST':
        try:
            job_data = {
                'employer_id': session['user_id'],
                'organization_name': request.form.get('organization_name') or 'Test',
                'payment_amount': float(request.form.get('payment', 100)),
                'date_time': f"{request.form['date']}T{request.form['time']}:00",
                'city': request.form.get('city', 'Moscow'),
                'lat': float(request.form.get('lat', 55.75)),
                'lng': float(request.form.get('lng', 37.61)),
            }
            
            app.logger.info(f"DEBUG: Creating job with data: {job_data}")
            
            resp = supabase_request('POST', 'jobs', json=job_data)
            
            app.logger.info(f"DEBUG: Response status: {resp.status_code}")
            app.logger.info(f"DEBUG: Response text: {resp.text[:300]}")
            
            if resp.ok:
                return "✅ Job created successfully!"
            else:
                return f"❌ Error: {resp.text}", 400
        except Exception as e:
            app.logger.error(f"DEBUG: Error: {traceback.format_exc()}")
            return f"❌ Exception: {str(e)}", 500
    return """
    <form method="post">
        <input name="organization_name" placeholder="Название" required><br>
        <input name="date" type="date" required><br>
        <input name="time" type="time" required><br>
        <input name="payment" type="number" value="100" required><br>
        <input name="city" placeholder="Город" required><br>
        <button type="submit">Create</button>
    </form>
    """
```

---

## 📞 КОНТАКТЫ

- **PythonAnywhere Console:** https://www.pythonanywhere.com/consoles/
- **Error Logs:** https://www.pythonanywhere.com/domains/logs/
- **Web Configuration:** https://www.pythonanywhere.com/webapps/

---

**Готово! Обновление заняло ~5 минут.**
