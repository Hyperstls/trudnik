"""Full-text search helpers (J132).

Uses the precomputed ``search_vector`` GIN columns. Only Cyrillic words are
passed to ``to_tsquery`` (the vectors are built with the Russian dictionary);
queries with Latin letters/digits fall back to the previous icontains filter.
"""
import re

_CYR_WORD = re.compile(r"[А-Яа-яЁё]{2,}")


def ts_query(text: str) -> str:
    """Return a safe ``to_tsquery`` expression or '' for fallback."""
    value = (text or "").strip()
    if len(value) < 3 or re.search(r"[A-Za-z0-9]", value):
        return ""
    words = _CYR_WORD.findall(value)[:8]
    if not words:
        return ""
    escaped = [word.replace("'", "''") for word in words]
    escaped[-1] += ":*"
    return " & ".join(escaped)
