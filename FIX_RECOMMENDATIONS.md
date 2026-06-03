# РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ ОШИБКИ 500 ПРИ СОЗДАНИИ ЗАДАНИЯ

## 🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА

**Симптом:** При отправке формы `/create-job` сервер PythonAnywhere возвращает **500 Internal Server Error**

**Рабочее окружение:** Supabase API работает напрямую (201 Created)

---

## 🔧 ШАГ 1: Проверка Логов PythonAnywhere

### Что делать:
1. Перейти на https://www.pythonanywhere.com/
2. Войти в аккаунт Hyperstls
3. Перейти в **Web →hyperstls.pythonanywhere.com**
4. Нажать **Error log** или **Access log**
5. Найти записи за текущую дату с ошибкой 500

### Что искать:
```
[Sun Jun 03 19:30:14.416+00:00] [error] [client ...] 
Internal Server Error: /create-job
Traceback (most recent call last):
  ...
```

### Если логи недоступны:
Добавить обработку ошибок в Flask для получения подробной информации:

```python
# В app.py в функцию create_job добавить:
import traceback

@app.route('/create-job', methods=['GET', 'POST'])
@login_required
@role_required('employer')
def create_job():
    if request.method == 'POST':
        try:
            job_data = {
                'employer_id': session['user_id'],
                'organization_name': request.form.get('organization_name') or 'Храм',
                'org_description': request.form.get('org_description', ''),
                'object_description': request.form.get('object_description', ''),
                'work_type': request.form.get('work_type', ''),
                'detailed_description': request.form.get('detailed_description', ''),
                'date_time': f"{request.form['date']}T{request.form['time']}:00",
                'payment_amount': float(request.form['payment']),
                'address': request.form.get('address', ''),
                'city': request.form.get('city', ''),
                'lat': float(request.form.get('lat', 55.75)),
                'lng': float(request.form.get('lng', 37.61)),
                'preferred_religion': request.form.get('preferred_religion', 'не важно'),
            }
            
            # Логирование данных
            app.logger.info(f"Creating job: {job_data}")
            
            resp = supabase_request('POST', 'jobs', json=job_data)
            
            # Логирование ответа
            app.logger.info(f"Supabase response: {resp.status_code} - {resp.text}")
            
            if resp.ok:
                flash('Задание опубликовано', 'success')
                return redirect(url_for('my_jobs'))
            else:
                flash(f'Ошибка создания задания: {resp.text}', 'danger')
        except Exception as e:
            # Логирование ошибки
            error_details = traceback.format_exc()
            app.logger.error(f"Error creating job: {error_details}")
            flash(f'Ошибка сервера: {str(e)}', 'danger')
    return render_template('create_job.html', yandex_api_key=app.config['YANDEX_MAPS_API_KEY'])
```

---

## 🔧 ШАГ 2: Проверка RLS Policies для Таблицы jobs

### Что делать:
1. Перейти в Supabase Dashboard: https://supabase.com/dashboard
2. Выбрать проект: ***REMOVED***
3. Перейти в **Table Editor → jobs**
4. Нажать **SQL Editor**

### Запрос для проверки RLS:
```sql
-- Проверить, включен ли RLS
SELECT relname, relrowsecurity 
FROM pg_class 
WHERE relname = 'jobs';

-- Проверить текущие policies
SELECT * FROM pg_policies 
WHERE tablename = 'jobs';
```

### Если RLS включен:
```sql
-- Отключить RLS для тестирования
ALTER TABLE jobs DISABLE ROW LEVEL SECURITY;

-- ИЛИ создать правильные policies
CREATE POLICY "Users can insert jobs"
ON jobs FOR INSERT
WITH CHECK (
  auth.uid() = employer_id
);

CREATE POLICY "Users can select jobs"
ON jobs FOR SELECT
USING (
  true
);

CREATE POLICY "Users can update own jobs"
ON jobs FOR UPDATE
USING (
  auth.uid() = employer_id
);
```

---

## 🔧 ШАГ 3: Проверка Прав Доступа для ANON_KEY

### Что делать:
1. В Supabase Dashboard: **Project Settings → API**
2. Скопировать `anon public key`
3. Проверить, что этот ключ имеет права на INSERT в таблицу jobs

### Запрос для проверки:
```sql
-- В SQL Editor в Supabase Dashboard:
SELECT 
  rulename,
  permissive,
  roles,
  cmd,
  qual,
  with_check
FROM pg_rules
WHERE tablename = 'jobs';
```

### Если права отсутствуют:
```sql
-- Включить RLS и создать policies для anon
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

-- Удалить старые policies если есть
DROP POLICY IF EXISTS "Enable insert for anon" ON jobs;
DROP POLICY IF EXISTS "Allow anon insert" ON jobs;

-- Создать policy для anon
CREATE POLICY "Allow anon insert"
ON jobs FOR INSERT
TO anon
WITH CHECK (true);
```

---

## 🔧 ШАГ 4: Проверка Формы create_job.html

### Проблема:
Форма отправляется как `multipart/form-data`, но поля могут не заполняться.

