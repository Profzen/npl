from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

TARGET_TABLE = "PROD2_WLS"
BACKUP_SUFFIX = ".bak_hide_prod2wls_note"

SETTINGS_TEXTS_TO_REMOVE = [
    "La langue est fixée en français tant que le modèle ne répond pas encore en anglais.",
    "La langue est fixee en francais tant que le modele ne repond pas encore en anglais.",
]

# Clés probables utilisées pour afficher la note dans la page Paramètres.
SETTINGS_NOTE_KEYS = [
    "settings.lang_en_disabled",
    "settings.language_fixed_fr_note",
    "settings.lang_fr_only_note",
    "settings.language_fr_only_note",
    "settings.lang_disabled_note",
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


def remove_settings_note_from_text(text: str) -> str:
    new = text

    # 1) Supprime les paragraphes JSX qui affichent explicitement la phrase.
    for phrase in SETTINGS_TEXTS_TO_REMOVE:
        escaped = re.escape(phrase)
        new = re.sub(
            rf"\n?\s*<p\b[^>]*>\s*{escaped}\s*</p>",
            "",
            new,
            flags=re.S,
        )
        new = new.replace(phrase, "")

    # 2) Supprime les paragraphes JSX qui affichent une clé de note via t('...').
    for key in SETTINGS_NOTE_KEYS:
        new = re.sub(
            rf"\n?\s*<p\b[^>]*>\s*\{{\s*t\(['\"]{re.escape(key)}['\"]\)\s*\}}\s*</p>",
            "",
            new,
            flags=re.S,
        )
        new = re.sub(
            rf"\n?\s*<p\b[^>]*>.*?\{{\s*t\(['\"]{re.escape(key)}['\"]\)\s*\}}.*?</p>",
            "",
            new,
            flags=re.S,
        )

    # 3) Supprime les lignes de dictionnaire i18n dédiées à ces notes.
    for key in SETTINGS_NOTE_KEYS:
        new = re.sub(
            rf"^\s*['\"]{re.escape(key)}['\"]\s*:\s*['\"][^'\"]*['\"]\s*,?\s*$\n?",
            "",
            new,
            flags=re.M,
        )

    # 4) Nettoyage doux des espaces vides laissés dans JSX.
    new = re.sub(r"\n{3,}", "\n\n", new)
    return new


def patch_settings_note(root: Path) -> int:
    frontend = root / "frontend"
    if not frontend.exists():
        print("[WARN] Dossier frontend introuvable, partie Paramètres ignorée.")
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
        # Évite de modifier tout le frontend inutilement : seulement fichiers contenant la phrase ou les clés.
        if not any(s in old for s in SETTINGS_TEXTS_TO_REMOVE + SETTINGS_NOTE_KEYS):
            continue
        new = remove_settings_note_from_text(old)
        if write_text_if_changed(path, old, new):
            changed += 1

    return changed


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def patch_sidebar_policy_file(root: Path) -> bool:
    policy_path = root / "backend" / "app" / "sidebar_table_policy.json"
    policy = load_json(policy_path)

    if not policy:
        policy = {
            "description": "Politique d'affichage de la colonne Tables. Ne filtre pas les requêtes SQL utilisateur.",
            "visible_now": ["EMPLOYEES", "DEPARTMENTS", "RULE_SET", "HR", "ADRESS"],
            "baseline_current_objects": [],
            "technical_hide_exact": [],
            "technical_hide_like": ["SCHEMA_VERSION_REGIST%", "TEST%", "%VROMUALD%", "%ROMUALD%", "BIN$%", "SYS_EXPORT%"],
        }

    changed = False

    # S'assurer que PROD2_WLS n'est jamais dans les visibles.
    for key in ["visible_now", "allowed_tables", "visible_tables"]:
        if isinstance(policy.get(key), list):
            old_list = policy[key]
            new_list = [x for x in old_list if str(x).strip().upper() != TARGET_TABLE]
            if new_list != old_list:
                policy[key] = new_list
                changed = True

    exact = policy.get("technical_hide_exact")
    if not isinstance(exact, list):
        exact = []
    exact_upper = {str(x).strip().upper() for x in exact}
    if TARGET_TABLE not in exact_upper:
        exact.append(TARGET_TABLE)
        policy["technical_hide_exact"] = sorted({str(x).strip().upper() for x in exact if str(x).strip()})
        changed = True

    # Ajoute aussi un LIKE exact-friendly, utile si une ancienne logique n'utilise que les patterns LIKE.
    like = policy.get("technical_hide_like")
    if not isinstance(like, list):
        like = []
    like_upper = {str(x).strip().upper() for x in like}
    if TARGET_TABLE not in like_upper:
        like.append(TARGET_TABLE)
        policy["technical_hide_like"] = sorted({str(x).strip().upper() for x in like if str(x).strip()})
        changed = True

    if changed or not policy_path.exists():
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        if policy_path.exists():
            backup(policy_path)
        policy_path.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] Politique Tables mise à jour : {policy_path}")
        return True

    print("[INFO] Politique Tables déjà à jour.")
    return False


