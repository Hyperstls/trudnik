import subprocess

# Очистка и финальный коммит
commands = [
    ["git", "add", "-A"],
    ["git", "commit", "-m", "clean: remove helper files"],
    ["git", "push", "origin", "main"],
]

for cmd in commands:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("Command:", ' '.join(cmd))
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    print("---")
