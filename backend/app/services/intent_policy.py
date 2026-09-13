from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

from app.services.safe_sql_builder import ALLOWED_ACTIONS, ALLOWED_AGGREGATES, ALLOWED_PERIODS


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.upper().replace("-", " ").replace("_", " ")
    return re.sub(r"[^A-Z0-9_$#]+", " ", value).strip()


def _catalog_matches(question_norm: str, values: Iterable[str]) -> list[str]:
    padded = f" {question_norm} "
    matches: list[str] = []
    for value in values:
        canonical = str(value).strip().upper().replace(" ", "_")
        needle = _norm(canonical).replace("_", " ")
        if needle and f" {needle} " in padded:
            matches.append(canonical)
    return sorted(set(matches), key=lambda item: (-len(item), item))


def _detect_actions(text: str) -> list[str]:
    actions: list[str] = []
    create_account = re.search(
        r"\b(CREE|CREER|CREATION)\b.*\b(COMPTES?|UTILISATEURS?)\b", text
    )
    drop_account = re.search(
        r"\b(SUPRIME|SUPRIMER|SUPPRIME|SUPPRIMER|SUPPRESSIONS?)\b.*"
        r"\b(COMPTES?|UTILISATEURS?)\b",
        text,
    )
    if create_account:
        actions.append("CREATE USER")
    if drop_account:
        actions.append("DROP USER")
    if not drop_account and (
        re.search(
            r"\b(SUPRIME|SUPRIMER|SUPPRIME|SUPPRIMER|SUPPRESSIONS?|EFFACE|EFFACER)\b",
            text,
        )
        or re.search(r"\bRETIRE\b.*\b(LIGNES?|ENREGISTREMENTS?)\b", text)
    ):
        actions.append("DELETE")
    if re.search(r"\b(DONNE|DONNER|ACCORDE|ACCORDER)\b.*\b(DROITS?|PRIVILEGES?)\b", text):
        actions.append("GRANT")
    if (
        re.search(r"\b(PRIVILEGES?|DROITS?)\b.*\b(RETIRE|RETIRES|REVOQUE|REVOQUES)\b", text)
        or re.search(r"\bRETRAITS?\b.*\b(AUTORISATIONS?|DROITS?|PRIVILEGES?)\b", text)
    ):
        actions.append("REVOKE")
    if re.search(r"\b(VIDE|VIDER|TRUNCATE|PURGE|PURGER)\b", text):
        actions.append("TRUNCATE")
    if re.search(
        r"\b(CONNEXIONS?|CONNECTE|LOGIN|LOGON)\b|"
        r"\bOUVERTURES?\s+DE\s+SESSION\b|"
        r"\bSESSIONS?\b.*\b(REFUSEES?|REJETEES?|ECHOUES?)\b",
        text,
    ):
        actions.append("LOGON")
    if re.search(r"\b(CONSULTE|CONSULTEES|LECTURE|SELECT)\b", text):
        actions.append("SELECT")
    if re.search(r"\bMODIFICATIONS?\b", text):
        actions.extend(["UPDATE", "ALTER"])
    elif re.search(r"\b(MODIFIE|MODIFIER)\b", text):
        actions.append("UPDATE")
    return list(dict.fromkeys(actions))

def _detect_period(text: str) -> str | None:
    if re.search(r"\bHIER\b.*\bAUJOURD HUI\b|\bAUJOURD HUI\b.*\bHIER\b|COMPARE.*\bHIER\b.*\bAUJOURD HUI\b", text):
        return "compare_today_yesterday"
    if re.search(r"\b(AUJOURD HUI|CE JOUR|CE MATIN|JOURNEE EN COURS)\b|DANS LA JOURNEE", text):
        return "today"
    if re.search(r"\bHIER\b|\bLA VEILLE\b", text):
        return "yesterday"
    if re.search(r"VENDREDI\s+(DERNIER|PRECEDENT)", text):
        return "last_friday"
    if re.search(r"ENTRE\s+LUNDI\s+ET\s+MERCREDI", text):
        return "range_weekdays"
    if re.search(
        r"DEUX\s+(DERNIERES?\s+)?SEMAINES(\s+ECOULEES?)?|QUINZAINE|14\s+JOURS?\s+(DERNIERS?|ECOULES?)|"
        r"14\s+DERNIERS?\s+JOURS",
        text,
    ):
        return "last_14_days"
    if (
        re.search(r"ENTRE\s+22H?\s+ET\s+6H?|\bNUIT\b", text)
        or re.search(r"APRES\s+22\s+HEURES?.*AVANT\s+6\s+HEURES?", text)
    ):
        return "night_range"
    if re.search(r"CETTE\s+SEMAINE|DEPUIS\s+LUNDI", text):
        return "this_week"
    if re.search(r"CE\s+MOIS|MOIS CI|MOIS\s+EN\s+COURS", text):
        return "this_month"
    if re.search(
        r"TRENTE\s+(DERNIERS?\s+JOURS|JOURNEES?\s+PASSEES?)|30\s+JOURS?|MOIS\s+ECOULE",
        text,
    ):
        return "last_30_days"
    return None

