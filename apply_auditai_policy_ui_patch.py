"""
Audit AI — Patch politique métadonnées + UI

À placer à la racine du projet : C:\\dossier3\\nlp
Commande : python .\\apply_auditai_policy_ui_patch.py

Ce script corrige :
1) Tables : masque TEST et VROMUALD, garde les tables métier déjà acceptées,
   et permet aux nouvelles tables de remonter automatiquement.
2) Utilisateurs : masque les anciens comptes non souhaités, garde les comptes demandés,
   et permet aux nouveaux utilisateurs Oracle de remonter automatiquement.
3) Sidebar : texte plus blanc et plus gras pour une meilleure lisibilité.
4) Paramètres : l'anglais n'est plus visible, langue forcée en français.
5) Paramètres : la section Connexion Oracle est visible seulement pour les admins.
6) Dashboard : ajoute une petite description sous Utilisateurs, Tables et Actions.

Le script crée des sauvegardes .bak_auditai_policy_ui avant chaque modification.
"""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime

BACKUP_SUFFIX = ".bak_auditai_policy_ui"

FEATURED_AUDIT_OBJECTS = (
    "EMPLOYEES",
    "DEPARTMENTS",
    "HR",
    "ADRESS",
    "CLIENT",
)

HIDDEN_AUDIT_OBJECTS = (
    "VROMUALD",
    "TEST",
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
)

HIDDEN_AUDIT_OBJECT_PREFIXES = (
    "SCHEMA_VERSION_REGIST",
)

PINNED_AUDIT_USERS = (
    "VROMUALD",
    "SYS",
    "SYSTEM",
    "CYRILLE",
    "ITEST",
    "CYRILLE_TBS",
)

HIDDEN_AUDIT_USERS = (
    "PROD2_MDS",
    "PROD2_STB",
    "TEST",
    "SMART2DADMIN",
    "BATCH_USER",
    "SMART2DADMINI",
    "SMART2DSECU",
    "\\\\SMART2DADMIN",
)


