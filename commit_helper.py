import subprocess

# Список коммитов
commits = [
    ["git", "commit", "-m", "fix: max_workers and duplicate button"],
]

for cmd in commits:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    print("---")
