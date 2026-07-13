"""
Audit AI — Patch dynamique non rigide

À placer à la racine du projet : C:\\dossier3\\nlp
Commande : python .\\apply_auditai_dynamic_guardrails_patch.py

Objectif : garder le modèle NLP comme moteur principal, sans transformer la
plateforme en système de questions préfabriquées.

Ce patch ajoute une couche de garde-fous dynamiques :
- le LoRA génère toujours le SQL librement ;
- le backend vérifie ensuite la sécurité et ajoute uniquement les contraintes
  évidentes oubliées par le modèle quand elles sont clairement présentes dans
  la question : utilisateur, table/objet, action, période ;
- les utilisateurs et tables visibles restent dynamiques depuis
  SMART2DSECU.UNIFIED_AUDIT_DATA : les nouveaux éléments apparaissent
  automatiquement sauf s'ils correspondent à une liste d'exclusion technique ;
- les comptes/tables de bruit sont masqués dans les colonnes, sans bloquer les
  nouveaux utilisateurs/tables métier ;
- les questions temporelles ne sont pas mises en cache ;
- l'interface reste en français, l'anglais n'est plus visible dans Paramètres ;
- la section Connexion Oracle est visible uniquement pour les administrateurs.

Des sauvegardes .bak_dynamic_guardrails sont créées avant modification.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

BACKUP_SUFFIX = ".bak_dynamic_guardrails"

DYNAMIC_GUARDRAILS_SERVICE = r'''from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from app.services.settings_service import get_fetch_limit, get_oracle_table

# ---------------------------------------------------------------------------
# Audit AI — garde-fous dynamiques, non rigides
# ---------------------------------------------------------------------------
# Ce module ne remplace PAS le modèle NLP.
# Il ne contient pas de requêtes préfabriquées par question.
# Il sert uniquement à :
#   1) sécuriser la requête SQL générée par le modèle ;
#   2) ajouter des filtres évidents quand la question les mentionne clairement
#      et que le modèle les a oubliés ;
#   3) masquer les objets/comptes techniques sans bloquer les nouveaux objets
#      métier ou nouveaux utilisateurs.

AUDIT_SCOPE_MARKER = "/* AUDITAI_DYNAMIC_GUARDRAILS_SCOPE */"

AUDIT_ACTIONS = (
    "SELECT", "INSERT", "UPDATE", "DELETE", "GRANT", "REVOKE", "ALTER",
    "DROP", "CREATE", "TRUNCATE", "EXECUTE", "LOGON", "LOGOFF",
)

ACTION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "SELECT": ("SELECT", "LECTURE", "LIRE", "LU", "CONSULTE", "CONSULTATION", "AFFICHE", "VOIR"),
    "INSERT": ("INSERT", "INSERTION", "AJOUT", "AJOUTE", "AJOUTER", "CREE LIGNE", "CREATION LIGNE"),
    "UPDATE": ("UPDATE", "MODIFICATION", "MODIFIE", "MODIFIER", "MIS A JOUR", "MISE A JOUR", "CHANGE"),
    "DELETE": ("DELETE", "SUPPRESSION", "SUPPRIME", "SUPPRIMER", "EFFACE"),
    "GRANT": ("GRANT", "PRIVILEGE", "PRIVILEGES", "ATTRIBUE", "DONNE DROIT"),
    "REVOKE": ("REVOKE", "RETIRE PRIVILEGE", "RETIRE DROIT", "REVOQUE"),
    "ALTER": ("ALTER", "STRUCTURE", "MODIFIE STRUCTURE", "CHANGE STRUCTURE"),
    "DROP": ("DROP", "SUPPRIME TABLE", "SUPPRIME OBJET"),
    "CREATE": ("CREATE", "CREATION", "CREE", "CREER", "NOUVEL OBJET", "NOUVELLE TABLE"),
    "TRUNCATE": ("TRUNCATE", "VIDER", "VIDAGE"),
    "EXECUTE": ("EXECUTE", "EXECUTION", "PROCEDURE", "FONCTION"),
    "LOGON": ("LOGON", "CONNEXION", "CONNECTE", "CONNECTER"),
    "LOGOFF": ("LOGOFF", "DECONNEXION", "DECONNECTE", "DECONNECTER"),
}

# Objets techniques / de test à masquer.
# Les nouvelles tables métier restent visibles automatiquement si elles ne
# correspondent pas à ces noms ou motifs.
HIDDEN_AUDIT_OBJECTS_EXACT = (
    "AUD$",
    "DEVICE_ADDRESS",
    "SMA_MIGRATION_17_TEST",
    "PROD1_UMS",
    "MGMT_VIEW",
    "USER_DEVICE",
    "COMPONENT_SCHEMA_INFO",
    "ADD_JOB_HISTORY",
    "SYSMAN",
    "COMP_PROFILE_TEST",
    "VROMUALD",
    "TEST",
)

HIDDEN_AUDIT_OBJECT_LIKE = (
    "SCHEMA_VERSION_REGIST%",
    "TEST%",
    "%VROMUALD%",
    "%ROMUALD%",
    "BIN$%",
    "SYS_EXPORT%",
)

# Comptes techniques / bruités à masquer de la colonne Utilisateurs.
# Les nouveaux utilisateurs Oracle non listés ici apparaissent automatiquement
# dès qu'ils sont présents dans SMART2DSECU.UNIFIED_AUDIT_DATA.
HIDDEN_AUDIT_USERS_EXACT = (
    "PROD2_MDS",
    "PROD2_STB",
    "TEST",
    "SMART2DADMIN",
    "BATCH_USER",
    "SMART2DADMINI",
    "SMART2DSECU",
    "\\SMART2DADMIN",
)

# Ceux-ci restent visibles même si on ajoute plus tard des règles générales.
PINNED_AUDIT_USERS = (
    "VROMUALD",
    "SYS",
    "SYSTEM",
    "CYRILLE",
    "ITEST",
    "CYRILLE_TBS",
)

STOPWORDS = {
    "UN", "UNE", "LE", "LA", "LES", "L", "DES", "DE", "DU", "D", "PAR", "SUR",
    "TABLE", "OBJET", "BASE", "ACTION", "ACTIONS", "UTILISATEUR", "USER", "USERS",
    "QUI", "QUE", "QUEL", "QUELLE", "QUELS", "QUELLES", "EST", "CE", "FAIT", "FAIRE",
    "HIER", "AUJOURD", "AUJOURDHUI", "AVANT", "DERNIER", "DERNIERE", "PASSEE", "PASSE",
    "MOIS", "AN", "ANS", "JOUR", "JOURS", "SEMAINE", "NUIT", "DANS",
}

WEEKDAY_OFFSETS = {
    "LUNDI": 0,
    "MARDI": 1,
    "MERCREDI": 2,
    "JEUDI": 3,
    "VENDREDI": 4,
    "SAMEDI": 5,
    "DIMANCHE": 6,
}

NUMBER_WORDS = {
    "UN": 1, "UNE": 1, "DEUX": 2, "TROIS": 3, "QUATRE": 4, "CINQ": 5,
    "SIX": 6, "SEPT": 7, "HUIT": 8, "NEUF": 9, "DIX": 10,
    "ONZE": 11, "DOUZE": 12,
}


def _strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(char)
    )


def normalize_text(value: str) -> str:
    text = _strip_accents(value or "").upper()
    text = text.replace("’", "'")
    text = re.sub(r"[^A-Z0-9_\\$#.' -]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _sql_list(values: Iterable[str]) -> str:
    return ", ".join("'" + str(item).replace("'", "''").upper() + "'" for item in values)


def get_hidden_objects_condition(column: str = "OBJECT_NAME") -> str:
    clauses: list[str] = [f"{column} IS NOT NULL"]
    if HIDDEN_AUDIT_OBJECTS_EXACT:
        clauses.append(f"UPPER({column}) NOT IN ({_sql_list(HIDDEN_AUDIT_OBJECTS_EXACT)})")
    for pattern in HIDDEN_AUDIT_OBJECT_LIKE:
        clauses.append(f"UPPER({column}) NOT LIKE '{pattern.replace("'", "''").upper()}'")
    return " AND ".join(clauses)


def get_visible_users_condition(column: str = "DBUSERNAME") -> str:
    clauses = [f"{column} IS NOT NULL"]
    if HIDDEN_AUDIT_USERS_EXACT:
        clauses.append(
            f"(UPPER({column}) IN ({_sql_list(PINNED_AUDIT_USERS)}) "
            f"OR UPPER({column}) NOT IN ({_sql_list(HIDDEN_AUDIT_USERS_EXACT)}))"
        )
    return " AND ".join(clauses)


def strip_sql_comments(sql: str) -> str:
    text = re.sub(r"--.*?$", "", sql or "", flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _without_string_literals(sql: str) -> str:
    # ACTION_NAME='DELETE' ou ACTION_NAME='CREATE' sont des valeurs d'audit,
    # pas des instructions SQL exécutées. On retire donc les chaînes avant de
    # chercher les mots-clés dangereux.
    return re.sub(r"'(?:''|[^'])*'", "''", sql or "")


def validate_readonly_audit_sql(sql: str) -> tuple[bool, str]:
    cleaned = strip_sql_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        return False, "Requête SQL vide."

    upper = cleaned.upper()
    upper_no_strings = _without_string_literals(upper)

    if not upper.startswith(("SELECT", "WITH")):
        return False, "Seules les requêtes SELECT/WITH sont autorisées."

    if ";" in cleaned:
        return False, "Une seule requête SQL est autorisée."

    forbidden = r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COMMIT|ROLLBACK|EXECUTE|BEGIN|DECLARE)\b"
    if re.search(forbidden, upper_no_strings):
        return False, "Mot-clé SQL interdit détecté."

    oracle_table = get_oracle_table().upper()
    if oracle_table not in upper and "ORACLE_AUDIT_TRAIL" not in upper and AUDIT_SCOPE_MARKER.upper() not in upper:
        return False, "La requête doit interroger uniquement la table d'audit configurée."

    blocked_sources = r"\b(DBA_|ALL_|V\$|GV\$|SYS\.|SYSTEM\.)"
    if re.search(blocked_sources, upper):
        return False, "Vue système ou schéma interdit détecté."

    return True, "OK"


def is_question_cacheable(question: str) -> bool:
    q = normalize_text(question)
    # Les questions temporelles ou de dernière activité doivent toujours relire Oracle.
    time_terms = (
        "DERNIER", "DERNIERE", "RECENT", "RECENTE", "AUJOURD", "HIER", "AVANT HIER",
        "SEMAINE", "MOIS", "AN ", "ANS", "JOUR", "JOURS", "NUIT", "MATIN", "SOIR",
        "LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE",
        "DERNIERS", "DERNIERES", "PASSE", "PASSEE",
    )
    return not any(term in q for term in time_terms)


def _safe_identifier(token: str | None) -> str | None:
    if not token:
        return None
    token = token.strip().strip("'\"`.,;:!?()[]{}")
    token = _strip_accents(token).upper()
    if not re.fullmatch(r"[A-Z0-9_\\$#.-]{2,80}", token):
        return None
    if token in STOPWORDS:
        return None
    return token


def _contains_name(question_norm: str, name: str) -> bool:
    candidate = normalize_text(name)
    if not candidate:
        return False
    # Délimiteurs adaptés aux noms Oracle avec _, $, #, \\.
    return re.search(rf"(?<![A-Z0-9_\\$#]){re.escape(candidate)}(?![A-Z0-9_\\$#])", question_norm) is not None


def _detect_from_catalog(question: str, known_values: Iterable[str]) -> list[str]:
    q = normalize_text(question)
    values = sorted({str(v) for v in known_values if v}, key=len, reverse=True)
    found: list[str] = []
    for value in values:
        safe = _safe_identifier(value)
        if safe and _contains_name(q, safe):
            found.append(safe)
    return found


def _detect_user_fallback(question: str) -> str | None:
    q = normalize_text(question)
    patterns = (
        r"\bUTILISATEUR\s+([A-Z0-9_\\$#.-]{2,80})\b",
        r"\bUSER\s+([A-Z0-9_\\$#.-]{2,80})\b",
        r"\bPAR\s+L?\s*'?UTILISATEUR\s+([A-Z0-9_\\$#.-]{2,80})\b",
        r"\bPAR\s+([A-Z0-9_\\$#.-]{2,80})\b",
        r"\bDE\s+L?\s*'?UTILISATEUR\s+([A-Z0-9_\\$#.-]{2,80})\b",
    )
    for pattern in patterns:
        m = re.search(pattern, q)
        if m:
            return _safe_identifier(m.group(1))
    return None


def _detect_object_fallback(question: str) -> str | None:
    q = normalize_text(question)
    patterns = (
        r"\bTABLE\s+([A-Z0-9_\\$#.-]{2,80})\b",
        r"\bOBJET\s+([A-Z0-9_\\$#.-]{2,80})\b",
        r"\bSUR\s+LA\s+TABLE\s+([A-Z0-9_\\$#.-]{2,80})\b",
        r"\bSUR\s+([A-Z0-9_\\$#.-]{2,80})\b",
    )
    for pattern in patterns:
        m = re.search(pattern, q)
        if m:
            return _safe_identifier(m.group(1))
    return None


def detect_question_users(question: str, known_users: Iterable[str] | None = None) -> list[str]:
    found = _detect_from_catalog(question, known_users or [])
    if found:
        return found[:3]
    fallback = _detect_user_fallback(question)
    return [fallback] if fallback else []


def detect_question_objects(question: str, known_objects: Iterable[str] | None = None) -> list[str]:
    found = _detect_from_catalog(question, known_objects or [])
    if found:
        return found[:3]
    fallback = _detect_object_fallback(question)
    return [fallback] if fallback else []


def detect_question_actions(question: str) -> list[str]:
    q = normalize_text(question)
    found: list[str] = []
    for action in AUDIT_ACTIONS:
        if _contains_name(q, action):
            found.append(action)
            continue
        for synonym in ACTION_SYNONYMS.get(action, ()):  # synonymes génériques, pas questions préfaites
            if _contains_name(q, synonym):
                found.append(action)
                break
    # Éviter de transformer "créé en base" etc. en CREATE si une autre action explicite est présente.
    return list(dict.fromkeys(found))[:3]


def _number_after(pattern: str, q: str) -> int | None:
    m = re.search(pattern, q)
    if not m:
        return None
    raw = m.group(1).upper()
    if raw.isdigit():
        return max(1, min(365, int(raw)))
    return NUMBER_WORDS.get(raw)


def detect_time_condition(question: str) -> str | None:
    q = normalize_text(question)
    night = "NUIT" in q or "NOCTURNE" in q
    night_clause = "TO_NUMBER(TO_CHAR(EVENT_TIMESTAMP, 'HH24')) BETWEEN 0 AND 5"

    if "AVANT HIER" in q or "AVANT-HIER" in q:
        day_clause = "EVENT_TIMESTAMP >= TRUNC(SYSDATE) - 2 AND EVENT_TIMESTAMP < TRUNC(SYSDATE) - 1"
        return f"{day_clause} AND {night_clause}" if night else day_clause

    if "HIER" in q:
        day_clause = "EVENT_TIMESTAMP >= TRUNC(SYSDATE) - 1 AND EVENT_TIMESTAMP < TRUNC(SYSDATE)"
        return f"{day_clause} AND {night_clause}" if night else day_clause

    if "AUJOURD" in q or "AUJOURDHUI" in q:
        day_clause = "EVENT_TIMESTAMP >= TRUNC(SYSDATE) AND EVENT_TIMESTAMP < TRUNC(SYSDATE) + 1"
        return f"{day_clause} AND {night_clause}" if night else day_clause

    if "MOIS DERNIER" in q:
        return "EVENT_TIMESTAMP >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -1) AND EVENT_TIMESTAMP < TRUNC(SYSDATE, 'MM')"

    if "CE MOIS" in q or "MOIS EN COURS" in q:
        return "EVENT_TIMESTAMP >= TRUNC(SYSDATE, 'MM') AND EVENT_TIMESTAMP < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1)"

    if "AN DERNIER" in q or "ANNEE DERNIERE" in q:
        return "EVENT_TIMESTAMP >= ADD_MONTHS(TRUNC(SYSDATE, 'YYYY'), -12) AND EVENT_TIMESTAMP < TRUNC(SYSDATE, 'YYYY')"

    if "CETTE ANNEE" in q or "ANNEE EN COURS" in q:
        return "EVENT_TIMESTAMP >= TRUNC(SYSDATE, 'YYYY') AND EVENT_TIMESTAMP < ADD_MONTHS(TRUNC(SYSDATE, 'YYYY'), 12)"

    n = _number_after(r"(?:CES|LES)\s+([0-9]+|UN|UNE|DEUX|TROIS|QUATRE|CINQ|SIX|SEPT|HUIT|NEUF|DIX|ONZE|DOUZE)\s+DERNIERS?\s+JOURS?", q)
    if n:
        return f"EVENT_TIMESTAMP >= SYSDATE - {n}"

    n = _number_after(r"IL\s+Y\s+A\s+([0-9]+|UN|UNE|DEUX|TROIS|QUATRE|CINQ|SIX|SEPT|HUIT|NEUF|DIX|ONZE|DOUZE)\s+JOURS?", q)
    if n:
        return f"EVENT_TIMESTAMP >= TRUNC(SYSDATE) - {n} AND EVENT_TIMESTAMP < TRUNC(SYSDATE) - {n - 1}"

    n = _number_after(r"IL\s+Y\s+A\s+([0-9]+|UN|UNE|DEUX|TROIS|QUATRE|CINQ|SIX|SEPT|HUIT|NEUF|DIX|ONZE|DOUZE)\s+MOIS", q)
    if n:
        return f"EVENT_TIMESTAMP >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -{n}) AND EVENT_TIMESTAMP < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -{n - 1})"

    for day, offset in WEEKDAY_OFFSETS.items():
        if f"{day} PASSE" in q or f"{day} DERNIER" in q:
            return f"EVENT_TIMESTAMP >= TRUNC(SYSDATE, 'IW') - 7 + {offset} AND EVENT_TIMESTAMP < TRUNC(SYSDATE, 'IW') - 7 + {offset + 1}"

    # La nuit est un filtre horaire. Si la question dit aussi hier/avant-hier,
    # les branches ci-dessus auront déjà ajouté la journée. Le modèle peut aussi
    # générer la date, ici on ajoute seulement le créneau horaire si nécessaire.
    if "NUIT" in q or "NOCTURNE" in q:
        return "TO_NUMBER(TO_CHAR(EVENT_TIMESTAMP, 'HH24')) BETWEEN 0 AND 5"

    return None


def _has_filter(sql: str, column: str) -> bool:
    return re.search(rf"\b{re.escape(column)}\b\s*(=|IN|LIKE|BETWEEN|>=|<=|>|<)", sql, flags=re.IGNORECASE) is not None


def _has_event_timestamp_filter(sql: str) -> bool:
    return _has_filter(sql, "EVENT_TIMESTAMP") or "TO_CHAR(EVENT_TIMESTAMP" in sql.upper()


def _has_order_by(sql: str) -> bool:
    return re.search(r"\bORDER\s+BY\b", sql, flags=re.IGNORECASE) is not None


def _has_fetch(sql: str) -> bool:
    return re.search(r"\bFETCH\s+FIRST\b", sql, flags=re.IGNORECASE) is not None


def _is_aggregation(sql: str) -> bool:
    return bool(re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", sql, flags=re.IGNORECASE) or re.search(r"\bGROUP\s+BY\b", sql, flags=re.IGNORECASE))


def _add_final_order_fetch_if_needed(sql: str, question: str) -> str:
    q = normalize_text(question)
    wants_last = any(term in q for term in ("DERNIERE", "DERNIER", "PLUS RECENT", "PLUS RECENTE", "RECENT", "RECENTE"))
    if not wants_last or _is_aggregation(sql):
        return sql

    sql_no_sc = sql.rstrip().rstrip(";").rstrip()
    if not _has_order_by(sql_no_sc):
        if _has_fetch(sql_no_sc):
            sql_no_sc = re.sub(r"\bFETCH\s+FIRST\b", "ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST", sql_no_sc, count=1, flags=re.IGNORECASE)
        else:
            sql_no_sc = f"{sql_no_sc} ORDER BY EVENT_TIMESTAMP DESC"
    if not _has_fetch(sql_no_sc):
        sql_no_sc = f"{sql_no_sc} FETCH FIRST 1 ROWS ONLY"
    return sql_no_sc


def _remove_legacy_scopes(sql: str) -> str:
    table = re.escape(get_oracle_table().strip())
    # Retire les anciens scopes générés par les scripts précédents pour repartir
    # d'une base propre et éviter des filtres incohérents empilés.
    marker = r"/\*\s*AUDITAI_[A-Z_]+_SCOPE\s*\*/"
    pattern = rf"\bFROM\s+\(\s*SELECT\s+\*\s+FROM\s+{table}\s+WHERE\s+.*?\)\s*{marker}"
    return re.sub(pattern, f"FROM {get_oracle_table().strip()}", sql, count=1, flags=re.IGNORECASE | re.DOTALL)


def _build_question_filters(
    question: str | None,
    sql: str,
    known_users: Iterable[str] | None = None,
    known_objects: Iterable[str] | None = None,
) -> list[str]:
    filters: list[str] = [get_hidden_objects_condition("OBJECT_NAME")]

    if not question:
        return filters

    users = detect_question_users(question, known_users)
    if users and not _has_filter(sql, "DBUSERNAME"):
        filters.append("UPPER(DBUSERNAME) IN (" + _sql_list(users) + ")")

    objects = detect_question_objects(question, known_objects)
    if objects and not _has_filter(sql, "OBJECT_NAME"):
        filters.append("UPPER(OBJECT_NAME) IN (" + _sql_list(objects) + ")")

    actions = detect_question_actions(question)
    if actions and not _has_filter(sql, "ACTION_NAME"):
        filters.append("UPPER(ACTION_NAME) IN (" + _sql_list(actions) + ")")

    time_condition = detect_time_condition(question)
    if time_condition and not _has_event_timestamp_filter(sql):
        filters.append(time_condition)
    elif time_condition and ("TO_NUMBER(TO_CHAR(EVENT_TIMESTAMP" in time_condition and "TO_CHAR(EVENT_TIMESTAMP" not in sql.upper()):
        # Cas particulier : "dans la nuit" peut compléter un filtre de date déjà généré par le modèle.
        filters.append(time_condition)

    return filters


def apply_base_scope(sql: str, filters: list[str]) -> str:
    sql = (sql or "").strip().rstrip(";").strip()
    sql = re.sub(r"\bORACLE_AUDIT_TRAIL\b", get_oracle_table().strip(), sql, flags=re.IGNORECASE)
    sql = _remove_legacy_scopes(sql)

    table = get_oracle_table().strip()
    where_clause = " AND ".join(f"({clause})" for clause in filters if clause)
    scoped_source = f"(SELECT * FROM {table} WHERE {where_clause}) {AUDIT_SCOPE_MARKER}"
    pattern = rf"\bFROM\s+{re.escape(table)}\b"

    if re.search(pattern, sql, flags=re.IGNORECASE):
        return re.sub(pattern, f"FROM {scoped_source}", sql, count=1, flags=re.IGNORECASE)

    return sql


def prepare_sql_for_execution(
    sql: str,
    question: str | None = None,
    known_users: Iterable[str] | None = None,
    known_objects: Iterable[str] | None = None,
) -> str:
    """
    Prépare le SQL généré par le modèle sans le remplacer par une requête codée.
    Le modèle reste la source principale ; ce module ajoute seulement un scope de
    sécurité et les filtres évidents manquants.
    """
    prepared = (sql or "").strip().rstrip(";").strip()
    if not prepared:
        return prepared

    filters = _build_question_filters(question, prepared, known_users, known_objects)
    prepared = apply_base_scope(prepared, filters)
    if question:
        prepared = _add_final_order_fetch_if_needed(prepared, question)

    if not _has_fetch(prepared) and not _is_aggregation(prepared):
        prepared = f"{prepared.rstrip()} FETCH FIRST {max(1, int(get_fetch_limit()))} ROWS ONLY"

    return prepared.rstrip().rstrip(";") + ";"


def sanitize_runtime_settings_for_user(settings_payload: dict, is_admin: bool) -> dict:
    data = dict(settings_payload)
    data["interface_lang"] = "fr"
    if not is_admin:
        # Ne pas exposer la connexion Oracle aux utilisateurs simples.
        for key in ("oracle_user", "oracle_password", "oracle_host", "oracle_port", "oracle_service", "oracle_table"):
            if key in data:
                data[key] = "" if key != "oracle_port" else 0
    return data


def merge_settings_for_role(incoming: dict, current: dict, is_admin: bool) -> dict:
    merged = dict(current)
    allowed_common = {"max_results", "session_duration", "logs_retention"}
    allowed_admin = allowed_common | {"oracle_user", "oracle_password", "oracle_host", "oracle_port", "oracle_service", "oracle_table"}
    allowed = allowed_admin if is_admin else allowed_common

    for key in allowed:
        if key in incoming:
            merged[key] = incoming[key]

    # L'anglais est désactivé fonctionnellement, même si une ancienne valeur "en"
    # existe encore en localStorage ou dans un ancien payload.
    merged["interface_lang"] = "fr"
    return merged
'''

ORACLE_SERVICE = r'''try:
    import oracledb

    _ORACLE_DRIVER_OK = True
except Exception:
    oracledb = None
    _ORACLE_DRIVER_OK = False

from threading import Lock
import time as time_module

from app.config import settings
from app.services.settings_service import get_oracle_connection_config, get_oracle_table
from app.services.dynamic_guardrails_service import (
    get_hidden_objects_condition,
    get_visible_users_condition,
    prepare_sql_for_execution,
)


_POOL = None
_POOL_CFG: tuple[str, str, str, int, str] | None = None
_POOL_LOCK = Lock()

# Metadata cache (TTL: 300s = 5 min)
_METADATA_CACHE: tuple[list[dict], list[dict], str, float] | None = None
_METADATA_CACHE_LOCK = Lock()
_METADATA_CACHE_TTL_SECONDS = 300


def _build_connection_config() -> tuple[str, str, str, int, str]:
    user, password, host, port, service = get_oracle_connection_config()
    return user, password, host, int(port), service


def _create_pool(cfg: tuple[str, str, str, int, str]):
    user, password, host, port, service = cfg
    dsn = f"{host}:{port}/{service}"
    return oracledb.create_pool(
        user=user,
        password=password,
        dsn=dsn,
        min=max(1, settings.oracle_pool_min),
        max=max(2, settings.oracle_pool_max),
        increment=max(1, settings.oracle_pool_increment),
    )


def _get_pool():
    global _POOL, _POOL_CFG
    cfg = _build_connection_config()

    with _POOL_LOCK:
        if _POOL is None or _POOL_CFG != cfg:
            if _POOL is not None:
                try:
                    _POOL.close(force=True)
                except Exception:
                    pass
            _POOL = _create_pool(cfg)
            _POOL_CFG = cfg
        return _POOL


def get_connection():
    if not _ORACLE_DRIVER_OK:
        raise RuntimeError("oracledb package is not installed")
    pool = _get_pool()
    return pool.acquire()


def execute_sql(sql: str) -> tuple[list[dict], str | None]:
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        if "AUDITAI_DYNAMIC_GUARDRAILS_SCOPE" in (sql or ""):
            prepared_sql = sql
        else:
            prepared_sql = prepare_sql_for_execution(sql)
        cur.execute(prepared_sql.rstrip().rstrip(";"))
        cols = [d[0].upper() for d in cur.description]
        rows = cur.fetchall()
        payload = [dict(zip(cols, row)) for row in rows]
        return payload, None
    except Exception as exc:
        return [], str(exc)
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def oracle_status() -> str:
    conn = None
    try:
        conn = get_connection()
        return "connected"
    except Exception:
        return "disconnected"
    finally:
        if conn is not None:
            conn.close()


def clear_metadata_cache() -> None:
    global _METADATA_CACHE
    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE = None


def fetch_metadata() -> tuple[list[dict], list[dict], str]:
    global _METADATA_CACHE

    with _METADATA_CACHE_LOCK:
        if _METADATA_CACHE is not None:
            users, objects, status, timestamp = _METADATA_CACHE
            elapsed = time_module.time() - timestamp
            if elapsed < _METADATA_CACHE_TTL_SECONDS:
                print(f"[METADATA_CACHE_HIT] (cached {elapsed:.1f}s ago)")
                return users, objects, status

    conn = None
    cur = None
    users: list[dict] = []
    objects: list[dict] = []
    status = "disconnected"

    try:
        conn = get_connection()
        cur = conn.cursor()
        oracle_table = get_oracle_table()

        user_sql = (
            f"SELECT DBUSERNAME, COUNT(*) AS ACTIONS FROM {oracle_table} "
            f"WHERE {get_visible_users_condition('DBUSERNAME')} "
            "GROUP BY DBUSERNAME "
            "ORDER BY ACTIONS DESC FETCH FIRST 500 ROWS ONLY"
        )
        cur.execute(user_sql)
        users = [{"name": str(r[0]), "actions": int(r[1])} for r in cur.fetchall()]

        obj_sql = (
            f"SELECT OBJECT_NAME, COUNT(*) AS ACTIONS FROM {oracle_table} "
            f"WHERE {get_hidden_objects_condition('OBJECT_NAME')} "
            "GROUP BY OBJECT_NAME "
            "ORDER BY ACTIONS DESC FETCH FIRST 500 ROWS ONLY"
        )
        cur.execute(obj_sql)
        objects = [{"name": str(r[0]), "actions": int(r[1])} for r in cur.fetchall()]

        status = "connected"
    except Exception as exc:
        print(f"[METADATA_ERROR] {exc}")
        status = "disconnected"
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()

    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE = (users, objects, status, time_module.time())

    return users, objects, status
'''


def backup(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ensure_import(text: str, import_line: str) -> str:
    if import_line in text:
        return text
    lines = text.splitlines()
    idx = 0
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            idx = i + 1
    lines.insert(idx, import_line)
    return "\n".join(lines) + "\n"


def normalize_oracle_import(text: str) -> str:
    replacement = "from app.services.oracle_service import execute_sql, fetch_metadata, get_connection, oracle_status"

    text = re.sub(
        r"from app\.services\.oracle_service import \([^)]*\)",
        replacement,
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"from app\.services\.oracle_service import [^\n]+",
        replacement,
        text,
    )
    return text


def patch_nlp_service(path: Path) -> None:
    backup(path)
    text = path.read_text(encoding="utf-8")
    new_func = '''def validate_sql_guardrails(sql: str) -> tuple[bool, str]:
    from app.services.dynamic_guardrails_service import validate_readonly_audit_sql
    return validate_readonly_audit_sql(sql)
'''
    text = re.sub(
        r"def validate_sql_guardrails\(sql: str\) -> tuple\[bool, str\]:\n(?:    .*\n)+?\n(?=def generate_sql_from_question)",
        new_func + "\n",
        text,
        flags=re.DOTALL,
    )
    path.write_text(text, encoding="utf-8")


def patch_main(path: Path) -> None:
    backup(path)
    text = path.read_text(encoding="utf-8")
    text = normalize_oracle_import(text)
    dynamic_import = "from app.services.dynamic_guardrails_service import is_question_cacheable, merge_settings_for_role, prepare_sql_for_execution, sanitize_runtime_settings_for_user, validate_readonly_audit_sql"
    text = ensure_import(text, dynamic_import)

    if "if not is_question_cacheable(question):" not in text:
        text = text.replace(
            "def _get_cached_response(question: str) -> QueryResponse | None:\n    \"\"\"Retrieve cached response if exists and not expired.\"\"\"\n",
            "def _get_cached_response(question: str) -> QueryResponse | None:\n    \"\"\"Retrieve cached response if exists and not expired.\"\"\"\n    if not is_question_cacheable(question):\n        return None\n",
        )

    if "[CACHE_SKIP] question non cacheable" not in text:
        text = text.replace(
            "def _cache_response(question: str, response: QueryResponse) -> None:\n    \"\"\"Store response in cache with timestamp. Evict oldest 50% if size exceeds 256MB.\"\"\"\n",
            "def _cache_response(question: str, response: QueryResponse) -> None:\n    \"\"\"Store response in cache with timestamp. Evict oldest 50% if size exceeds 256MB.\"\"\"\n    if not is_question_cacheable(question):\n        print(\"[CACHE_SKIP] question non cacheable car temporelle ou récente\")\n        return\n",
        )

    if "AUDITAI_DYNAMIC_GUARDRAILS_PREPARE_BEGIN" not in text:
        text = text.replace(
            "    sql = generate_sql_from_question(req.question)\n",
            "    sql = generate_sql_from_question(req.question)\n"
            "\n"
            "    # AUDITAI_DYNAMIC_GUARDRAILS_PREPARE_BEGIN\n"
            "    known_users: list[str] = []\n"
            "    known_objects: list[str] = []\n"
            "    try:\n"
            "        metadata_users, metadata_objects, _metadata_status = fetch_metadata()\n"
            "        known_users = [str(item.get(\"name\")) for item in metadata_users if item.get(\"name\")]\n"
            "        known_objects = [str(item.get(\"name\")) for item in metadata_objects if item.get(\"name\")]\n"
            "    except Exception as exc:\n"
            "        print(f\"[DYNAMIC_GUARDRAILS_METADATA_WARNING] {exc}\")\n"
            "\n"
            "    sql = prepare_sql_for_execution(\n"
            "        sql,\n"
            "        question=req.question,\n"
            "        known_users=known_users,\n"
            "        known_objects=known_objects,\n"
            "    )\n"
            "    guardrail_ok, guardrail_message = validate_readonly_audit_sql(sql)\n"
            "    # AUDITAI_DYNAMIC_GUARDRAILS_PREPARE_END\n",
            1,
        )

    old_exec_block = (
        "    if request_id is not None:\n"
        "        rows, error = _execute_sql_with_progress(sql, request_id)\n"
        "    else:\n"
        "        rows, error = execute_sql(sql)\n"
        "\n"
        "    blocked = False\n"
    )
    new_exec_block = (
        "    if not guardrail_ok:\n"
        "        rows, error = [], guardrail_message\n"
        "        blocked = True\n"
        "        if request_id is not None:\n"
        "            _update_query_progress(\n"
        "                request_id,\n"
        "                stage_key=\"execute_sql\",\n"
        "                stage_status=\"error\",\n"
        "                current_summary=\"Requête bloquée par les garde-fous de sécurité\",\n"
        "                error=guardrail_message,\n"
        "            )\n"
        "    else:\n"
        "        if request_id is not None:\n"
        "            rows, error = _execute_sql_with_progress(sql, request_id)\n"
        "        else:\n"
        "            rows, error = execute_sql(sql)\n"
        "        blocked = False\n"
    )
    if old_exec_block in text:
        text = text.replace(old_exec_block, new_exec_block, 1)
    elif "guardrail_ok" in text and "Requête bloquée par les garde-fous" not in text:
        raise RuntimeError("Impossible de localiser le bloc d'exécution SQL dans main.py. Patch manuel requis.")

    # Sécurise /api/settings : les utilisateurs simples ne reçoivent pas et ne peuvent pas écraser la connexion Oracle.
    text = re.sub(
        r"@app\.get\(\"/api/settings\", response_model=RuntimeSettings\)\ndef read_settings\([^)]*\) -> RuntimeSettings:\n    return RuntimeSettings\(\*\*get_runtime_settings\(\)\)",
        "@app.get(\"/api/settings\", response_model=RuntimeSettings)\n"
        "def read_settings(current_user: dict = Depends(get_current_user)) -> RuntimeSettings:\n"
        "    payload = sanitize_runtime_settings_for_user(get_runtime_settings(), bool(current_user.get(\"is_admin\")))\n"
        "    return RuntimeSettings(**payload)",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"@app\.post\(\"/api/settings\", response_model=RuntimeSettings\)\ndef write_settings\(payload: RuntimeSettings, current_user: dict = Depends\(get_current_user\)\) -> RuntimeSettings:\n    updated = update_runtime_settings\(payload\.model_dump\(\)\)(.*?)    return RuntimeSettings\(\*\*updated\)",
        "@app.post(\"/api/settings\", response_model=RuntimeSettings)\n"
        "def write_settings(payload: RuntimeSettings, current_user: dict = Depends(get_current_user)) -> RuntimeSettings:\n"
        "    merged_payload = merge_settings_for_role(\n"
        "        payload.model_dump(),\n"
        "        get_runtime_settings(),\n"
        "        bool(current_user.get(\"is_admin\")),\n"
        "    )\n"
        "    updated = update_runtime_settings(merged_payload)\n"
        "    write_audit_log(\n"
        "        username=str(current_user[\"username\"]),\n"
        "        action=\"settings_update\",\n"
        "        result_status=\"ok\",\n"
        "        details=\"Parametres mis a jour\",\n"
        "    )\n"
        "    return RuntimeSettings(**updated)",
        text,
        flags=re.DOTALL,
    )

    path.write_text(text, encoding="utf-8")


def patch_settings_page(path: Path) -> None:
    backup(path)
    text = path.read_text(encoding="utf-8")

    text = ensure_import(text, "import { useAuth } from '@/lib/auth-context'")

    if "const { user } = useAuth()" not in text:
        text = text.replace(
            "  const { settings, refreshSettings, refreshAll } = useAppData()\n",
            "  const { settings, refreshSettings, refreshAll } = useAppData()\n  const { user } = useAuth()\n",
            1,
        )

    text = text.replace(
        "setFormData({ ...settings })",
        "setFormData({ ...settings, interface_lang: 'fr' })",
    )

    if "AUDITAI_FORCE_FRENCH_FIELD_BEGIN" not in text:
        text = text.replace(
            "  const handleInputChange = (field: keyof RuntimeSettings, value: string | number) => {\n    if (!formData) return\n    setFormData({ ...formData, [field]: value })\n  }",
            "  const handleInputChange = (field: keyof RuntimeSettings, value: string | number) => {\n"
            "    if (!formData) return\n"
            "    // AUDITAI_FORCE_FRENCH_FIELD_BEGIN\n"
            "    if (field === 'interface_lang') {\n"
            "      setFormData({ ...formData, interface_lang: 'fr' })\n"
            "      return\n"
            "    }\n"
            "    // AUDITAI_FORCE_FRENCH_FIELD_END\n"
            "    setFormData({ ...formData, [field]: value })\n"
            "  }",
        )

    text = text.replace(
        "await updateSettings(formData)",
        "await updateSettings({ ...formData, interface_lang: 'fr' })",
    )

    if "AUDITAI_ADMIN_ORACLE_CARD_BEGIN" not in text:
        pattern = r"(\s*\{/\* Oracle Connection \*/\}\s*)(<Card>.*?</Card>)(\s*\{/\* Analysis Settings \*/\})"
        m = re.search(pattern, text, flags=re.DOTALL)
        if m:
            text = text[:m.start()] + m.group(1) + "\n          {/* AUDITAI_ADMIN_ORACLE_CARD_BEGIN */}\n          {user?.is_admin && (\n" + m.group(2) + "\n          )}\n          {/* AUDITAI_ADMIN_ORACLE_CARD_END */}" + m.group(3) + text[m.end():]

    # Remplace le sélecteur de langue par un affichage fixe en français.
    fixed_lang = '''<div className="rounded-md border border-input bg-muted/40 px-3 py-2 text-sm font-semibold text-foreground">
                  Français
                </div>'''
    text = re.sub(
        r"<Select\s+value=\{formData\.interface_lang\}.*?</Select>",
        fixed_lang,
        text,
        count=1,
        flags=re.DOTALL,
    )

    path.write_text(text, encoding="utf-8")


def patch_dashboard_page(path: Path) -> None:
    backup(path)
    text = path.read_text(encoding="utf-8")
    if "dashboard.users_subtitle" not in text:
        text = text.replace(
            "<span className=\"text-foreground font-semibold\">{t('dashboard.users_title')}</span>\n                        </div>",
            "<span className=\"text-foreground font-semibold\">{t('dashboard.users_title')}</span>\n                          <p className=\"text-xs font-normal text-muted-foreground\">{t('dashboard.users_subtitle')}</p>\n                        </div>",
            1,
        )
        text = text.replace(
            "<span className=\"text-foreground font-semibold\">{t('dashboard.tables_title')}</span>\n                        </div>",
            "<span className=\"text-foreground font-semibold\">{t('dashboard.tables_title')}</span>\n                          <p className=\"text-xs font-normal text-muted-foreground\">{t('dashboard.tables_subtitle')}</p>\n                        </div>",
            1,
        )
    path.write_text(text, encoding="utf-8")


def patch_i18n(path: Path) -> None:
    backup(path)
    text = path.read_text(encoding="utf-8")

    replacements = {
        "'login.brand': 'ASKSMART'": "'login.brand': 'Audit AI'",
        "accéder à ASKSMART": "accéder à Audit AI",
        "access ASKSMART": "access Audit AI",
        "'settings.lang_en': 'English'": "'settings.lang_en': 'English'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    if "'dashboard.users_subtitle'" not in text:
        text = text.replace(
            "  'dashboard.users_title': 'Utilisateurs',\n",
            "  'dashboard.users_title': 'Utilisateurs',\n  'dashboard.users_subtitle': 'Comptes détectés dans les audits',\n",
            1,
        )
        text = text.replace(
            "  'dashboard.tables_title': 'Tables',\n",
            "  'dashboard.tables_title': 'Tables',\n  'dashboard.tables_subtitle': 'Objets audités disponibles',\n",
            1,
        )
        text = text.replace(
            "  'dashboard.actions_subtitle': 'Types audités',\n",
            "  'dashboard.actions_subtitle': 'Types d’actions auditées',\n",
            1,
        )
        text = text.replace(
            "  'dashboard.users_title': 'Users',\n",
            "  'dashboard.users_title': 'Users',\n  'dashboard.users_subtitle': 'Accounts found in audit logs',\n",
            1,
        )
        text = text.replace(
            "  'dashboard.tables_title': 'Tables',\n",
            "  'dashboard.tables_title': 'Tables',\n  'dashboard.tables_subtitle': 'Available audited objects',\n",
            1,
        )

    path.write_text(text, encoding="utf-8")


def patch_globals(path: Path) -> None:
    backup(path)
    text = path.read_text(encoding="utf-8")
    css = r'''

/* AUDITAI_DYNAMIC_GUARDRAILS_SIDEBAR_READABILITY_BEGIN */
[data-sidebar="sidebar"] {
  color: #f8fbff;
}

[data-sidebar="menu-button"] {
  color: rgba(248, 251, 255, 0.94);
  font-weight: 650;
}

[data-sidebar="menu-button"] span,
[data-sidebar="content"] button,
[data-sidebar="footer"] button,
[data-sidebar="footer"] p,
[data-sidebar="footer"] span {
  font-weight: 650;
}

[data-sidebar="menu-button"]:hover,
[data-sidebar="menu-button"][data-active="true"] {
  color: #ffffff;
  font-weight: 750;
}

[data-sidebar="content"] .text-muted-foreground,
[data-sidebar="footer"] .text-muted-foreground {
  color: rgba(248, 251, 255, 0.82) !important;
}
/* AUDITAI_DYNAMIC_GUARDRAILS_SIDEBAR_READABILITY_END */
'''
    if "AUDITAI_DYNAMIC_GUARDRAILS_SIDEBAR_READABILITY_BEGIN" not in text:
        text += css
    path.write_text(text, encoding="utf-8")


def patch_sidebar_brand(path: Path) -> None:
    backup(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace("ASKSMART", "Audit AI")
    text = text.replace("AuditAI", "Audit AI")
    # Renforce quelques classes sans dépendre du thème.
    text = text.replace(
        'font-semibold text-sm tracking-tight truncate">Audit AI',
        'font-bold text-2xl tracking-tight truncate">Audit AI',
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    root = Path.cwd()
    backend = root / "backend"
    frontend = root / "frontend"
    if not backend.exists() or not frontend.exists():
        raise SystemExit("Lance ce script depuis la racine du projet, par exemple C:\\dossier3\\nlp")

    dynamic_service_path = backend / "app" / "services" / "dynamic_guardrails_service.py"
    oracle_service_path = backend / "app" / "services" / "oracle_service.py"
    nlp_service_path = backend / "app" / "services" / "nlp_service.py"
    main_path = backend / "app" / "main.py"
    settings_page_path = frontend / "app" / "(dashboard)" / "settings" / "page.tsx"
    dashboard_page_path = frontend / "app" / "(dashboard)" / "page.tsx"
    i18n_path = frontend / "lib" / "i18n.ts"
    globals_path = frontend / "app" / "globals.css"
    sidebar_path = frontend / "components" / "app-sidebar.tsx"

    for path in (oracle_service_path, nlp_service_path, main_path, settings_page_path, dashboard_page_path, i18n_path, globals_path, sidebar_path):
        if not path.exists():
            raise FileNotFoundError(f"Fichier requis introuvable : {path}")

    backup(oracle_service_path)
    write_text(dynamic_service_path, DYNAMIC_GUARDRAILS_SERVICE)
    write_text(oracle_service_path, ORACLE_SERVICE)

    patch_nlp_service(nlp_service_path)
    patch_main(main_path)
    patch_settings_page(settings_page_path)
    patch_dashboard_page(dashboard_page_path)
    patch_i18n(i18n_path)
    patch_globals(globals_path)
    patch_sidebar_brand(sidebar_path)

    print()
    print("=" * 72)
    print("PATCH AUDIT AI DYNAMIC GUARDRAILS APPLIQUÉ")
    print("=" * 72)
    print(f"Date : {datetime.now()}")
    print("\nFichiers modifiés :")
    for path in (
        dynamic_service_path,
        oracle_service_path,
        nlp_service_path,
        main_path,
        settings_page_path,
        dashboard_page_path,
        i18n_path,
        globals_path,
        sidebar_path,
    ):
        print(f"- {path.relative_to(root)}")
    print("\nSauvegardes : suffixe", BACKUP_SUFFIX)
    print("\nÀ faire maintenant :")
    print("1) Redémarrer le backend : cd backend ; uvicorn app.main:app --reload")
    print("2) Redémarrer/rafraîchir le frontend : cd frontend ; npm run dev")
    print("3) Tester une question comme : Quelle est la dernière action de SYSTEM ?")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
