from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

TARGET = "PROD2_WLS"
BACKUP_SUFFIX = ".bak_prod2wls_user_only"

TABLE_COLLECTION_NAMES = [
    "TECHNICAL_HIDE_EXACT",
    "HIDDEN_AUDIT_TABLES_EXACT",
    "HIDDEN_TABLES_EXACT",
    "MASKED_TABLES",
    "EXCLUDED_TABLES",
    "TABLE_HIDE_LIST",
    "hiddenTables",
    "excludedTables",
    "maskedTables",
]

USER_COLLECTION_NAMES = [
    "HIDDEN_SIDEBAR_USERS_EXACT",
    "TECHNICAL_HIDE_USERS_EXACT",
    "HIDDEN_AUDIT_USERS_EXACT",
    "HIDDEN_USERS_EXACT",
    "HIDDEN_USERS",
    "MASKED_USERS",
    "EXCLUDED_USERS",
    "USER_HIDE_LIST",
    "hiddenUsers",
    "excludedUsers",
    "maskedUsers",
]


def find_project_root() -> Path:
    cwd = Path.cwd().resolve()
    candidates = [cwd, cwd.parent]
    for c in candidates:
        if (c / "frontend").exists() and (c / "backend").exists():
            return c
        if c.name == "frontend" and (c.parent / "backend").exists():
            return c.parent
        if c.name == "backend" and (c.parent / "frontend").exists():
            return c.parent
    raise SystemExit(
        "Impossible de trouver la racine du projet.\n"
        "Lance ce script depuis la racine du projet nlp, ou depuis frontend/backend."
    )


