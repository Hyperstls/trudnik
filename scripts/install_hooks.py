#!/usr/bin/env python3
"""Install pre-commit hook that auto-updates VERSION and .env.amvera.

Run once:  python scripts/install_hooks.py
After that every `git commit` will stamp the latest version automatically.
"""

import os
import stat
from pathlib import Path


HOOK_CONTENT = """#!/bin/bash
# Auto-update VERSION and .env.amvera before commit
python scripts/update_version.py
git add VERSION .env.amvera 2>/dev/null || true
"""


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    hooks_dir = project_root / ".git" / "hooks"
    hook_path = hooks_dir / "pre-commit"

    # Ensure .git/hooks exists
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Write the hook
    hook_path.write_text(HOOK_CONTENT, encoding="utf-8")

    # Make executable (no-op on Windows, but harmless and helps on Linux/macOS)
    try:
        st = os.stat(hook_path)
        os.chmod(hook_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass  # Windows typically ignores chmod for executables

    print("Pre-commit hook installed. Version will auto-update on every commit.")


if __name__ == "__main__":
    main()
