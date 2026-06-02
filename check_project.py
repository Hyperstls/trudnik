import os
from openai import OpenAI

client = OpenAI(
    api_key="sk-4192af6e581549b58d35cedb5b8743b5",
    base_url="https://api.deepseek.com/v1"
)

def collect_files(root_dir, extensions=(".py", ".html")):
    """Собрать содержимое всех файлов с указанными расширениями."""
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

def check_project():
    root = os.path.dirname(os.path.abspath(__file__))
    all_files = collect_files(root)

    if not all_files:
        print("❌ Не найдено файлов для проверки.")
        return

    # Формируем промпт
    prompt = "Ты проверяешь проект «Трудник» (Flask + Supabase).\n"
    prompt += "Ниже приведены все файлы проекта. Найди ошибки:\n"
    prompt += "- синтаксические ошибки,\n- маршруты с неправильными методами,\n"
    prompt += "- отсутствующие импорты,\n- проблемы безопасности,\n- дублирование кода.\n"
    prompt += "Для каждой ошибки укажи **файл, строку и описание**.\n\n"

    for fpath, content in all_files:
        prompt += f"=== {fpath} ===\n{content}\n\n"

    print("🔍 Отправка проекта на анализ...")

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=3000
    )

    report = response.choices[0].message.content
    print("✅ Анализ завершён:\n")
    print(report)

if __name__ == "__main__":
    check_project()