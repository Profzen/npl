"""
Patch Audit AI — Limitation des tables visibles/interrogeables

Objectif : limiter la plateforme aux objets Oracle autorisés :
VROMUALD, EMPLOYEES, DEPARTMENTS, HR, ADRESS, TEST, CLIENT

À placer et exécuter à la racine du projet : C:\\dossier3\\nlp
Commande : python apply_allowed_tables_patch.py

Le script crée automatiquement des sauvegardes .bak_allowed_tables avant modification.
"""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime

ALLOWED_TABLES = [
    "VROMUALD",
    "EMPLOYEES",
    "DEPARTMENTS",
    "HR",
    "ADRESS",
    "TEST",
    "CLIENT",
]

BACKUP_SUFFIX = ".bak_allowed_tables"


def find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [here, Path.cwd().resolve(), here.parent, Path.cwd().resolve().parent]

    for candidate in candidates:
        if (candidate / "backend" / "app" / "services" / "oracle_service.py").exists():
            return candidate

    raise FileNotFoundError(
        "Impossible de trouver backend/app/services/oracle_service.py. "
        "Place ce script à la racine du projet nlp, puis relance-le."
    )


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def backup(path: Path) -> Path:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="")
    return backup_path


def ensure_import_re(content: str) -> str:
    if re.search(r"^import\s+re\s*$", content, flags=re.MULTILINE):
        return content

    # Le fichier commence par try: import oracledb, donc on ajoute re après ce bloc si possible.
    marker = "from threading import Lock\n"
    if marker in content:
        return content.replace(marker, marker + "import re\n", 1)

    return "import re\n" + content


def allowed_block() -> str:
    tables_repr = ",\n    ".join(f'"{name}"' for name in ALLOWED_TABLES)
    return f'''

# ---------------------------------------------------------------------------
# Audit AI — périmètre fonctionnel autorisé
# ---------------------------------------------------------------------------
# Ces objets restent les seuls visibles dans les métadonnées et les seuls
# interrogeables par les requêtes générées. Pour réactiver d'autres objets,
# ajoute simplement leur nom Oracle exact dans cette liste.
ALLOWED_AUDIT_OBJECTS = (
    {tables_repr},
)

_ALLOWED_OBJECT_SCOPE_MARKER = "/* AUDITAI_ALLOWED_OBJECT_SCOPE */"


def _allowed_objects_sql_list() -> str:
    return ", ".join(
        "'" + obj.replace("'", "''").upper() + "'"
        for obj in ALLOWED_AUDIT_OBJECTS
    )


def apply_allowed_object_scope(sql: str) -> str:
    """
    Force les requêtes sur la table d'audit à rester dans le périmètre autorisé.
    Ce filtre est appliqué côté backend, pas seulement dans l'interface.
    """
    if _ALLOWED_OBJECT_SCOPE_MARKER in sql:
        return sql

    oracle_table = get_oracle_table().strip()
    allowed_objects = _allowed_objects_sql_list()

    scoped_table = (
        f"(SELECT * FROM {{oracle_table}} "
        f"WHERE UPPER(OBJECT_NAME) IN ({{allowed_objects}})) "
        f"{{_ALLOWED_OBJECT_SCOPE_MARKER}}"
    )

    pattern = rf"\\bFROM\\s+{{re.escape(oracle_table)}}\\b"

    return re.sub(
        pattern,
        f"FROM {{scoped_table}}",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
'''


def ensure_allowed_block(content: str) -> str:
    if "ALLOWED_AUDIT_OBJECTS" in content and "apply_allowed_object_scope" in content:
        return content

    marker = "_METADATA_CACHE_TTL_SECONDS = 300\n"
    if marker not in content:
        raise RuntimeError("Marqueur _METADATA_CACHE_TTL_SECONDS introuvable dans oracle_service.py")

    return content.replace(marker, marker + allowed_block(), 1)


def patch_execute_sql(content: str) -> str:
    old = '        cur.execute(sql.rstrip().rstrip(";"))\n'
    new = (
        '        scoped_sql = apply_allowed_object_scope(sql)\n'
        '        cur.execute(scoped_sql.rstrip().rstrip(";"))\n'
    )

    if new in content:
        return content

    if old not in content:
        raise RuntimeError("Instruction cur.execute(sql.rstrip().rstrip(';')) introuvable dans oracle_service.py")

    return content.replace(old, new, 1)


