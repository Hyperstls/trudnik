#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pipeline.py — управляемый агентный конвейер (stdlib, Python 3.10+).

Контракт задачи -> изолированный промпт исполнителя -> verify по exit-кодам ->
review-пакет (diff + критерии) -> независимый ревьюер -> done/fixing/blocked.

Три столпа (механически, не «по слову»):
  1) exit-код — единственный вердикт проверки;
  2) ревьюер не видит рассуждений исполнителя;
  3) лимит попыток (3) и раундов ревью (2), дальше blocked и вопрос человеку.

Данные по умолчанию: <repo>/context/agent-pipeline/. Корень ищется по .git
выше scripts/tools/pipeline.py; переопределяется --root/--context.
"""

from __future__ import annotations

import argparse
import difflib
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

STATUSES = ("planned", "implementing", "verifying", "reviewing", "done", "fixing", "blocked")
EDITABLE = ("planned", "fixing", "blocked")
REQUIRED = ("id", "title", "goal", "why", "files", "context_files",
            "interfaces", "acceptance", "out_of_scope", "checks")
DEFAULT_SPILL = [r"/packs/", r"/logs/", r"/tasks/", r"state\.json$", r"progress\.md$", r"decisions\.md$",
                 r"__pycache__/", r"\.pyc$", r"\.pytest_cache/", r"\.mypy_cache/", r"\.ruff_cache/"]
PROGRESS_HEADER = "# Progress — agent pipeline\n\nХронология: каждая verify/review — строкой. Append-only.\n\n"
DECISIONS_HEADER = "# Decisions — agent pipeline\n\nAppend-only: решения и измерения. Числа, команды, причины.\n"

IMPL_RULES = """\
Жёсткие правила для исполнителя:
- Менять можно ТОЛЬКО файлы из `files`. Нужен ещё файл — верни `NEED: <путь>`, а не догадку.
- Интерфейсы из раздела «Интерфейсы» не выдумывать и не «улучшать». Не хватает данных — `NEED: <что именно>`.
- Сеть, БД, установка пакетов — только если явно разрешено контрактом.
- Верни: список изменённых файлов; для каждой проверки — команду, exit-код и краткий фактический вывод.
  Не «всё ок», а доказательство.
- Прогоняй проверки сам ДО сдачи. Сдавать с красными проверками запрещено.
- Если требование контракта технически невыполнимо — не хакай, пиши `BLOCKED: <почему>`
  со ссылкой на строку/правило контракта.
- Не трогай `context/agent-pipeline/` — это зона оркестратора.
"""

TRAPS = """\
Типовые ловушки (реальные ошибки, стоившие раундов):
1. Контракт ссылается на канон проекта, а не на самодельные регэкспы.
2. Кэш: ключ включает ВСЁ, от чего зависит результат; ветка кэш-хита проходит ту же валидацию.
3. Счётчики не врут молча: метрику, которая должна делиться по каналам/типам, дели сразу.
4. Фолбэк «нет данных — подставь само значение» — дыра в инварианте. Формулируй, что НЕЛЬЗЯ.
5. Контракт может быть неправ, а код — прав. Сначала проверь выполнимость требования.
6. Ревьюер — отдельный вызов с лимитом контекста: заголовок и критерии → grep → range-чтения.
7. Другие процессы портят scope. Отсюда baseline и spill-исключения; `--skip-scope` — только со следом.
8. Windows/оболочки: `>` в PowerShell = UTF-16LE; `&&` может не поддерживаться; `$d:` ломает парсер.
9. JSON-контракты пиши инструментом записи целиком, а не точечными правками со вставками `\\n`.
10. «Проверено» должно быть доказуемым: у факта — ссылка на источник, у отсечённого — причина.
11. Лимит раундов: 2 узких фикса на задачу. Дальше `blocked` и вопрос человеку.
"""

REVIEW_RULES = """\
Ты — независимый ревьюер. Ты видишь ТОЛЬКО этот пакет: цель, критерии приёмки,
out_of_scope и diff. Ты НЕ видишь рассуждений и отчёта исполнителя и не читаешь
проект «для контекста».

