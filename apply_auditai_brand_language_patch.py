from pathlib import Path
import re
import shutil
import sys

BRAND_OLD = "ASKSMART"
BRAND_NEW = "AuditAI"
BACKUP_SUFFIX = ".bak_auditai_brand_lang"


def find_frontend_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "frontend" / "app").exists():
        return cwd / "frontend"
    if cwd.name == "frontend" and (cwd / "app").exists():
        return cwd
    raise SystemExit(
        "Impossible de trouver le dossier frontend.\n"
        "Lance ce script depuis la racine du projet nlp, ou depuis le dossier frontend."
    )


def backup(path: Path) -> None:
    backup_path = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    backup(path)
    path.write_text(text, encoding="utf-8")


def replace_all_visible_brand(frontend: Path) -> None:
    # Remplace le nom affiché dans le frontend sans toucher node_modules/.next.
    allowed_ext = {".ts", ".tsx", ".css", ".json", ".md", ".html", ".mjs"}
    excluded_dirs = {"node_modules", ".next", "dist", "build", ".git"}

    for path in frontend.rglob("*"):
        if not path.is_file() or path.suffix not in allowed_ext:
            continue
        if any(part in excluded_dirs for part in path.parts):
            continue

        text = read(path)
        new_text = text
        new_text = new_text.replace("ASKSMART", BRAND_NEW)
        new_text = new_text.replace("AskSmart", BRAND_NEW)
        new_text = new_text.replace("asksmart_lang", "auditai_lang")

        if new_text != text:
            write(path, new_text)


def patch_i18n(frontend: Path) -> None:
    path = frontend / "lib" / "i18n.ts"
    text = read(path)

    # Si on force l'interface en français, useAppData n'est plus nécessaire ici.
    text = text.replace("import { useAppData } from '@/components/app-shell'\n\n", "")

    # Ajoute une clé d'aide sans supprimer les traductions anglaises.
    fr_key = "  'settings.lang_en': 'English',\n"
    fr_insert = (
        "  'settings.lang_en': 'English',\n"
        "  'settings.lang_en_disabled': 'Anglais temporairement désactivé : le modèle NLP répond actuellement en français.',\n"
    )
    if "settings.lang_en_disabled" not in text:
        text = text.replace(fr_key, fr_insert, 1)
        # deuxième occurrence dans EN
        text = text.replace(
            fr_key,
            "  'settings.lang_en': 'English',\n"
            "  'settings.lang_en_disabled': 'English is temporarily disabled because the NLP model currently answers in French.',\n",
            1,
        )

    # Force l'interface en français, en gardant le dictionnaire EN dans le fichier.
    text = re.sub(
        r"export function useT\(\) \{\n\s*const \{ settings \} = useAppData\(\)\n\s*const lang: Lang = \(settings\?\.interface_lang as Lang\) \|\| 'fr'\n\s*return \(key: string\) => translate\(lang, key\)\n\}",
        "export function useT() {\n"
        "  // Anglais temporairement désactivé : le modèle NLP répond actuellement en français.\n"
        "  // Pour le réactiver plus tard, remettre la langue depuis settings.interface_lang.\n"
        "  const lang: Lang = 'fr'\n"
        "  return (key: string) => translate(lang, key)\n"
        "}",
        text,
    )

    text = re.sub(
        r"export function useLang\(\): Lang \{\n\s*const \{ settings \} = useAppData\(\)\n\s*return \(settings\?\.interface_lang as Lang\) \|\| 'fr'\n\}",
        "export function useLang(): Lang {\n"
        "  // Anglais temporairement désactivé.\n"
        "  return 'fr'\n"
        "}",
        text,
    )

    # Remplace complètement getStandaloneLang, même s'il lit localStorage/navigator avant.
    text = re.sub(
        r"export function getStandaloneLang\(\): Lang \{.*?\n\}\n\nexport function tStandalone",
        "export function getStandaloneLang(): Lang {\n"
        "  // Anglais temporairement désactivé : premier rendu serveur et client toujours en français.\n"
        "  return 'fr'\n"
        "}\n\nexport function tStandalone",
        text,
        flags=re.S,
    )

    write(path, text)


