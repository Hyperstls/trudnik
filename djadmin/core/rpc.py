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


def sync_user_skills_raw(user_id, skill_ids) -> int:
    """Атомарная замена user_skills (в LIVE-БД нет RPC sync_user_skills — миграция 144
    применена не полностью), поэтому DELETE+INSERT в транзакции вызова."""
    from django.db import transaction

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("DELETE FROM user_skills WHERE user_id = %s", [user_id])
            for skill_id in skill_ids:
                cur.execute(
                    "INSERT INTO user_skills (user_id, skill_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [user_id, skill_id],
                )
            cur.execute("SELECT count(*) FROM user_skills WHERE user_id = %s", [user_id])
            return cur.fetchone()[0]


def sync_job_skills_raw(job_id, skill_ids) -> int:
    """Атомарная замена job_skills (составной PK, отдельного RPC нет)."""
    from django.db import transaction

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("DELETE FROM job_skills WHERE job_id = %s", [job_id])
            for skill_id in skill_ids:
                cur.execute(
                    "INSERT INTO job_skills (job_id, skill_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [job_id, skill_id],
                )
            cur.execute("SELECT count(*) FROM job_skills WHERE job_id = %s", [job_id])
            return cur.fetchone()[0]