def patch_fetch_metadata(content: str) -> str:
    # Ajoute allowed_objects juste après oracle_table = get_oracle_table()
    old_line = "        oracle_table = get_oracle_table()\n"
    new_line = "        oracle_table = get_oracle_table()\n        allowed_objects = _allowed_objects_sql_list()\n"
    if new_line not in content:
        if old_line not in content:
            raise RuntimeError("Ligne oracle_table = get_oracle_table() introuvable dans fetch_metadata")
        content = content.replace(old_line, new_line, 1)

    old_user = (
        '        user_sql = (\n'
        '            f"SELECT DBUSERNAME, COUNT(*) AS ACTIONS FROM {oracle_table} "\n'
        '            "WHERE DBUSERNAME IS NOT NULL "\n'
        '            "GROUP BY DBUSERNAME ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"\n'
        '        )\n'
    )
    new_user = (
        '        user_sql = (\n'
        '            f"SELECT DBUSERNAME, COUNT(*) AS ACTIONS FROM {oracle_table} "\n'
        '            "WHERE DBUSERNAME IS NOT NULL "\n'
        '            f"AND UPPER(OBJECT_NAME) IN ({allowed_objects}) "\n'
        '            "GROUP BY DBUSERNAME ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"\n'
        '        )\n'
    )
    if new_user not in content:
        if old_user not in content:
            raise RuntimeError("Bloc user_sql introuvable ou déjà différent dans oracle_service.py")
        content = content.replace(old_user, new_user, 1)

    old_obj = (
        '        obj_sql = (\n'
        '            f"SELECT OBJECT_NAME, COUNT(*) AS ACTIONS FROM {oracle_table} "\n'
        '            "WHERE OBJECT_NAME IS NOT NULL "\n'
        '            "GROUP BY OBJECT_NAME ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"\n'
        '        )\n'
    )
    new_obj = (
        '        obj_sql = (\n'
        '            f"SELECT OBJECT_NAME, COUNT(*) AS ACTIONS FROM {oracle_table} "\n'
        '            "WHERE OBJECT_NAME IS NOT NULL "\n'
        '            f"AND UPPER(OBJECT_NAME) IN ({allowed_objects}) "\n'
        '            "GROUP BY OBJECT_NAME ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"\n'
        '        )\n'
    )
    if new_obj not in content:
        if old_obj not in content:
            raise RuntimeError("Bloc obj_sql introuvable ou déjà différent dans oracle_service.py")
        content = content.replace(old_obj, new_obj, 1)

    return content


def patch_oracle_service(path: Path) -> None:
    original = read(path)
    content = original

    content = ensure_import_re(content)
    content = ensure_allowed_block(content)
    content = patch_execute_sql(content)
    content = patch_fetch_metadata(content)

    if content != original:
        backup(path)
        write(path, content)
        print(f"[OK] Modifié : {path}")
    else:
        print(f"[OK] Déjà à jour : {path}")


def patch_main_import(content: str) -> str:
    if "apply_allowed_object_scope" in content:
        return content

    old = "from app.services.oracle_service import execute_sql, fetch_metadata, get_connection, oracle_status\n"
    new = (
        "from app.services.oracle_service import (\n"
        "    execute_sql,\n"
        "    fetch_metadata,\n"
        "    get_connection,\n"
        "    oracle_status,\n"
        "    apply_allowed_object_scope,\n"
        ")\n"
    )

    if old not in content:
        raise RuntimeError("Import oracle_service introuvable dans main.py")

    return content.replace(old, new, 1)


def patch_main_execute_with_progress(content: str) -> str:
    old = '        cur.execute(sql.rstrip().rstrip(";"))\n'
    new = (
        '        scoped_sql = apply_allowed_object_scope(sql)\n'
        '        cur.execute(scoped_sql.rstrip().rstrip(";"))\n'
    )

    if new in content:
        return content

    # Il y a normalement une seule occurrence restante dans main.py.
    if old not in content:
        raise RuntimeError("Instruction cur.execute(sql.rstrip().rstrip(';')) introuvable dans main.py")

    return content.replace(old, new, 1)


def patch_main_generated_sql(content: str) -> str:
    old = "    sql = generate_sql_from_question(req.question)\n"
    new = "    sql = generate_sql_from_question(req.question)\n    sql = apply_allowed_object_scope(sql)\n"

    if new in content:
        return content

    if old not in content:
        raise RuntimeError("Ligne generate_sql_from_question introuvable dans main.py")

    return content.replace(old, new, 1)


def patch_main(path: Path) -> None:
    original = read(path)
    content = original

    content = patch_main_import(content)
    content = patch_main_execute_with_progress(content)
    content = patch_main_generated_sql(content)

    if content != original:
        backup(path)
        write(path, content)
        print(f"[OK] Modifié : {path}")
    else:
        print(f"[OK] Déjà à jour : {path}")


def main() -> None:
    root = find_project_root()
    oracle_service = root / "backend" / "app" / "services" / "oracle_service.py"
    main_py = root / "backend" / "app" / "main.py"

    print("=" * 72)
    print("Audit AI — Patch limitation tables Oracle")
    print(f"Projet : {root}")
    print(f"Date   : {datetime.now()}")
    print("Tables autorisées : " + ", ".join(ALLOWED_TABLES))
    print("=" * 72)

    patch_oracle_service(oracle_service)
    patch_main(main_py)

    print("=" * 72)
    print("Patch terminé.")
    print()
    print("À faire maintenant :")
    print("1) Arrêter le backend FastAPI avec CTRL + C")
    print("2) Relancer le backend, par exemple : uvicorn app.main:app --reload")
    print("3) Rafraîchir le frontend et cliquer sur Refresh si besoin")
    print()
    print("Sauvegardes créées avec le suffixe : " + BACKUP_SUFFIX)
    print("=" * 72)


if __name__ == "__main__":
    main()
