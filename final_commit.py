import subprocess

commands = [
    ["git", "add", "DEPLOY_SUMMARY.txt"],
    ["git", "commit", "-m", "docs: deploy summary"],
    ["git", "push", "origin", "main"],
]

for cmd in commands:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("Command:", ' '.join(cmd))
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    print("---")
