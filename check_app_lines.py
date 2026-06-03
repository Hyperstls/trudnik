import subprocess

result = subprocess.run(
    ['git', 'show', 'ca7dee0:app.py'],
    capture_output=True
)

lines = result.stdout.decode('utf-8', errors='ignore').split('\n')
print(f"Total lines: {len(lines)}")