def add_value_to_python_collection(text: str, names: list[str], value: str) -> tuple[str, bool]:
    for name in names:
        m = re.search(rf"(?m)^([ \t]*{re.escape(name)}\s*=\s*)([\[\(\{{])", text)
        if not m:
            continue
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
            continue
        block = text[m.start(): end + 1]
        if re.search(rf"['\"]{re.escape(value)}['\"]", block, re.I):
            return text, False
        indent = re.match(r"(?m)^([ \t]*)", text[m.start():]).group(1)  # type: ignore[union-attr]
        item_indent = indent + "    "
        text = text[:end] + f'\n{item_indent}"{value}",' + text[end:]
        return text, True
    return text, False


def patch_oracle_service(root: Path) -> bool:
    path = root / "backend" / "app" / "services" / "oracle_service.py"
    if not path.exists():
        print("[WARN] oracle_service.py introuvable, patch backend SQL ignoré.")
        return False

    old = read_text(path)
    new = old

    # 1) Cas normal après le patch dynamique : collection technique dans le bloc politique.
    collection_names = [
        "TECHNICAL_HIDE_EXACT",
        "HIDDEN_AUDIT_TABLES_EXACT",
        "HIDDEN_TABLES_EXACT",
        "MASKED_TABLES",
        "EXCLUDED_TABLES",
        "TABLE_HIDE_LIST",
    ]
    new, changed_collection = add_value_to_python_collection(new, collection_names, TARGET_TABLE)

    # 2) Cas du bloc injecté : dictionnaire default_policy avec technical_hide_exact.
    def repl_default_policy(m: re.Match[str]) -> str:
        inside = m.group(1)
        if TARGET_TABLE in inside.upper():
            return m.group(0)
        return m.group(0).replace("]", f', "{TARGET_TABLE}"]', 1)

    new = re.sub(
        r'("technical_hide_exact"\s*:\s*\[([^\]]*)\])',
        lambda m: m.group(1) if TARGET_TABLE in m.group(2).upper() else m.group(1).replace("]", f', "{TARGET_TABLE}"]'),
        new,
        count=1,
    )

    # 3) Si le service n'utilise pas encore la politique, filtre uniquement la requête metadata OBJECT_NAME.
    #    On ne touche pas aux vraies requêtes SQL générées par le modèle.
    if TARGET_TABLE not in new or "build_sidebar_objects_sql" not in new:
        # Ajout prudent dans les requêtes qui listent OBJECT_NAME pour la sidebar.
        patterns = [
            r"(WHERE\s+OBJECT_NAME\s+IS\s+NOT\s+NULL\s*)",
            r"(WHERE\s+UPPER\(OBJECT_NAME\)\s+IS\s+NOT\s+NULL\s*)",
        ]
        for pat in patterns:
            if re.search(pat, new, flags=re.I):
                new2, n = re.subn(
                    pat,
                    lambda m: m.group(1) + f" AND UPPER(OBJECT_NAME) <> '{TARGET_TABLE}' ",
                    new,
                    count=1,
                    flags=re.I,
                )
                if n:
                    new = new2
                    break

    return write_text_if_changed(path, old, new)


def patch_frontend_hidden_table_arrays(root: Path) -> int:
    frontend = root / "frontend"
    if not frontend.exists():
        return 0
    allowed_ext = {".ts", ".tsx", ".js", ".jsx"}
    excluded_dirs = {"node_modules", ".next", "dist", "build", ".git"}
    names = [
        "HIDDEN_TABLES",
        "HIDDEN_OBJECTS",
        "EXCLUDED_TABLES",
        "MASKED_TABLES",
        "TABLE_HIDE_LIST",
        "hiddenTables",
        "excludedTables",
        "maskedTables",
    ]
    changed = 0
    for path in frontend.rglob("*"):
        if not path.is_file() or path.suffix not in allowed_ext:
            continue
        if any(part in excluded_dirs for part in path.parts):
            continue
        old = read_text(path)
        # Ne modifie que les fichiers qui contiennent déjà une logique de masquage de tables.
        if not any(name in old for name in names):
            continue
        new, did = add_value_to_python_collection(old, names, TARGET_TABLE)
        if did and write_text_if_changed(path, old, new):
            changed += 1
    return changed


def main() -> None:
    root = find_project_root()
    print("=" * 72)
    print("Audit AI - Suppression note Paramètres + masquage table PROD2_WLS")
    print("=" * 72)
    print(f"Racine projet : {root}")

    settings_changed = patch_settings_note(root)
    policy_changed = patch_sidebar_policy_file(root)
    oracle_changed = patch_oracle_service(root)
    frontend_tables_changed = patch_frontend_hidden_table_arrays(root)

    print("=" * 72)
    print("RÉSUMÉ")
    print("=" * 72)
    print(f"Fichiers frontend Paramètres modifiés : {settings_changed}")
    print(f"Politique backend Tables modifiée : {'oui' if policy_changed else 'non'}")
    print(f"oracle_service.py modifié : {'oui' if oracle_changed else 'non'}")
    print(f"Filtres frontend tables modifiés : {frontend_tables_changed}")
    print()
    print("Actions après patch :")
    print("1) Redémarrer le backend FastAPI")
    print("2) Redémarrer ou rafraîchir le frontend")
    print("3) Actualiser/reconnecter l'application")
    print()
    print("Important : ce patch masque PROD2_WLS dans la colonne Tables uniquement.")
    print("Il ne doit pas filtrer les vraies requêtes SQL posées par l'utilisateur.")
    print(f"Sauvegardes : *{BACKUP_SUFFIX}")
    print("=" * 72)


if __name__ == "__main__":
    main()
