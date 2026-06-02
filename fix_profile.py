import re

with open('templates/profile.html', 'r', encoding='utf-8') as f:
    c = f.read()

# Добавляем {% endif %} перед {% if current_user_role (после </div>)
c = c.replace(
    '</div>\n{% if current_user_role == \'employer\' and profile_user.id != current_user_id %}',
    '</div>\n{% endif %}\n{% if current_user_role == \'employer\' and profile_user.id != current_user_id %}'
)

with open('templates/profile.html', 'w', encoding='utf-8') as f:
    f.write(c)

print('OK')
