#!/usr/bin/env python3
"""Install post-commit hook that auto-updates VERSION and .env.amvera.

Run once:  python scripts/install_hooks.py
After that every `git commit` will stamp the latest version automatically.
"""

import os
import shutil
import stat
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    hooks_dir = project_root / ".git" / "hooks"
    hook_path = hooks_dir / "post-commit"

    # Ensure .git/hooks exists
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Copy update_version.py as post-commit hook
    shutil.copy(str(project_root / "scripts" / "update_version.py"), str(hook_path))

    # Make executable (no-op on Windows, but harmless and helps on Linux/macOS)
    try:
        st = os.stat(hook_path)
        os.chmod(hook_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass  # Windows typically ignores chmod for executables

    print("Post-commit hook installed. Version will auto-update on every commit.")


if __name__ == "__main__":
    main()
