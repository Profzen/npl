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

    def add(action: str) -> None:
        if action not in actions:
            actions.append(action)

    create_user = bool(
        re.search(r"\bCREATE\s+USER\b", text)
        or re.search(r"\b(CREE|CREER|CREATION|OUVRE|OUVRIR)\b.*\b(COMPTES?|UTILISATEURS?)\b", text)
    )
    drop_user = bool(
        re.search(r"\bDROP\s+USER\b", text)
        or re.search(
            r"\b(SUPRIME|SUPRIMER|SUPPRIME|SUPPRIMER|EFFACE|EFFACER)\b.*"
            r"\b(COMPTES?|UTILISATEURS?)\b",
            text,
        )
    )
    alter_user = bool(
        re.search(r"\bALTER\s+USER\b", text)
        or re.search(r"\b(MODIFIE|MODIFIER|CHANGE|CHANGER)\b.*\b(COMPTES?|UTILISATEURS?)\b", text)
    )
    create_table = bool(
        re.search(r"\bCREATE\s+TABLE\b", text)
        or re.search(r"\b(CREE|CREER|CREATION)\b.*\bTABLES?\b", text)
    )
    drop_table = bool(
        re.search(r"\bDROP\s+TABLE\b", text)
        or re.search(
            r"\b(SUPRIME|SUPRIMER|SUPPRIME|SUPPRIMER|EFFACE|EFFACER)\b.*\bTABLES?\b",
            text,
        )
    )
    alter_table = bool(
        re.search(r"\bALTER\s+TABLE\b", text)
        or re.search(r"\b(MODIFIE|MODIFIER|CHANGE|CHANGER)\b.*\bSTRUCTURES?\b.*\bTABLES?\b", text)
    )

    for matched, action in (
        (create_user, "CREATE USER"),
        (drop_user, "DROP USER"),
        (alter_user, "ALTER USER"),
        (create_table, "CREATE TABLE"),
        (drop_table, "DROP TABLE"),
        (alter_table, "ALTER TABLE"),
    ):
        if matched:
            add(action)

    if not drop_user and not drop_table and (
        re.search(r"\bDELETE\b", text)
        or re.search(
            r"\b(SUPRIME|SUPRIMER|SUPPRIME|SUPPRIMER|SUPPRESSIONS?|EFFACE|EFFACER)\b",
            text,
        )
        or re.search(r"\bRETIRE\b.*\b(LIGNES?|ENREGISTREMENTS?|DONNEES?)\b", text)
    ):
        add("DELETE")
    if (
        re.search(r"\bGRANT\b", text)
        or re.search(r"\b(DONNE|DONNER|ACCORDE|ACCORDER|ATTRIBUE|ATTRIBUER)\b.*\b(DROITS?|PRIVILEGES?)\b", text)
    ):
        add("GRANT")
    if (
        re.search(r"\bREVOKE\b", text)
        or re.search(r"\b(PRIVILEGES?|DROITS?)\b.*\b(RETIRE|RETIRES|REVOQUE|REVOQUES)\b", text)
        or re.search(r"\b(RETRAITS?|RETIRE|RETIRER|REVOQUE|REVOQUER)\b.*\b(AUTORISATIONS?|DROITS?|PRIVILEGES?)\b", text)
    ):
        add("REVOKE")
    if re.search(r"\b(TRUNCATE|TRONQUE|TRONQUER|VIDE|VIDER|PURGE|PURGER)\b", text):
        add("TRUNCATE")
    if re.search(r"\b(LOGOFF|DECONNEXIONS?|DECONNECTE|FERMETURES?\s+DE\s+SESSION)\b", text):
        add("LOGOFF")
    if re.search(
        r"\b(LOGON|LOGIN|CONNEXIONS?|CONNECTE)\b|\bOUVERTURES?\s+DE\s+SESSION\b|"
        r"\bSESSIONS?\b.*\b(REFUSEES?|REJETEES?|ECHOUES?)\b",
        text,
    ):
        add("LOGON")
    if re.search(r"\b(SELECT|CONSULTE|CONSULTER|CONSULTEES|LECTURE|LIT|LIRE)\b", text):
        add("SELECT")
    if re.search(r"\b(INSERT|INSERTS|INSERE|INSERER|INSERTIONS?|AJOUTE|AJOUTER)\b", text):
        add("INSERT")
    if not alter_user and not alter_table and re.search(
        r"\b(UPDATE|UPDATES|MIS(?:E|ES)?\s+A\s+JOUR|MODIFICATIONS?|MODIFIE|MODIFIER)\b",
        text,
    ):
        add("UPDATE")
    if not alter_user and not alter_table and re.search(r"\bALTER\b", text):
        add("ALTER")
    return actions

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
    if (
        re.search(
            r"\b(DERNIERS?|DERNIERES?|RECENTS?|RECENTES?)\b.*"
            r"\b(USERS?|UTILISATEURS?|COMPTES?)\b",
            text,
        )
        or re.search(
            r"\b(USERS?|UTILISATEURS?|COMPTES?)\b.*"
            r"\b(DERNIERS?|DERNIERES?|RECENTS?|RECENTES?)\b",
            text,
        )
    ):
        return "latest_users", 200
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


