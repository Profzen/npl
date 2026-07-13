from pathlib import Path
import re
import shutil

ROOT = Path.cwd()
TARGET_USER = "PROD2_WLS"
BACKUP_SUFFIX = ".bak_hide_prod2_wls"

ORACLE_SERVICE = ROOT / "backend" / "app" / "services" / "oracle_service.py"
GUARDRAILS_SERVICE = ROOT / "backend" / "app" / "services" / "dynamic_guardrails_service.py"


def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if path.exists() and not backup_path.exists():
        shutil.copy2(path, backup_path)


def add_value_to_collection(text: str, var_names: list[str], value: str) -> tuple[str, bool]:
    """Ajoute value dans une liste/tuple/set Python simple si une variable existe."""
    for var in var_names:
        m = re.search(rf"(?m)^({re.escape(var)}\s*=\s*)([\(\[\{{])", text)
        if not m:
            continue
        start = m.start(2)
        opener = text[start]
        closer = {"(": ")", "[": "]", "{": "}"}[opener]
        depth = 0
        end = None
        for i in range(start, len(text)):
            ch = text[i]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            continue
        block = text[m.start():end + 1]
        if value in block:
            return text, False
        insert = f'    "{value}",\n'
        text = text[:end] + insert + text[end:]
        return text, True
    return text, False


def patch_guardrails_service() -> bool:
    if not GUARDRAILS_SERVICE.exists():
        return False
    text = GUARDRAILS_SERVICE.read_text(encoding="utf-8")
    original = text
    candidates = [
        "HIDDEN_AUDIT_USERS_EXACT",
        "HIDDEN_USERS_EXACT",
        "HIDDEN_DBUSERS_EXACT",
        "HIDDEN_USER_EXACT",
        "EXCLUDED_USERS",
        "MASKED_USERS",
        "USER_HIDE_LIST",
    ]
    text, changed = add_value_to_collection(text, candidates, TARGET_USER)
    if changed:
        backup(GUARDRAILS_SERVICE)
        GUARDRAILS_SERVICE.write_text(text, encoding="utf-8")
        return True
    return False


def patch_oracle_service_sql() -> bool:
    """Ajoute le filtre dans la requête de métadonnées utilisateurs uniquement."""
    if not ORACLE_SERVICE.exists():
        raise FileNotFoundError(f"Fichier introuvable : {ORACLE_SERVICE}")
    text = ORACLE_SERVICE.read_text(encoding="utf-8")
    original = text

    if TARGET_USER in text and ("DBUSERNAME" in text or "HIDDEN" in text):
        # Une modification existe probablement déjà.
        return False

    # Cas le plus courant : user_sql = (... "WHERE DBUSERNAME IS NOT NULL " ...)
    marker = '"WHERE DBUSERNAME IS NOT NULL "'
    replacement = '"WHERE DBUSERNAME IS NOT NULL "\n        "AND UPPER(DBUSERNAME) <> \'PROD2_WLS\' "'
    if marker in text:
        text = text.replace(marker, replacement, 1)
    else:
        # Variante avec f-string ou simple quote.
        marker2 = "'WHERE DBUSERNAME IS NOT NULL '"
        replacement2 = "'WHERE DBUSERNAME IS NOT NULL '\n        \"AND UPPER(DBUSERNAME) <> 'PROD2_WLS' \""
        if marker2 in text:
            text = text.replace(marker2, replacement2, 1)
        else:
            # Variante plus robuste : après toute condition DBUSERNAME IS NOT NULL dans user_sql.
            pattern = r"(DBUSERNAME\s+IS\s+NOT\s+NULL\s*)"
            def repl(m):
                return m.group(1) + " AND UPPER(DBUSERNAME) <> 'PROD2_WLS' "
            text, n = re.subn(pattern, repl, text, count=1, flags=re.IGNORECASE)
            if n == 0:
                return False

    if text != original:
        backup(ORACLE_SERVICE)
        ORACLE_SERVICE.write_text(text, encoding="utf-8")
        return True
    return False


def main():
    print("=" * 70)
    print("Masquage de PROD2_WLS dans la colonne Utilisateurs")
    print("=" * 70)
    print(f"Racine projet : {ROOT}")

    changed_guardrails = patch_guardrails_service()
    changed_oracle = patch_oracle_service_sql()

    if changed_guardrails:
        print("OK : PROD2_WLS ajouté à la liste des utilisateurs masqués dans dynamic_guardrails_service.py")
    else:
        print("Info : aucune liste utilisateurs masqués modifiée dans dynamic_guardrails_service.py")

    if changed_oracle:
        print("OK : filtre PROD2_WLS ajouté dans la requête metadata utilisateurs de oracle_service.py")
    else:
        print("Info : oracle_service.py semblait déjà corrigé ou aucun bloc standard trouvé")

    print()
    print("Terminé.")
    print("Redémarre le backend puis actualise la page.")
    print("Sauvegardes créées avec le suffixe :", BACKUP_SUFFIX)
    print("=" * 70)


if __name__ == "__main__":
    main()
