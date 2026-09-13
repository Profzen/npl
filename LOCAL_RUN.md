# Exécution locale AuditAI

## Prérequis

- Windows avec PowerShell, WSL2 Oracle Linux et Docker déjà configurés ;
- conteneur `auditai-oracle` créé ;
- modèle Qwen2.5-Coder Q4 dans `models/qwen2.5-coder-1.5b/` ;
- dépendances Python de `backend/requirements.txt` et dépendances npm installées.

## Démarrer

Depuis la racine du projet :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

Le script démarre Oracle, Qwen via llama.cpp, FastAPI et Next.js sur les interfaces de boucle locale. Les secrets restent dans `infra/oracle/.env`, ignoré par Git. Il crée un mot de passe administrateur local si nécessaire sans l'afficher.

Pour démarrer uniquement Oracle, le modèle et l'API :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -SkipFrontend
```

## Vérifier

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-local.ps1
```

Ce test se connecte à l'API, vérifie Oracle et le modèle, charge les catalogues, exécute une lecture agrégée, demande une clarification et refuse une mutation.

## Arrêter

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
```

L'arrêt libère la RAM du frontend, du backend, du modèle et du conteneur Oracle.