def _detect_requested_limit(text: str) -> int | None:
    item_words = (
        r"DERNIERS?|DERNIERES?|PREMIERS?|PREMIERES?|EVENEMENTS?|RESULTATS?|"
        r"LIGNES?|OPERATIONS?|ACTIONS?|TABLES?|OBJETS?"
    )
    # Forme grammaticale singulière générale : elle fonctionne quel que soit
    # le nom employé ensuite (personne, auteur, événement, opération, etc.).
    if re.search(
        r"\b(?:LE|LA)\s+(?:DERNIER|DERNIERE|PREMIER|PREMIERE)\b",
        text,
    ):
        return 1

    ranking_cue = (
        r"DERNIERS?|DERNIERES?|PREMIERS?|PREMIERES?|PLUS\s+RECEMMENT|"
        r"PLUS\s+RECENTS?|PLUS\s+RECENTES?|PLUS\s+FREQUENTS?|PLUS\s+FREQUENTES?"
    )
    ranked_numeric = re.search(
        rf"\b(\d{{1,3}})\b(?:\s+[A-Z0-9_$#]+){{0,4}}\s+(?:{ranking_cue})\b",
        text,
    )
    if ranked_numeric:
        return max(1, min(200, int(ranked_numeric.group(1))))

    numeric = re.search(rf"\b(\d{{1,3}})\s+(?:{item_words})\b", text)
    if numeric:
        return max(1, min(200, int(numeric.group(1))))

    words = {
        "DEUX": 2, "TROIS": 3, "QUATRE": 4,
        "CINQ": 5, "SIX": 6, "SEPT": 7, "HUIT": 8, "NEUF": 9, "DIX": 10,
    }
    word_matches: list[tuple[int, int]] = []
    for word, value in words.items():
        patterns = (
            rf"\b{word}\b(?:\s+[A-Z0-9_$#]+){{0,4}}\s+(?:{ranking_cue})\b",
            rf"\b{word}\s+(?:{item_words})\b",
        )
        matches = [match for pattern in patterns if (match := re.search(pattern, text))]
        if matches:
            word_matches.append((min(match.start() for match in matches), value))
    if word_matches:
        return min(word_matches)[1]
    return None


def _has_recency_cue(text: str) -> bool:
    return bool(re.search(r"\b(DERNIERS?|DERNIERES?|RECENTS?|RECENTES?|RECEMMENT)\b", text))


def _model_aggregate_is_supported(aggregate: str | None, text: str) -> bool:
    if aggregate == "latest_users":
        return _has_recency_cue(text)
    if aggregate == "count_distinct_user":
        return bool(re.search(r"\b(COMBIEN|NOMBRE|TOTAL)\b", text))
    if aggregate == "compare":
        return bool(re.search(r"\b(COMPARE|COMPARER|COMPARAISON|PARALLELE|DIFFERENCE)\b", text))
    if aggregate in {"top_action", "top_host", "top_user", "top_objects"}:
        if aggregate == "top_user" and _has_recency_cue(text):
            return False
        return bool(re.search(
            r"\b(PLUS|MAXIMUM|MAX|DOMINANTE|FREQUENTE|CLASSEMENT|PREMIER|NUMERO UN)\b",
            text,
        ))
    return aggregate is None


