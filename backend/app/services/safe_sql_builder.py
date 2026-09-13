from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


AUDIT_TABLE = "SMART2DSECU.UNIFIED_AUDIT_DATA"
ALLOWED_ACTIONS = {
    "LOGON", "LOGOFF", "SELECT", "INSERT", "UPDATE", "DELETE", "GRANT",
    "REVOKE", "ALTER", "TRUNCATE", "CREATE USER", "DROP USER",
    "ALTER USER", "CREATE TABLE", "DROP TABLE",
}
ALLOWED_PERIODS = {
    None, "today", "yesterday", "last_friday", "range_weekdays",
    "last_14_days", "night_range", "this_week", "this_month",
    "last_30_days", "compare_today_yesterday",
}
ALLOWED_AGGREGATES = {
    None, "count_distinct_user", "top_action", "compare",
    "top_host", "top_user", "top_objects",
}
_SAFE_VALUE = re.compile(r"^[A-Z0-9_$# .-]{1,128}$")


class UnsafeIntentError(ValueError):
    pass


@dataclass(frozen=True)
class SafeQuery:
    sql: str
    binds: dict[str, Any]


def _values(intent: Mapping[str, Any], key: str) -> list[str]:
    raw = intent.get(key) or []
    if not isinstance(raw, list):
        raise UnsafeIntentError(f"{key} doit être une liste")
    values: list[str] = []
    for item in raw[:20]:
        value = str(item).strip().upper().replace(" ", "_") if key == "users" else str(item).strip().upper()
        if not value or not _SAFE_VALUE.fullmatch(value):
            raise UnsafeIntentError(f"Valeur interdite dans {key}")
        values.append(value)
    return list(dict.fromkeys(values))


def _add_in_filter(
    clauses: list[str],
    binds: dict[str, Any],
    column: str,
    prefix: str,
    values: list[str],
) -> None:
    if not values:
        return
    names = []
    for index, value in enumerate(values):
        name = f"{prefix}_{index}"
        binds[name] = value
        names.append(f":{name}")
    clauses.append(f"UPPER({column}) IN ({', '.join(names)})")


def _period_clause(period: str | None) -> str | None:
    clauses = {
        "today": "EVENT_TIMESTAMP >= TRUNC(SYSDATE) AND EVENT_TIMESTAMP < TRUNC(SYSDATE) + 1",
        "yesterday": "EVENT_TIMESTAMP >= TRUNC(SYSDATE) - 1 AND EVENT_TIMESTAMP < TRUNC(SYSDATE)",
        "last_friday": (
            "EVENT_TIMESTAMP >= TRUNC(SYSDATE) - MOD(TRUNC(SYSDATE) - DATE '2000-01-07', 7) "
            "AND EVENT_TIMESTAMP < TRUNC(SYSDATE) - MOD(TRUNC(SYSDATE) - DATE '2000-01-07', 7) + 1"
        ),
        "range_weekdays": (
            "EVENT_TIMESTAMP >= TRUNC(SYSDATE, 'IW') "
            "AND EVENT_TIMESTAMP < TRUNC(SYSDATE, 'IW') + 3"
        ),
        "last_14_days": "EVENT_TIMESTAMP >= TRUNC(SYSDATE) - 13 AND EVENT_TIMESTAMP < TRUNC(SYSDATE) + 1",
        "night_range": (
            "(TO_NUMBER(TO_CHAR(EVENT_TIMESTAMP, 'HH24')) >= 22 "
            "OR TO_NUMBER(TO_CHAR(EVENT_TIMESTAMP, 'HH24')) < 6)"
        ),
        "this_week": (
            "EVENT_TIMESTAMP >= TRUNC(SYSDATE, 'IW') "
            "AND EVENT_TIMESTAMP < TRUNC(SYSDATE, 'IW') + 7"
        ),
        "this_month": (
            "EVENT_TIMESTAMP >= TRUNC(SYSDATE, 'MM') "
            "AND EVENT_TIMESTAMP < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1)"
        ),
        "last_30_days": "EVENT_TIMESTAMP >= TRUNC(SYSDATE) - 29 AND EVENT_TIMESTAMP < TRUNC(SYSDATE) + 1",
    }
    return clauses.get(period)


