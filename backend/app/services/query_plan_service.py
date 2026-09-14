from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

from app.services.intent_policy import detect_actions
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


_NUMBER_WORDS = {
    "UN": 1, "UNE": 1, "DEUX": 2, "TROIS": 3, "QUATRE": 4, "CINQ": 5,
    "SIX": 6, "SEPT": 7, "HUIT": 8, "NEUF": 9, "DIX": 10, "ONZE": 11,
    "DOUZE": 12, "TREIZE": 13, "QUATORZE": 14, "QUINZE": 15, "SEIZE": 16,
    "DIX SEPT": 17, "DIX HUIT": 18, "DIX NEUF": 19, "VINGT": 20,
}


def _number_requested(text: str) -> int | None:
    words = "|".join(
        sorted((re.escape(item) for item in _NUMBER_WORDS), key=len, reverse=True)
    )
    pattern = re.compile(
        rf"\b(\d{{1,3}}|{words})\b\s+"
        rf"(?=(?:DERNIER|DERNIERE|RECENT|RECENTE|PREMIER|PREMIERE|"
        rf"UTILISATEUR|USER|COMPTE|PERSONNE|ACTION|OPERATION|EVENEMENT|"
        rf"TABLE|OBJET|POSTE|MACHINE))"
    )
    for match in pattern.finditer(text):
        suffix = text[match.end():]
        if re.match(
            r"\s*(?:DERNIERS?|DERNIERES?)?\s*"
            r"(?:MINUTES?|HEURES?|JOURS?|SEMAINES?|MOIS|ANS?|ANNEES?)\b",
            suffix,
        ):
            continue
        raw = re.sub(r"\s+", " ", match.group(1))
        value = int(raw) if raw.isdigit() else _NUMBER_WORDS.get(raw)
        if value is not None:
            return max(1, min(200, value))
    return None


def _mentioned_dimensions(text: str) -> list[str]:
    patterns = (
        ("user", r"\b(QUI|UTILISATEURS?|USERS?|COMPTES?|PERSONNES?|INDIVIDUS?|AUTEURS?|ACTEURS?)\b"),
        ("object", r"\b(TABLES?|OBJETS?|RESSOURCES?)\b"),
        ("host", r"\b(POSTES?|MACHINES?|HOTES?)\b"),
        ("action", r"\b(ACTIONS?|ACTIVITES?|OPERATIONS?|EVENEMENTS?)\b"),
        ("timestamp", r"\b(DATES?|HEURES?|QUAND)\b"),
    )
    return [field for field, pattern in patterns if re.search(pattern, text)]


def _has_specific_action(text: str) -> bool:
    canonical = any(re.search(rf"\b{re.escape(action)}\b", text) for action in ALLOWED_ACTIONS)
    semantic = bool(re.search(
        r"\b(SUPPRIM|EFFAC|AJOUT|INSER|MODIFI|MISE A JOUR|CONSULT|LECTUR|"
        r"CONNEX|DECONNEX|ATTRIBU|RETIR|DROITS?|PRIVILEG|VID|PURG)\w*\b",
        text,
    ))
    return canonical or semantic


def _question_semantics(question: str) -> dict[str, Any]:
    text = _norm(question)
    dimensions = _mentioned_dimensions(text)
    minimum = bool(re.search(
        r"\b(MOIN|MOINS|MOINDRE|MINIMUM|MINIMAL|PLUS FAIBLE)\b", text
    ))
    maximum = bool(re.search(
        r"\b(PLUS D ACTIONS?|PLUS D ACTIVITES?|PLUS D OPERATIONS?|"
        r"PLUS ACTIF|PLUS ACTIVE|DAVANTAGE D|MAXIMUM|MAXIMAL|PLUS FREQUENT|"
        r"PLUS D(?:E)? (?:ACTIONS?|ACTIVITES?|OPERATIONS?|EVENEMENTS?|ECHECS?|ERREURS?|"
        r"SUPPRESSIONS?|CREATIONS?|TABLES?|OBJETS?))\b",
        text,
    ))
    ranking_direction = "asc" if minimum else ("desc" if maximum else None)
    recency = bool(re.search(
        r"\b(DERNIERS?|DERNIERES?|RECENTS?|RECENTES?)\b\s+"
        r"(?:\w+\s+){0,2}(UTILISATEURS?|USERS?|COMPTES?|PERSONNES?|ACTIONS?|"
        r"ACTIVITES?|OPERATIONS?|EVENEMENTS?|TABLES?|OBJETS?)\b",
        text,
    ))
    singular = bool(
        re.search(r"\b(LE|LA|L|QUEL|QUELLE)\s+(DERNIER|DERNIERE|PLUS)\b", text)
        or (ranking_direction and re.search(r"\bLE PLUS D(?:E)?\b", text))
    )
    explicit_actions = detect_actions(text)
    outcome = (
        "failure" if re.search(r"\b(ECHECS?|ECHOUES?|ERREURS?|REFUSEES?|REJETEES?)\b", text)
        else "success" if re.search(r"\b(REUSSIS?|REUSSITES?|SUCCES)\b", text)
        else None
    )
    return {
        "text": text,
        "dimensions": dimensions,
        "ranking_direction": ranking_direction,
        "recency": recency and ranking_direction is None and bool(re.search(
            r"\b(BASE|ACTION|ACTIVITE|OPERATION|EVENEMENT|AUDIT|JOURNAL)\w*\b", text
        )),
        "limit": _number_requested(text) or (1 if singular else None),
        "specific_action": bool(explicit_actions) or _has_specific_action(text),
        "explicit_actions": explicit_actions,
        "outcome": outcome,
        "time": _time_requested(text),
    }


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