### Решение:
1. Убедиться, что все обязательные поля заполнены
2. Проверить, что JavaScript заполняет скрытые поля до отправки

### Обновленный шаблон:
```html
<!-- templates/create_job.html -->
<form method="post" id="job-form">
    <!-- Видимые поля -->
    <input name="organization_name" required>
    <textarea name="org_description"></textarea>
    <textarea name="object_description"></textarea>
    <input name="work_type">
    <textarea name="detailed_description"></textarea>
    <input type="date" name="date" required>
    <input type="time" name="time" required>
    <input type="number" name="payment" required>
    <input type="text" name="city" required>
    
    <!-- Скрытые поля -->
    <input type="hidden" name="lat" id="lat" value="55.75">
    <input type="hidden" name="lng" id="lng" value="37.61">
    <input type="hidden" name="address" id="address">
    <input type="hidden" name="preferred_religion" value="не важно">
    
    <button type="submit" onclick="fillHiddenFields()">Опубликовать</button>
</form>

<script>
function fillHiddenFields() {
    // Заполнить скрытые поля перед отправкой
    document.getElementById('lat').value = '55.75';
    document.getElementById('lng').value = '37.61';
    
    // Если используется Яндекс Карта, заполнить address
    if (typeof ymaps !== 'undefined') {
        const coords = [55.75, 37.61];
        ymaps.geocode(coords).then(res => {
            const obj = res.geoObjects.get(0);
            if (obj) {
                document.getElementById('address').value = obj.getAddressLine();
            }
        });
    } else {
        document.getElementById('address').value = 'Moscow, Russia';
    }
    
    // Отправить форму
    setTimeout(() => {
        document.getElementById('job-form').submit();
    }, 1000);
}
</script>
```

---

## 🔧 ШАГ 5: Альтернативное Решение - Создание через API

### Создать новый маршрут для создания задания через JSON API:

```python
# В app.py
@app.route('/api/create-job', methods=['POST'])
@login_required
@role_required('employer')
def api_create_job():
    """Создание задания через JSON API"""
    try:
        data = request.get_json()
        
        job_data = {
            'employer_id': session['user_id'],
            'organization_name': data.get('organization_name', 'Храм'),
            'org_description': data.get('org_description', ''),
            'object_description': data.get('object_description', ''),
            'work_type': data.get('work_type', ''),
            'detailed_description': data.get('detailed_description', ''),
            'date_time': data.get('date_time', ''),
            'payment_amount': float(data.get('payment_amount', 0)),
            'address': data.get('address', ''),
            'city': data.get('city', ''),
            'lat': float(data.get('lat', 55.75)),
            'lng': float(data.get('lng', 37.61)),
            'preferred_religion': data.get('preferred_religion', 'не важно'),
        }
        
        resp = supabase_request('POST', 'jobs', json=job_data)
        
        if resp.ok:
            return jsonify({
                'success': True,
                'message': 'Задание опубликовано',
                'job_id': resp.json()[0]['id']
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Ошибка: {resp.text}'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Ошибка сервера: {str(e)}'
        }), 500
```

### Использование через JavaScript:

```javascript
// В create_job.html
async function createJobViaAPI() {
    const jobData = {
        organization_name: document.querySelector('input[name="organization_name"]').value,
        payment_amount: document.querySelector('input[name="payment"]').value,
        date_time: document.querySelector('input[name="date"]').value + 'T' + 
                   document.querySelector('input[name="time"]').value + ':00',
        // ... другие поля
    };
    
    const response = await fetch('/api/create-job', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(jobData)
    });
    
    const result = await response.json();
    if (result.success) {
        alert('Задание создано!');
        window.location.href = '/my-jobs';
    } else {
        alert('Ошибка: ' + result.message);
    }
}
```

---

## 🧪 ПРОВЕРКА ИСПРАВЛЕНИЯ

### После каждого изменения:

1. **Протестировать через браузер:**
   ```bash
   python create_job_direct.py
   ```

2. **Проверить логи:**
   - PythonAnywhere: https://www.pythonanywhere.com/domains/logs/
   - Supabase: Dashboard → Logs

3. **Проверить таблицу jobs:**
   ```bash
   python check_created_jobs.py
   ```

---

## 📋 ЧЕК-ЛИСТ ИСПРАВЛЕНИЯ

- [ ] Проверить логи PythonAnywhere
- [ ] Проверить RLS policies для jobs
- [ ] Проверить права доступа для ANON_KEY
- [ ] Обновить create_job.html с правильным JavaScript
- [ ] Добавить обработку ошибок в Flask
- [ ] Протестировать через браузер
- [ ] Проверить, что задание появляется в /my-jobs
- [ ] Протестировать отображение задания на главной странице

---

## 🎯 ЦЕЛЕВОЙ РЕЗУЛЬТАТ

После исправления:
- ✅ Форма `/create-job` должна отправляться без ошибок
- ✅ Задание должно появляться в `/my-jobs`
- ✅ Задание должно отображаться на главной странице
- ✅ Статус страницы: 200 OK (не 500)

---

**Документ создан 2026-06-03**
