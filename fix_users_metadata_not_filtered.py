"""
Audit AI — Correction métadonnées utilisateurs

But : garder le filtrage des TABLES autorisées, mais ne PAS filtrer la colonne Utilisateurs.

À placer/exécuter à la racine du projet : C:\\dossier3\\nlp
Commande conseillée : python .\\fix_users_metadata_not_filtered.py

Le script modifie uniquement : backend/app/services/oracle_service.py
Il crée une sauvegarde : oracle_service.py.bak_users_unfiltered
"""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime

BACKUP_SUFFIX = ".bak_users_unfiltered"


def find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [here, Path.cwd().resolve(), here.parent, Path.cwd().resolve().parent]

    for candidate in candidates:
        target = candidate / "backend" / "app" / "services" / "oracle_service.py"
        if target.exists():
            return candidate

    raise FileNotFoundError(
        "Impossible de trouver backend/app/services/oracle_service.py. "
        "Place ce script à la racine du projet nlp, puis relance-le."
    )


def backup(path: Path) -> Path:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="")
    return backup_path


def main() -> None:
    root = find_project_root()
    oracle_service = root / "backend" / "app" / "services" / "oracle_service.py"

    print("=" * 72)
    print("Audit AI — Correction affichage utilisateurs")
    print(f"Projet : {root}")
    print(f"Date   : {datetime.now()}")
    print("Objectif : tables filtrées, utilisateurs non filtrés")
    print("=" * 72)

    content = oracle_service.read_text(encoding="utf-8")
    original = content

    # Cas exact généré par le patch précédent : le filtre OBJECT_NAME est dans user_sql.
    filtered_user_sql_pattern = re.compile(
        r'(\s*user_sql\s*=\s*\(\s*\n'
        r'\s*f"SELECT DBUSERNAME, COUNT\(\*\) AS ACTIONS FROM \{oracle_table\} "\s*\n'
        r'\s*"WHERE DBUSERNAME IS NOT NULL "\s*\n)'
        r'\s*f"AND UPPER\(OBJECT_NAME\) IN \(\{allowed_objects\}\) "\s*\n'
        r'(\s*"GROUP BY DBUSERNAME ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"\s*\n'
        r'\s*\)\s*)',
        flags=re.MULTILINE,
    )

    content, changes = filtered_user_sql_pattern.subn(r"\1\2", content, count=1)

    if changes == 0:
        # Sécurité : on vérifie si user_sql semble déjà non filtré.
        if "SELECT DBUSERNAME, COUNT(*) AS ACTIONS" in content and "AND UPPER(OBJECT_NAME) IN ({allowed_objects})" in content:
            print("[INFO] Aucun filtre utilisateur exact trouvé.")
            print("[INFO] Le filtre restant semble probablement être celui des tables, ce qui est normal.")
        else:
            print("[INFO] Aucun filtre utilisateur trouvé. Le fichier semble déjà corrigé.")
        print("=" * 72)
        return

    backup_path = backup(oracle_service)
    oracle_service.write_text(content, encoding="utf-8", newline="")

    print(f"[OK] Modifié : {oracle_service}")
    print(f"[OK] Sauvegarde : {backup_path}")
    print()
    print("À faire maintenant :")
    print("1) Arrêter le backend avec CTRL + C")
    print("2) Relancer : cd backend puis uvicorn app.main:app --reload")
    print("3) Rafraîchir le frontend")
    print()
    print("Résultat attendu :")
    print("- Colonne Tables : seulement VROMUALD, EMPLOYEES, DEPARTMENTS, HR, ADRESS, TEST, CLIENT")
    print("- Colonne Utilisateurs : tous les utilisateurs reviennent")
    print("=" * 72)


if __name__ == "__main__":
    main()
