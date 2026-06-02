import re

with open('templates/my_applications.html', 'r', encoding='utf-8') as f:
    c = f.read()

# Убираем shifts полностью
c = re.sub(r"{% set shift = shifts\.get\(app\.shift_id, \{\}\) %}", '', c)
c = re.sub(r"{% set shift_status = shift\.get\(\"status\", \"pending\"\) %}", '', c)

# Заменяем shift_status на app.status
c = c.replace("{{ shift_status }}", "{{ app.status }}")
c = c.replace("shift_status == 'pending'", "app.status == 'pending'")
c = c.replace("shift_status == 'accepted' or shift_status == 'active'", "app.status == 'accepted'")
c = c.replace("shift_status == 'rejected' or shift_status == 'cancelled'", "app.status == 'rejected'")
c = c.replace("shift_status == 'completed'", "app.status == 'completed'")

# Заменяем имена колонок под реальную БД
c = c.replace("worker.get('name'", "worker.get('full_name'")
c = c.replace("worker.get('avatar_url'", "worker.get('photo_url'")
c = c.replace("job.get('title'", "job.get('organization_name'")

# Убираем блоки с shift_id (кнопка чата и данные)
c = c.replace('data-shift-id="{{ app.shift_id }}"', '')

# Убираем блок shift_id полностью
old_chat_block = """                    {% if app.shift_id %}
                    <button onclick="event.stopPropagation(); window.location.href='/chat/{{ app.shift_id }}'"
                            class="bg-blue-500 text-white px-4 py-2 rounded-lg hover:bg-blue-600 transition-colors text-sm flex items-center space-x-1">
                        <span>✉️</span>
                        <span>Написать</span>
                    </button>
                    {% endif %}"""
c = c.replace(old_chat_block, '')

with open('templates/my_applications.html', 'w', encoding='utf-8') as f:
    f.write(c)

print('OK')
