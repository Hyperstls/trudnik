import subprocess

commands = [
    ["git", "add", "templates/job_new.html"],
    ["git", "commit", "-m", "fix: restore job_new.html template"],
    ["git", "push", "origin", "main"],
]

for cmd in commands:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("Command:", ' '.join(cmd))
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    print("---")
