"""Вызов существующих SECURITY DEFINER RPC напрямую через psycopg2.

Наследуем атомарность и инварианты RPC (apply_job_atomic, delete_user_cascade, …),
не дублируя бизнес-логику в Python (см. спеку §1.2).
"""
from typing import Any

from django.db import connection


class RpcError(RuntimeError):
    pass


def call_rpc(name: str, *args: Any) -> Any:
    """SELECT * FROM name(...); возвращает первую строку как dict (jsonb → dict)."""
    if not name.replace("_", "").isalnum():
        raise RpcError("недопустимое имя RPC: %r" % name)
    placeholders = ", ".join(["%s"] * len(args))
    sql = "SELECT * FROM %s(%s)" % (name, placeholders)
    with connection.cursor() as cur:
        cur.execute(sql, args)
        if cur.description is None:
            return None
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None


def call_rpc_void(name: str, *args: Any) -> None:
    if not name.replace("_", "").isalnum():
        raise RpcError("недопустимое имя RPC: %r" % name)
    placeholders = ", ".join(["%s"] * len(args))
    with connection.cursor() as cur:
        cur.execute("SELECT %s(%s)" % (name, placeholders), args)
        cur.fetchall()


def _replace_through_raw(table: str, owner_col: str, owner_id, other_col: str, other_ids) -> int:
    """Атомарная замена строк составного-PK M2M (user_skills/job_skills): DELETE+INSERT."""
    from django.db import transaction

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("DELETE FROM %s WHERE %s = %%s" % (table, owner_col), [owner_id])
            for other_id in other_ids:
                cur.execute(
                    "INSERT INTO %s (%s, %s) VALUES (%%s, %%s) ON CONFLICT DO NOTHING" % (table, owner_col, other_col),
                    [owner_id, other_id],
                )
            cur.execute("SELECT count(*) FROM %s WHERE %s = %%s" % (table, owner_col), [owner_id])
            return cur.fetchone()[0]


def sync_user_skills_raw(user_id, skill_ids) -> int:
    """Замена user_skills (в LIVE-БД нет RPC sync_user_skills — миграция 144
    применена не полностью), поэтому raw-SQL в транзакции."""
    return _replace_through_raw("user_skills", "user_id", user_id, "skill_id", skill_ids)


def sync_job_skills_raw(job_id, skill_ids) -> int:
    return _replace_through_raw("job_skills", "job_id", job_id, "skill_id", skill_ids)

def call_rpc_rows(name: str, *args: Any) -> list[dict]:
    """SELECT * FROM name(...); ВСЕ строки как list[dict] (таблицы-возвраты)."""
    if not name.replace("_", "").isalnum():
        raise RpcError("недопустимое имя RPC: %r" % name)
    placeholders = ", ".join(["%s"] * len(args))
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM %s(%s)" % (name, placeholders), args)
        if cur.description is None:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def call_rpc_as_user(name: str, user_id, *args: Any) -> Any:
    """Вызов RPC от имени пользователя: SET LOCAL request.jwt.claims в транзакции.

    Контракт: ряд функций (file_report и др.) читает автора из GUC
    request.jwt.claims (паритет PostgREST + pgrst_pre_request). Прямой вызов
    из Django без claims вернёт not_authenticated, поэтому claims ставим явно.
    """
    import json as _json

    from django.db import transaction

    if not name.replace("_", "").isalnum():
        raise RpcError("недопустимое имя RPC: %r" % name)
    claims = _json.dumps({"user_id": str(user_id), "role": "authenticated"})
    placeholders = ", ".join(["%s"] * len(args))
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET LOCAL request.jwt.claims = %s", [claims])
            cur.execute("SELECT * FROM %s(%s)" % (name, placeholders), args)
            if cur.description is None:
                return None
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            return dict(zip(cols, row)) if row else None
