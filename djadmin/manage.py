#!/usr/bin/env python
"""Управляющий скрипт Django-компаньона «Трудник».

Запуск из корня репозитория:
    .venv/Scripts/python.exe djadmin/manage.py check
    .venv/Scripts/python.exe djadmin/manage.py test core --keepdb -v 1
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.sys.path.insert(0, BASE_DIR)  # пакет config/ и core/ лежат в djadmin/
    os.sys.path.insert(1, REPO_ROOT)  # доступ к app.* Flask для утилит не требуется, но путь привычен
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
