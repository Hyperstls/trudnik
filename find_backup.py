import subprocess

# Получаем последний коммит с полным app.py
result = subprocess.run(
    ['git', 'log', '--oneline', '-20'],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='ignore'
)

print("Last 20 commits:")
print(result.stdout)
