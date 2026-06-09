# Промт для ИИ-агента: Исправление чекбоксов навыков на странице регистрации

```markdown
# ЗАДАЧА: Исправить сломанную верстку чекбоксов навыков на странице /register

## ПРОБЛЕМА
На странице регистрации (шаг 2 из 2) поле выбора навыков отображается некорректно:
- Чекбоксы накладываются друг на друга
- Текст меток обрезается ("Юридическая е" вместо полного текста)
- Отсутствуют правильные отступы между элементами
- Визуально это выглядит как "каша" из перекрывающихся элементов

## ТЕКУЩАЯ СТРУКТУРА (из register.html)
```html
<label>Навыки (выберите один или несколько)</label>
<!-- Чекбоксы навыков без правильного контейнера -->
<input type="checkbox" name="skills" value="Другое"> Другое
<input type="checkbox" name="skills" value="Юридические услуги"> Юридические услуги
<!-- и т.д. -->
```

## ТРЕБОВАНИЯ К ИСПРАВЛЕНИЮ

### 1. HTML-структура
Оберни чекбоксы навыков в правильный контейнер:
```html
<div class="skills-container grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
  {% for skill in skills_list %}
    <label class="flex items-center space-x-3 p-3 bg-neutral-50 border border-neutral-200 rounded-xl cursor-pointer hover:bg-neutral-100 transition-colors">
      <input type="checkbox" name="skill_ids" value="{{ skill.id }}" 
             class="w-5 h-5 text-primary-500 rounded border-neutral-300 focus:ring-primary-500">
      <span class="text-neutral-700 font-medium text-sm">{{ skill.name }}</span>
    </label>
  {% endfor %}
</div>
```

### 2. CSS-классы (Tailwind)
- **Контейнер**: `grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2`
  - На мобильных: 1 колонка
  - На планшетах/ПК: 2 колонки
  - Отступы между элементами: 12px (gap-3)
  
- **Каждый label**: 
  - `flex items-center space-x-3` — чекбокс и текст в ряд
  - `p-3` — внутренние отступы
  - `bg-neutral-50` — светлый фон
  - `border border-neutral-200` — граница
  - `rounded-xl` — скругленные углы
  - `cursor-pointer` — курсор-рука
  - `hover:bg-neutral-100` — подсветка при наведении
  - `transition-colors` — плавный переход

- **Чекбокс**: `w-5 h-5 text-primary-500 rounded border-neutral-300 focus:ring-primary-500`

- **Текст**: `text-neutral-700 font-medium text-sm`

### 3. Бэкенд (auth.py)
Убедись, что в маршруте `/register` (GET) запрашиваются навыки из справочника:
```python
# Запросить список навыков из справочника
skills_resp = supabase_request('GET', 'skills?select=id,name&order=name.asc')
skills_list = skills_resp.json() if skills_resp.ok else []

return render_template('register.html', skills_list=skills_list, ...)
```

### 4. Адаптивность
- На мобильных (<640px): чекбоксы в 1 колонку, на всю ширину
- На планшетах и ПК (≥640px): 2 колонки
- Максимальная ширина контейнера не должна выходить за пределы карточки формы

### 5. Доступность (a11y)
- Каждый `<label>` должен быть связан с `<input>` (через вложенность или `for/id`)
- Чекбоксы должны быть доступны с клавиатуры (Tab для навигации, Space для выбора)
- Добавь `aria-label="Выберите ваши навыки"` к контейнеру

### 6. Валидация
- Если пользователь не выбрал ни одного навыка — покажи мягкое предупреждение: "Рекомендуем выбрать хотя бы один навык" (не блокируй регистрацию)

## ОЖИДАЕМЫЙ РЕЗУЛЬТАТ
- Чекбоксы отображаются как аккуратные карточки в сетке
- Нет наложений и перекрытий
- Текст полностью виден
- При наведении карточка подсвечивается
- На мобильных устройствах удобно нажимать (минимум 44px высота)
- Сохранена вся существующая логика отправки данных (навыки как строка через запятую ИЛИ как список ID в `skill_ids`)

## ФОРМАТ ОТВЕТА
Предоставь:
1. Обновленный код `templates/register.html` (секция с навыками)
2. Обновленный код `app/blueprints/auth.py` (маршрут GET /register с запросом skills)
3. Краткое пояснение, что было исправлено
```

---

### 💡 Альтернативный вариант (если skills_list не передается)

Если в бэкенде еще нет запроса к справочнику `skills`, используй этот упрощенный промт:

```markdown
# ЗАДАЧА: Исправить верстку чекбоксов навыков на регистрации

## ПРОБЛЕМА
Чекбоксы навыков накладываются друг на друга, текст обрезается.

## РЕШЕНИЕ
Замени текущую структуру на:

```html
<div class="mt-2">
  <label class="block text-sm font-medium text-neutral-700 mb-2">Навыки</label>
  <div class="space-y-2">
    <label class="flex items-center p-3 bg-neutral-50 rounded-xl cursor-pointer hover:bg-neutral-100">
      <input type="checkbox" name="skill_1" value="Уборка" class="w-5 h-5 text-primary-500 rounded">
      <span class="ml-3 text-sm">Уборка</span>
    </label>
    <label class="flex items-center p-3 bg-neutral-50 rounded-xl cursor-pointer hover:bg-neutral-100">
      <input type="checkbox" name="skill_2" value="Ремонт" class="w-5 h-5 text-primary-500 rounded">
      <span class="ml-3 text-sm">Ремонт</span>
    </label>
    <!-- Добавь остальные навыки -->
  </div>
  <p class="text-xs text-neutral-500 mt-2">Или укажите навыки через запятую:</p>
  <input type="text" name="skills" placeholder="Уборка, Ремонт, Вождение" 
         class="mt-1 w-full px-4 py-2 border border-neutral-200 rounded-xl">
</div>
```

Это временное решение до внедрения справочника `skills` из БД.
```