def _time_requested(text: str) -> dict[str, Any] | None:
    units = {
        "MINUTE": "minute", "MINUTES": "minute",
        "HEURE": "hour", "HEURES": "hour",
        "JOUR": "day", "JOURS": "day",
        "SEMAINE": "week", "SEMAINES": "week",
        "MOIS": "month",
        "AN": "year", "ANS": "year", "ANNEE": "year", "ANNEES": "year",
    }
    number_words = "|".join(
        sorted((re.escape(item) for item in _NUMBER_WORDS), key=len, reverse=True)
    )
    match = re.search(
        rf"\b(\d{{1,4}}|{number_words})\s+"
        rf"(?:DERNIERS?|DERNIERES?)?\s*"
        rf"(MINUTES?|HEURES?|JOURS?|SEMAINES?|MOIS|ANS?|ANNEES?)\b",
        text,
    )
    if match:
        raw_value = re.sub(r"\s+", " ", match.group(1))
        value = int(raw_value) if raw_value.isdigit() else _NUMBER_WORDS.get(raw_value)
        unit = units.get(match.group(2))
        if value and unit:
            return {"mode": "relative_last", "unit": unit, "value": value}
    if re.search(r"\bAUJOURD HUI\b", text):
        return {"mode": "today"}
    if re.search(r"\bHIER\b", text):
        return {"mode": "yesterday"}
    if re.search(r"\b(?:CE|CETTE)\s+(JOUR|SEMAINE|MOIS|ANNEE)\b", text):
        raw_unit = re.search(r"\b(JOUR|SEMAINE|MOIS|ANNEE)\b", text)
        return {"mode": "current", "unit": units[raw_unit.group(1)]}
    if re.search(r"\b(?:DERNIER|DERNIERE)\s+(JOUR|SEMAINE|MOIS|ANNEE)\b", text):
        raw_unit = re.search(r"\b(JOUR|SEMAINE|MOIS|ANNEE)\b", text)
        return {"mode": "previous", "unit": units[raw_unit.group(1)]}
    return None


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

    cues = _question_semantics(question)
    ranking_field = next(
        (field for field in ("user", "object", "host", "action") if field in cues["dimensions"]),
        group_by[0] if group_by else (dimensions[0] if dimensions else None),
    )
    if status == "clarification" and cues["ranking_direction"] and ranking_field:
        status = "query"
        clarification = None
    if status == "query" and cues["ranking_direction"]:
        if ranking_field:
            source = "events"
            dimensions = [ranking_field]
            calculation = {"operation": "count", "field": "event"}
            group_by = [ranking_field]
            order_by = [{"field": "event_count", "direction": cues["ranking_direction"]}]
            limit = cues["limit"] or limit
            response_mode = "ranking"
            if not cues["specific_action"]:
                filters = [item for item in filters if item["field"] != "action"]
    elif status == "query" and cues["recency"]:
        source = "events"
        calculation = None
        group_by = []
        order_by = [{"field": "timestamp", "direction": "desc"}]
        limit = cues["limit"] or limit
        response_mode = "detail"
        for field in cues["dimensions"]:
            if field not in dimensions:
                dimensions.append(field)
        if not cues["specific_action"]:
            filters = [item for item in filters if item["field"] != "action"]

    if status == "query" and cues["explicit_actions"]:
        filters = [item for item in filters if item["field"] != "action"]
        filters.append({
            "field": "action", "operator": "in", "value": cues["explicit_actions"]
        })
    if status == "query" and cues["outcome"]:
        filters = [item for item in filters if item["field"] != "return_code"]
        filters.append({
            "field": "return_code", "operator": cues["outcome"], "value": None
        })

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
        "time": cues["time"] or _normalise_time(payload.get("time")),
        "comparison_ranges": comparison_ranges,
        "group_by": group_by,
        "order_by": order_by,
        "limit": limit,
        "response_mode": response_mode,
        "clarification": clarification,
    }

