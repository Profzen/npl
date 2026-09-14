from __future__ import annotations

from typing import Any, Mapping


AUDIT_TABLE = "SMART2DSECU.UNIFIED_AUDIT_DATA"

COLUMN_SQL = {
    "user": "DBUSERNAME",
    "object": "OBJECT_NAME",
    "action": "ACTION_NAME",
    "host": "USERHOST",
    "program": "CLIENT_PROGRAM_NAME",
    "timestamp": "EVENT_TIMESTAMP",
    "day": "TRUNC(EVENT_TIMESTAMP)",
    "return_code": "RETURNCODE",
}
COLUMN_ALIAS = {
    "user": "DBUSERNAME",
    "object": "OBJECT_NAME",
    "action": "ACTION_NAME",
    "host": "USERHOST",
    "program": "CLIENT_PROGRAM_NAME",
    "timestamp": "EVENT_TIMESTAMP",
    "day": "EVENT_DAY",
    "return_code": "RETURNCODE",
}
SOURCE_DIMENSION = {"users": "user", "objects": "object", "actions": "action"}
WEEKDAY_ANCHOR = {
    "monday": "2000-01-03",
    "tuesday": "2000-01-04",
    "wednesday": "2000-01-05",
    "thursday": "2000-01-06",
    "friday": "2000-01-07",
    "saturday": "2000-01-08",
    "sunday": "2000-01-09",
}


class GeneralPlanError(ValueError):
    pass


def _configured_limit(default_limit: int, requested: Any) -> int:
    try:
        configured = max(1, min(200, int(default_limit)))
    except (TypeError, ValueError):
        configured = 10
    if requested in (None, ""):
        return configured
    try:
        return min(configured, max(1, int(requested)))
    except (TypeError, ValueError):
        return configured


def _date_value(value: str) -> str:
    return value.replace("T", " ") + (" 00:00:00" if len(value) == 10 else ":00" if len(value) == 16 else "")


def _time_clause(spec: Mapping[str, Any], binds: dict[str, Any], prefix: str = "time") -> str | None:
    mode = str(spec.get("mode") or "all")
    unit = str(spec.get("unit") or "")
    if mode == "all":
        return None
    if mode == "today":
        return "EVENT_TIMESTAMP >= TRUNC(SYSDATE) AND EVENT_TIMESTAMP < TRUNC(SYSDATE) + 1"
    if mode == "yesterday":
        return "EVENT_TIMESTAMP >= TRUNC(SYSDATE) - 1 AND EVENT_TIMESTAMP < TRUNC(SYSDATE)"
    if mode == "relative_last":
        value = int(spec["value"])
        if unit == "week":
            binds[f"{prefix}_value"] = value * 7
            return f"EVENT_TIMESTAMP >= SYSTIMESTAMP - NUMTODSINTERVAL(:{prefix}_value, 'DAY')"
        if unit in {"minute", "hour", "day"}:
            binds[f"{prefix}_value"] = value
            oracle_unit = unit.upper()
            return f"EVENT_TIMESTAMP >= SYSTIMESTAMP - NUMTODSINTERVAL(:{prefix}_value, '{oracle_unit}')"
        months = value * (12 if unit == "year" else 1)
        binds[f"{prefix}_value"] = months
        return f"EVENT_TIMESTAMP >= ADD_MONTHS(SYSTIMESTAMP, -:{prefix}_value)"
    if mode in {"current", "previous"}:
        start_shift = -1 if mode == "previous" else 0
        if unit == "day":
            start = f"TRUNC(SYSDATE){' - 1' if start_shift else ''}"
            return f"EVENT_TIMESTAMP >= {start} AND EVENT_TIMESTAMP < {start} + 1"
        if unit == "week":
            start = f"TRUNC(SYSDATE, 'IW'){' - 7' if start_shift else ''}"
            return f"EVENT_TIMESTAMP >= {start} AND EVENT_TIMESTAMP < {start} + 7"
        if unit == "month":
            start = f"ADD_MONTHS(TRUNC(SYSDATE, 'MM'), {start_shift})"
            return f"EVENT_TIMESTAMP >= {start} AND EVENT_TIMESTAMP < ADD_MONTHS({start}, 1)"
        start = f"ADD_MONTHS(TRUNC(SYSDATE, 'YYYY'), {start_shift * 12})"
        return f"EVENT_TIMESTAMP >= {start} AND EVENT_TIMESTAMP < ADD_MONTHS({start}, 12)"
    if mode in {"between", "after"}:
        binds[f"{prefix}_start"] = _date_value(str(spec["start"]))
        start_clause = f"EVENT_TIMESTAMP >= TO_TIMESTAMP(:{prefix}_start, 'YYYY-MM-DD HH24:MI:SS')"
        if mode == "after":
            return start_clause
    else:
        start_clause = ""
    if mode in {"between", "before"}:
        binds[f"{prefix}_end"] = _date_value(str(spec["end"]))
        end_clause = f"EVENT_TIMESTAMP < TO_TIMESTAMP(:{prefix}_end, 'YYYY-MM-DD HH24:MI:SS')"
        return f"{start_clause} AND {end_clause}" if start_clause else end_clause
    if mode == "previous_weekday":
        anchor = WEEKDAY_ANCHOR[str(spec["weekday"])]
        start = f"TRUNC(SYSDATE) - MOD(TRUNC(SYSDATE) - DATE '{anchor}', 7)"
        return f"EVENT_TIMESTAMP >= {start} AND EVENT_TIMESTAMP < {start} + 1"
    raise GeneralPlanError("Période invalide")


