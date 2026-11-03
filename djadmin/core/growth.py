"""First-touch attribution and cohort/retention analytics (J157).

Privacy: only UTM campaign parameters, an external referrer *host* and the
landing path are kept, plus one ``user_activity`` row per user per day. No IP
addresses, user agents or full referrer URLs are stored.
"""
import logging
from datetime import date, timedelta
from urllib.parse import urlparse

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)

UTM_FIELDS = ("source", "medium", "campaign", "content", "term")
UTM_MAX_LEN = 120
ACTIVITY_CACHE_SECONDS = 26 * 3600

MONTHS_RU = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)


# ── First-touch attribution ─────────────────────────────────────────────────
def _external_referrer_host(request):
    raw = (request.META.get("HTTP_REFERER") or "").strip()
    if not raw:
        return ""
    try:
        host = urlparse(raw).netloc.lower().split("@")[-1]
        own = request.get_host().lower()
    except Exception:  # DisallowedHost and malformed URLs
        return ""
    if not host:
        return ""
    if host == own or host == "www." + own or "www." + host == own:
        return ""
    return host[:UTM_MAX_LEN]


def capture_first_touch(request):
    """Return attribution data from the current query string, or ``None``.

    Called on every request while the session has no attribution yet, so the
    first campaign the visitor arrives from wins.
    """
    data = {}
    for field in UTM_FIELDS:
        value = (request.GET.get("utm_%s" % field) or "").strip()
        if value:
            data[field] = value[:UTM_MAX_LEN]
    if not data.get("source") and not data.get("campaign"):
        return None
    data["landing"] = (request.path or "/")[:300]
    referrer = _external_referrer_host(request)
    if referrer:
        data["referrer"] = referrer
    data["captured_at"] = timezone.now().isoformat()
    return data


# ── Daily activity ──────────────────────────────────────────────────────────
def record_activity(user_id, day=None):
    """Remember that ``user_id`` was active today (one row per user/day)."""
    day = day or timezone.localdate()
    key = "activity:seen:%s:%s" % (user_id, day.isoformat())
    try:
        if not cache.add(key, 1, ACTIVITY_CACHE_SECONDS):
            return False
    except Exception:
        # Analytics must never break a request; without fast dedupe skip the
        # write entirely instead of adding a query to every page view.
        return False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_activity (user_id, day) VALUES (%s, %s) "
                "ON CONFLICT (user_id, day) DO NOTHING",
                [str(user_id), day],
            )
    except Exception:
        logger.debug("record_activity failed for %s", user_id, exc_info=True)
        return False
    return True


def activity_summary():
    today = timezone.localdate()
    week_ago = today - timedelta(days=6)
    month_ago = today - timedelta(days=29)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                count(DISTINCT ua.user_id) FILTER (WHERE ua.day = %s),
                count(DISTINCT ua.user_id) FILTER (WHERE ua.day >= %s),
                count(DISTINCT ua.user_id) FILTER (WHERE ua.day >= %s)
            FROM user_activity ua
            JOIN profiles p ON p.id = ua.user_id
            WHERE p.role IN ('worker', 'employer')
            """,
            [today, week_ago, month_ago],
        )
        dau, wau, mau = cursor.fetchone()
        cursor.execute(
            """
            SELECT count(*), count(*) FILTER (WHERE created_at >= %s)
            FROM profiles
            WHERE role IN ('worker', 'employer')
            """,
            [month_ago],
        )
        total_users, new_users = cursor.fetchone()
    return {
        "dau": dau or 0,
        "wau": wau or 0,
        "mau": mau or 0,
        "total_users": total_users or 0,
        "new_users": new_users or 0,
    }


def _daily_counts(table, date_column, days, where=""):
    start = timezone.localdate() - timedelta(days=days - 1)
    sql = (
        "SELECT %s::date AS day, count(*) FROM %s "
        "WHERE %s >= %%s %s GROUP BY 1" % (date_column, table, date_column, where)
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, [start])
        return {row[0]: row[1] for row in cursor.fetchall()}


def signup_series(days=7):
    return _daily_counts(
        "profiles", "created_at", days, "AND role IN ('worker', 'employer')"
    )


def activity_series(days=7):
    start = timezone.localdate() - timedelta(days=days - 1)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ua.day, count(DISTINCT ua.user_id)
            FROM user_activity ua
            JOIN profiles p ON p.id = ua.user_id
            WHERE ua.day >= %s AND p.role IN ('worker', 'employer')
            GROUP BY ua.day
            """,
            [start],
        )
        return {row[0]: row[1] for row in cursor.fetchall()}


