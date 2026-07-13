"""
Audit AI — Correctif référence obsolète apply_allowed_object_scope

À placer à la racine du projet : C:\\dossier3\\nlp
Commande : python .\\fix_stale_allowed_object_scope_reference.py

Pourquoi :
Un ancien patch utilisait apply_allowed_object_scope(). Le patch dynamique utilise
maintenant prepare_sql_for_execution(). Si une ancienne ligne est restée dans
main.py, le backend démarre mais plante au moment de répondre à une question avec :
    name 'apply_allowed_object_scope' is not defined

Ce script supprime uniquement les références obsolètes à apply_allowed_object_scope.
Il ne désactive pas les garde-fous dynamiques.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from datetime import datetime

BACKUP_SUFFIX = ".bak_fix_stale_allowed_scope"


def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def normalize_oracle_import(text: str) -> str:
    wanted = "from app.services.oracle_service import execute_sql, fetch_metadata, get_connection, oracle_status"

    # Cas import multi-ligne depuis oracle_service
    def repl_multiline(match: re.Match[str]) -> str:
        content = match.group(0)
        if "apply_allowed_object_scope" not in content:
            return content
        return wanted

    text = re.sub(
        r"from app\.services\.oracle_service import \([^)]*\)",
        repl_multiline,
        text,
        flags=re.DOTALL,
    )

    # Cas import sur une seule ligne depuis oracle_service
    def repl_single(match: re.Match[str]) -> str:
        line = match.group(0)
        if "apply_allowed_object_scope" not in line:
            return line
        return wanted

    text = re.sub(
        r"from app\.services\.oracle_service import [^\n]+",
        repl_single,
        text,
    )

    # Cas import direct isolé
    text = re.sub(
        r"^\s*from app\.services\.oracle_service import apply_allowed_object_scope\s*$\n?",
        "",
        text,
        flags=re.MULTILINE,
    )
    return text


def remove_stale_calls(text: str) -> tuple[str, int]:
    count = 0

    # Supprime les lignes simples du type : sql = apply_allowed_object_scope(sql)
    pattern_line = r"^\s*sql\s*=\s*apply_allowed_object_scope\([^\n]*\)\s*$\n?"
    text, n = re.subn(pattern_line, "", text, flags=re.MULTILINE)
    count += n

    # Supprime les autres lignes simples contenant uniquement l'appel obsolète.
    pattern_call_only = r"^\s*apply_allowed_object_scope\([^\n]*\)\s*$\n?"
    text, n = re.subn(pattern_call_only, "", text, flags=re.MULTILINE)
    count += n

    return text, count


def patch_file(path: Path) -> tuple[bool, int]:
    if not path.exists():
        return False, 0
    text = path.read_text(encoding="utf-8")
    original = text

    text = normalize_oracle_import(text)
    text, removed_calls = remove_stale_calls(text)

    if text != original:
        backup(path)
        path.write_text(text, encoding="utf-8")
        return True, removed_calls
    return False, 0


def main() -> None:
    root = Path.cwd()
    backend_app = root / "backend" / "app"
    if not backend_app.exists():
        raise SystemExit("Lance ce script depuis la racine du projet, par exemple C:\\dossier3\\nlp")

    changed_files: list[tuple[Path, int]] = []
    remaining: list[Path] = []

    for path in backend_app.rglob("*.py"):
        changed, removed_calls = patch_file(path)
        if changed:
            changed_files.append((path, removed_calls))

    # Vérification : il ne doit rester aucune référence sauf éventuellement dans les sauvegardes, ignorées ici.
    for path in backend_app.rglob("*.py"):
        if path.name.endswith(BACKUP_SUFFIX):
            continue
        text = path.read_text(encoding="utf-8")
        if "apply_allowed_object_scope" in text:
            remaining.append(path)

    print()
    print("=" * 72)
    print("CORRECTIF RÉFÉRENCE OBSOLÈTE APPLIQUÉ")
    print("=" * 72)
    print(f"Date : {datetime.now()}")

    if changed_files:
        print("\nFichiers modifiés :")
        for path, removed_calls in changed_files:
            print(f"- {path.relative_to(root)}  | appels supprimés : {removed_calls}")
    else:
        print("\nAucun fichier n'avait besoin d'être modifié.")

    if remaining:
        print("\nATTENTION : références restantes à vérifier manuellement :")
        for path in remaining:
            print(f"- {path.relative_to(root)}")
    else:
        print("\nOK : plus aucune référence active à apply_allowed_object_scope dans backend/app.")

    print("\nSauvegardes : suffixe", BACKUP_SUFFIX)
    print("\nRedémarre ensuite le backend :")
    print("cd backend")
    print("uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
    print()


if __name__ == "__main__":
    main()