def _filter_clauses(filters: Any, binds: dict[str, Any]) -> list[str]:
    clauses: list[str] = []
    if not isinstance(filters, list):
        return clauses
    for index, item in enumerate(filters):
        if not isinstance(item, Mapping):
            continue
        field = str(item.get("field") or "")
        operator = str(item.get("operator") or "")
        if operator == "success":
            clauses.append("NVL(RETURNCODE, 0) = 0")
            continue
        if operator == "failure":
            clauses.append("NVL(RETURNCODE, 0) <> 0")
            continue
        if field not in COLUMN_SQL or field in {"timestamp", "day"}:
            raise GeneralPlanError("Filtre non autorisé")
        column = COLUMN_SQL[field]
        values = item.get("value")
        if not isinstance(values, list) or not values:
            continue
        if field == "return_code":
            try:
                clean_values: list[Any] = [int(value) for value in values]
            except (TypeError, ValueError) as exc:
                raise GeneralPlanError("Code retour invalide") from exc
            expression = f"NVL({column}, 0)"
        else:
            clean_values = [str(value).upper() for value in values]
            expression = f"UPPER({column})"
        if operator in {"eq", "in", "ne"}:
            names: list[str] = []
            for value_index, value in enumerate(clean_values):
                name = f"filter_{index}_{value_index}"
                binds[name] = value
                names.append(f":{name}")
            predicate = f"{expression} IN ({', '.join(names)})"
            clauses.append(f"NOT ({predicate})" if operator == "ne" else predicate)
        elif operator == "contains":
            name = f"filter_{index}"
            binds[name] = f"%{clean_values[0]}%"
            clauses.append(f"{expression} LIKE :{name} ESCAPE '\\'")
        else:
            raise GeneralPlanError("Opérateur de filtre invalide")
    return clauses


def _select_dimension(field: str) -> str:
    if field not in COLUMN_SQL:
        raise GeneralPlanError("Dimension invalide")
    return f"{COLUMN_SQL[field]} AS {COLUMN_ALIAS[field]}" if field == "day" else COLUMN_SQL[field]


def _metric_expression(calculation: Mapping[str, Any], grouped: bool) -> tuple[str, str]:
    operation = str(calculation.get("operation") or "")
    field = str(calculation.get("field") or "")
    column = COLUMN_SQL.get(field)
    alias = "EVENT_COUNT" if grouped and operation == "count" else "VALUE"
    if operation == "count":
        return "COUNT(*)", alias
    if operation == "count_distinct" and column:
        return f"COUNT(DISTINCT {column})", alias
    if operation in {"min", "max"} and column and field in {"timestamp", "return_code"}:
        return f"{operation.upper()}({column})", alias
    if operation == "avg" and field == "return_code":
        return "AVG(RETURNCODE)", alias
    raise GeneralPlanError("Calcul incompatible avec le champ demandé")


def _order_clause(order_by: Any, selected_dimensions: list[str], has_metric: bool) -> str:
    if not isinstance(order_by, list):
        return ""
    items: list[str] = []
    for item in order_by:
        if not isinstance(item, Mapping):
            continue
        field = str(item.get("field") or "")
        direction = str(item.get("direction") or "").upper()
        if direction not in {"ASC", "DESC"}:
            continue
        if field == "event_count" and has_metric:
            expression = "EVENT_COUNT"
        elif field == "value" and has_metric:
            expression = "VALUE"
        elif field in selected_dimensions:
            expression = COLUMN_ALIAS[field]
        elif field == "timestamp" and not selected_dimensions:
            expression = "EVENT_TIMESTAMP"
        else:
            continue
        items.append(f"{expression} {direction}")
    return " ORDER BY " + ", ".join(items) if items else ""


