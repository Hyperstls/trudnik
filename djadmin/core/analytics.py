"""First-party aggregate funnel counters (J123).

Only aggregate numbers are stored in Redis; no cookies, IP addresses or user
identifiers are persisted. Anonymous job views and PWA launches are deduplicated
client-side (localStorage) and sent as one beacon per browser/day. Daily keys
expire after 90 days.
"""
from datetime import date, timedelta

from django.core.cache import cache

EVENTS = ("job_view", "application_sent", "job_created", "install", "app_open", "app_return")
RETENTION_DAYS = 90


def _key(event, day):
    return "analytics:%s:%s" % (event, day.isoformat())


def incr(event, amount=1):
    if event not in EVENTS:
        return
    key = _key(event, date.today())
    try:
        if cache.add(key, amount, RETENTION_DAYS * 86400):
            return
        try:
            cache.incr(key, amount)
        except ValueError:
            cache.set(key, amount, RETENTION_DAYS * 86400)
    except Exception:
        pass  # analytics must never break a request


def series(event, days=7):
    today = date.today()
    return [
        (today - timedelta(days=offset), int(cache.get(_key(event, today - timedelta(days=offset))) or 0))
        for offset in range(days - 1, -1, -1)
    ]


def totals(days=7):
    return {event: sum(value for _, value in series(event, days)) for event in EVENTS}


def track_job_view(request, job_id):
    """Authenticated views: once per session/job/day.

    Anonymous views are counted by ``static/js/job-view.js`` once per browser/day
    (localStorage marker), so server-side tracking must not count them again.
    """
    if not request.user.is_authenticated:
        return
    if request.session.session_key:
        key = "analytics:view:%s:%s:%s" % (
            request.session.session_key, job_id, date.today().isoformat(),
        )
        try:
            if not cache.add(key, 1, 86400):
                return
        except Exception:
            pass
    incr("job_view")