# ── Cohorts / retention ─────────────────────────────────────────────────────
def _month_start(value, offset=0):
    index = value.year * 12 + (value.month - 1) + offset
    return date(index // 12, index % 12 + 1, 1)


def _month_label(value):
    return "%s %s" % (MONTHS_RU[value.month - 1], value.year)


def retention_matrix(months=6, weeks=8):
    """Cohorts by registration month and weekly retention.

    Week 0 is the registration week. A user is retained in week N when they
    have at least one ``user_activity`` row in that period.
    """
    today = timezone.localdate()
    first_month = _month_start(today, -(months - 1))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT to_char(date_trunc('month', created_at), 'YYYY-MM') AS cohort,
                   date_trunc('month', created_at)::date AS cohort_start,
                   count(*) AS size
            FROM profiles
            WHERE role IN ('worker', 'employer') AND created_at >= %s
            GROUP BY 1, 2
            ORDER BY 2 DESC
            """,
            [first_month],
        )
        sizes = {
            (row[0], row[1]): row[2] for row in cursor.fetchall()
        }
        cursor.execute(
            """
            SELECT cohort, week_no, count(DISTINCT user_id) FROM (
                SELECT to_char(date_trunc('month', c.created_at), 'YYYY-MM') AS cohort,
                       (ua.day - c.created_at::date) / 7 AS week_no,
                       c.id AS user_id
                FROM profiles c
                JOIN user_activity ua ON ua.user_id = c.id
                WHERE c.role IN ('worker', 'employer')
                  AND c.created_at >= %s
                  AND ua.day >= c.created_at::date
            ) t
            WHERE week_no BETWEEN 0 AND %s
            GROUP BY cohort, week_no
            """,
            [first_month, weeks - 1],
        )
        active = {(row[0], row[1]): row[2] for row in cursor.fetchall()}

    result = []
    for (cohort, cohort_start), size in sizes.items():
        elapsed_weeks = (today - cohort_start).days // 7
        cells = []
        for week in range(weeks):
            not_yet = week > elapsed_weeks
            count = active.get((cohort, week), 0)
            cells.append({
                "week": week,
                "active": None if not_yet else count,
                "pct": None if not_yet else (round(count / size * 100) if size else 0),
            })
        result.append({
            "cohort": cohort,
            "label": _month_label(cohort_start),
            "size": size,
            "weeks": cells,
        })
    result.sort(key=lambda row: row["cohort"], reverse=True)
    return result


# ── Acquisition ─────────────────────────────────────────────────────────────
def acquisition_breakdown(days=90):
    start = timezone.localdate() - timedelta(days=days - 1)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(NULLIF(acquisition->>'source', ''), '') AS source,
                   COALESCE(NULLIF(acquisition->>'medium', ''), '') AS medium,
                   COALESCE(NULLIF(acquisition->>'campaign', ''), '') AS campaign,
                   count(*) AS users,
                   count(*) FILTER (
                       WHERE EXISTS (SELECT 1 FROM jobs j WHERE j.employer_id = p.id)
                          OR EXISTS (SELECT 1 FROM applications a WHERE a.worker_id = p.id)
                   ) AS activated
            FROM profiles p
            WHERE role IN ('worker', 'employer') AND created_at >= %s
            GROUP BY 1, 2, 3
            ORDER BY users DESC, source, medium, campaign
            """,
            [start],
        )
        rows = cursor.fetchall()
    return [
        {
            "source": source or "Без метки",
            "medium": medium or "—",
            "campaign": campaign or "—",
            "users": users,
            "activated": activated,
            "pct": round(activated / users * 100) if users else 0,
        }
        for source, medium, campaign, users, activated in rows
    ]