Правила:
- Проверяй только соответствие diff критериям приёмки и out_of_scope.
- Не изобретай новые требования в финальном раунде: если требование не следует из критериев — это не блокер.
- Блокер обязан иметь привязку `файл:строка` (или `файл (строка отсутствует)`).
- Формат ответа строго: `VERDICT: PASS` или `VERDICT: FAIL`, затем блокеры или одно предложение подтверждения.
"""

REVIEW_READING = """\
Если пакет большой (60+ КБ): 1) прочитай заголовок и критерии; 2) найди нужное grep'ом по файлу пакета;
3) читай точечные диапазоны строк, не грузи файл целиком.
"""


class PipelineError(Exception):
    """Ожидаемая ошибка CLI: печатается без traceback, exit-код 2."""


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def now_human() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def discover_git_root(start: Path) -> Path | None:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8-sig", errors="strict") as fh:
        return fh.read()


def read_text_soft(path: Path) -> str | None:
    try:
        return read_text(path)
    except (UnicodeDecodeError, OSError):
        return None


def write_json(path: Path, data: object) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def norm_rel(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.replace("\\", "/").strip()
    if not s or s.startswith("/") or re.match(r"^[A-Za-z]:", s):
        return None
    parts = [p for p in s.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def expand_cmd(cmd: str) -> str:
    return cmd.replace("{python}", f'"{sys.executable}"')


def split_globals(argv: list[str]) -> tuple[str | None, str | None, list[str]]:
    root = context = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--root", "--context") and i + 1 < len(argv):
            if arg == "--root":
                root = argv[i + 1]
            else:
                context = argv[i + 1]
            i += 2
        elif arg.startswith("--root="):
            root = arg.split("=", 1)[1]
            i += 1
        elif arg.startswith("--context="):
            context = arg.split("=", 1)[1]
            i += 1
        else:
            rest.append(arg)
            i += 1
    return root, context, rest


def default_config() -> dict:
    return {"max_attempts": 3, "max_review_rounds": 2,
            "check_timeout_seconds": 600, "spill_patterns": list(DEFAULT_SPILL)}


def default_state() -> dict:
    return {"schema": 1, "created_at": now_iso(), "updated_at": now_iso(),
            "config": default_config(), "tasks": {}, "totals": {}}


def ensure_structure(ctx: Path) -> None:
    for name in ("tasks", "packs", "logs", "templates"):
        (ctx / name).mkdir(parents=True, exist_ok=True)
    if not (ctx / "state.json").exists():
        save_state(ctx, default_state())
    if not (ctx / "progress.md").exists():
        write_text(ctx / "progress.md", PROGRESS_HEADER)
    if not (ctx / "decisions.md").exists():
        write_text(ctx / "decisions.md", DECISIONS_HEADER)


def load_state(ctx: Path) -> dict:
    path = ctx / "state.json"
    if not path.exists():
        return default_state()
    try:
        data = json.loads(read_text(path))
    except (json.JSONDecodeError, OSError) as exc:
        raise PipelineError(f"не читается {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelineError(f"{path}: ожидался JSON-объект")
    config = data.setdefault("config", {})
    for key, value in default_config().items():
        config.setdefault(key, value)
    data.setdefault("tasks", {})
    return data


def save_state(ctx: Path, state: dict) -> None:
    counts: dict[str, int] = {}
    for task in state.get("tasks", {}).values():
        counts[task.get("status", "unknown")] = counts.get(task.get("status", "unknown"), 0) + 1
    state["totals"] = dict(sorted(counts.items()))
    state["totals"]["total"] = len(state.get("tasks", {}))
    state["updated_at"] = now_iso()
    write_json(ctx / "state.json", state)


def get_task(state: dict, task_id: str) -> dict:
    task = state.get("tasks", {}).get(task_id)
    if not isinstance(task, dict):
        raise PipelineError(f"задача {task_id} не найдена (см. pipeline.py list)")
    return task


def load_contract(ctx: Path, task_id: str) -> dict:
    path = ctx / "tasks" / f"{task_id}.json"
    if not path.exists():
        raise PipelineError(f"нет контракта {path}")
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise PipelineError(f"контракт {path} не парсится: {exc}") from exc


def append_progress(ctx: Path, task_id: str, phase: str, result: str, details: str) -> None:
    append_text(ctx / "progress.md",
                f"- **{now_human()}** | **{task_id}** | `{phase}` | **{result}** | {details}\n")


def append_decision(ctx: Path, task_id: str, title: str, body: str) -> None:
    append_text(ctx / "decisions.md", f"\n## {now_human()} — {task_id}: {title}\n\n{body}\n")


def current_user(root: Path) -> str:
    try:
        cp = subprocess.run(["git", "-C", str(root), "config", "user.name"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if cp.returncode == 0 and cp.stdout.strip():
            return cp.stdout.strip()
    except OSError:
        pass
    return getpass.getuser()


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError as exc:
        raise PipelineError("git не найден в PATH — конвейеру нужен git-репозиторий") from exc
    except OSError as exc:
        raise PipelineError(f"git не запускается: {exc}") from exc


def git_head(root: Path) -> str | None:
    cp = git(root, "rev-parse", "--short", "HEAD")
    return cp.stdout.strip() if cp.returncode == 0 and cp.stdout.strip() else None


def changed_files(root: Path) -> list[str]:
    files: set[str] = set()
    cp = git(root, "diff", "--name-only", "HEAD")
    if cp.returncode == 0:
        files.update(line.strip() for line in cp.stdout.splitlines() if line.strip())
    else:
        cp_status = git(root, "status", "--porcelain", "--untracked-files=all")
        if cp_status.returncode != 0:
            raise PipelineError(f"git status не работает: {cp_status.stderr.strip()}")
        for line in cp_status.stdout.splitlines():
            if len(line) < 4:
                continue
            rest = line[3:]
            if " -> " in rest:
                rest = rest.split(" -> ", 1)[1]
            rest = rest.strip().strip('"')
            if rest.endswith("/") or (root / rest).is_dir():
                continue
            files.add(rest)
    cp_untracked = git(root, "ls-files", "--others", "--exclude-standard")
    if cp_untracked.returncode != 0:
        raise PipelineError(f"git ls-files не работает: {cp_untracked.stderr.strip()}")
    files.update(line.strip() for line in cp_untracked.stdout.splitlines() if line.strip())
    return sorted(norm_rel(f) or f for f in files)


def is_spill(path: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, path.replace("\\", "/")) for pattern in patterns)


def compute_scope(root: Path, task: dict, patterns: list[str]) -> dict:
    contract = set(task.get("files", []))
    baseline_hashes: dict[str, str | None] = task.get("baseline_hashes") or {}
    current_changed = set(changed_files(root))
    touched: set[str] = set()
    for path in current_changed:
        if path not in baseline_hashes or file_hash(root / path) != baseline_hashes[path]:
            touched.add(path)
    for path, old_hash in baseline_hashes.items():
        if file_hash(root / path) != old_hash:
            touched.add(path)
    drift = sorted(path for path in touched if path not in contract and not is_spill(path, patterns))
    return {"changed": sorted(current_changed), "touched": sorted(touched), "drift": drift,
            "contract": sorted(contract)}


def _norm_list(value: object, field: str, errors: list[str], allow_empty: bool) -> list[str]:
    result: list[str] = []
    if not isinstance(value, list):
        errors.append(f"`{field}` должен быть списком путей")
        return result
    for item in value:
        normalized = norm_rel(item)
        if normalized is None:
            errors.append(f"`{field}`: небезопасный или пустой относительный путь: {item!r}")
        elif normalized in result:
            errors.append(f"`{field}`: дубликат {normalized}")
        else:
            result.append(normalized)
    if not result and not allow_empty:
        errors.append(f"`{field}`: нужен хотя бы один путь")
    return result


def _nonempty(data: dict, field: str, errors: list[str]) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"поле `{field}` обязательно и должно быть непустой строкой")
        return ""
    return value.strip()


def validate_contract(data: object) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return None, ["контракт должен быть JSON-объектом"]
    for field in REQUIRED:
        if field not in data:
            errors.append(f"отсутствует обязательное поле `{field}`")
    if errors:
        return None, errors

    task_id = data.get("id")
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", task_id):
        errors.append("`id`: [A-Za-z0-9._-], начинается с буквы/цифры, без пробелов, до 64 символов")
    title = _nonempty(data, "title", errors)
    goal = _nonempty(data, "goal", errors)
    why = _nonempty(data, "why", errors)
    interfaces = _nonempty(data, "interfaces", errors)

    files = _norm_list(data.get("files"), "files", errors, allow_empty=False)
    if len(files) > 4:
        errors.append(f"`files`: максимум 4 файла, получено {len(files)} — декомпозируйте задачу")
    context_files = _norm_list(data.get("context_files"), "context_files", errors, allow_empty=True)
    for path in files:
        if path in context_files:
            errors.append(f"`{path}` указан и в `files`, и в `context_files` — уберите дубликат")

    acceptance: list[str] = []
    raw_acceptance = data.get("acceptance")
    if not isinstance(raw_acceptance, list) or not raw_acceptance:
        errors.append("`acceptance`: нужен непустой нумерованный список критериев")
    else:
        for index, item in enumerate(raw_acceptance, 1):
            if not isinstance(item, str) or not item.strip():
                errors.append(f"`acceptance`: критерий #{index} пустой или не строка")
            else:
                acceptance.append(item.strip())

    out_of_scope: list[str] = []
    raw_out = data.get("out_of_scope")
    if not isinstance(raw_out, list):
        errors.append("`out_of_scope` должен быть списком (может быть пустым)")
    else:
        for item in raw_out:
            if not isinstance(item, str) or not item.strip():
                errors.append("`out_of_scope`: элементы должны быть непустыми строками")
            else:
                out_of_scope.append(item.strip())

    checks: list[dict] = []
    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        errors.append("`checks`: нужен непустой список проверок")
    else:
        names: set[str] = set()
        for index, item in enumerate(raw_checks, 1):
            if not isinstance(item, dict):
                errors.append(f"`checks` #{index}: ожидался объект {{name, cmd, cwd}}")
                continue
            name, cmd, cwd = item.get("name"), item.get("cmd"), item.get("cwd", ".")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"`checks` #{index}: пустой `name`")
                continue
            if name in names:
                errors.append(f"`checks`: дубликат имени {name}")
            names.add(name)
            if not isinstance(cmd, str) or not cmd.strip():
                errors.append(f"`checks` {name}: пустой `cmd`")
                continue
            if "\n" in cmd or "\r" in cmd:
                errors.append(f"`checks` {name}: команда должна быть одной строкой (длинное — файлом)")
                continue
            if not isinstance(cwd, str):
                errors.append(f"`checks` {name}: `cwd` должен быть строкой")
                continue
            cwd_norm = cwd.replace("\\", "/").strip() or "."
            if cwd_norm.startswith("/") or re.match(r"^[A-Za-z]:", cwd_norm) or ".." in cwd_norm.split("/"):
                errors.append(f"`checks` {name}: `cwd` должен быть относительным и без `..`")
                continue
            checks.append({"name": name, "cmd": cmd.strip(), "cwd": cwd_norm.rstrip("/") or "."})

    if errors:
        return None, errors
    return {"id": task_id, "title": title, "goal": goal, "why": why, "files": files,
            "context_files": context_files, "interfaces": interfaces, "acceptance": acceptance,
            "out_of_scope": out_of_scope, "checks": checks}, []


def baseline_dir(ctx: Path, task_id: str) -> Path:
    return ctx / "logs" / f"{task_id}.baseline"


def snapshot_contract_files(root: Path, ctx: Path, task_id: str, files: list[str]) -> dict:
    target = baseline_dir(ctx, task_id)
    if target.exists():
        for child in sorted(target.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
    target.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    for index, path in enumerate(files, 1):
        source = root / path
        if source.is_file():
            name = f"{index:03d}_{source.name}"
            destination = target / name
            with open(source, "rb") as src, open(destination, "wb") as dst:
                dst.write(src.read())
            manifest[path] = {"exists": True, "snapshot": name}
        else:
            manifest[path] = {"exists": False, "snapshot": None}
    write_json(target / "_manifest.json", manifest)
    return manifest


def read_baseline_manifest(ctx: Path, task_id: str) -> dict:
    path = baseline_dir(ctx, task_id) / "_manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return {}


def _with_newlines(lines: list[str]) -> list[str]:
    return [line if line.endswith("\n") else line + "\n" for line in lines]


def file_diff(ctx: Path, task_id: str, root: Path, rel_path: str, manifest: dict) -> tuple[str, bool]:
    meta = manifest.get(rel_path) or {"exists": False, "snapshot": None}
    before = ""
    if meta.get("exists") and meta.get("snapshot"):
        snapshot = baseline_dir(ctx, task_id) / meta["snapshot"]
        if snapshot.exists():
            loaded = read_text_soft(snapshot)
            if loaded is None:
                return "[бинарный файл: diff не рендерится]", False
            before = loaded
    current_path = root / rel_path
    is_new = not meta.get("exists") and current_path.is_file()
    after = ""
    if current_path.is_file():
        loaded = read_text_soft(current_path)
        if loaded is None:
            return "[бинарный файл: diff не рендерится]", is_new
        after = loaded
    if before == after and bool(meta.get("exists")) == current_path.is_file():
        return "", False
    from_name = f"a/{rel_path}" if meta.get("exists") else "/dev/null"
    to_name = f"b/{rel_path}" if current_path.is_file() or not meta.get("exists") else "/dev/null"
    diff = difflib.unified_diff(_with_newlines(before.splitlines()), _with_newlines(after.splitlines()),
                                fromfile=from_name, tofile=to_name, lineterm="\n")
    return "".join(diff), is_new


def build_impl_prompt(root: Path, contract: dict) -> str:
    lines = [
        f"# IMPL PACK — {contract['id']}: {contract['title']}\n",
        f"Дата: {now_iso()}\n",
        f"Корень проекта: `{root}`\n",
        "\nТы — исполнитель. Пакет самодостаточен: истории чата нет, ходить по проекту "
        "«за контекстом» не нужно. Работай строго по контракту.\n",
        f"\n## 1. Цель (goal)\n\n{contract['goal']}\n",
        f"\n## 2. Зачем (why)\n\n{contract['why']}\n",
        "\n## 3. Файлы\n\n**Можно менять ТОЛЬКО:**\n",
    ]
    lines.extend(f"- `{path}`\n" for path in contract["files"])
    lines.append("\n**Можно читать (но не менять):**\n")
    if contract["context_files"]:
        lines.extend(f"- `{path}`\n" for path in contract["context_files"])
    else:
        lines.append("- (нет)\n")
    lines.append("\nЛюбой другой файл — вне контракта. Если он нужен: `NEED: <путь>` и остановись.\n")
    lines.append(f"\n## 4. Интерфейсы (не выдумывать и не «улучшать»)\n\n{contract['interfaces']}\n")
    lines.append("\n## 5. Критерии приёмки\n\n")
    lines.extend(f"{index}. {item}\n" for index, item in enumerate(contract["acceptance"], 1))
    lines.append("\n## 6. Вне scope (запрещено)\n\n")
    if contract["out_of_scope"]:
        lines.extend(f"- {item}\n" for item in contract["out_of_scope"])
    else:
        lines.append("- (явных запретов нет; действует правило «только files»)\n")
    lines.append("\n## 7. Проверки (вердикт = exit-код, текст вывода не важен)\n\n")
    lines.append("| name | cmd | cwd |\n|---|---|---|\n")
    lines.extend(f"| `{check['name']}` | `{check['cmd']}` | `{check['cwd']}` |\n"
                 for check in contract["checks"])
    lines.append("\n`{python}` — плейсхолдер: оркестратор заменит его на текущий интерпретатор. "
                 "В своих командах оставляй как есть.\n")
    lines.append("\n## 8. " + IMPL_RULES)
    lines.append("\n## 9. " + TRAPS)
    lines.append("\n## 10. Формат отчёта (обязателен)\n\n```\nCHANGED:\n- <путь>\nCHECKS:\n"
                 "- name: <имя> | cmd: <команда> | exit: <код> | output: <1-3 строки факта>\n"
                 "RESULT: DONE | NEED: ... | BLOCKED: ...\n```\n")
    return "".join(lines)


def build_review_prompt(root: Path, ctx: Path, task: dict, contract: dict) -> tuple[str, list[str]]:
    manifest = read_baseline_manifest(ctx, task["id"])
    lines = [
        f"# REVIEW PACK — {contract['id']}: {contract['title']}\n",
        f"Дата: {now_iso()}\n",
        "\n## 0. Роль\n\n" + REVIEW_RULES + "\n",
        f"\n## 1. Цель (goal)\n\n{contract['goal']}\n",
        "\n## 2. Критерии приёмки\n\n",
    ]
    lines.extend(f"{index}. {item}\n" for index, item in enumerate(contract["acceptance"], 1))
    lines.append("\n## 3. Вне scope\n\n")
    if contract["out_of_scope"]:
        lines.extend(f"- {item}\n" for item in contract["out_of_scope"])
    else:
        lines.append("- (нет)\n")
    lines.append("\n## 4. Diff (baseline → current), только файлы контракта\n\n")
    new_files: list[str] = []
    for path in contract["files"]:
        diff_text, is_new = file_diff(ctx, task["id"], root, path, manifest)
        if is_new:
            new_files.append(path)
        if diff_text:
            lines.append(f"### `{path}`\n\n```diff\n{diff_text.rstrip()}\n```\n\n")
        else:
            lines.append(f"### `{path}`\n\n_Изменений нет._\n\n")
    lines.append("\n## 5. Новые файлы\n\n")
    if new_files:
        lines.extend(f"- `{path}` (создан задачей)\n" for path in new_files)
    else:
        lines.append("- (нет)\n")
    lines.append("\n## 6. Формат вердикта\n\nПервая строка: `VERDICT: PASS` или `VERDICT: FAIL`.\n"
                 "Для FAIL: блокеры с привязкой `файл:строка` и указанием нарушенного критерия.\n")
    lines.append("\n## 7. Стратегия чтения большого пакета\n\n" + REVIEW_READING + "\n")
    return "".join(lines), new_files


def cmd_init(args, root: Path, ctx: Path) -> int:
    ensure_structure(ctx)
    print(f"INIT: {ctx}\n  root: {root}\n  state: {ctx / 'state.json'}")
    return 0


def cmd_add(args, root: Path, ctx: Path) -> int:
    source = Path(args.file)
    if not source.is_absolute():
        candidate = ctx / source
        source = candidate if candidate.exists() else root / source
    if not source.is_file():
        raise PipelineError(f"файл контракта не найден: {source}")
    try:
        raw = json.loads(read_text(source))
    except json.JSONDecodeError as exc:
        raise PipelineError(f"{source}: невалидный JSON: {exc}") from exc
    contract, errors = validate_contract(raw)
    if errors:
        print(f"ОТКЛОНЕНО: {source}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    assert contract is not None
    state = load_state(ctx)
    if contract["id"] in state["tasks"]:
        raise PipelineError(f"задача {contract['id']} уже зарегистрирована")
    target = ctx / "tasks" / f"{contract['id']}.json"
    write_json(target, contract)
    state["tasks"][contract["id"]] = {
        "id": contract["id"], "title": contract["title"], "status": "planned",
        "attempts": 0, "review_rounds": 0, "files": contract["files"],
        "context_files": contract["context_files"], "baseline": [], "baseline_hashes": {},
        "baseline_at": None, "baseline_head": None,
        "verify": {"last": None, "log": None, "at": None, "scope": None,
                   "skip_scope": False, "checks": []},
        "review": {"last": None, "verdict": None, "at": None, "round": 0},
        "skip_scope_events": [], "contract_revisions": 0,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    save_state(ctx, state)
    append_progress(ctx, contract["id"], "add", "OK", f"contract={rel(root, target)}")
    print(f"ADDED: {contract['id']} — {contract['title']}")
    print(f"  contract: {rel(root, target)}\n  status:   planned")
    print(f"  files ({len(contract['files'])}): {', '.join(contract['files'])}")
    print(f"  checks ({len(contract['checks'])}): {', '.join(c['name'] for c in contract['checks'])}")
    return 0


def cmd_update(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    task = get_task(state, args.task_id)
    if task["status"] not in EDITABLE:
        raise PipelineError(f"контракт можно менять только в {EDITABLE}; сейчас {task['status']}")
    source = Path(args.file)
    if not source.is_absolute():
        candidate = ctx / source
        source = candidate if candidate.exists() else root / source
    if not source.is_file():
        raise PipelineError(f"файл контракта не найден: {source}")
    contract, errors = validate_contract(json.loads(read_text(source)))
    if errors:
        print(f"ОТКЛОНЕНО: {source}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    assert contract is not None
    if contract["id"] != args.task_id:
        raise PipelineError(f"id в контракте ({contract['id']}) != {args.task_id}")
    old = load_contract(ctx, args.task_id)
    write_json(ctx / "tasks" / f"{args.task_id}.json", contract)
    task.update(title=contract["title"], files=contract["files"],
                context_files=contract["context_files"],
                contract_revisions=int(task.get("contract_revisions", 0)) + 1, updated_at=now_iso())
    save_state(ctx, state)
    reason = args.reason or "(без причины)"
    append_progress(ctx, args.task_id, "update", "OK",
                    f"revision={task['contract_revisions']} reason={reason}")
    append_decision(ctx, args.task_id, "контракт обновлён",
                    f"**Причина:** {reason}\n\n**Проверки до:** {[c['name'] for c in old.get('checks', [])]}\n\n"
                    f"**Проверки после:** {[c['name'] for c in contract['checks']]}")
    print(f"UPDATED: {args.task_id} (revision {task['contract_revisions']}); reason: {reason}")
    return 0


def cmd_dispatch(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    task = get_task(state, args.task_id)
    if task["status"] != "planned":
        raise PipelineError(f"dispatch возможен только из planned; сейчас {task['status']}")
    contract = load_contract(ctx, args.task_id)
    baseline = changed_files(root)
    snapshot_contract_files(root, ctx, args.task_id, contract["files"])
    task.update(baseline=baseline, baseline_hashes={p: file_hash(root / p) for p in baseline},
                baseline_at=now_iso(), baseline_head=git_head(root), status="implementing",
                updated_at=now_iso())
    pack_path = ctx / "packs" / f"{args.task_id}.impl.prompt.md"
    write_text(pack_path, build_impl_prompt(root, contract))
    save_state(ctx, state)
    append_progress(ctx, args.task_id, "dispatch", "OK",
                    f"status=implementing baseline={len(baseline)} pack={rel(root, pack_path)}")
    print(f"DISPATCHED: {args.task_id} → implementing")
    print(f"  pack: {rel(root, pack_path)}\n  baseline: {len(baseline)} файлов (head={task['baseline_head']})")
    print("  next: передать исполнителю pack ДОСЛОВНО")
    return 0


def _run_check(root: Path, check: dict, timeout: int, env: dict) -> dict:
    cwd = root / check["cwd"] if check["cwd"] not in (".", "") else root
    command = expand_cmd(check["cmd"])
    output, code = "", None
    try:
        completed = subprocess.run(command, shell=True, cwd=str(cwd), env=env, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   timeout=timeout if timeout and timeout > 0 else None)
        code = completed.returncode
        output = (completed.stdout or "") + (completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        output = f"TIMEOUT: проверка превысила {timeout} с\n{exc.stdout or ''}{exc.stderr or ''}"
    except OSError as exc:
        output = f"OSError: {exc}\n"
    return {"name": check["name"], "cmd": command, "cwd": check["cwd"], "exit": code, "output": output}


def _check_env() -> dict:
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def cmd_verify(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    task = get_task(state, args.task_id)
    before = task["status"]
    if before == "blocked":
        raise PipelineError(
            f"задача {args.task_id} в blocked: лимит исчерпан (attempts={task['attempts']}, "
            f"review_rounds={task['review_rounds']}). Verify не запускается. Сначала человек: "
            f"pipeline.py set {args.task_id} --status fixing --reason '...' [--reset-attempts] [--reset-review-rounds]")
    if before == "planned":
        raise PipelineError(f"сначала dispatch: python pipeline.py dispatch {args.task_id}")
    if args.skip_scope and not (args.reason or "").strip():
        raise PipelineError("--skip-scope требует --reason: обход scope обязан оставить след (кто/когда/почему)")

    recheck = before == "done"
    contract = load_contract(ctx, args.task_id)
    config = state["config"]
    timeout = int(config.get("check_timeout_seconds", 600) or 0)
    actor = args.by or current_user(root)
    if not recheck:
        task["status"], task["updated_at"] = "verifying", now_iso()
        save_state(ctx, state)

    scope = compute_scope(root, task, config["spill_patterns"])
    if args.skip_scope:
        scope_ok, scope_status = True, "skipped"
        event = {"at": now_iso(), "by": actor, "reason": args.reason.strip(),
                 "status_before": before, "drift": scope["drift"]}
        task.setdefault("skip_scope_events", []).append(event)
        append_progress(ctx, args.task_id, "verify", "SKIP-SCOPE",
                        f"by={actor} reason={event['reason']} drift={scope['drift'] or '[]'}")
        append_decision(ctx, args.task_id, "verify --skip-scope (обход scope)",
                        f"**Кто:** {actor}\n\n**Почему:** {event['reason']}\n\n"
                        f"**Дрейф, который обойдён:** {scope['drift'] or '[]'}")
        print(f"SCOPE: SKIPPED — обойдён дрейф: {scope['drift'] or '[]'} "
              f"(by={actor}, reason={event['reason']})")
    else:
        scope_ok = not scope["drift"]
        scope_status = "ok" if scope_ok else "fail"

    log = [f"# verify {args.task_id} @ {now_iso()}", f"status_before: {before}",
           f"attempt: {task['attempts']}/{config['max_attempts']}",
           f"skip_scope: {bool(args.skip_scope)}", f"scope: {scope_status}",
           f"changed_files: {scope['changed']}", f"touched_since_baseline: {scope['touched']}",
           f"drift: {scope['drift']}"]
    results: list[dict] = []
    if not scope_ok:
        log.append("checks: SKIPPED (scope failure — результаты на загрязнённом дереве не принимаются)")
        print("SCOPE: FAIL — изменения вне контракта:")
        for path in scope["drift"]:
            print(f"  - {path}")
        print(f"  contract: {scope['contract']}")
    else:
        if scope_status != "skipped":
            print(f"SCOPE: {scope_status.upper()} (drift={len(scope['drift'])})")
        env = _check_env()
        for check in contract["checks"]:
            result = _run_check(root, check, timeout, env)
            results.append(result)
            print(f"CHECK {result['name']}: exit={result['exit']} "
                  f"{'PASS' if result['exit'] == 0 else 'FAIL'}")
            log.extend([f"\n## check: {result['name']}", f"cmd: {result['cmd']}",
                        f"cwd: {result['cwd']}", f"exit: {result['exit']}",
                        "--- output ---", result["output"].rstrip("\n") or "(empty)"])

    passed = scope_ok and all(result["exit"] == 0 for result in results)
    result_word = "PASS" if passed else "FAIL"
    log.append(f"\n## RESULT: {result_word}")
    if not scope_ok:
        log.append("reason: scope drift (files outside contract)")
    elif not passed:
        log.append("reason: failed checks: " + ", ".join(r["name"] for r in results if r["exit"] != 0))
    log_path = ctx / "logs" / f"{args.task_id}.verify.log"
    write_text(log_path, "\n".join(log) + "\n")
    checks = [{"name": r["name"], "exit": r["exit"]} for r in results]
    summary = ", ".join(f"{r['name']}={r['exit']}" for r in results) or "skipped(scope)"
    record = {"last": result_word, "log": rel(ctx, log_path), "at": now_iso(),
              "scope": scope_status, "skip_scope": bool(args.skip_scope), "checks": checks}

    if recheck:
        task.setdefault("rechecks", []).append(
            {"at": now_iso(), "result": result_word, "scope": scope_status, "checks": checks})
        task["updated_at"] = now_iso()
        save_state(ctx, state)
        append_progress(ctx, args.task_id, "verify", f"{result_word}(recheck)",
                        f"scope={scope_status} checks={summary} (status остаётся done)")
        print(f"RECHECK: {result_word} (статус done не изменён)\n  log: {rel(root, log_path)}")
        return 0 if passed else 1

    task["verify"] = record
    if passed:
        task["status"], task["updated_at"] = "reviewing", now_iso()
        save_state(ctx, state)
        append_progress(ctx, args.task_id, "verify", "PASS",
                        f"scope={scope_status} checks={summary} "
                        f"attempts={task['attempts']}/{config['max_attempts']}")
        print(f"VERDICT: PASS\n  status: reviewing\n  attempts: {task['attempts']}/{config['max_attempts']}")
        print(f"  log: {rel(root, log_path)}\n  next: python pipeline.py review-packet {args.task_id}")
        return 0

    task["attempts"] = int(task.get("attempts", 0)) + 1
    blocked = task["attempts"] >= int(config["max_attempts"])
    task["status"] = "blocked" if blocked else "fixing"
    task["updated_at"] = now_iso()
    save_state(ctx, state)
    append_progress(ctx, args.task_id, "verify", "FAIL",
                    f"scope={scope_status} checks={summary} "
                    f"attempts={task['attempts']}/{config['max_attempts']}"
                    f"{' → blocked' if blocked else ' → fixing'}")
    if blocked:
        append_decision(ctx, args.task_id, "BLOCKED: лимит механических попыток",
                        f"**Измерение:** attempts={task['attempts']}/{config['max_attempts']}, "
                        f"scope={scope_status}, checks={summary}.\n\n"
                        f"**Решение:** остановка. Третья вариация той же ошибки дороже вопроса человеку.\n\n"
                        f"**Вопрос человеку:** что чинить — код, контракт или проверку? После ответа: "
                        f"`pipeline.py set {args.task_id} --status fixing --reason '...' --reset-attempts`.")
        print(f"VERDICT: FAIL\n  status: blocked ({task['attempts']}/{config['max_attempts']})")
        print("  СТОП: лимит попыток. Нужен человек. Разблокировка:")
        print(f"    python pipeline.py set {args.task_id} --status fixing --reason '...' --reset-attempts")
    else:
        print(f"VERDICT: FAIL\n  status: fixing\n  attempts: {task['attempts']}/{config['max_attempts']}")
        print(f"  log: {rel(root, log_path)}")
    return 1


def cmd_review_packet(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    task = get_task(state, args.task_id)
    if task["status"] != "reviewing":
        raise PipelineError(f"review-packet доступен из reviewing; сейчас {task['status']} (сначала verify PASS)")
    contract = load_contract(ctx, args.task_id)
    packet, new_files = build_review_prompt(root, ctx, task, contract)
    path = ctx / "packs" / f"{args.task_id}.review.prompt.md"
    write_text(path, packet)
    size = len(packet.encode("utf-8"))
    append_progress(ctx, args.task_id, "review-packet", "READY",
                    f"bytes={size} new_files={new_files or '[]'}")
    print(f"REVIEW PACKET: {args.task_id}\n  file: {rel(root, path)}\n  bytes: {size}")
    print(f"  new files: {', '.join(new_files) if new_files else '(нет)'}\n  TOC:")
    for line in packet.splitlines():
        if line.startswith("#"):
            print(f"    {line}")
    print("  next: передать ревьюеру пакет ДОСЛОВНО (без отчёта исполнителя)")
    return 0


def cmd_review(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    task = get_task(state, args.task_id)
    if task["status"] != "reviewing":
        raise PipelineError(f"review доступен из reviewing; сейчас {task['status']}")
    if task["verify"].get("last") != "PASS":
        raise PipelineError("review запрещён: последний verify не PASS — сначала зелёный verify")
    packet_path = ctx / "packs" / f"{args.task_id}.review.prompt.md"
    if not packet_path.exists():
        raise PipelineError(f"нет review-пакета {packet_path}: сначала review-packet {args.task_id}")
    actor = args.by or current_user(root)
    config = state["config"]

    if args.ok:
        task["review"] = {"last": "PASS", "verdict": None, "at": now_iso(),
                          "round": task["review_rounds"]}
        task["status"], task["updated_at"] = "done", now_iso()
        save_state(ctx, state)
        append_progress(ctx, args.task_id, "review", "PASS", f"by={actor} → done")
        append_decision(ctx, args.task_id, "ревью пройдено",
                        f"**Вердикт:** PASS\n\n**Кто:** {actor}\n\n**Пакет:** {rel(root, packet_path)}")
        print("REVIEW: PASS → done")
        return 0

    verdict = (args.verdict or "").strip()
    if not verdict:
        raise PipelineError("--fail требует --verdict с текстом вердикта ревьюера")
    task["review_rounds"] = int(task.get("review_rounds", 0)) + 1
    rounds = task["review_rounds"]
    max_rounds = int(config["max_review_rounds"])
    task["review"] = {"last": "FAIL", "verdict": verdict, "at": now_iso(), "round": rounds}
    blocked = rounds >= max_rounds
    task["status"] = "blocked" if blocked else "fixing"
    task["updated_at"] = now_iso()
    save_state(ctx, state)
    append_progress(ctx, args.task_id, "review", "FAIL",
                    f"by={actor} round={rounds}/{max_rounds} verdict={verdict}"
                    f"{' → blocked' if blocked else ' → fixing'}")
    append_decision(ctx, args.task_id, "ревью: FAIL",
                    f"**Раунд:** {rounds}/{max_rounds}\n\n**Вердикт ревьюера:** {verdict}\n\n"
                    f"**Действие:** {'blocked — вопрос человеку' if blocked else 'fixing — раунд исправлений'}")
    if blocked:
        print(f"REVIEW: FAIL → blocked (раунд {rounds}/{max_rounds})")
        print("  СТОП: лимит содержательных раундов. Нужен человек. Разблокировка:")
        print(f"    python pipeline.py set {args.task_id} --status fixing --reason '...' --reset-review-rounds")
    else:
        print(f"REVIEW: FAIL → fixing (раунд {rounds}/{max_rounds})\n  verdict: {verdict}")
    return 0


def cmd_set(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    task = get_task(state, args.task_id)
    before = task["status"]
    task["status"] = args.status
    if args.reset_attempts:
        task["attempts"] = 0
    if args.reset_review_rounds:
        task["review_rounds"] = 0
    task["updated_at"] = now_iso()
    save_state(ctx, state)
    actor = args.by or current_user(root)
    reason = args.reason or "(без причины)"
    reset = [name for flag, name in ((args.reset_attempts, "attempts=0"),
                                     (args.reset_review_rounds, "review_rounds=0")) if flag]
    append_progress(ctx, args.task_id, "set", f"{before}→{args.status}",
                    f"by={actor} reason={reason}" + (f" reset={','.join(reset)}" if reset else ""))
    append_decision(ctx, args.task_id, "ручной перевод статуса",
                    f"**Кто:** {actor}\n\n**Почему:** {reason}\n\n**Переход:** {before} → {args.status}"
                    + (f"\n\n**Сброс:** {', '.join(reset)}" if reset else ""))
    print(f"SET: {args.task_id} {before} → {args.status}"
          + (f" (reset: {', '.join(reset)})" if reset else ""))
    return 0


def cmd_note(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    get_task(state, args.task_id)
    text = " ".join(args.text).strip()
    if not text:
        raise PipelineError("note: пустой текст")
    append_decision(ctx, args.task_id, "заметка",
                    f"**Кто:** {args.by or current_user(root)}\n\n{text}")
    print(f"NOTE: {args.task_id} → decisions.md")
    return 0


def cmd_list(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    config = state["config"]
    tasks = state.get("tasks", {})
    if not tasks:
        print("Задач нет. Добавьте контракт: python pipeline.py add --file <contract.json>")
        return 0
    print(f"{'ID':<8} {'STATUS':<13} {'ATT':<6} {'REV':<6} {'VERIFY':<7} TITLE")
    print("-" * 100)
    for task_id in sorted(tasks):
        task = tasks[task_id]
        print(f"{task_id:<8} {task.get('status', '?'):<13} "
              f"{str(task.get('attempts', 0)) + '/' + str(config['max_attempts']):<6} "
              f"{str(task.get('review_rounds', 0)) + '/' + str(config['max_review_rounds']):<6} "
              f"{(task.get('verify') or {}).get('last') or '-':<7} {task.get('title', '')}")
    totals = state.get("totals", {})
    print("-" * 100)
    print("Totals: " + ", ".join(f"{k}={v}" for k, v in totals.items() if k != "total")
          + f" | total={totals.get('total', len(tasks))}")
    return 0


def cmd_status(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    totals = state.get("totals", {})
    print(f"State: {ctx / 'state.json'}")
    print("Totals: " + ", ".join(f"{k}={v}" for k, v in totals.items() if k != "total")
          + f" | total={totals.get('total', 0)}")
    for task_id in sorted(state.get("tasks", {})):
        task = state["tasks"][task_id]
        print(f"  {task_id}: {task['status']} (attempts={task.get('attempts', 0)}, "
              f"review_rounds={task.get('review_rounds', 0)})")
    return 0


def cmd_show(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    task = get_task(state, args.task_id)
    print(json.dumps(load_contract(ctx, args.task_id), ensure_ascii=False, indent=2))
    print("\n--- state ---")
    print(json.dumps({k: v for k, v in task.items() if k != "baseline_hashes"},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_config(args, root: Path, ctx: Path) -> int:
    state = load_state(ctx)
    config = state["config"]
    changed = False
    for pattern in args.spill_add or []:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise PipelineError(f"невалидный regex spill-паттерна {pattern!r}: {exc}") from exc
        if pattern not in config["spill_patterns"]:
            config["spill_patterns"].append(pattern)
            changed = True
    for field, value, minimum in (("max_attempts", args.max_attempts, 1),
                                  ("max_review_rounds", args.max_review_rounds, 1),
                                  ("check_timeout_seconds", args.check_timeout, 0)):
        if value is not None:
            if value < minimum:
                raise PipelineError(f"{field}: значение должно быть >= {minimum}")
            config[field] = value
            changed = True
    if changed:
        save_state(ctx, state)
        append_decision(ctx, "CONFIG", "конфигурация изменена",
                        f"**Кто:** {current_user(root)}\n\n**Новое значение:** "
                        f"max_attempts={config['max_attempts']}, "
                        f"max_review_rounds={config['max_review_rounds']}, "
                        f"check_timeout={config['check_timeout_seconds']}, "
                        f"spill_patterns={config['spill_patterns']}")
        print("CONFIG: обновлено")
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline.py",
                                     description="Агентный конвейер: контракты, exit-код, ревью, лимиты.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_text: str):
        cmd = sub.add_parser(name, help=help_text)
        cmd.set_defaults(func=func)
        return cmd

    add("init", cmd_init, "создать каталоги и state.json")
    p = add("add", cmd_add, "валидировать контракт и зарегистрировать задачу")
    p.add_argument("--file", required=True)
    p = add("update", cmd_update, "заменить контракт (planned/fixing/blocked)")
    p.add_argument("task_id"); p.add_argument("--file", required=True); p.add_argument("--reason")
    p = add("dispatch", cmd_dispatch, "impl-pack + baseline")
    p.add_argument("task_id")
    p = add("verify", cmd_verify, "scope-check + проверки; вердикт по exit-коду")
    p.add_argument("task_id"); p.add_argument("--skip-scope", action="store_true")
    p.add_argument("--reason"); p.add_argument("--by")
    p = add("review-packet", cmd_review_packet, "пакет ревьюеру (diff + критерии)")
    p.add_argument("task_id")
    p = add("review", cmd_review, "зафиксировать вердикт ревьюера")
    p.add_argument("task_id")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--ok", action="store_true"); group.add_argument("--fail", action="store_true")
    p.add_argument("--verdict"); p.add_argument("--by")
    p = add("set", cmd_set, "ручной перевод статуса")
    p.add_argument("task_id"); p.add_argument("--status", required=True, choices=STATUSES)
    p.add_argument("--reason"); p.add_argument("--reset-attempts", action="store_true")
    p.add_argument("--reset-review-rounds", action="store_true"); p.add_argument("--by")
    p = add("note", cmd_note, "заметка в decisions.md")
    p.add_argument("task_id"); p.add_argument("text", nargs="+"); p.add_argument("--by")
    add("list", cmd_list, "таблица задач")
    p = add("status", cmd_status, "машинное состояние")
    p.add_argument("--json", action="store_true")
    p = add("show", cmd_show, "контракт + состояние задачи")
    p.add_argument("task_id")
    p = add("config", cmd_config, "показать/изменить конфигурацию")
    p.add_argument("--spill-add", action="append"); p.add_argument("--max-attempts", type=int)
    p.add_argument("--max-review-rounds", type=int); p.add_argument("--check-timeout", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        root_arg, context_arg, rest = split_globals(argv)
    except PipelineError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 2
    root = Path(root_arg).resolve() if root_arg else (
        discover_git_root(Path(__file__).resolve().parent) or Path.cwd().resolve())
    ctx = Path(context_arg).resolve() if context_arg else root / "context" / "agent-pipeline"
    parser = build_parser()
    if not rest:
        parser.print_help()
        return 0
    args = parser.parse_args(rest)
    try:
        ensure_structure(ctx)
        return int(args.func(args, root, ctx) or 0)
    except PipelineError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ОШИБКА: прервано", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
