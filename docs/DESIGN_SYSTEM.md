# Дизайн-система (J139)

## Токены

Токены живут в `static/css/app.css` (`:root`). Компоненты используют их вместо
хардкод-цветов:

| Группа | Токены |
|---|---|
| Действия | `--ui-color-primary`, `--ui-color-primary-hover`, `--ui-color-primary-soft` |
| Текст/фон | `--ui-color-text-strong`, `--ui-color-text`, `--ui-color-muted`, `--ui-color-surface`, `--ui-color-surface-muted`, `--ui-color-bg`, `--ui-color-border` |
| Статусы | `--ui-color-success*`, `--ui-color-warning*`, `--ui-color-danger*`, `--ui-color-info*` |
| Размеры | `--ui-control-sm/md/lg`, `--ui-radius-*`, `--ui-shadow-*` |
| Движение | `--ui-duration-*`, `--ui-ease-*` |
| Фокус | `--ui-focus-ring` |

Тёмная тема в будущем = переопределение этих токенов; Tailwind-утилиты
(`bg-white`, `text-neutral-*`) пока остаются в старых шаблонах и требуют
постепенной миграции.

## Partial-компоненты

Атомы — Django includes в `djadmin/core/templates/core/`:

```django
{% include "core/_ui_button.html" with label="Сохранить" variant="primary" icon="check" %}
{% include "core/_ui_button.html" with label="Отмена" variant="secondary" href="/jobs" %}
{% include "core/_ui_badge.html" with label="Принят" variant="success" %}
{% include "core/_ui_field.html" with field=form.email hint="you@example.com" %}
{% include "core/_ui_empty_state.html" with title="Пусто" description="..." action_url="/jobs" action_label="К заданиям" icon="search" %}
```

`_ui_button`: `variant=primary|secondary|danger|ghost`, `size=sm|lg`,
`block`, `icon`, `disabled`, `aria_label`, `href`, `type`, `extra_class`.

`_ui_badge`: `variant=neutral|primary|success|warning|danger|info`.

`_ui_field`: `field` (BoundField), `label`, `hint`, `extra_class`; ошибки
рендерятся с `role="alert"`.

`_ui_empty_state`: обёртка с иконкой (`folder|bell|search`) и кнопкой.

## Card / Modal / Sheet

В Django include не поддерживает слоты, поэтому это CSS-компоненты:

```html
<div class="ui-card p-4">…</div>

<dialog class="ui-modal" aria-labelledby="...">
  <div class="p-5">…</div>
</dialog>

<div class="ui-sheet">…</div>
```

Классы используют токены и готовы к тёмной теме. Существующие `.card`,
`.report-dialog`, `.action-menu-sheet` не ломаются и мигрируются постепенно.

## Тёмная тема (J142)

- Переключатель `#theme-toggle` в шапке; выбор хранится в
  `localStorage['trudnik-theme']` (`light`/`dark`).
- Пока выбора нет — тема следует `prefers-color-scheme`.
- Ранний inline-script в `<head>` применяет сохранённую тему до отрисовки,
  `meta[name=theme-color]` меняется вместе с темой.
- Tailwind-палитры `white`, `neutral`, `primary` переведены на CSS-переменные
  (`tailwind.config.js`); `[data-theme="dark"]` и media-query переопределяют
  палитру. Статусные `red/green/amber/blue/purple/gray` имеют точечные
  dark-overrides.
- `scripts/axe_audit.mjs` проверяет **обе темы** (desktop/mobile, 5 страниц);
  `scripts/e2e/critical_flows.sh` проверяет переключение и сохранение после reload.
- Ограничение: тайлы Яндекс.Карт остаются светлыми — это сторонний слой,
  стилизовать его под тему нельзя без отдельного API-решения.

## Миграция

1. Новые элементы — только через `_ui_*`/`.ui-*`.
2. Старые статусы/чипы заменяются на `_ui_badge` по мере правок шаблона.
3. После любых изменений шаблонов: `npm run build:css`.
4. Проверка: `manage.py test core.tests.test_ui_partials`, axe/Lighthouse после
   деплоя (UX quality).