def _is_mutation_order(text: str) -> bool:
    return bool(re.match(
        r"^(SUPPRIME|SUPPRIMER|EFFACE|EFFACER|VIDE|VIDER|TRONQUE|TRUNCATE|"
        r"METS\s+A\s+JOUR|METTRE\s+A\s+JOUR|REMETS|REMETTRE|"
        r"REINITIALISE|REINITIALISER|PURGE|PURGER|"
        r"MODIFIE|MODIFIER|INSERE|INSERER|ACCORDE|REVOQUE|DROP|CREATE|ALTER|"
        r"GRANT|REVOKE|DELETE|UPDATE|INSERT)\b",
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
    known_user_set = {
        str(value).strip().upper().replace(" ", "_") for value in known_users
    }
    known_object_set = {
        str(value).strip().upper() for value in known_objects
    }

    explicit_users = _catalog_matches(text, known_user_set)
    explicit_objects = _catalog_matches(text, known_object_set)
    # Les noms propres doivent être présents dans la question et dans le catalogue.
    # Le modèle ne peut donc pas ajouter un compte ou un objet seulement parce qu'il existe.
    users = explicit_users
    objects = explicit_objects

    evidence = raw_intent.get("evidence")
    if isinstance(evidence, Mapping):
        raw_action_evidence = evidence.get("actions") or []
    elif isinstance(evidence, list):
        raw_action_evidence = evidence
    else:
        raw_action_evidence = []
    if isinstance(raw_action_evidence, str):
        raw_action_evidence = [raw_action_evidence]
    grounded_evidence = [
        normalized
        for value in raw_action_evidence
        if (normalized := _norm(str(value))) and normalized in text
    ]
    action_evidence_is_grounded = bool(grounded_evidence)

    explicit_actions = _detect_actions(text)
    model_actions = list(dict.fromkeys(
        str(value).strip().upper()
        for value in (raw_intent.get("actions") or [])
        if str(value).strip().upper() in ALLOWED_ACTIONS
    ))
    # Une question normale combine peu d'actions. Une longue énumération produite
    # par le petit modèle est traitée comme « toutes les actions », donc sans filtre.
    tentative_model_actions = (
        model_actions
        if not explicit_actions and action_evidence_is_grounded and 0 < len(model_actions) <= 4
        else []
    )
    actions = explicit_actions or tentative_model_actions

    explicit_period = _detect_period(text)
    model_period = raw_intent.get("period")
    if model_period == "null":
        model_period = None
    period = explicit_period
    if period is None and model_period in ALLOWED_PERIODS:
        period = model_period

    explicit_aggregate, _ = _detect_aggregate(text)
    model_aggregate = raw_intent.get("aggregate")
    if model_aggregate == "null":
        model_aggregate = None
    aggregate = explicit_aggregate
    if aggregate is None and model_aggregate in ALLOWED_AGGREGATES:
        if model_aggregate == "top_user" and _has_recency_cue(text):
            aggregate = "latest_users"
        elif _model_aggregate_is_supported(model_aggregate, text):
            aggregate = model_aggregate
    if period == "compare_today_yesterday":
        aggregate = "compare"

    requested_limit = _detect_requested_limit(text)
    model_limit: int | None = None
    try:
        if raw_intent.get("limit") not in (None, "", "null"):
            model_limit = max(1, min(200, int(raw_intent["limit"])))
    except (TypeError, ValueError):
        model_limit = None
    evidence_has_quantity = any(re.search(
        r"\b(\d{1,3}|UN|UNE|DEUX|TROIS|QUATRE|CINQ|SIX|SEPT|HUIT|NEUF|DIX|"
        r"DERNIER|DERNIERE|PREMIER|PREMIERE)\b",
        value,
    ) for value in grounded_evidence)
    limit = requested_limit
    if limit is None and model_limit is not None and evidence_has_quantity:
        limit = model_limit
    if (
        limit is None
        and aggregate == "latest_users"
        and re.match(r"^(QUI\s+EST|QUEL|QUELLE)\b", text)
    ):
        limit = 1
    if limit is None and aggregate == "top_objects":
        limit = 5

    model_status = str(raw_intent.get("status") or "query").strip().lower()
    if model_status not in {"query", "clarification", "refusal"}:
        model_status = "query"
    status = "query"
    clarification = str(raw_intent.get("clarification") or "").strip() or None

    if _is_mutation_order(text):
        status = "refusal"
        clarification = "Je peux consulter les journaux d'audit, mais pas modifier la base."
        actions = []
    elif _needs_clarification(text):
        status = "clarification"
        clarification = clarification or (
            "Précisez l'action, l'objet ou la date exacte à examiner."
        )
    elif tentative_model_actions:
        status = "clarification"
        actions = []
        clarification = (
            "L'action demandée reste incertaine. Précisez s'il s'agit d'un ajout, "
            "d'une modification, d'une consultation, d'une suppression ou d'une autre opération."
        )
    elif model_status == "clarification":
        status = "clarification"
        clarification = clarification or (
            "Précisez l'utilisateur, l'objet, l'action ou la période à examiner."
        )
    else:
        status = "query"
        clarification = None

    explicit_failure = bool(re.search(
        r"\b(RATEES?|ECHOUES?|ECHECS?|ERREURS?|REFUSEES?|REJETEES?)\b",
        text,
    ))
    failed_only = explicit_failure or bool(raw_intent.get("failed_only"))

    if status != "query":
        aggregate = None
        limit = None

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

