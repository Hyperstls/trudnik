#!/usr/bin/env python
"""Управляющий скрипт Django-компаньона «Трудник».

Запуск из корня репозитория:
    .venv/Scripts/python.exe djadmin/manage.py check
    .venv/Scripts/python.exe djadmin/manage.py test core --keepdb -v 1
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, BASE_DIR)  # пакеты config/ и core/ лежат в djadmin/
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
