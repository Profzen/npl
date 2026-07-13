# Patch AuditAI — nom de plateforme + anglais désactivé

Ce patch fait deux choses sans écraser le thème bleu ardoise :

1. Remplace le nom affiché `ASKSMART` par `AuditAI` dans le frontend.
2. Désactive temporairement l'anglais dans l'interface sans supprimer les traductions anglaises.

## Utilisation

Copier `apply_auditai_brand_language_patch.py` à la racine du projet `nlp`, puis exécuter :

```powershell
python apply_auditai_brand_language_patch.py
```

Tu peux aussi l'exécuter depuis le dossier `frontend`.

Ensuite :

```powershell
cd frontend
npm run dev
```

## Pour réactiver l'anglais plus tard

Les traductions anglaises ne sont pas supprimées.

Il faudra revenir dans :

```text
frontend/lib/i18n.ts
frontend/app/(dashboard)/settings/page.tsx
frontend/components/app-shell.tsx
```

et remettre l'utilisation de `settings.interface_lang` au lieu de la valeur forcée `'fr'`.

Le script crée des sauvegardes avec le suffixe :

```text
.bak_auditai_brand_lang
```
