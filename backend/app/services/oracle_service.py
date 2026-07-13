
# === AUDITAI SIDEBAR TABLE POLICY START ===
# Cette politique ne filtre QUE l'affichage de la colonne Tables dans l'interface.
# Elle ne doit pas réécrire les vraies requêtes SQL générées par le modèle NLP.
from pathlib import Path as _AuditAIPath
import json as _auditai_json

_SIDEBAR_TABLE_POLICY_PATH = _AuditAIPath(__file__).resolve().parents[1] / "sidebar_table_policy.json"


def _auditai_sql_list(values):
    cleaned = []
    for value in values or []:
        text = str(value).strip().upper()
        if text:
            cleaned.append("'" + text.replace("'", "''") + "'")
    return ", ".join(sorted(set(cleaned)))


def _load_sidebar_table_policy():
    default_policy = {
        "visible_now": ["EMPLOYEES", "DEPARTMENTS", "RULE_SET", "HR", "ADRESS"],
        "baseline_current_objects": [],
        "technical_hide_exact": ["AUD$", "VROMUALD", "TEST"],
        "technical_hide_like": ["SCHEMA_VERSION_REGIST%", "TEST%", "%VROMUALD%", "%ROMUALD%", "BIN$%", "SYS_EXPORT%"],
    }
    try:
        if _SIDEBAR_TABLE_POLICY_PATH.exists():
            loaded = _auditai_json.loads(_SIDEBAR_TABLE_POLICY_PATH.read_text(encoding="utf-8"))
            default_policy.update({k: loaded.get(k, v) for k, v in default_policy.items()})
    except Exception:
        pass
    return default_policy


def build_sidebar_objects_sql(oracle_table: str) -> str:
    """Construit la requête des tables affichées dans la colonne Tables.

    Logique :
    - les tables dans visible_now sont visibles maintenant ;
    - les tables déjà connues au moment de la baseline sont masquées si elles ne sont pas dans visible_now ;
    - toute nouvelle table future absente de baseline_current_objects devient visible automatiquement ;
    - les patterns techniques restent masqués.
    """
    policy = _load_sidebar_table_policy()
    visible_now = [str(x).upper() for x in policy.get("visible_now", [])]
    baseline = [str(x).upper() for x in policy.get("baseline_current_objects", [])]
    technical_exact = [str(x).upper() for x in policy.get("technical_hide_exact", [])]
    technical_like = [str(x).upper() for x in policy.get("technical_hide_like", [])]

    visible_sql = _auditai_sql_list(visible_now) or "'__AUDITAI_EMPTY__'"
    baseline_sql = _auditai_sql_list(baseline) or "'__AUDITAI_EMPTY__'"
    technical_sql = _auditai_sql_list(technical_exact) or "'__AUDITAI_EMPTY__'"

    new_object_conditions = [
        "OBJECT_NAME IS NOT NULL",
        f"UPPER(OBJECT_NAME) NOT IN ({baseline_sql})",
        f"UPPER(OBJECT_NAME) NOT IN ({technical_sql})",
    ]
    for pattern in technical_like:
        safe_pattern = pattern.replace("'", "''")
        new_object_conditions.append(f"UPPER(OBJECT_NAME) NOT LIKE '{safe_pattern}'")

    new_object_sql = " AND ".join(new_object_conditions)

    return (
        f"SELECT OBJECT_NAME, COUNT(*) AS ACTIONS FROM {oracle_table} "
        f"WHERE OBJECT_NAME IS NOT NULL "
        f"AND (UPPER(OBJECT_NAME) IN ({visible_sql}) OR ({new_object_sql})) "
        f"GROUP BY OBJECT_NAME ORDER BY ACTIONS DESC FETCH FIRST 500 ROWS ONLY"
    )
# === AUDITAI SIDEBAR TABLE POLICY END ===

try:
    import oracledb

    _ORACLE_DRIVER_OK = True
