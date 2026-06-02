import sys
import os
from openai import OpenAI

client = OpenAI(
    api_key="sk-4192af6e581549b58d35cedb5b8743b5",
    base_url="https://api.deepseek.com/v1"
)

def edit_file(filepath, instruction):
    if not os.path.exists(filepath):
        print(f"ERROR: File {filepath} not found")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        original_content = f.read()

    prompt = f"""У тебя есть файл, содержимое которого приведено ниже.
Твоя задача — изменить его согласно инструкции и вернуть **только новый код файла целиком**.
Не добавляй пояснений, markdown-разметки или лишнего текста. Только код.

Инструкция:
{instruction}

Содержимое файла:
{original_content}
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4000
    )

    new_content = response.choices[0].message.content.strip()

    if new_content.startswith("```"):
        new_content = new_content.split("\n", 1)[-1]
        if new_content.endswith("```"):
            new_content = new_content.rsplit("\n```", 1)[0]

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"SUCCESS: File {filepath} updated.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python agent_edit.py <file_path> <instruction>")
        sys.exit(1)

    file = sys.argv[1]
    instruction = " ".join(sys.argv[2:])
    edit_file(file, instruction)