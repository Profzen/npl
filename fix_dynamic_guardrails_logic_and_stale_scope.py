"""
Audit AI — Correctif garde-fous dynamiques v2

À placer à la racine du projet : C:\\dossier3\\nlp
Commande : python .\\fix_dynamic_guardrails_logic_and_stale_scope.py

Ce correctif répare trois problèmes observés après le patch dynamique :
1) références restantes à l'ancienne fonction apply_allowed_object_scope ;
2) confusion entre utilisateur SYSTEM et objet SYSTEM ;
3) SQL généré avec USERNAME au lieu de DBUSERNAME.

Il ne transforme pas le système en questions préfabriquées. Il garde le modèle
comme moteur principal et ne corrige que des erreurs structurelles évidentes.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from datetime import datetime

BACKUP_SUFFIX = ".bak_dynamic_guardrails_v2_fix"

APPEND_PATCH = r'''

# ---------------------------------------------------------------------------
# Audit AI — correctifs dynamiques v2
# ---------------------------------------------------------------------------
# Ces définitions remplacent volontairement les versions précédentes du module.
# Python utilise les dernières fonctions définies dans le fichier.
# Objectif : éviter les faux filtres, notamment SYSTEM détecté à tort comme
# OBJECT_NAME, et normaliser USERNAME vers DBUSERNAME.


def _question_has_object_intent_v2(question: str | None) -> bool:
    q = normalize_text(question or "")
    object_terms = (
        "TABLE", "OBJET", "OBJECT", "SUR LA TABLE", "SUR L OBJET",
        "TOUCHE A LA TABLE", "TOUCHER LA TABLE", "CONSULTE LA TABLE",
        "MODIFIE LA TABLE", "SUPPRIME LA TABLE", "BASE SUR", "DANS LA TABLE",
    )
    return any(term in q for term in object_terms)


def _question_has_user_intent_v2(question: str | None) -> bool:
    q = normalize_text(question or "")
    user_terms = (
        "UTILISATEUR", "USER", "PAR ", "PAR L UTILISATEUR", "DE L UTILISATEUR",
        "AUTEUR", "COMPTE", "DBUSERNAME",
    )
    return any(term in q for term in user_terms)


def _normalize_audit_column_aliases_v2(sql: str) -> str:
    """Corrige les alias de colonnes fréquents produits par le modèle.

    Dans UNIFIED_AUDIT_DATA, la colonne utilisateur est DBUSERNAME.
    Le modèle génère parfois USERNAME='SYSTEM'. On normalise vers DBUSERNAME.
    """
    fixed = sql or ""
    # Remplacer USERNAME seulement comme identifiant SQL isolé, pas DBUSERNAME.
    fixed = re.sub(r"(?<![A-Z0-9_])USERNAME(?![A-Z0-9_])", "DBUSERNAME", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"(?<![A-Z0-9_])USER_NAME(?![A-Z0-9_])", "DBUSERNAME", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"(?<![A-Z0-9_])OBJECT(?![A-Z0-9_])", "OBJECT_NAME", fixed, flags=re.IGNORECASE)
    fixed = re.sub(r"(?<![A-Z0-9_])ACTION(?![A-Z0-9_])", "ACTION_NAME", fixed, flags=re.IGNORECASE)
    return fixed


def detect_question_objects(question: str, known_objects: Iterable[str] | None = None) -> list[str]:
    """Détection volontairement prudente des objets.

    Avant, on cherchait aveuglément tous les noms du catalogue dans la question.
    Si OBJECT_NAME contenait SYSTEM, la phrase "utilisateur SYSTEM" ajoutait
    par erreur OBJECT_NAME='SYSTEM'. Maintenant, on ne détecte un objet que si
    la question parle clairement d'une table/objet.
    """
    if not _question_has_object_intent_v2(question):
        return []
    found = _detect_from_catalog(question, known_objects or [])
    if found:
        return found[:3]
    fallback = _detect_object_fallback(question)
    return [fallback] if fallback else []


def _build_question_filters(
    question: str | None,
    sql: str,
    known_users: Iterable[str] | None = None,
    known_objects: Iterable[str] | None = None,
) -> list[str]:
    """Construit les filtres de contrôle sans rendre le système rigide."""
    filters: list[str] = [get_hidden_objects_condition("OBJECT_NAME")]

    if not question:
        return filters

    normalized_sql = _normalize_audit_column_aliases_v2(sql)

    users = detect_question_users(question, known_users)
    if users and not _has_filter(normalized_sql, "DBUSERNAME"):
        filters.append("UPPER(DBUSERNAME) IN (" + _sql_list(users) + ")")

    # On ne cherche les objets que si la question contient une intention objet/table.
    objects = detect_question_objects(question, known_objects)
    # Évite aussi les doublons absurdes : un mot déjà détecté comme utilisateur ne doit pas devenir objet.
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

    return filters


def prepare_sql_for_execution(
    sql: str,
    question: str | None = None,
    known_users: Iterable[str] | None = None,
    known_objects: Iterable[str] | None = None,
) -> str:
    """Prépare le SQL généré par le modèle sans le remplacer.

    Le modèle reste la source principale. Ce correctif :
    - normalise USERNAME -> DBUSERNAME ;
    - ajoute uniquement les contraintes évidentes absentes ;
    - évite de confondre SYSTEM utilisateur avec SYSTEM objet ;
    - applique le scope dynamique des objets masqués.
    """
    prepared = (sql or "").strip().rstrip(";").strip()
    if not prepared:
        return prepared

    prepared = _normalize_audit_column_aliases_v2(prepared)

    filters = _build_question_filters(question, prepared, known_users, known_objects)
    prepared = apply_base_scope(prepared, filters)
    if question:
        prepared = _add_final_order_fetch_if_needed(prepared, question)

    if not _has_fetch(prepared) and not _is_aggregation(prepared):
        prepared = f"{prepared.rstrip()} FETCH FIRST {max(1, int(get_fetch_limit()))} ROWS ONLY"

    return prepared.rstrip().rstrip(";") + ";"
'''


def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def fix_dynamic_guardrails_service(path: Path) -> bool:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    text = read(path)
    original = text

    # Corrige l'erreur de guillemets si elle est encore présente.
    bad = 'clauses.append(f"UPPER({column}) NOT LIKE \'{pattern.replace("\'", "\'\'").upper()}\'")'
    if bad in text:
        text = text.replace(
            bad,
            'safe_pattern = pattern.replace("\\\'", "\\\'\\\'").upper()\n        clauses.append(f"UPPER({column}) NOT LIKE \'{safe_pattern}\'")'
        )

    # Assurer que Iterable est importé si le fichier a été modifié à la main.
    if "from typing import Iterable" not in text:
        if "import unicodedata" in text:
            text = text.replace("import unicodedata\n", "import unicodedata\nfrom typing import Iterable\n", 1)
        else:
            text = "from typing import Iterable\n" + text

    # Supprimer une ancienne version du correctif v2 pour rendre le script relançable.
    marker = "# Audit AI — correctifs dynamiques v2"
    idx = text.find(marker)
    if idx != -1:
        # garder les deux lignes séparatrices précédentes si présentes
        start = text.rfind("# ---------------------------------------------------------------------------", 0, idx)
        if start != -1:
            text = text[:start].rstrip() + "\n"
        else:
            text = text[:idx].rstrip() + "\n"

    text = text.rstrip() + APPEND_PATCH + "\n"

    if text != original:
        backup(path)
        write(path, text)
        return True
    return False


def normalize_oracle_imports_and_stale_calls(path: Path) -> tuple[bool, int]:
    if not path.exists():
        return False, 0
    text = read(path)
    original = text
    removed = 0

    wanted = "from app.services.oracle_service import execute_sql, fetch_metadata, get_connection, oracle_status"

    def repl_multiline(match: re.Match[str]) -> str:
        block = match.group(0)
        if "apply_allowed_object_scope" in block:
            return wanted
        return block

    text = re.sub(
        r"from app\.services\.oracle_service import \([^)]*\)",
        repl_multiline,
        text,
        flags=re.DOTALL,
    )

    def repl_single(match: re.Match[str]) -> str:
        line = match.group(0)
        if "apply_allowed_object_scope" in line:
            return wanted
        return line

    text = re.sub(
        r"from app\.services\.oracle_service import [^\n]+",
        repl_single,
        text,
    )

    # Supprime tout appel direct à l'ancienne fonction.
    text, n = re.subn(r"^\s*sql\s*=\s*apply_allowed_object_scope\([^\n]*\)\s*$\n?", "", text, flags=re.MULTILINE)
    removed += n
    text, n = re.subn(r"^\s*[^\n]*apply_allowed_object_scope\([^\n]*\)\s*$\n?", "", text, flags=re.MULTILINE)
    removed += n

    if text != original:
        backup(path)
        write(path, text)
        return True, removed
    return False, 0


def main() -> None:
    root = Path.cwd()
    backend_app = root / "backend" / "app"
    service_path = backend_app / "services" / "dynamic_guardrails_service.py"

    if not backend_app.exists():
        raise SystemExit("Lance ce script depuis la racine du projet, par exemple C:\\dossier3\\nlp")

    changed: list[str] = []
    if fix_dynamic_guardrails_service(service_path):
        changed.append(str(service_path.relative_to(root)))

    total_removed = 0
    for py_file in backend_app.rglob("*.py"):
        if py_file.name.endswith(BACKUP_SUFFIX):
            continue
        did, removed = normalize_oracle_imports_and_stale_calls(py_file)
        if did:
            changed.append(str(py_file.relative_to(root)))
            total_removed += removed

    remaining = []
    for py_file in backend_app.rglob("*.py"):
        if py_file.name.endswith(BACKUP_SUFFIX):
            continue
        if "apply_allowed_object_scope" in read(py_file):
            remaining.append(str(py_file.relative_to(root)))

    print()
    print("=" * 80)
    print("AUDIT AI — CORRECTIF DYNAMIC GUARDRAILS V2")
    print("=" * 80)
    print(f"Date : {datetime.now()}")
    if changed:
        print("\nFichiers modifiés :")
        for item in sorted(set(changed)):
            print(f"- {item}")
    else:
        print("\nAucun changement nécessaire.")
    print(f"\nAppels obsolètes apply_allowed_object_scope supprimés : {total_removed}")
    if remaining:
        print("\nATTENTION : références restantes à vérifier :")
        for item in remaining:
            print(f"- {item}")
    else:
        print("\nOK : aucune référence active à apply_allowed_object_scope.")

    print("\nCe correctif évite notamment :")
    print("- USERNAME='SYSTEM' au lieu de DBUSERNAME='SYSTEM'")
    print("- OBJECT_NAME='SYSTEM' ajouté par erreur quand SYSTEM est un utilisateur")
    print("- ancien appel apply_allowed_object_scope restant dans le backend")
    print("\nRedémarre ensuite le backend :")
    print("cd backend")
    print("uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
    print()


if __name__ == "__main__":
    main()
