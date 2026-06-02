import os
from openai import OpenAI

client = OpenAI(
    api_key="sk-4192af6e581549b58d35cedb5b8743b5",
    base_url="https://api.deepseek.com/v1"
)

def collect_files(root_dir, extensions=(".py", ".html")):
    files_content = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith(extensions) and '.venv' not in dirpath and '__pycache__' not in dirpath:
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    files_content.append((fpath, content))
                except Exception as e:
                    print(f"⚠️ Пропущен {fpath}: {e}")
    return files_content

def auto_fix():
    root = os.path.dirname(os.path.abspath(__file__))
    all_files = collect_files(root)

    if not all_files:
        print("❌ Не найдено файлов для проверки.")
        return

    prompt = """
Ты — эксперт по Flask, Python и веб-разработке. Ниже приведены ВСЕ файлы проекта «Трудник».
Найди и исправь ошибки:
- синтаксические ошибки,
- маршруты с неправильными методами (GET/POST),
- отсутствующие импорты,
- проблемы безопасности (неправильное использование service_role),
- дублирование кода,
- несоответствие переменных в шаблонах.

Верни ответ СТРОГО в формате:
### path/to/file
новый код файла полностью
### path/to/another/file
новый код файла полностью
...
Не добавляй пояснений, только блоки с именами файлов и новым кодом.
"""

    for fpath, content in all_files:
        prompt += f"=== {fpath} ===\n{content}\n\n"

    print("🔍 Отправка проекта на анализ и исправление...")
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4000
    )

    answer = response.choices[0].message.content

    # Парсим ответ: ищем блоки ### filename ... новый код
    import re
    pattern = r'###\s*(.+?)\n(.*?)(?=###|$)'
    matches = re.findall(pattern, answer, re.DOTALL)

    if not matches:
        print("❌ Не удалось распознать формат ответа. Ответ модели:")
        print(answer)
        return

    for filename, code in matches:
        filename = filename.strip()
        code = code.strip()
        if not os.path.exists(filename):
            print(f"⚠️ Файл {filename} не найден, пропускаю.")
            continue
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(code)
        print(f"✅ Исправлен: {filename}")

    print("🎉 Все найденные ошибки исправлены.")

if __name__ == "__main__":
    auto_fix()