def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if path.exists() and not backup_path.exists():
        shutil.copy2(path, backup_path)
        print(f"[OK] Sauvegarde créée : {backup_path}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text_if_changed(path: Path, old: str, new: str) -> bool:
    if new == old:
        return False
    backup(path)
    path.write_text(new, encoding="utf-8")
    print(f"[OK] Modifié : {path}")
    return True


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def remove_from_json_lists(obj: Any, target: str) -> tuple[Any, bool]:
    changed = False
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            new_v, ch = remove_from_json_lists(v, target)
            new_obj[k] = new_v
            changed = changed or ch
        return new_obj, changed
    if isinstance(obj, list):
        new_list = [x for x in obj if str(x).strip().upper() != target]
        if len(new_list) != len(obj):
            changed = True
        return new_list, changed
    return obj, False


def patch_table_policy(root: Path) -> bool:
    """Annule l'ancien masquage de PROD2_WLS comme table."""
    path = root / "backend" / "app" / "sidebar_table_policy.json"
    if not path.exists():
        print("[INFO] sidebar_table_policy.json introuvable : rien à nettoyer côté Tables.")
        return False

    old_policy = load_json(path)
    if not old_policy:
        print("[WARN] sidebar_table_policy.json illisible : nettoyage ignoré.")
        return False

    new_policy, changed = remove_from_json_lists(old_policy, TARGET)
    if changed:
        save_json(path, new_policy)
        print(f"[OK] {TARGET} retiré de la politique Tables.")
        return True

    print(f"[INFO] {TARGET} n'était pas présent dans la politique Tables.")
    return False


def patch_user_policy(root: Path) -> bool:
    """Crée/met à jour une politique dédiée aux utilisateurs masqués."""
    path = root / "backend" / "app" / "sidebar_user_policy.json"
    policy = load_json(path)
    if not policy:
        policy = {
            "description": "Politique d'affichage de la colonne Utilisateurs. Ne filtre pas les requêtes SQL utilisateur.",
            "technical_hide_exact": [],
            "technical_hide_like": []
        }

    exact = policy.get("technical_hide_exact")
    if not isinstance(exact, list):
        exact = []
    exact_upper = {str(x).strip().upper() for x in exact if str(x).strip()}

    if TARGET not in exact_upper:
        exact.append(TARGET)
        policy["technical_hide_exact"] = sorted({str(x).strip().upper() for x in exact if str(x).strip()})
        save_json(path, policy)
        print(f"[OK] Politique Utilisateurs mise à jour : {path}")
        return True

    print("[INFO] Politique Utilisateurs déjà à jour.")
    return False


def find_collection_bounds(text: str, name: str) -> tuple[int, int] | None:
    m = re.search(rf"(?m)^([ \t]*{re.escape(name)}\s*=\s*)([\[\(\{{])", text)
    if not m:
        return None
    start = m.start(2)
    opener = text[start]
    closer = {"[": "]", "(": ")", "{": "}"}[opener]
    depth = 0
    end = None
    in_string = None
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
            continue
        if ch in {"'", '"'}:
            in_string = ch
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        return None
    return start, end


def add_to_python_collection(text: str, names: list[str], value: str) -> tuple[str, bool]:
    for name in names:
        bounds = find_collection_bounds(text, name)
        if not bounds:
            continue
        start, end = bounds
        block = text[start:end + 1]
        if re.search(rf"['\"]{re.escape(value)}['\"]", block, re.I):
            return text, False
        line_start = text.rfind("\n", 0, start) + 1
        indent = re.match(r"[ \t]*", text[line_start:start]).group(0)  # type: ignore[union-attr]
        item_indent = indent + "    "
        text = text[:end] + f'\n{item_indent}"{value}",' + text[end:]
        return text, True
    return text, False


def remove_from_python_collection(text: str, names: list[str], value: str) -> tuple[str, bool]:
    changed = False
    for name in names:
        bounds = find_collection_bounds(text, name)
        if not bounds:
            continue
        start, end = bounds
        block = text[start:end + 1]
        new_block = re.sub(
            rf"\n?[ \t]*['\"]{re.escape(value)}['\"][ \t]*,?",
            "",
            block,
            flags=re.I,
        )
        # Nettoyage des doubles virgules simples possibles.
        new_block = re.sub(r",\s*,", ",", new_block)
        if new_block != block:
            text = text[:start] + new_block + text[end + 1:]
            changed = True
    return text, changed


def clean_table_filter_in_oracle_service(text: str) -> tuple[str, bool]:
    old = text

    # Retire l'ancien filtre ajouté par erreur sur OBJECT_NAME.
    text = re.sub(
        rf"\s+AND\s+UPPER\(OBJECT_NAME\)\s*<>\s*['\"]{re.escape(TARGET)}['\"]",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        rf"\s+AND\s+OBJECT_NAME\s*<>\s*['\"]{re.escape(TARGET)}['\"]",
        "",
        text,
        flags=re.I,
    )

    # Retire PROD2_WLS des collections de tables si l'ancien patch l'a ajouté.
    text, _ = remove_from_python_collection(text, TABLE_COLLECTION_NAMES, TARGET)

    # Retire PROD2_WLS de technical_hide_exact seulement quand le bloc est clairement table-side.
    def clean_table_json_like_block(match: re.Match[str]) -> str:
        before = text[max(0, match.start() - 250):match.start()].upper()
        if "TABLE" not in before and "OBJECT" not in before:
            return match.group(0)
        block = match.group(0)
        block2 = re.sub(
            rf"\s*,?\s*['\"]{re.escape(TARGET)}['\"]",
            "",
            block,
            flags=re.I,
        )
        block2 = block2.replace("[,", "[").replace(",]", "]")
        return block2

    text = re.sub(r"(['\"]technical_hide_exact['\"]\s*:\s*\[[^\]]*\])", clean_table_json_like_block, text, flags=re.I | re.S)
    text = re.sub(r"(['\"]technical_hide_like['\"]\s*:\s*\[[^\]]*\])", clean_table_json_like_block, text, flags=re.I | re.S)

    return text, text != old


def patch_oracle_service(root: Path) -> bool:
    path = root / "backend" / "app" / "services" / "oracle_service.py"
    if not path.exists():
        print("[WARN] oracle_service.py introuvable.")
        return False

    old = read_text(path)
    new = old

    # 1) Annuler le masquage table erroné.
    new, _ = clean_table_filter_in_oracle_service(new)

    # 2) Ajouter PROD2_WLS dans une collection utilisateurs existante, si elle existe.
    new, added_existing = add_to_python_collection(new, USER_COLLECTION_NAMES, TARGET)

    # 3) Sinon, injecter une constante claire et dédiée.
    if not added_existing and "HIDDEN_SIDEBAR_USERS_EXACT" not in new:
        anchor = None
        # Après les imports, avant la première classe/fonction.
        m = re.search(r"(?m)^(class\s+|def\s+|async\s+def\s+)", new)
        if m:
            anchor = m.start()
        if anchor is None:
            anchor = 0
        injection = (
            "\n# Utilisateurs masqués uniquement dans la colonne d'aide Utilisateurs.\n"
            "# Ne filtre pas les vraies requêtes SQL générées par le modèle.\n"
            f"HIDDEN_SIDEBAR_USERS_EXACT = {{\"{TARGET}\"}}\n\n"
            "def _is_hidden_sidebar_user(value):\n"
            "    if value is None:\n"
            "        return True\n"
            "    return str(value).strip().upper() in HIDDEN_SIDEBAR_USERS_EXACT\n\n"
        )
        new = new[:anchor] + injection + new[anchor:]

    # 4) Filtrer les requêtes de metadata/sidebar qui listent DISTINCT DBUSERNAME.
    # Important : on vise seulement les chaînes SQL internes qui servent à lister les utilisateurs.
    def add_dbusername_filter_to_sql_literal(match: re.Match[str]) -> str:
        sql = match.group(0)
        if TARGET in sql.upper():
            return sql
        if "DBUSERNAME" not in sql.upper() or "DISTINCT" not in sql.upper():
            return sql
        if "WHERE" in sql.upper():
            # Ajoute juste après une condition DBUSERNAME IS NOT NULL si elle existe, sinon avant GROUP/ORDER/FETCH.
            sql2, n = re.subn(
                r"(DBUSERNAME\s+IS\s+NOT\s+NULL)",
                rf"\1 AND UPPER(DBUSERNAME) <> '{TARGET}'",
                sql,
                count=1,
                flags=re.I,
            )
            if n:
                return sql2
            sql2, n = re.subn(
                r"(WHERE\s+)",
                rf"\1UPPER(DBUSERNAME) <> '{TARGET}' AND ",
                sql,
                count=1,
                flags=re.I,
            )
            if n:
                return sql2
        return sql

    # Triple-quoted SQL blocks.
    new = re.sub(r"(?s)([rubfRUBF]*['\"]{3}.*?['\"]{3})", add_dbusername_filter_to_sql_literal, new)

    # Simple one-line SQL strings containing SELECT DISTINCT DBUSERNAME.
    new = re.sub(
        r"(['\"][^'\"\n]*SELECT\s+DISTINCT\s+DBUSERNAME[^'\"\n]*['\"])",
        add_dbusername_filter_to_sql_literal,
        new,
        flags=re.I,
    )

    return write_text_if_changed(path, old, new)


def patch_frontend_user_filters(root: Path) -> int:
    frontend = root / "frontend"
    if not frontend.exists():
        return 0
    allowed_ext = {".ts", ".tsx", ".js", ".jsx"}
    excluded_dirs = {"node_modules", ".next", "dist", "build", ".git"}
    changed = 0

    for path in frontend.rglob("*"):
        if not path.is_file() or path.suffix not in allowed_ext:
            continue
        if any(part in excluded_dirs for part in path.parts):
            continue
        old = read_text(path)
        if not any(name in old for name in USER_COLLECTION_NAMES):
            continue
        new, did = add_to_python_collection(old, USER_COLLECTION_NAMES, TARGET)
        if did and write_text_if_changed(path, old, new):
            changed += 1
    return changed


def main() -> None:
    root = find_project_root()
    print("=" * 72)
    print("Audit AI - Correction PROD2_WLS : utilisateur uniquement")
    print("=" * 72)
    print(f"Racine projet : {root}")
    print()

    table_policy_changed = patch_table_policy(root)
    user_policy_changed = patch_user_policy(root)
    oracle_changed = patch_oracle_service(root)
    frontend_changed = patch_frontend_user_filters(root)

    print("=" * 72)
    print("RÉSUMÉ")
    print("=" * 72)
    print(f"Nettoyage politique Tables : {'oui' if table_policy_changed else 'non'}")
    print(f"Politique Utilisateurs modifiée : {'oui' if user_policy_changed else 'non'}")
    print(f"oracle_service.py modifié : {'oui' if oracle_changed else 'non'}")
    print(f"Filtres frontend utilisateurs modifiés : {frontend_changed}")
    print()
    print("Actions après patch :")
    print("1) Redémarrer le backend FastAPI")
    print("2) Redémarrer ou rafraîchir le frontend")
    print("3) Actualiser/reconnecter l'application")
    print()
    print(f"Important : {TARGET} est traité comme UTILISATEUR à masquer dans la colonne Utilisateurs.")
    print("Le script retire aussi l'ancien masquage côté Tables s'il avait été ajouté.")
    print("Il ne doit pas filtrer les vraies requêtes SQL posées par l'utilisateur.")
    print(f"Sauvegardes : *{BACKUP_SUFFIX}")
    print("=" * 72)


if __name__ == "__main__":
    main()
