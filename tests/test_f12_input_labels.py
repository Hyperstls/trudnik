"""F12: Все input-поля должны иметь явный label или aria-label."""
import os
import re
import pytest

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')


def _read_all_templates():
    """Считать все HTML-шаблоны (не email)."""
    result = {}
    for fname in os.listdir(TEMPLATES_DIR):
        if fname.endswith('.html') and 'email' not in fname:
            fpath = os.path.join(TEMPLATES_DIR, fname)
            with open(fpath, encoding='utf-8') as f:
                result[fname] = f.read()
    return result


def _extract_inputs(html):
    """Извлечь все <input> теги из HTML."""
    pattern = re.compile(r'<input\s[^>]*>', re.IGNORECASE | re.DOTALL)
    return pattern.findall(html)


def _is_hidden_input(input_tag):
    """Проверить, является ли input скрытым (type=hidden)."""
    type_match = re.search(r'type=["\']([^"\']+)["\']', input_tag, re.IGNORECASE)
    if type_match and type_match.group(1).lower() == 'hidden':
        return True
    return False


def _has_label(input_tag, html):
    """Проверить, имеет ли input связанный label."""
    # 1. aria-label
    if re.search(r'aria-label=["\'][^"\']+["\']', input_tag, re.IGNORECASE):
        return True
    # 2. aria-labelledby
    if re.search(r'aria-labelledby=["\'][^"\']+["\']', input_tag, re.IGNORECASE):
        return True
    # 3. title (fallback для a11y)
    if re.search(r'title=["\'][^"\']+["\']', input_tag, re.IGNORECASE):
        return True
    # 4. <label for="id">
    id_match = re.search(r'id=["\']([^"\']+)["\']', input_tag, re.IGNORECASE)
    if id_match:
        input_id = id_match.group(1)
        label_pattern = re.compile(
            r'<label[^>]*\bfor=["\']' + re.escape(input_id) + r'["\']',
            re.IGNORECASE
        )
        if label_pattern.search(html):
            return True
    # 5. Input внутри <label> (обёрнутый label)
    # Проверяем, находится ли input внутри <label>...</label>
    # Это упрощённая проверка — ищем <label> перед input и </label> после
    input_pos = html.find(input_tag)
    if input_pos >= 0:
        # Ищем ближайший <label> перед input
        before = html[:input_pos]
        after = html[input_pos:]
        last_label_open = before.rfind('<label')
        if last_label_open >= 0:
            # Проверяем, что </label> идёт после input
            label_close = after.find('</label>')
            if label_close >= 0:
                return True
    return False


def test_all_inputs_have_labels():
    """Все видимые input-поля должны иметь label, aria-label или быть внутри <label>."""
    templates = _read_all_templates()
    violations = []
    for fname, html in templates.items():
        inputs = _extract_inputs(html)
        for input_tag in inputs:
            if _is_hidden_input(input_tag):
                continue
            if not _has_label(input_tag, html):
                # Сокращаем для читаемости
                short_tag = input_tag[:120] + '...' if len(input_tag) > 120 else input_tag
                violations.append(f"{fname}: {short_tag}")
    assert not violations, (
        "Следующие input-поля не имеют label/aria-label:\n" +
        "\n".join(violations)
    )
