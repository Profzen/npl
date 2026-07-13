# Patch thème ASKSMART — Bleu ardoise

Fichiers à remplacer dans ton projet local :

- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/components/app-sidebar.tsx`

## Thème actif

Le thème actif est défini dans `frontend/app/layout.tsx` :

```tsx
<html lang="fr" data-theme="slate">
```

`slate` = Bleu ardoise.

## Activer rapidement le thème Gris graphite

Dans `frontend/app/layout.tsx`, remplacer :

```tsx
<html lang="fr" data-theme="slate">
```

par :

```tsx
<html lang="fr" data-theme="graphite">
```

Puis relancer le frontend ou laisser Next.js rafraîchir automatiquement.

## Revenir au Bleu ardoise

Remettre :

```tsx
<html lang="fr" data-theme="slate">
```
