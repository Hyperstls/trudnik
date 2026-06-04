import subprocess

commands = [
    ["git", "status"],
    ["git", "add", "-A"],
    ["git", "commit", "-m", "fix: abort merge"],
    ["git", "push", "origin", "main"],
]

for cmd in commands:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("Command:", ' '.join(cmd))
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    print("---")
