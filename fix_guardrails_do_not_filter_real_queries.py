from pathlib import Path
import re
import shutil
import sys

BACKUP_SUFFIX = ".bak_no_query_object_filter"


def find_root() -> Path:
    cwd = Path.cwd().resolve()
    candidates = [cwd, cwd.parent]
    for c in candidates:
        if (c / "backend" / "app" / "services").exists():
            return c
    raise SystemExit("Racine projet introuvable. Lance ce script depuis C:\\dossier3\\nlp ou C:\\dossier3\\nlp\\backend.")


def backup(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    bak = path.with_name(path.name + BACKUP_SUFFIX)
    if not bak.exists():
        shutil.copy2(path, bak)


def replace_function(text: str, func_name: str, new_source: str) -> str:
    pattern = rf"\ndef {re.escape(func_name)}\(.*?\n(?=def |class |$)"
    m = re.search(pattern, text, flags=re.DOTALL)
    if not m:
        # function could be at very top
        pattern = rf"^def {re.escape(func_name)}\(.*?\n(?=def |class |$)"
        m = re.search(pattern, text, flags=re.DOTALL)
    if not m:
        raise SystemExit(f"Fonction {func_name} introuvable dans dynamic_guardrails_service.py")
    prefix = "" if m.group(0).startswith("def ") else "\n"
    return text[:m.start()] + prefix + new_source.rstrip() + "\n\n" + text[m.end():]


NEW_BUILD_FILTERS = r'''def _build_question_filters(
    question: str | None,
    sql: str,
    known_users: Iterable[str] | None = None,
    known_objects: Iterable[str] | None = None,
) -> list[str]:
    """Construit uniquement des filtres explicites issus de la question.

    Point important : on ne filtre plus globalement OBJECT_NAME ici.
    Les filtres de tables masquées servent à l'affichage de la colonne Tables,
    pas à supprimer des lignes dans les vraies questions utilisateur.

    Exemple : "dernière action de SYSTEM" doit chercher toutes les actions de
    SYSTEM, même si OBJECT_NAME est NULL ou correspond à une table masquée de
    l'interface. Sinon on obtient de faux "aucun résultat".
    """
    filters: list[str] = []

    if not question:
        return filters

    normalized_sql = _normalize_audit_column_aliases_v2(sql) if "_normalize_audit_column_aliases_v2" in globals() else sql

    users = detect_question_users(question, known_users)
    if users and not _has_filter(normalized_sql, "DBUSERNAME"):
        filters.append("UPPER(DBUSERNAME) IN (" + _sql_list(users) + ")")

    # On ne détecte une table/objet que si la question parle clairement d'une table/objet.
    objects = detect_question_objects(question, known_objects)
    user_set = {u.upper() for u in users}
    objects = [obj for obj in objects if obj.upper() not in user_set]
    if objects and not _has_filter(normalized_sql, "OBJECT_NAME"):
        filters.append("UPPER(OBJECT_NAME) IN (" + _sql_list(objects) + ")")

    actions = detect_question_actions(question)
    if actions and not _has_filter(normalized_sql, "ACTION_NAME"):
        filters.append("UPPER(ACTION_NAME) IN (" + _sql_list(actions) + ")")

    time_condition = detect_time_condition(question)
    if time_condition and not _has_event_timestamp_filter(normalized_sql):
        filters.append(time_condition)
    elif time_condition and ("TO_NUMBER(TO_CHAR(EVENT_TIMESTAMP" in time_condition and "TO_CHAR(EVENT_TIMESTAMP" not in normalized_sql.upper()):
        filters.append(time_condition)

    return filters'''


NEW_APPLY_BASE_SCOPE = r'''def apply_base_scope(sql: str, filters: list[str]) -> str:
    sql = (sql or "").strip().rstrip(";").strip()
    sql = re.sub(r"\bORACLE_AUDIT_TRAIL\b", get_oracle_table().strip(), sql, flags=re.IGNORECASE)
    sql = _remove_legacy_scopes(sql)

    # Si aucun filtre explicite n'est nécessaire, on ne wrappe pas la table.
    # Cela évite un faux filtrage global des lignes d'audit.
    clean_filters = [clause for clause in filters if clause]
    if not clean_filters:
        return sql

    table = get_oracle_table().strip()
    where_clause = " AND ".join(f"({clause})" for clause in clean_filters)
    scoped_source = f"(SELECT * FROM {table} WHERE {where_clause}) {AUDIT_SCOPE_MARKER}"
    pattern = rf"\bFROM\s+{re.escape(table)}\b"

    if re.search(pattern, sql, flags=re.IGNORECASE):
        return re.sub(pattern, f"FROM {scoped_source}", sql, count=1, flags=re.IGNORECASE)

    return sql'''


def clean_stale_references(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    text = re.sub(r"\n\s*sql\s*=\s*apply_allowed_object_scope\(sql\)\s*", "\n", text)
    text = re.sub(r"\n\s*prepared_sql\s*=\s*apply_allowed_object_scope\(prepared_sql\)\s*", "\n", text)
    text = text.replace(", apply_allowed_object_scope", "")
    text = text.replace("apply_allowed_object_scope, ", "")
    if text != original:
        backup(path)
        path.write_text(text, encoding="utf-8")
        print(f"[OK] Anciennes références nettoyées : {path}")


def main() -> None:
    root = find_root()
    service = root / "backend" / "app" / "services" / "dynamic_guardrails_service.py"
    main_py = root / "backend" / "app" / "main.py"
    oracle_service = root / "backend" / "app" / "services" / "oracle_service.py"

    if not service.exists():
        raise SystemExit(f"Fichier introuvable : {service}")

    backup(service)
    text = service.read_text(encoding="utf-8")
    text = replace_function(text, "_build_question_filters", NEW_BUILD_FILTERS)
    text = replace_function(text, "apply_base_scope", NEW_APPLY_BASE_SCOPE)
    service.write_text(text, encoding="utf-8")
    print(f"[OK] Guardrails corrigés : plus de filtre OBJECT_NAME global dans les vraies requêtes.")

    if main_py.exists():
        clean_stale_references(main_py)
    if oracle_service.exists():
        clean_stale_references(oracle_service)

    print("\nTerminé.")
    print("Redémarre le backend :")
    print("  cd backend")
    print("  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")


if __name__ == "__main__":
    main()
