import subprocess

# Очистка и коммит
commands = [
    ["git", "status"],
    ["git", "add", "-A"],
    ["git", "commit", "-m", "Final: max_workers, duplicate button, migrations"],
    ["git", "push", "origin", "main"],
]

for cmd in commands:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("Command:", ' '.join(cmd))
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    print("---")