except Exception:
    oracledb = None
    _ORACLE_DRIVER_OK = False

import time as time_module
from threading import Lock

from app.config import settings
from app.services.settings_service import get_oracle_connection_config, get_oracle_table


_POOL = None
_POOL_CFG: tuple[str, str, str, int, str] | None = None
_POOL_LOCK = Lock()

# Metadata cache (TTL: 300s = 5 min)
_METADATA_CACHE: tuple[list[dict], list[dict], str, float] | None = None
_METADATA_CACHE_LOCK = Lock()
_METADATA_CACHE_TTL_SECONDS = 300

# Ces filtres servent uniquement à nettoyer les colonnes d'aide de l'interface.
# Ils ne doivent jamais être injectés dans les vraies requêtes utilisateur.
HIDDEN_OBJECTS_EXACT = {
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
}

HIDDEN_OBJECTS_LIKE = (
    "SCHEMA_VERSION_REGIST%",
    "TEST%",
    "%VROMUALD%",
    "%ROMUALD%",
    "BIN$%",
    "SYS_EXPORT%",
)

# Utilisateurs historiques/bruités à masquer dans la colonne d'aide.
# Les nouveaux utilisateurs apparaissent automatiquement s'ils ne sont pas ici.
HIDDEN_USERS_EXACT = {
    "PROD2_MDS",
    "PROD2_STB",
    "TEST",
    "SMART2DADMIN",
    "SMART2DADMINI",
    "SMART2DSECU",
    "BATCH_USER",
    "\\SMART2DADMIN",

    "PROD2_WLS",}


def _sql_list(values: set[str] | tuple[str, ...]) -> str:
    return ", ".join("'" + str(v).replace("'", "''").upper() + "'" for v in values)


def _hidden_objects_condition(column: str = "OBJECT_NAME") -> str:
    clauses = [f"{column} IS NOT NULL"]
    if HIDDEN_OBJECTS_EXACT:
        clauses.append(f"UPPER({column}) NOT IN ({_sql_list(HIDDEN_OBJECTS_EXACT)})")
    for pattern in HIDDEN_OBJECTS_LIKE:
        safe_pattern = pattern.replace("'", "''").upper()
        clauses.append(f"UPPER({column}) NOT LIKE '{safe_pattern}'")
    return " AND ".join(clauses)


def _hidden_users_condition(column: str = "DBUSERNAME") -> str:
    clauses = [f"{column} IS NOT NULL"]
    if HIDDEN_USERS_EXACT:
        clauses.append(f"UPPER({column}) NOT IN ({_sql_list(HIDDEN_USERS_EXACT)})")
    return " AND ".join(clauses)


def clear_metadata_cache() -> None:
    global _METADATA_CACHE
    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE = None


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
    """Exécute uniquement le SQL produit par le modèle, sans ajout de filtre métier.

    Les filtres d'affichage des colonnes Users/Tables ne doivent pas modifier les vraies réponses.
    """
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql.rstrip().rstrip(";"))
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


def fetch_metadata() -> tuple[list[dict], list[dict], str]:
    """Récupère les colonnes d'aide dynamiquement.

    - Les nouveaux utilisateurs apparaissent automatiquement, sauf s'ils sont dans HIDDEN_USERS_EXACT.
    - Les nouvelles tables apparaissent automatiquement, sauf si elles matchent les règles HIDDEN_OBJECTS_*.
    - Ces filtres ne s'appliquent qu'à l'affichage des colonnes, pas aux requêtes utilisateur.
    """
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
            f"WHERE {_hidden_users_condition('DBUSERNAME')} "
            "GROUP BY DBUSERNAME ORDER BY ACTIONS DESC FETCH FIRST 500 ROWS ONLY"
        )
        cur.execute(user_sql)
        users = [{"name": str(r[0]), "actions": int(r[1])} for r in cur.fetchall()]

        obj_sql = build_sidebar_objects_sql(oracle_table)
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
