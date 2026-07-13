"""
Audit AI - Politique dynamique d'affichage de la colonne Tables

Objectif :
- Afficher maintenant uniquement les tables métier souhaitées :
  EMPLOYEES, DEPARTMENTS, RULE_SET, HR, ADRESS
- Masquer les autres tables déjà présentes actuellement dans SMART2DSECU.UNIFIED_AUDIT_DATA
- Laisser apparaître automatiquement toute nouvelle table future qui n'existait pas au moment de l'application du script.

Usage depuis la racine du projet :
    cd C:\\dossier3\\nlp
    python .\\manage_sidebar_tables_dynamic_policy.py

Puis redémarrer le backend FastAPI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path.cwd().resolve()
BACKEND_DIR = ROOT / "backend"
ORACLE_SERVICE = BACKEND_DIR / "app" / "services" / "oracle_service.py"
POLICY_FILE = BACKEND_DIR / "app" / "sidebar_table_policy.json"
BACKUP_SUFFIX = ".bak_sidebar_table_policy"

VISIBLE_NOW = [
    "EMPLOYEES",
    "DEPARTMENTS",
    "RULE_SET",
    "HR",
    "ADRESS",
]

# Ces patterns restent masqués même si de nouvelles tables futures correspondent à ces noms techniques.
TECHNICAL_HIDE_EXACT = [
    "AUD$",
    "VROMUALD",
    "TEST",
]

TECHNICAL_HIDE_LIKE = [
    "SCHEMA_VERSION_REGIST%",
    "TEST%",
    "%VROMUALD%",
    "%ROMUALD%",
    "BIN$%",
    "SYS_EXPORT%",
]

# Liste de secours utilisée seulement si le script n'arrive pas à interroger Oracle.
# Le mode idéal reste la capture automatique de toutes les tables actuelles.
FALLBACK_CURRENT_OBJECTS = [
    "VROMUALD",
    "EMPLOYEES",
    "AUD$",
    "SCHEMA_VERSION_REGIST",
    "SCHEMA_VERSION_REGISTRY",
    "DEVICE_ADDRESS",
    "SMA_MIGRATION_17_TEST",
    "PROD1_UMS",
    "DEPARTMENTS",
    "MGMT_VIEW",
    "USER_DEVICE",
    "COMPONENT_SCHEMA_INFO",
    "ADD_JOB_HISTORY",
    "TEST",
    "TEST_ROMUALD",
    "TEST_CLIENT",
    "HR",
    "ADRESS",
    "RULE_SET",
    "CLIENT",
]


def fail(message: str) -> None:
    print(f"[ERREUR] {message}")
    raise SystemExit(1)


def backup_file(path: Path) -> Path:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"[OK] Sauvegarde créée : {backup}")
    else:
        print(f"[INFO] Sauvegarde déjà existante : {backup}")
    return backup


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_runtime_settings() -> dict[str, Any]:
    """Tente de lire les paramètres Oracle déjà présents dans le projet."""
    candidates = [
        ROOT / "backend_runtime_settings.json",
        BACKEND_DIR / "backend_runtime_settings.json",
        BACKEND_DIR / "runtime_settings.json",
        BACKEND_DIR / "app" / "runtime_settings.json",
    ]
    for path in candidates:
        data = load_json_if_exists(path)
        if data:
            print(f"[INFO] Paramètres runtime trouvés : {path}")
            return data
    return {}


def pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def normalize_table_name(name: str | None) -> str:
    if not name:
        return "SMART2DSECU.UNIFIED_AUDIT_DATA"
    return str(name).strip()


def query_current_objects_from_oracle() -> list[str]:
    """Capture les OBJECT_NAME actuellement présents dans la table d'audit.

    Cette capture sert de baseline : les tables actuelles non autorisées seront masquées,
    mais les futures tables non présentes dans cette baseline resteront visibles.
    """
    settings = load_runtime_settings()

    # Plusieurs noms possibles selon les versions du backend.
    user = pick(settings, "oracle_user", "user", "username", "db_user")
    password = pick(settings, "oracle_password", "password", "db_password")
    host = pick(settings, "oracle_host", "host", "db_host")
    port = int(pick(settings, "oracle_port", "port", "db_port", default=1521))
    service = pick(settings, "oracle_service", "service", "service_name", "db_service")
    table_name = normalize_table_name(pick(settings, "oracle_table", "audit_table", "table_name"))

    if not all([user, password, host, service]):
        print("[WARN] Paramètres Oracle incomplets. Utilisation de la baseline de secours.")
        return sorted(set(FALLBACK_CURRENT_OBJECTS))

    try:
        import oracledb  # type: ignore
    except Exception as exc:
        print(f"[WARN] Module oracledb indisponible ({exc}). Utilisation de la baseline de secours.")
        return sorted(set(FALLBACK_CURRENT_OBJECTS))

    conn = None
    cur = None
    try:
        dsn = oracledb.makedsn(host, port, service_name=service)
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        cur = conn.cursor()
        sql = f"""
            SELECT DISTINCT UPPER(OBJECT_NAME)
            FROM {table_name}
            WHERE OBJECT_NAME IS NOT NULL
        """
        cur.execute(sql)
        objects = sorted({str(row[0]).strip().upper() for row in cur.fetchall() if row and row[0]})
        if not objects:
            print("[WARN] Aucun OBJECT_NAME trouvé. Utilisation de la baseline de secours.")
            return sorted(set(FALLBACK_CURRENT_OBJECTS))
        print(f"[OK] Baseline Oracle capturée : {len(objects)} objets actuels.")
        return objects
    except Exception as exc:
        print(f"[WARN] Impossible d'interroger Oracle ({exc}). Utilisation de la baseline de secours.")
        return sorted(set(FALLBACK_CURRENT_OBJECTS))
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            if conn is not None:
                conn.close()


def write_policy_file(current_objects: list[str]) -> None:
    visible = sorted({x.upper() for x in VISIBLE_NOW})
    baseline = sorted({x.upper() for x in current_objects})

    policy = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "description": (
            "Tables visibles dans la colonne Tables : tables métier autorisées maintenant + "
            "nouvelles tables futures non présentes dans baseline_current_objects. "
            "Cette politique concerne uniquement l'affichage de la colonne Tables, pas les requêtes utilisateur."
        ),
        "visible_now": visible,
        "baseline_current_objects": baseline,
        "technical_hide_exact": sorted({x.upper() for x in TECHNICAL_HIDE_EXACT}),
        "technical_hide_like": sorted({x.upper() for x in TECHNICAL_HIDE_LIKE}),
    }
    POLICY_FILE.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Politique écrite : {POLICY_FILE}")
    print("[INFO] Tables visibles immédiatement : " + ", ".join(visible))
    print("[INFO] Toute table future absente de la baseline pourra apparaître automatiquement.")


POLICY_BLOCK = r'''
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
'''


def insert_or_replace_policy_block(text: str) -> str:
    start = "# === AUDITAI SIDEBAR TABLE POLICY START ==="
    end = "# === AUDITAI SIDEBAR TABLE POLICY END ==="
    if start in text and end in text:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
        return pattern.sub(POLICY_BLOCK.strip(), text)

    # Insérer après les imports principaux.
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from ") or stripped == "" or stripped.startswith("#"):
            insert_at = i + 1
            continue
        break
    lines.insert(insert_at, "\n" + POLICY_BLOCK.strip() + "\n")
    return "\n".join(lines) + "\n"


def replace_obj_sql_assignment(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    replaced = False

    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*obj_sql\s*=", line):
            indent = re.match(r"^(\s*)", line).group(1)  # type: ignore[union-attr]
            # Remplacer le bloc d'affectation obj_sql = (...) ou obj_sql = "...".
            paren_depth = line.count("(") - line.count(")")
            j = i
            if paren_depth > 0:
                while j + 1 < len(lines) and paren_depth > 0:
                    j += 1
                    paren_depth += lines[j].count("(") - lines[j].count(")")
            out.append(f"{indent}obj_sql = build_sidebar_objects_sql(oracle_table)")
            i = j + 1
            replaced = True
            continue
        out.append(line)
        i += 1

    new_text = "\n".join(out) + "\n"
    if replaced:
        print("[OK] Requête obj_sql remplacée par build_sidebar_objects_sql(...).")
        return new_text

    # Si aucun obj_sql n'est trouvé, essayer une insertion prudente autour de OBJECT_NAME query.
    print("[WARN] Aucun bloc obj_sql trouvé automatiquement. Le bloc politique a été ajouté, mais vérifie fetch_metadata manuellement.")
    return new_text


def main() -> None:
    print("=" * 72)
    print("Audit AI - Patch dynamique colonne Tables")
    print("=" * 72)

    if not ORACLE_SERVICE.exists():
        fail(f"Fichier introuvable : {ORACLE_SERVICE}. Lance le script depuis la racine du projet nlp.")

    current_objects = query_current_objects_from_oracle()
    write_policy_file(current_objects)

    original = ORACLE_SERVICE.read_text(encoding="utf-8")
    backup_file(ORACLE_SERVICE)

    patched = insert_or_replace_policy_block(original)
    patched = replace_obj_sql_assignment(patched)

    ORACLE_SERVICE.write_text(patched, encoding="utf-8")

    print("=" * 72)
    print("PATCH TERMINÉ")
    print("=" * 72)
    print("Redémarre ensuite le backend :")
    print("  cd backend")
    print("  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
    print()
    print("Comportement attendu :")
    print("- visibles maintenant : EMPLOYEES, DEPARTMENTS, RULE_SET, HR, ADRESS")
    print("- les autres tables actuelles sont masquées")
    print("- une nouvelle table future apparaîtra automatiquement après actualisation / reconnexion")
    print("=" * 72)


if __name__ == "__main__":
    main()