def build_general_query(plan: Mapping[str, Any], default_limit: int) -> tuple[str, dict[str, Any]]:
    if str(plan.get("status") or "") != "query":
        raise GeneralPlanError("Seul un plan de consultation peut être exécuté")
    source = str(plan.get("source") or "")
    if source not in {"events", "users", "objects", "actions"}:
        raise GeneralPlanError("Source non autorisée")
    limit = _configured_limit(default_limit, plan.get("limit"))
    binds: dict[str, Any] = {}
    base_clauses = _filter_clauses(plan.get("filters"), binds)

    comparison_ranges = plan.get("comparison_ranges")
    if isinstance(comparison_ranges, list) and comparison_ranges:
        expressions: list[str] = []
        range_clauses: list[str] = []
        for index, item in enumerate(comparison_ranges):
            if not isinstance(item, Mapping):
                continue
            clause = _time_clause(item.get("time") or {}, binds, f"period_{index}")
            if not clause:
                continue
            range_clauses.append(f"({clause})")
            expressions.append(f"SUM(CASE WHEN {clause} THEN 1 ELSE 0 END) AS PERIOD_{index + 1}_COUNT")
        if len(expressions) < 2:
            raise GeneralPlanError("Une comparaison exige au moins deux périodes")
        where_parts = [*base_clauses, "(" + " OR ".join(range_clauses) + ")"]
        where = " WHERE " + " AND ".join(f"({item})" for item in where_parts)
        return f"SELECT {', '.join(expressions)} FROM {AUDIT_TABLE}{where}", binds

    time_clause = _time_clause(plan.get("time") or {}, binds)
    if time_clause:
        base_clauses.append(time_clause)
    where = " WHERE " + " AND ".join(f"({item})" for item in base_clauses) if base_clauses else ""

    if source in SOURCE_DIMENSION:
        field = SOURCE_DIMENSION[source]
        column = COLUMN_SQL[field]
        clauses = list(base_clauses)
        clauses.append(f"{column} IS NOT NULL")
        source_where = " WHERE " + " AND ".join(f"({item})" for item in clauses)
        distinct_sql = f"SELECT DISTINCT {column} FROM {AUDIT_TABLE}{source_where}"
        sql = (
            f"SELECT {column}, COUNT(*) OVER () AS AUDITAI_TOTAL_AVAILABLE "
            f"FROM ({distinct_sql}) ORDER BY {column} ASC FETCH FIRST {limit} ROWS ONLY"
        )
        return sql, binds

    dimensions = [str(item) for item in (plan.get("group_by") or []) if str(item) in COLUMN_SQL]
    calculation = plan.get("calculation")
    if isinstance(calculation, Mapping):
        metric, alias = _metric_expression(calculation, bool(dimensions))
        select_items = [_select_dimension(field) for field in dimensions]
        select_items.append(f"{metric} AS {alias}")
        group = ""
        if dimensions:
            group = " GROUP BY " + ", ".join(COLUMN_SQL[field] for field in dimensions)

        if dimensions and alias == "EVENT_COUNT" and str(plan.get("response_mode") or "") == "ranking":
            ranking_clauses = list(base_clauses)
            ranking_clauses.extend(
                f"{COLUMN_SQL[field]} IS NOT NULL" for field in dimensions
            )
            ranking_where = (
                " WHERE " + " AND ".join(f"({item})" for item in ranking_clauses)
                if ranking_clauses else ""
            )
            inner_sql = (
                f"SELECT {', '.join(select_items)} FROM {AUDIT_TABLE}"
                f"{ranking_where}{group}"
            )
            requested_order = plan.get("order_by") or []
            direction = "DESC"
            if requested_order and isinstance(requested_order[0], Mapping):
                candidate = str(requested_order[0].get("direction") or "").upper()
                if candidate in {"ASC", "DESC"}:
                    direction = candidate
            aliases = [COLUMN_ALIAS[field] for field in dimensions]
            stable_order = ", ".join(f"{item} ASC" for item in aliases)
            outer_order = f"EVENT_COUNT {direction}" + (f", {stable_order}" if stable_order else "")
            sql = (
                f"SELECT {', '.join(aliases)}, EVENT_COUNT, "
                f"COUNT(*) OVER (PARTITION BY EVENT_COUNT) AS AUDITAI_TIE_COUNT "
                f"FROM ({inner_sql}) ORDER BY {outer_order} FETCH FIRST {limit} ROWS ONLY"
            )
            return sql, binds

        order = _order_clause(plan.get("order_by"), dimensions, True)
        if not order and dimensions:
            order = f" ORDER BY {alias} DESC"
        sql = f"SELECT {', '.join(select_items)} FROM {AUDIT_TABLE}{where}{group}{order}"
        if dimensions:
            sql += f" FETCH FIRST {limit} ROWS ONLY"
        return sql, binds

    requested_dimensions = [str(item) for item in (plan.get("dimensions") or []) if str(item) in COLUMN_SQL]
    if requested_dimensions:
        select = ", ".join(_select_dimension(field) for field in requested_dimensions)
    else:
        requested_dimensions = ["user", "action", "object", "timestamp", "host", "return_code"]
        select = "DBUSERNAME, ACTION_NAME, OBJECT_NAME, EVENT_TIMESTAMP, USERHOST, RETURNCODE"
    order = _order_clause(plan.get("order_by"), requested_dimensions, False)
    if not order:
        order = " ORDER BY EVENT_TIMESTAMP DESC"
    return f"SELECT {select} FROM {AUDIT_TABLE}{where}{order} FETCH FIRST {limit} ROWS ONLY", binds

