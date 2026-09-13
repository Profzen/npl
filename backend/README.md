# Backend AuditAI

Le backend FastAPI transforme une question française en intention structurée, ancre les utilisateurs et objets dans les catalogues Oracle, puis construit une requête de lecture paramétrée. Le modèle local ne produit jamais le SQL exécuté.

## Pipeline actif

1. Qwen2.5-Coder local via `llama-server` produit une intention JSON.
2. `intent_policy.py` valide le statut, les entités, actions, périodes et agrégats.
3. `safe_sql_builder.py` construit uniquement un `SELECT` sur `SMART2DSECU.UNIFIED_AUDIT_DATA`.
4. Oracle est interrogé avec `AUDITAI_READER` et des paramètres liés.
5. Le même Qwen résume les résultats multiples. Les agrégats et résultats uniques utilisent une synthèse déterministe exacte.

## Installation

Depuis `backend/` :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Le runtime actif n'installe pas Torch, Transformers, PEFT ni llama-cpp-python. Le modèle tourne dans le processus `llama-server` séparé.

## Exécution

Utiliser les scripts racine documentés dans `LOCAL_RUN.md`. Pour lancer seulement l'API lorsque Oracle et Qwen sont déjà prêts :

```powershell
$env:ORACLE_PASSWORD="<secret local>"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Tests

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app
```

Les routes principales sont `/api/health`, `/api/metadata`, `/api/query`, `/api/query/start` et `/api/query/progress/{request_id}`. Toutes exigent une session, sauf la connexion.