def _detect_aggregate(text: str) -> tuple[str | None, int]:
    if re.search(
        r"(COMBIEN|NOMBRE).*(UTILISATEURS?|COMPTES?).*(DIFFERENTS?|DISTINCTS?)",
        text,
    ):
        return "count_distinct_user", 200
    if re.search(r"(ACTION|OPERATION).*(PLUS\s+FREQUENTE|DOMINANTE)", text):
        return "top_action", 200
    if re.search(r"COMPARE.*\bHIER\b.*\bAUJOURD HUI\b|NOMBRE.*\bHIER\b.*\bAUJOURD HUI\b", text):
        return "compare", 200
    if re.search(
        r"(QUEL\s+POSTE|POSTE|MACHINE).*(PLUS|MAXIMUM).*(ECHECS?|ERREURS?|CONNEXIONS?)",
        text,
    ):
        return "top_host", 200
    if re.search(r"QUEL\s+UTILISATEUR.*PLUS\s+SOUVENT|UTILISATEUR.*PLUS\s+CONNECTE", text):
        return "top_user", 200
    if (
        re.search(r"CINQ\s+TABLES?.*PLUS\s+CONSULTEES?|5\s+TABLES?.*PLUS\s+CONSULTEES?", text)
        or re.search(r"(RESSOURCE|OBJET|TABLE).*(PREMIERE|PLUS|NUMERO UN).*CONSULT", text)
    ):
        return "top_objects", 5
    return None, 200


def _has_time_cue(text: str) -> bool:
    return bool(re.search(
        r"\b(JOUR|JOURNEE|HIER|VEILLE|SEMAINE|QUINZAINE|MOIS|VENDREDI|"
        r"HEURE|NUIT|MATIN|AUJOURD HUI|PRECEDENTE?|COURANTE?|ECOULEE?)\b|"
        r"\b(14|30|22|6)\b",
        text,
    ))


def _has_action_cue(text: str) -> bool:
    return bool(re.search(
        r"\b(EFFAC|SUPPR|RAYE|DETRUIT|DROIT|PRIVILEGE|AUTORISATION|HABILITATION|"
        r"REVOQU|ANNULE|PURG|VIDE|ZERO|SESSION|CONNEX|AUTHENT|LOGIN|LOGON|"
        r"CONSULT|LECTURE|MODIFI|CHANGE|AJOUT|INSER|CREATE|DROP|ALTER|GRANT|"
        r"REVOKE|TRUNCATE|SELECT|UPDATE|DELETE)\w*\b",
        text,
    ))


def _has_aggregate_cue(text: str) -> bool:
    return bool(re.search(
        r"\b(COMBIEN|NOMBRE|TOTAL|PLUS|MAXIMUM|MAX|DOMINANTE|FREQUENTE|"
        r"CLASSEMENT|PREMIER|NUMERO UN|COMPARE)\b",
        text,
    ))

def _is_mutation_order(text: str) -> bool:
    return bool(re.match(
        r"^(SUPPRIME|SUPPRIMER|EFFACE|EFFACER|VIDE|VIDER|TRONQUE|TRUNCATE|"
        r"METS|METTRE|REMETS|REMETTRE|REINITIALISE|REINITIALISER|PURGE|PURGER|"
        r"MODIFIE|MODIFIER|INSERE|INSERER|ACCORDE|REVOQUE)\b",
        text,
    ))


def _needs_clarification(text: str) -> bool:
    if re.search(r"\bFAIT\s+CA\b|\b(CETTE|CET)\s+(TABLE|RESSOURCE|OBJET)\b|"
        r"^MONTRE MOI LA TABLE$|"
        r"^ET POUR\b|^REGARDE\s+CA$|DE QUELLE (OPERATION|ACTION) PARLES", text):
        return True
    if (
        re.search(r"\bVENDREDI\b", text)
        and not re.search(r"VENDREDI\s+(DERNIER|PRECEDENT)", text)
    ):
        return True
    if re.search(r"\bDERNIERES?\s+MODIFICATIONS?\b", text) and _detect_period(text) is None:
        return True
    return False


def normalize_intent(
    question: str,
    raw_intent: Mapping[str, Any],
    known_users: Iterable[str],
    known_objects: Iterable[str],
) -> dict[str, Any]:
    text = _norm(question)
    users = _catalog_matches(text, known_users)
    objects = _catalog_matches(text, known_objects)
    actions = _detect_actions(text)
    period = _detect_period(text)
    aggregate, limit = _detect_aggregate(text)

    # Preserve a model classification only where deterministic language has no stronger signal.
    status = str(raw_intent.get("status") or "query").lower()
    clarification: str | None = None
    if _is_mutation_order(text):
        status = "refusal"
        clarification = "Je peux consulter les journaux d'audit, mais pas modifier la base."
        actions = []
    elif _needs_clarification(text):
        status = "clarification"
        clarification = str(raw_intent.get("clarification") or "").strip() or (
            "Précisez l'action, l'objet ou la date exacte à examiner."
        )
    else:
        status = "query"

    failed_only = bool(re.search(r"\b(RATEES?|ECHOUES?|ECHECS?|ERREURS?|REFUSEES?|REJETEES?)\b", text))
    if status == "query" and not actions:
        raw_actions = list(dict.fromkeys(
            str(value).strip().upper()
            for value in (raw_intent.get("actions") or [])
            if str(value).strip().upper() in ALLOWED_ACTIONS
        ))
        if _has_action_cue(text) and 0 < len(raw_actions) <= 2:
            actions = raw_actions

    if aggregate is None:
        raw_aggregate = raw_intent.get("aggregate")
        if (
            _has_aggregate_cue(text)
            and raw_aggregate in ALLOWED_AGGREGATES
            and raw_aggregate is not None
        ):
            aggregate = raw_aggregate
    raw_period = raw_intent.get("period")
    if raw_period == "null":
        raw_period = None
    if period is None and _has_time_cue(text) and raw_period in ALLOWED_PERIODS:
        period = raw_period

    if status != "query":
        aggregate = None
        limit = 200

    return {
        "status": status,
        "users": users,
        "objects": objects,
        "actions": actions,
        "period": period,
        "aggregate": aggregate,
        "failed_only": failed_only,
        "limit": limit,
        "clarification": clarification,
    }

