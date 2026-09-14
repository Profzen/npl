from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

from app.services.safe_sql_builder import ALLOWED_ACTIONS


ALLOWED_SOURCES = {"events", "users", "objects", "actions"}
ALLOWED_DIMENSIONS = {
    "user", "object", "action", "host", "program", "timestamp", "day", "return_code"
}
ALLOWED_OPERATIONS = {"count", "count_distinct", "min", "max", "avg"}
ALLOWED_FILTER_OPERATORS = {"eq", "ne", "contains", "in", "success", "failure"}
ALLOWED_TIME_MODES = {
    "all", "today", "yesterday", "relative_last", "current", "previous",
    "between", "before", "after", "previous_weekday",
}
ALLOWED_TIME_UNITS = {"minute", "hour", "day", "week", "month", "year"}
ALLOWED_RESPONSES = {"detail", "list", "ranking", "count", "comparison"}
_SAFE_VALUE = re.compile(r"^[\w $#.\-/:'À-ÿ]{1,160}$", re.UNICODE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9_$#]+", " ", text.upper()).strip()


def _catalog_mentions(question: str, values: Iterable[str]) -> list[str]:
    padded = f" {_norm(question)} "
    found: list[str] = []
    for item in values:
        canonical = _text(item).upper()
        needle = _norm(canonical)
        if needle and f" {needle} " in padded:
            found.append(canonical)
    return list(dict.fromkeys(found))


def _safe_list(raw: Any, allowed: set[str]) -> list[str]:
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw[:12]:
        value = _text(item).lower()
        if value in allowed and value not in result:
            result.append(value)
    return result


def _normalise_time(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {"mode": "all"}
    mode = _text(raw.get("mode")).lower()
    if mode not in ALLOWED_TIME_MODES:
        return {"mode": "all"}
    result: dict[str, Any] = {"mode": mode}
    unit = _text(raw.get("unit")).lower()
    if unit in ALLOWED_TIME_UNITS:
        result["unit"] = unit
    if mode == "relative_last":
        try:
            value = int(raw.get("value"))
        except (TypeError, ValueError):
            return {"mode": "all"}
        if not (1 <= value <= 10000) or unit not in ALLOWED_TIME_UNITS:
            return {"mode": "all"}
        result["value"] = value
    if mode in {"current", "previous"} and unit not in {"day", "week", "month", "year"}:
        return {"mode": "all"}
    if mode in {"between", "after"}:
        start = _text(raw.get("start"))
        if not _ISO_DATE.fullmatch(start):
            return {"mode": "all"}
        result["start"] = start
    if mode in {"between", "before"}:
        end = _text(raw.get("end"))
        if not _ISO_DATE.fullmatch(end):
            return {"mode": "all"}
        result["end"] = end
    if mode == "previous_weekday":
        weekday = _text(raw.get("weekday")).lower()
        if weekday not in {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}:
            return {"mode": "all"}
        result["weekday"] = weekday
    return result


def normalize_query_plan(
    question: str,
    raw: Mapping[str, Any] | None,
    known_users: Iterable[str],
    known_objects: Iterable[str],
) -> dict[str, Any]:
    """Validate the model's semantic plan without reinterpreting the user's wording."""
    payload = raw if isinstance(raw, Mapping) else {}
    status = _text(payload.get("status")).lower()
    if status not in {"query", "clarification", "refusal"}:
        status = "clarification"

    source = _text(payload.get("source")).lower()
    if source not in ALLOWED_SOURCES:
        source = "events"
    dimensions = _safe_list(payload.get("dimensions"), ALLOWED_DIMENSIONS)
    group_by = _safe_list(payload.get("group_by"), ALLOWED_DIMENSIONS)

    calculation = None
    raw_calculation = payload.get("calculation")
    if isinstance(raw_calculation, Mapping):
        operation = _text(raw_calculation.get("operation")).lower()
        field = _text(raw_calculation.get("field")).lower()
        if operation in ALLOWED_OPERATIONS and field in ALLOWED_DIMENSIONS | {"event"}:
            calculation = {"operation": operation, "field": field}

    filters: list[dict[str, Any]] = []
    mentioned_users = set(_catalog_mentions(question, known_users))
    mentioned_objects = set(_catalog_mentions(question, known_objects))
    raw_filters = payload.get("filters")
    if isinstance(raw_filters, list):
        for raw_filter in raw_filters[:20]:
            if not isinstance(raw_filter, Mapping):
                continue
            field = _text(raw_filter.get("field")).lower()
            operator = _text(raw_filter.get("operator")).lower()
            value = raw_filter.get("value")
            if field not in ALLOWED_DIMENSIONS or operator not in ALLOWED_FILTER_OPERATORS:
                continue
            if operator in {"success", "failure"}:
                filters.append({"field": "return_code", "operator": operator, "value": None})
                continue
            if field == "return_code" and operator == "eq" and _text(value).upper() in {"FAILURE", "FAILED", "ECHEC", "ÉCHEC"}:
                filters.append({"field": "return_code", "operator": "failure", "value": None})
                continue
            if field == "return_code" and operator == "eq" and _text(value).upper() in {"SUCCESS", "SUCCEEDED", "REUSSI", "RÉUSSI"}:
                filters.append({"field": "return_code", "operator": "success", "value": None})
                continue
            values = value if isinstance(value, list) else [value]
            clean_values = [_text(item).upper() for item in values if _text(item) and _SAFE_VALUE.fullmatch(_text(item))]
            if field == "action":
                clean_values = [item for item in clean_values if item in ALLOWED_ACTIONS]
            if field == "user":
                clean_values = [item.replace(" ", "_") for item in clean_values if item.replace(" ", "_") in mentioned_users]
            if field == "object":
                clean_values = [item for item in clean_values if item in mentioned_objects]
            if clean_values:
                filters.append({"field": field, "operator": operator, "value": clean_values})

    existing_users = {value for f in filters if f["field"] == "user" for value in f["value"]}
    existing_objects = {value for f in filters if f["field"] == "object" for value in f["value"]}
    for user in _catalog_mentions(question, known_users):
        if user not in existing_users:
            filters.append({"field": "user", "operator": "eq", "value": [user]})
    for obj in _catalog_mentions(question, known_objects):
        if obj not in existing_objects:
            filters.append({"field": "object", "operator": "eq", "value": [obj]})

    order_by: list[dict[str, str]] = []
    raw_order = payload.get("order_by")
    if isinstance(raw_order, Mapping):
        raw_order = [raw_order]
    if isinstance(raw_order, list):
        for item in raw_order[:5]:
            if not isinstance(item, Mapping):
                continue
            field = _text(item.get("field")).lower()
            direction = _text(item.get("direction")).lower()
            if field in ALLOWED_DIMENSIONS | {"event_count", "value"} and direction in {"asc", "desc"}:
                order_by.append({"field": field, "direction": direction})

    try:
        limit = int(payload.get("limit")) if payload.get("limit") not in (None, "") else None
    except (TypeError, ValueError):
        limit = None
    if limit is not None and not 1 <= limit <= 200:
        limit = None

    response_mode = _text(payload.get("response_mode")).lower()
    if response_mode not in ALLOWED_RESPONSES:
        response_mode = "detail"
    if response_mode in {"ranking", "count"} and calculation is None:
        calculation = {"operation": "count", "field": "event"}
    if source in {"users", "objects", "actions"} and response_mode == "detail":
        response_mode = "list"

    comparison_ranges: list[dict[str, Any]] = []
    raw_ranges = payload.get("comparison_ranges")
    if isinstance(raw_ranges, list):
        for index, item in enumerate(raw_ranges[:4]):
            if not isinstance(item, Mapping):
                continue
            period = _normalise_time(item.get("time"))
            if period.get("mode") == "all":
                continue
            label = _text(item.get("label"))[:40] or f"Période {index + 1}"
            comparison_ranges.append({"label": label, "time": period})

    clarification = _text(payload.get("clarification")) or None

    if status == "query" and response_mode == "ranking" and calculation is not None and not group_by:
        if source in {"users", "objects", "actions"}:
            group_by = [{"users": "user", "objects": "object", "actions": "action"}[source]]
        elif len(dimensions) == 1:
            group_by = list(dimensions)

    if status == "query" and source in {"users", "objects", "actions"} and (calculation is not None or group_by):
        source = "events"

    if status == "query" and source in {"users", "objects", "actions"}:
        source_field = {"users": "user", "objects": "object", "actions": "action"}[source]
        incompatible_order = any(item["field"] not in {source_field} for item in order_by)
        if calculation is not None or group_by or incompatible_order:
            status = "clarification"
            clarification = "La demande semble mélanger une liste de référence et une analyse d’événements. Pouvez-vous préciser le résultat attendu ?"
    if status == "query" and response_mode == "comparison" and len(comparison_ranges) < 2:
        status = "clarification"
        clarification = "Quelles sont les deux périodes que vous souhaitez comparer ?"
    if status == "query" and response_mode == "ranking" and (calculation is None or not group_by):
        status = "clarification"
        clarification = "Quel élément souhaitez-vous classer et selon quel critère ?"

    if status == "clarification" and not clarification:
        clarification = "Je n’ai pas identifié précisément les informations à rechercher. Pouvez-vous reformuler la demande ?"
    if status == "refusal" and not clarification:
        clarification = "Je peux consulter le journal d’audit, mais je ne peux pas modifier la base de données."

    return {
        "status": status,
        "source": source,
        "dimensions": dimensions,
        "calculation": calculation,
        "filters": filters,
        "time": _normalise_time(payload.get("time")),
        "comparison_ranges": comparison_ranges,
        "group_by": group_by,
        "order_by": order_by,
        "limit": limit,
        "response_mode": response_mode,
        "clarification": clarification,
    }

