#!/usr/bin/env python3
"""Auto-update VERSION file and .env.amvera with latest git commit info.

Run before commit (via pre-commit hook) to keep version stamp current.
Works from any directory — project root is resolved relative to this file.
"""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    # Resolve project root: scripts/update_version.py -> parent -> parent
    project_root = Path(__file__).resolve().parent.parent

    # --- 1. Get full version string from git ---
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%h %s (%ai)"],
            capture_output=True,
            text=True,
            cwd=project_root,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.exit(f"git command failed: {exc}")

    full_version = result.stdout.strip()
    if not full_version:
        sys.exit("No git commits found — cannot determine version.")

    # --- 2. Write full version to VERSION file ---
    version_path = project_root / "VERSION"
    version_path.write_text(full_version + "\n", encoding="utf-8")

    # --- 3. Build short version string ---
    try:
        hash_result = subprocess.run(
            ["git", "log", "-1", "--format=%h"],
            capture_output=True,
            text=True,
            cwd=project_root,
            check=True,
        )
        short_hash = hash_result.stdout.strip()
    except subprocess.CalledProcessError:
        short_hash = "???????"

    try:
        date_result = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d"],
            capture_output=True,
            text=True,
            cwd=project_root,
            check=True,
        )
        date_str = date_result.stdout.strip()
    except subprocess.CalledProcessError:
        date_str = "????-??-??"

    try:
        subject_result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True,
            text=True,
            cwd=project_root,
            check=True,
        )
        subject = subject_result.stdout.strip()
    except subprocess.CalledProcessError:
        subject = "unknown"

    # Truncate subject to 60 chars with ellipsis if longer
    if len(subject) > 60:
        subject = subject[:60] + "..."

    short_version = f"{short_hash} {date_str} ({subject})"

    # --- 4. Update GIT_VERSION in .env.amvera ---
    env_path = project_root / ".env.amvera"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines(True)
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("GIT_VERSION="):
                lines[i] = f"GIT_VERSION={short_version}\n"
                updated = True
                break
        if not updated:
            # Append if key not present
            lines.append(f"GIT_VERSION={short_version}\n")
        env_path.write_text("".join(lines), encoding="utf-8")
    else:
        print(f"Warning: {env_path} not found — skipping GIT_VERSION update.")

    # --- 5. Report ---
    print(f"Version updated: {full_version}")


if __name__ == "__main__":
    main()