def patch_settings_page(frontend: Path) -> None:
    path = frontend / "app" / "(dashboard)" / "settings" / "page.tsx"
    text = read(path)

    # Le formulaire affiche et sauvegarde toujours 'fr', même si l'ancien fichier de settings contient 'en'.
    text = text.replace("setFormData({ ...settings })", "setFormData({ ...settings, interface_lang: 'fr' })")
    text = text.replace("await updateSettings(formData)", "await updateSettings({ ...formData, interface_lang: 'fr' })")

    old_select = re.compile(
        r"<Select\s+value=\{formData\.interface_lang\}\s+onValueChange=\{\(value\) => handleInputChange\('interface_lang', value as 'fr' \| 'en'\)\}\s+>\s+"
        r"<SelectTrigger id=\"interface_lang\">\s+<SelectValue />\s+</SelectTrigger>\s+"
        r"<SelectContent>\s+<SelectItem value=\"fr\">Français</SelectItem>\s+<SelectItem value=\"en\">English</SelectItem>\s+</SelectContent>\s+</Select>",
        flags=re.S,
    )

    new_select = """<Select
                  value="fr"
                  onValueChange={() => handleInputChange('interface_lang', 'fr')}
                >
                  <SelectTrigger id="interface_lang">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fr">{t('settings.lang_fr')}</SelectItem>
                    <SelectItem value="en" disabled>
                      {t('settings.lang_en')} — désactivé
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {t('settings.lang_en_disabled')}
                </p>"""

    text = old_select.sub(new_select, text)
    write(path, text)


def patch_app_shell(frontend: Path) -> None:
    path = frontend / "components" / "app-shell.tsx"
    if not path.exists():
        return
    text = read(path)

    # Même si le backend renvoie 'en', l'interface reste en français pour le moment.
    text = text.replace("setSettings(data)", "setSettings({ ...data, interface_lang: 'fr' })")
    text = text.replace("window.localStorage.setItem('auditai_lang', data.interface_lang)", "window.localStorage.setItem('auditai_lang', 'fr')")
    text = text.replace("window.localStorage.setItem('asksmart_lang', data.interface_lang)", "window.localStorage.setItem('auditai_lang', 'fr')")
    text = text.replace("translate((settings?.interface_lang as 'fr' | 'en') || 'fr', 'app.loading')", "translate('fr', 'app.loading')")

    write(path, text)


def patch_login_hydration_if_needed(frontend: Path) -> None:
    path = frontend / "app" / "login" / "page.tsx"
    if not path.exists():
        return
    text = read(path)

    # Garde la correction anti-hydratation si elle est déjà faite ; sinon l'applique.
    text = text.replace("import { useState, useEffect } from 'react'", "import { useState, useEffect, type FormEvent } from 'react'")
    text = text.replace("import { tStandalone, getStandaloneLang } from '@/lib/i18n'", "import { translate, getStandaloneLang, type Lang } from '@/lib/i18n'")
    text = text.replace("const [, setLang] = useState<'fr' | 'en'>('fr')\n  useEffect(() => { setLang(getStandaloneLang()) }, [])\n  const t = tStandalone", "const [lang, setLang] = useState<Lang>('fr')\n\n  useEffect(() => {\n    setLang(getStandaloneLang())\n  }, [])\n\n  const t = (key: string) => translate(lang, key)")
    text = text.replace("const handleSubmit = async (e: React.FormEvent) => {", "const handleSubmit = async (e: FormEvent) => {")

    write(path, text)


def main() -> None:
    frontend = find_frontend_root()

    required = [
        frontend / "lib" / "i18n.ts",
        frontend / "app" / "(dashboard)" / "settings" / "page.tsx",
        frontend / "components" / "app-shell.tsx",
        frontend / "app" / "login" / "page.tsx",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit("Fichiers introuvables :\n" + "\n".join(missing))

    replace_all_visible_brand(frontend)
    patch_i18n(frontend)
    patch_settings_page(frontend)
    patch_app_shell(frontend)
    patch_login_hydration_if_needed(frontend)

    print("\nPatch appliqué avec succès.")
    print("- Nom affiché : AuditAI")
    print("- Interface forcée en français")
    print("- Option English visible mais désactivée dans Paramètres")
    print(f"- Backups créés avec le suffixe : {BACKUP_SUFFIX}")
    print("\nRelance ensuite : npm run dev")


if __name__ == "__main__":
    main()