def find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [here, Path.cwd().resolve(), here.parent, Path.cwd().resolve().parent]
    for candidate in candidates:
        if (candidate / "backend" / "app" / "services" / "oracle_service.py").exists() and (candidate / "frontend").exists():
            return candidate
    raise FileNotFoundError(
        "Impossible de trouver le projet. Place ce script à la racine C:\\dossier3\\nlp, puis relance-le."
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


def patch_file(path: Path, patcher, label: str) -> None:
    original = read(path)
    content = patcher(original)
    if content != original:
        backup(path)
        write(path, content)
        print(f"[OK] {label} : {path}")
    else:
        print(f"[OK] Déjà à jour : {path}")


def py_tuple(values: tuple[str, ...]) -> str:
    return ",\n    ".join(repr(v) for v in values)


def ensure_import_line(content: str, import_line: str, after: str | None = None) -> str:
    if re.search(rf"^{re.escape(import_line)}$", content, flags=re.MULTILINE):
        return content
    if after and after in content:
        return content.replace(after, after + import_line + "\n", 1)
    return import_line + "\n" + content


def dynamic_scope_block() -> str:
    return f'''

# ---------------------------------------------------------------------------
# Audit AI — politique dynamique des métadonnées d'audit
# ---------------------------------------------------------------------------
# - TEST et VROMUALD sont masquées.
# - Les tables métier existantes restent visibles.
# - Toute nouvelle table non masquée apparaîtra automatiquement.
# - Les anciens utilisateurs non souhaités sont masqués.
# - Tout nouvel utilisateur non masqué apparaîtra automatiquement.
FEATURED_AUDIT_OBJECTS = (
    {py_tuple(FEATURED_AUDIT_OBJECTS)},
)

HIDDEN_AUDIT_OBJECTS = (
    {py_tuple(HIDDEN_AUDIT_OBJECTS)},
)

HIDDEN_AUDIT_OBJECT_PREFIXES = (
    {py_tuple(HIDDEN_AUDIT_OBJECT_PREFIXES)},
)

PINNED_AUDIT_USERS = (
    {py_tuple(PINNED_AUDIT_USERS)},
)

HIDDEN_AUDIT_USERS = (
    {py_tuple(HIDDEN_AUDIT_USERS)},
)

_ALLOWED_OBJECT_SCOPE_MARKER = "/* AUDITAI_DYNAMIC_OBJECT_SCOPE */"


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + item.replace("'", "''").upper() + "'" for item in values)


def _hidden_objects_condition(column: str = "OBJECT_NAME") -> str:
    clauses: list[str] = []
    if HIDDEN_AUDIT_OBJECTS:
        clauses.append(f"UPPER({{column}}) NOT IN ({{_sql_list(HIDDEN_AUDIT_OBJECTS)}})")
    for prefix in HIDDEN_AUDIT_OBJECT_PREFIXES:
        safe_prefix = prefix.replace("'", "''").upper()
        clauses.append(f"UPPER({{column}}) NOT LIKE '{{safe_prefix}}%'")
    return " AND ".join(clauses) if clauses else "1=1"


def _visible_users_condition(column: str = "DBUSERNAME") -> str:
    if not HIDDEN_AUDIT_USERS:
        return "1=1"
    return (
        f"(UPPER({{column}}) IN ({{_sql_list(PINNED_AUDIT_USERS)}}) "
        f"OR UPPER({{column}}) NOT IN ({{_sql_list(HIDDEN_AUDIT_USERS)}}))"
    )


def apply_allowed_object_scope(sql: str) -> str:
    """
    Applique le périmètre dynamique côté backend aux requêtes générées.
    Les nouvelles tables non masquées peuvent apparaître et être interrogées.
    """
    if _ALLOWED_OBJECT_SCOPE_MARKER in sql:
        return sql

    oracle_table = get_oracle_table().strip()
    hidden_condition = _hidden_objects_condition("OBJECT_NAME")

    scoped_table = (
        f"(SELECT * FROM {{oracle_table}} "
        f"WHERE {{hidden_condition}}) "
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


def patch_oracle_service(content: str) -> str:
    content = ensure_import_line(content, "import re", after="from threading import Lock\n")

    marker_pattern = re.compile(
        r"(_METADATA_CACHE_TTL_SECONDS\s*=\s*300\s*\n)(.*?)(\ndef _build_connection_config\()",
        flags=re.DOTALL,
    )
    if not marker_pattern.search(content):
        raise RuntimeError("Marqueur _METADATA_CACHE_TTL_SECONDS introuvable dans oracle_service.py")
    content = marker_pattern.sub(lambda m: m.group(1) + dynamic_scope_block() + m.group(3), content, count=1)

    old_execute = '        cur.execute(sql.rstrip().rstrip(";"))\n'
    new_execute = '        scoped_sql = apply_allowed_object_scope(sql)\n        cur.execute(scoped_sql.rstrip().rstrip(";"))\n'
    if new_execute not in content and old_execute in content:
        content = content.replace(old_execute, new_execute, 1)

    new_fetch_metadata = r'''def fetch_metadata() -> tuple[list[dict], list[dict], str]:
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
        hidden_objects_condition = _hidden_objects_condition("OBJECT_NAME")
        visible_users_condition = _visible_users_condition("DBUSERNAME")

        user_sql = (
            f"SELECT DBUSERNAME, COUNT(*) AS ACTIONS FROM {oracle_table} "
            "WHERE DBUSERNAME IS NOT NULL "
            f"AND {visible_users_condition} "
            "GROUP BY DBUSERNAME "
            "ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"
        )
        cur.execute(user_sql)
        users = [{"name": str(r[0]), "actions": int(r[1])} for r in cur.fetchall()]

        obj_sql = (
            f"SELECT OBJECT_NAME, COUNT(*) AS ACTIONS FROM {oracle_table} "
            "WHERE OBJECT_NAME IS NOT NULL "
            f"AND {hidden_objects_condition} "
            "GROUP BY OBJECT_NAME "
            "ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"
        )
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
'''
    content = re.sub(
        r"def fetch_metadata\(\) -> tuple\[list\[dict\], list\[dict\], str\]:.*\Z",
        new_fetch_metadata,
        content,
        flags=re.DOTALL,
    )
    return content


def replace_oracle_service_import(content: str) -> str:
    canonical = (
        "from app.services.oracle_service import (\n"
        "    execute_sql,\n"
        "    fetch_metadata,\n"
        "    get_connection,\n"
        "    oracle_status,\n"
        "    apply_allowed_object_scope,\n"
        ")\n"
    )
    lines = content.splitlines(True)
    out: list[str] = []
    i = 0
    replaced = False
    while i < len(lines):
        line = lines[i]
        if not replaced and line.startswith("from app.services.oracle_service import"):
            out.append(canonical)
            replaced = True
            if "(" in line and ")" not in line:
                i += 1
                while i < len(lines) and not lines[i].startswith(")"):
                    i += 1
                if i < len(lines):
                    i += 1
            else:
                i += 1
            continue
        out.append(line)
        i += 1
    return "".join(out)


def patch_main_py(content: str) -> str:
    content = replace_oracle_service_import(content)

    old_execute = '        cur.execute(sql.rstrip().rstrip(";"))\n'
    new_execute = '        scoped_sql = apply_allowed_object_scope(sql)\n        cur.execute(scoped_sql.rstrip().rstrip(";"))\n'
    if new_execute not in content and old_execute in content:
        content = content.replace(old_execute, new_execute, 1)

    content = re.sub(
        r"    sql = generate_sql_from_question\(req\.question\)\s*\n(?:    sql = apply_allowed_object_scope\(sql\)\s*\n)?",
        "    sql = generate_sql_from_question(req.question)\n    sql = apply_allowed_object_scope(sql)\n",
        content,
        count=1,
    )
    return content


def patch_app_sidebar(content: str) -> str:
    content = content.replace("ASKSMART", "Audit AI").replace("AuditAI", "Audit AI")
    content = re.sub(
        r'<span className="[^"]*">\s*Audit AI\s*</span>',
        '<span className="font-bold text-2xl tracking-tight truncate text-white">Audit AI</span>',
        content,
        count=1,
        flags=re.DOTALL,
    )
    content = re.sub(
        r'<Link href=\{item\.href\}(?: className="[^"]*")?>',
        '<Link href={item.href} className="font-semibold text-white">',
        content,
    )
    replacements = {
        "text-muted-foreground": "text-white/75",
        "text-foreground": "text-white",
        "text-xs transition-colors": "text-sm font-semibold transition-colors",
        "text-[11px] leading-4": "text-xs font-semibold leading-4",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)
    return content


def patch_settings_page(content: str) -> str:
    if "from '@/lib/auth-context'" not in content:
        content = content.replace(
            "import { useAppData } from '@/components/app-shell'\n",
            "import { useAppData } from '@/components/app-shell'\nimport { useAuth } from '@/lib/auth-context'\n",
            1,
        )
    content = re.sub(
        r"import \{ Select, SelectContent, SelectItem, SelectTrigger, SelectValue \} from '@/components/ui/select'\n",
        "",
        content,
        count=1,
    )
    if "const { user } = useAuth()" not in content:
        content = content.replace("  const t = useT()\n", "  const t = useT()\n  const { user } = useAuth()\n", 1)

    content = content.replace("      setFormData({ ...settings })", "      setFormData({ ...settings, interface_lang: 'fr' })")
    content = content.replace("      await updateSettings(formData)", "      await updateSettings({ ...formData, interface_lang: 'fr' })")

    if "field === 'interface_lang'" not in content:
        content = content.replace(
            "  const handleInputChange = (field: keyof RuntimeSettings, value: string | number) => {\n    if (!formData) return\n    setFormData({ ...formData, [field]: value })\n  }",
            "  const handleInputChange = (field: keyof RuntimeSettings, value: string | number) => {\n    if (!formData) return\n    if (field === 'interface_lang') {\n      setFormData({ ...formData, interface_lang: 'fr' })\n      return\n    }\n    setFormData({ ...formData, [field]: value })\n  }",
        )

    if "user?.is_admin && (" not in content:
        content = re.sub(
            r"(\s*\{\/\* Oracle Connection \*\/\}\s*\n)(\s*<Card>.*?\n\s*</Card>)(\s*\n\s*\{\/\* Analysis Settings \*\/\})",
            lambda m: f"{m.group(1)}          {{user?.is_admin && (\n{m.group(2)}\n          )}}{m.group(3)}",
            content,
            count=1,
            flags=re.DOTALL,
        )

    interface_card = '''          {/* Interface */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Globe className="w-5 h-5 text-primary" />
                {t('settings.interface')}
              </CardTitle>
              <CardDescription>
                {t('settings.interface_desc')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-w-sm">
                <Label htmlFor="interface_lang">{t('settings.language')}</Label>
                <Input
                  id="interface_lang"
                  value="Français"
                  disabled
                  readOnly
                  className="font-medium"
                />
                <p className="text-xs text-muted-foreground">
                  {t('settings.language_locked_help')}
                </p>
              </div>
            </CardContent>
          </Card>'''
    content = re.sub(
        r"\s*\{\/\* Interface \*\/\}\s*\n\s*<Card>.*?\n\s*</Card>\s*(?=\n\s*\{\/\* Action Buttons \*\/\})",
        "\n" + interface_card + "\n",
        content,
        count=1,
        flags=re.DOTALL,
    )
    return content


def patch_dashboard_page(content: str) -> str:
    if "dashboard.users_subtitle" not in content:
        content = content.replace(
            '<span className="text-foreground font-semibold">{t(\'dashboard.users_title\')}</span>',
            '<span className="text-foreground font-semibold">{t(\'dashboard.users_title\')}</span>\n                          <p className="text-xs font-normal text-muted-foreground">{t(\'dashboard.users_subtitle\')}</p>',
            1,
        )
    if "dashboard.tables_subtitle" not in content:
        content = content.replace(
            '<span className="text-foreground font-semibold">{t(\'dashboard.tables_title\')}</span>',
            '<span className="text-foreground font-semibold">{t(\'dashboard.tables_title\')}</span>\n                          <p className="text-xs font-normal text-muted-foreground">{t(\'dashboard.tables_subtitle\')}</p>',
            1,
        )
    return content


def remove_i18n_key_lines(content: str, key: str) -> str:
    return re.sub(rf"\n  '{re.escape(key)}':\s*'[^\n]*',", "", content)


def insert_after_nth_key(content: str, after_key: str, new_line: str, occurrence: int) -> str:
    pattern = re.compile(rf"  '{re.escape(after_key)}':\s*'[^\n]*',\n")
    matches = list(pattern.finditer(content))
    if len(matches) < occurrence:
        return content
    m = matches[occurrence - 1]
    return content[:m.end()] + new_line + "\n" + content[m.end():]


def replace_nth_i18n_key(content: str, key: str, value: str, occurrence: int) -> str:
    pattern = re.compile(rf"  '{re.escape(key)}':\s*'[^\n]*',")
    matches = list(pattern.finditer(content))
    if len(matches) < occurrence:
        return content
    m = matches[occurrence - 1]
    line = f"  '{key}': '{value}',"
    return content[:m.start()] + line + content[m.end():]


def patch_i18n(content: str) -> str:
    for key in ("dashboard.users_subtitle", "dashboard.tables_subtitle", "settings.language_locked_help"):
        content = remove_i18n_key_lines(content, key)

    content = insert_after_nth_key(content, "dashboard.users_title", "  'dashboard.users_subtitle': 'Comptes Oracle ayant effectué des actions',", 1)
    content = insert_after_nth_key(content, "dashboard.tables_title", "  'dashboard.tables_subtitle': 'Tables ou objets concernés par l’audit',", 1)
    content = replace_nth_i18n_key(content, "dashboard.actions_subtitle", "Types d’actions auditées", 1)
    content = insert_after_nth_key(content, "settings.language", "  'settings.language_locked_help': 'La langue est fixée en français tant que le modèle ne répond pas encore en anglais.',", 1)

    content = insert_after_nth_key(content, "dashboard.users_title", "  'dashboard.users_subtitle': 'Oracle accounts that performed actions',", 2)
    content = insert_after_nth_key(content, "dashboard.tables_title", "  'dashboard.tables_subtitle': 'Tables or objects targeted by audit logs',", 2)
    content = replace_nth_i18n_key(content, "dashboard.actions_subtitle", "Audited action types", 2)
    content = insert_after_nth_key(content, "settings.language", "  'settings.language_locked_help': 'The language is locked to French until the model can answer in English.',", 2)

    content = content.replace("ASKSMART", "Audit AI").replace("AuditAI", "Audit AI")
    return content


def patch_app_shell(content: str) -> str:
    content = re.sub(
        r"if \(typeof window !== 'undefined' && \(data\.interface_lang === 'fr' \|\| data\.interface_lang === 'en'\)\) \{\s*window\.localStorage\.setItem\('asksmart_lang',\s*data\.interface_lang\)\s*\}",
        "if (typeof window !== 'undefined') {\n          window.localStorage.setItem('asksmart_lang', 'fr')\n        }",
        content,
        flags=re.DOTALL,
    )
    content = re.sub(
        r"window\.localStorage\.setItem\('asksmart_lang',\s*data\.interface_lang\)",
        "window.localStorage.setItem('asksmart_lang', 'fr')",
        content,
    )
    return content


def main() -> None:
    root = find_project_root()
    files = {
        "oracle_service": root / "backend" / "app" / "services" / "oracle_service.py",
        "main_py": root / "backend" / "app" / "main.py",
        "sidebar": root / "frontend" / "components" / "app-sidebar.tsx",
        "settings": root / "frontend" / "app" / "(dashboard)" / "settings" / "page.tsx",
        "dashboard": root / "frontend" / "app" / "(dashboard)" / "page.tsx",
        "i18n": root / "frontend" / "lib" / "i18n.ts",
        "app_shell": root / "frontend" / "components" / "app-shell.tsx",
    }

    print("=" * 80)
    print("Audit AI — Patch politique métadonnées + interface")
    print(f"Projet : {root}")
    print(f"Date   : {datetime.now()}")
    print("=" * 80)

    patch_file(files["oracle_service"], patch_oracle_service, "Backend métadonnées dynamiques")
    patch_file(files["main_py"], patch_main_py, "Backend exécution SQL scoped")
    patch_file(files["sidebar"], patch_app_sidebar, "Sidebar lisibilité")
    patch_file(files["settings"], patch_settings_page, "Paramètres langue/admin")
    patch_file(files["dashboard"], patch_dashboard_page, "Descriptions colonnes")
    patch_file(files["i18n"], patch_i18n, "Traductions")
    patch_file(files["app_shell"], patch_app_shell, "Langue forcée côté shell")

    print("=" * 80)
    print("Patch terminé.")
    print()
    print("À faire maintenant :")
    print("1) Redémarrer le backend :")
    print("   cd backend")
    print("   uvicorn app.main:app --reload")
    print()
    print("2) Redémarrer ou laisser rafraîchir le frontend :")
    print("   cd frontend")
    print("   npm run dev")
    print()
    print("Résultat attendu :")
    print("- Tables : TEST et VROMUALD masquées ; nouvelles tables non masquées visibles automatiquement.")
    print("- Utilisateurs : anciens comptes bruités masqués ; nouveaux utilisateurs non masqués visibles automatiquement.")
    print("- Anglais : non visible dans Paramètres ; langue forcée en français.")
    print("- Connexion Oracle : visible uniquement pour les administrateurs.")
    print("- Sidebar : textes plus blancs et plus gras.")
    print("=" * 80)


if __name__ == "__main__":
    main()
