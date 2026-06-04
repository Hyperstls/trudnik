import subprocess

# Git commit и push
commands = [
    ["git", "commit", "-m", "cleanup: remove temp files"],
    ["git", "pull", "origin", "main", "--rebase"],
    ["git", "push", "origin", "main"],
]

for cmd in commands:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("Command:", ' '.join(cmd))
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    print("---")
