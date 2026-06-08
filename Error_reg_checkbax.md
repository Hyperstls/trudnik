### 🛠 Промт для ИИ-агента: Исправление поля «Навыки» в регистрации

```markdown
# ЗАДАЧА: Исправить визуальную поломку поля «Навыки» на странице /register

## КОНТЕКСТ
На странице регистрации (`templates/register.html`) на шаге 2 («Шаг 2 из 2») поле выбора навыков отображается некорректно. Чекбоксы накладываются друг на друга, текст меток перекрывает границы соседних input-полей, отсутствует нормальный отступ между элементами. Это делает форму непригодной для использования.

## ТЕКУЩАЯ ПРОБЛЕМА (со скриншота)
- Чекбоксы навыков расположены в абсолютном позиционировании или без flex/grid-контейнера.
- Нет вертикального ритма (отступов) между чекбоксами и другими полями формы.
- Текст меток («Другие виды служения», «Музыкальное сопровождение» и др.) наезжает на границы input-полей.
- Визуально это выглядит как «сломанный» UI, нарушающий доверие к платформе.

## ТРЕБОВАНИЯ К ИСПРАВЛЕНИЮ

### 1. Структура HTML/Jinja2
- Оберни список навыков в контейнер с классом `skills-container`.
- Используй **flexbox** или **grid** для расположения чекбоксов:
  ```html
  <div class="skills-container grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
    {% for skill in skills_list %}
      <label class="flex items-center space-x-3 p-3 bg-neutral-50 border border-neutral-200 rounded-xl cursor-pointer hover:bg-neutral-100 transition-colors">
        <input type="checkbox" name="skill_ids" value="{{ skill.id }}" class="w-5 h-5 text-primary-500 rounded border-neutral-300 focus:ring-primary-500">
        <span class="text-neutral-700 font-medium">{{ skill.name }}</span>
      </label>
    {% endfor %}
  </div>
  ```
- Убедись, что `skills_list` передается в шаблон из бэкенда (`auth.py` → `register()`). Если нет — добавь запрос к таблице `skills` через Supabase API.

### 2. Стили (Tailwind CSS)
- Контейнер `.skills-container`:
  - `display: grid`
  - `grid-template-columns: repeat(auto-fill, minmax(250px, 1fr))` (адаптивно)
  - `gap: 12px` (вертикальный и горизонтальный)
  - `margin-top: 16px` (отступ от предыдущего поля)
  - `margin-bottom: 16px` (отступ до следующего поля)
- Каждый `<label>`:
  - `display: flex`, `align-items: center`, `space-x-3`
  - `padding: 12px`
  - `background-color: #f9fafb` (neutral-50)
  - `border: 1px solid #e5e7eb` (neutral-200)
  - `border-radius: 12px` (rounded-xl)
  - `cursor: pointer`
  - `transition: background-color 0.2s`
  - `hover:bg-neutral-100`
- Чекбокс:
  - `width: 20px`, `height: 20px`
  - `accent-color: #d97706` (primary-500)
  - `border-radius: 4px`
- Текст метки:
  - `font-size: 14px`
  - `color: #374151` (neutral-700)
  - `font-weight: 500`

### 3. Адаптивность
- На мобильных (<640px): 1 колонка (`grid-cols-1`)
- На планшетах и ПК (≥640px): 2 колонки (`sm:grid-cols-2`)
- Убедись, что контейнер не выходит за пределы карточки формы (`max-w-md mx-auto`).

### 4. Доступность (a11y)
- Каждый `<label>` должен быть связан с `<input>` через `for/id` или вложенность (как в примере выше).
- Добавь `aria-label` к группе чекбоксов: `<div role="group" aria-label="Выберите ваши навыки">`.
- Убедись, что чекбоксы доступны с клавиатуры (Tab, Space).

### 5. Бэкенд (auth.py)
- В маршруте `/register` (GET) добавь запрос к таблице `skills`:
  ```python
  skills_resp = supabase_request('GET', 'skills?select=id,name&order=name.asc')
  skills_list = skills_resp.json() if skills_resp.ok else []
  return render_template('register.html', ..., skills_list=skills_list)
  ```
- В POST-обработчике убедись, что `request.form.getlist('skill_ids')` корректно собирает выбранные ID и сохраняет их в таблицу `user_skills`.

### 6. Валидация
- Если пользователь не выбрал ни одного навыка — покажи мягкое предупреждение под полем: «Рекомендуем выбрать хотя бы один навык для лучшего поиска работы». Не блокируй регистрацию, но дай подсказку.

## ОЖИДАЕМЫЙ РЕЗУЛЬТАТ
- Поле «Навыки» выглядит как аккуратная сетка кликабельных карточек с чекбоксами.
- Нет наложений, перекрытий или «сломанной» верстки.
- Форма соответствует общей дизайн-системе приложения (нейтральные цвета, скругления, отступы).
- Работает на всех устройствах (мобильные, планшеты, ПК).
- Сохранена вся существующая логика регистрации (не трогай другие поля, шаги, валидацию email/пароля).

## ФОРМАТ ОТВЕТА
Предоставь:
1. Обновленный код `templates/register.html` (только секция с навыками + контекст вокруг).
2. Обновленный код `app/blueprints/auth.py` (маршрут `/register` GET).
3. Краткое пояснение, что было исправлено и почему.
```