def build_safe_audit_query(intent: Mapping[str, Any], default_limit: int = 200) -> SafeQuery:
    status = str(intent.get("status") or "").strip().lower()
    if status != "query":
        raise UnsafeIntentError("Seules les intentions query produisent du SQL")

    period = intent.get("period")
    aggregate = intent.get("aggregate")
    if period not in ALLOWED_PERIODS:
        raise UnsafeIntentError("Période non autorisée")
    if aggregate not in ALLOWED_AGGREGATES:
        raise UnsafeIntentError("Agrégat non autorisé")

    users = _values(intent, "users")
    objects = _values(intent, "objects")
    actions = _values(intent, "actions")
    unknown_actions = set(actions) - ALLOWED_ACTIONS
    if unknown_actions:
        raise UnsafeIntentError(f"Actions inconnues: {sorted(unknown_actions)}")

    try:
        configured_limit = max(1, min(200, int(default_limit)))
    except (TypeError, ValueError):
        configured_limit = 10
    raw_limit = intent.get("limit")
    if raw_limit in (None, ""):
        limit = configured_limit
    else:
        try:
            requested_limit = max(1, int(raw_limit))
        except (TypeError, ValueError):
            requested_limit = configured_limit
        limit = min(configured_limit, requested_limit)

    clauses: list[str] = []
    binds: dict[str, Any] = {}
    _add_in_filter(clauses, binds, "DBUSERNAME", "user", users)
    _add_in_filter(clauses, binds, "OBJECT_NAME", "object", objects)
    _add_in_filter(clauses, binds, "ACTION_NAME", "action", actions)

    if bool(intent.get("failed_only")):
        clauses.append("NVL(RETURNCODE, 0) <> 0")

    if period == "compare_today_yesterday":
        if aggregate != "compare":
            raise UnsafeIntentError("La comparaison temporelle exige l'agrégat compare")
        clauses.append("EVENT_TIMESTAMP >= TRUNC(SYSDATE) - 1")
        clauses.append("EVENT_TIMESTAMP < TRUNC(SYSDATE) + 1")
    else:
        period_sql = _period_clause(period)
        if period_sql:
            clauses.append(period_sql)

    where = " WHERE " + " AND ".join(f"({clause})" for clause in clauses) if clauses else ""

    if aggregate == "count_distinct_user":
        select = "SELECT COUNT(DISTINCT DBUSERNAME) AS USER_COUNT"
        suffix = ""
    elif aggregate == "top_action":
        select = "SELECT ACTION_NAME, COUNT(*) AS EVENT_COUNT"
        suffix = " GROUP BY ACTION_NAME ORDER BY EVENT_COUNT DESC FETCH FIRST 1 ROWS ONLY"
    elif aggregate == "top_host":
        select = "SELECT USERHOST, COUNT(*) AS EVENT_COUNT"
        suffix = " GROUP BY USERHOST ORDER BY EVENT_COUNT DESC FETCH FIRST 1 ROWS ONLY"
    elif aggregate == "top_user":
        select = "SELECT DBUSERNAME, COUNT(*) AS EVENT_COUNT"
        suffix = " GROUP BY DBUSERNAME ORDER BY EVENT_COUNT DESC FETCH FIRST 1 ROWS ONLY"
    elif aggregate == "top_objects":
        select = "SELECT OBJECT_NAME, COUNT(*) AS EVENT_COUNT"
        suffix = f" GROUP BY OBJECT_NAME ORDER BY EVENT_COUNT DESC FETCH FIRST {min(limit, 20)} ROWS ONLY"
    elif aggregate == "compare":
        select = (
            "SELECT SUM(CASE WHEN EVENT_TIMESTAMP >= TRUNC(SYSDATE) THEN 1 ELSE 0 END) AS TODAY_COUNT, "
            "SUM(CASE WHEN EVENT_TIMESTAMP < TRUNC(SYSDATE) THEN 1 ELSE 0 END) AS YESTERDAY_COUNT"
        )
        suffix = ""
    else:
        select = (
            "SELECT DBUSERNAME, ACTION_NAME, OBJECT_NAME, EVENT_TIMESTAMP, USERHOST, "
            "CLIENT_PROGRAM_NAME, RETURNCODE"
        )
        suffix = f" ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST {limit} ROWS ONLY"

    sql = f"{select} FROM {AUDIT_TABLE}{where}{suffix}"
    if not sql.lstrip().upper().startswith(("SELECT ", "WITH ")):
        raise UnsafeIntentError("Requête non SELECT")
    return SafeQuery(sql=sql, binds=binds)

