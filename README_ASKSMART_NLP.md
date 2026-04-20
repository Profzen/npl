# ASKSMART — NLP Oracle Audit Intelligence

## 1. Contexte du projet

ASKSMART est une application qui permet à des **utilisateurs non-techniciens** (responsables sécurité, auditeurs) de poser des questions en **français naturel** sur une base Oracle d'audit, et d'obtenir des réponses claires sans jamais voir de SQL.

**Exemple :** L'utilisateur tape "Qui s'est connecté hier ?" et reçoit "3 connexions détectées hier : JDUPONT, MDURAND et ADMIN."

---

## 2. Architecture générale

```
┌─────────────────┐     ┌──────────────────────────────────────────┐
│   Frontend      │     │   Backend (FastAPI)                      │
│   Next.js +     │────▶│                                          │
│   TypeScript    │ API │  ┌──────────┐   ┌──────────┐             │
│   Tailwind CSS  │     │  │TinyLlama │   │  Phi-3   │             │
│   shadcn/ui     │◀────│  │ + LoRA   │   │  GGUF    │             │
│                 │     │  │(SQL Gen) │   │(Synthèse)│             │
└─────────────────┘     │  └────┬─────┘   └────┬─────┘             │
                        │       │              │                    │
                        │       ▼              ▼                    │
                        │  ┌─────────────────────────┐             │
                        │  │   Oracle Database        │             │
                        │  │   Table audit unifiée    │             │
                        │  └─────────────────────────┘             │
                        └──────────────────────────────────────────┘
```

### Pipeline d'une question (5 étapes)

1. **Génération SQL** — TinyLlama 1.1B + LoRA traduit la question française en SQL Oracle
2. **Connexion Oracle** — Ouverture d'une connexion depuis le pool (max 15)
3. **Exécution** — Le SQL est exécuté sur `SMART2DSECU.UNIFIED_AUDIT_DATA`
4. **Traduction** — Phi-3 Mini (GGUF) transforme les résultats bruts en résumé français clair
5. **Finalisation** — Mise en forme + cache de la réponse

### Composants clés

| Composant | Rôle | Fichier(s) |
|---|---|---|
| **TinyLlama 1.1B** | Modèle de base (poids) | `TinyLlama-1.1B-Chat-v1.0/` |
| **LoRA V12** | Adapter entraîné pour SQL Oracle | `tinyllama_oracle_lora/` |
| **Phi-3 Mini GGUF** | Synthèse en français | `phi3-mini-gguf/` |
| **nlp_service.py** | Chargement TinyLlama + génération SQL | `backend/app/services/` |
| **synthesis_service.py** | Chargement Phi-3 + synthèse | `backend/app/services/` |
| **oracle_service.py** | Pool Oracle + exécution SQL | `backend/app/services/` |
| **main.py** | API FastAPI, cache, pipeline complet | `backend/app/` |
| **config.py** | Configuration centralisée | `backend/app/` |

### Machine de production

- 20 CPUs @ 3 GHz, 25 GB RAM, 100 GB HDD
- Pas de GPU — tout tourne sur CPU
- Les modèles doivent utiliser toutes les ressources nécessaires (pas de limitation artificielle)

---

## 3. Le modèle TinyLlama + LoRA — Comment ça marche

### Principe

TinyLlama 1.1B est un petit modèle de langage. Seul, il ne sait pas générer du SQL Oracle.
On lui apprend via **LoRA** (Low-Rank Adaptation) : on entraîne un petit "adapter" (~60 MB) qui modifie le comportement du modèle sans toucher aux poids originaux.

### Entraînement sur Google Colab

L'entraînement se fait sur Colab (GPU T4 gratuit) via un notebook `.ipynb`.
Le dataset contient des paires (question française → SQL Oracle attendu).

**Cycle d'amélioration :**
```
Question utilisateur → Modèle génère SQL → Test → Erreur détectée
    → Enrichir le dataset avec des exemples ciblant cette erreur
    → Réentraîner sur Colab → Nouveau LoRA
    → Télécharger et remplacer tinyllama_oracle_lora/
    → Tester à nouveau
```

### SYSTEM_PROMPT (critique)

Le SYSTEM_PROMPT utilisé à l'entraînement **doit être identique** à celui du backend.
Si on le modifie dans le notebook, il faut aussi le modifier dans `nlp_service.py`.

**SYSTEM_PROMPT actuel (V12 — dans le notebook) :**
```
Tu es un expert SQL Oracle specialise en audit.
Table : ORACLE_AUDIT_TRAIL
Colonnes : ID, DBUSERNAME, EVENT_TIMESTAMP, ACTION_NAME, OBJECT_NAME,
USERHOST, RETURNCODE, AUDIT_TYPE, OS_USERNAME.
Vue : DBA_USERS (USERNAME, ACCOUNT_STATUS, CREATED).
REGLES ABSOLUES :
1. Connexions : toujours WHERE ACTION_NAME='LOGON' — jamais WHERE LOGON seul.
2. Heures : SYSDATE-N/24. Jours : SYSDATE-N. Minutes : SYSDATE-N/1440.
3. Si question sur un utilisateur ET un objet : WHERE DBUSERNAME='X' AND OBJECT_NAME='Y'.
4. Poste/machine/terminal/hote reseau → colonne USERHOST.
5. SELECT uniquement.
6. Limite : FETCH FIRST N ROWS ONLY.
7. Tri par date : ORDER BY EVENT_TIMESTAMP DESC.
```

**SYSTEM_PROMPT backend (dans nlp_service.py) :**
```
Colonnes reelles : ID, AUDIT_TYPE, SESSIONID, OS_USERNAME, USERHOST, TERMINAL,
AUTHENTICATION_TYPE, DBUSERNAME, CLIENT_PROGRAM_NAME, OBJECT_SCHEMA, OBJECT_NAME,
SQL_TEXT, SQL_BINDS, EVENT_TIMESTAMP, ACTION_NAME, INSTANCE
```

> **ALERTE DIVERGENCE :** Les colonnes du SYSTEM_PROMPT d'entraînement ne correspondent
> pas aux colonnes réelles de la table Oracle en production. Voir section "Améliorations".

---

## 4. Historique des versions

| Version | Score benchmark | Dataset | Problèmes corrigés |
|---|---|---|---|
| **V9** | 30% | 9 000 ex | Version initiale |
| **V10** | Non testé | +blocs C-F | Mois nommés, OBJECT_NAME, actions, langage métier |
| **V11** | 50% (5/10) | +blocs G-H | Temporel paramétrique, error-driven |
| **V12** | **95% (9/10)** | ~9 500 ex | Failles α β δ ε, enrichissement global, SYSTEM_PROMPT renforcé |

### Résultat benchmark V12 (10 questions terrain)

| ID | Score | Description | Statut |
|---|---|---|---|
| Q1 | 100% | `ACTION_NAME='LOGON'` + `SYSDATE-1` | ✅ |
| Q2 | **50%** | 48h → `SYSDATE-48/24` (manque `/24`) | ⚠️ |
| Q3 | 100% | Mois nommé → `TO_DATE` bornes | ✅ |
| Q4 | 100% | `GROUP BY OBJECT_NAME` | ✅ |
| Q5 | 100% | Accès objet → pas LOGON | ✅ |
| Q6 | 100% | Double filtre acteur + objet | ✅ |
| Q7 | 100% | Poste → `USERHOST` | ✅ |
| Q8 | 100% | Suppression comptes → `DROP USER` | ✅ |
| Q9 | 100% | Changements 30 jours | ✅ |
| Q10 | 100% | Horaire nocturne → `HH24` | ✅ |

---

## 5. Failles connues et améliorations à faire

### 5.1 FAILLE PRIORITAIRE — Conversion heures en `/24`

**Problème :** Quand l'utilisateur dit "48 dernières heures", le modèle génère `SYSDATE-48` au lieu de `SYSDATE-48/24`. `SYSDATE-48` c'est 48 **jours**, pas 48 heures.

**Règle :** Toute durée exprimée en heures doit utiliser `/24` : `SYSDATE-N/24`.

**Solution V13 :** Enrichir le dataset avec des exemples variés :
- "dans les 24 dernières heures" → `SYSDATE-24/24` (= `SYSDATE-1`)
- "dans les 48 dernières heures" → `SYSDATE-48/24`
- "dans les 72 dernières heures" → `SYSDATE-72/24`
- "dans les 6 dernières heures" → `SYSDATE-6/24`
- "il y a 2 heures" → `SYSDATE-2/24`
- Varier les formulations : "ces 48h", "depuis 48 heures", "les 2 dernières heures"

### 5.2 DIVERGENCE SYSTEM_PROMPT — Colonnes entraînement vs production

**Problème :** Le modèle est entraîné avec des colonnes simplifiées :
```
ID, DBUSERNAME, EVENT_TIMESTAMP, ACTION_NAME, OBJECT_NAME,
USERHOST, RETURNCODE, AUDIT_TYPE, OS_USERNAME
```

Mais la table Oracle réelle contient des colonnes différentes/supplémentaires :
```
ID, AUDIT_TYPE, SESSIONID, OS_USERNAME, USERHOST, TERMINAL,
AUTHENTICATION_TYPE, DBUSERNAME, CLIENT_PROGRAM_NAME, OBJECT_SCHEMA,
OBJECT_NAME, SQL_TEXT, SQL_BINDS, EVENT_TIMESTAMP, ACTION_NAME, INSTANCE
```

**Conséquence :** Le modèle ne sait pas utiliser `SESSIONID`, `TERMINAL`, `CLIENT_PROGRAM_NAME`, `OBJECT_SCHEMA`, `SQL_TEXT`, etc. Et il pourrait générer `RETURNCODE` qui n'existe pas dans la vraie table.

**Solution V13 :** Aligner le SYSTEM_PROMPT d'entraînement sur les colonnes réelles, et ajouter des exemples utilisant les nouvelles colonnes.

### 5.3 GGUF quantification non fonctionnelle

**Problème :** Sur Colab, `llama-quantize` n'a pas compilé. Le fallback a copié le fichier fp16 en le renommant Q4 → fichier de 2.2 GB au lieu de ~600 MB.

**Solution :** Lors du prochain entraînement, s'assurer que `llama.cpp` compile correctement ou utiliser une méthode alternative de quantification (ex: `llama-cpp-python` avec `quantize()`).

### 5.4 Post-process SQL — Rustines à supprimer progressivement

Le fichier `nlp_service.py` (backend) et la fonction `post_process_sql()` (notebook cellule 12) contiennent des corrections en dur :
- `WHERE LOGON` → `WHERE ACTION_NAME='LOGON'` (faille α)
- `SYSDATE-N` → `SYSDATE-N/24` quand heures détectées (faille β)
- Alias colonnes : `OBJ_NAME` → `OBJECT_NAME`, etc.

**Objectif :** À chaque version, le modèle devrait mieux comprendre nativement ces règles, réduisant le besoin de rustines. Les rustines servent de filet de sécurité mais ne remplacent pas un bon entraînement.

### 5.5 Synthèse Phi-3 — Messages d'erreur

**Statut :** Corrigé dans le backend.
- Quand le SQL échoue → Phi-3 formule une réponse empathique (pas d'erreur technique)
- Quand Phi-3 échoue → Fallback vers synthèse par règles
- Quand aucun résultat → Message "aucune activité détectée"

---

## 6. Guide d'entraînement — Cycle V13+

### Étape 1 : Identifier les failles
Tester l'app avec des questions variées. Noter les cas qui échouent :
- SQL invalide (erreur Oracle)
- SQL valide mais mauvais résultat (mauvaise table, mauvaise colonne)
- SQL correct mais incomplet (manque un filtre)

### Étape 2 : Enrichir le dataset
Pour chaque faille, ajouter **15-30 exemples** avec des formulations variées.
Format CSV : `instruction,output`
- `instruction` = question en français
- `output` = SQL Oracle attendu

**Règles de qualité du dataset :**
- Varier les formulations (formel, informel, abrégé, détaillé)
- Inclure des pièges (ex: "48 heures" vs "48 jours")
- Équilibrer les types de questions (LOGON, SELECT, INSERT, GROUP BY, dates, etc.)
- Le SQL de sortie doit utiliser `ORACLE_AUDIT_TRAIL` (remplacé automatiquement en production)

### Étape 3 : Modifier le SYSTEM_PROMPT si nécessaire
Si on change les colonnes ou les règles, mettre à jour dans :
1. Le notebook (cellule 10 — entraînement)
2. Le notebook (cellule 12 — inférence/benchmark)
3. Le backend (`nlp_service.py` → fonction `_system_prompt()`)

### Étape 4 : Entraîner sur Colab
- Exécuter les cellules 1 à 10 du notebook
- Paramètres actuels : LoRA r=32, alpha=64, 4 époques, lr=1.5e-4, batch=8
- Durée : ~55-65 min sur T4

### Étape 5 : Benchmark
- Exécuter cellule 18 (benchmark 10 questions)
- Exécuter cellule 19 (rapport de performance)
- Objectif : **90%+** sur le benchmark

### Étape 6 : Déployer
- Télécharger `tinyllama_oracle_lora.zip` depuis Colab
- Dézipper et remplacer `tinyllama_oracle_lora/` sur le serveur
- Redémarrer le backend

---

## 7. Structure des fichiers

```
c:\dossier3\nlp\
├── backend/
│   └── app/
│       ├── config.py              ← Configuration centrale
│       ├── main.py                ← API FastAPI + pipeline + cache
│       ├── schemas.py             ← Modèles Pydantic
│       └── services/
│           ├── nlp_service.py     ← TinyLlama + LoRA (SQL generation)
│           ├── synthesis_service.py ← Phi-3 (synthèse française)
│           └── oracle_service.py  ← Pool Oracle + exécution
├── frontend/
│   ├── app/(dashboard)/page.tsx   ← Dashboard principal
│   ├── components/
│   │   ├── app-shell.tsx          ← Layout + contexte
│   │   └── app-sidebar.tsx        ← Sidebar (nav, historique, colonnes)
│   └── src/
├── TinyLlama-1.1B-Chat-v1.0/     ← Poids du modèle de base (~2.2 GB)
├── tinyllama_oracle_lora/         ← Adapter LoRA entraîné (V12)
├── phi3-mini-gguf/                ← Phi-3 pour synthèse
├── tinyllama_oracle_v12_dataset (2).ipynb  ← Notebook d'entraînement
├── oracle_nlp_dataset.csv         ← Dataset d'entraînement (~9500 lignes)
└── oracle_audit_trail.csv         ← Table audit simulée (benchmark)
```

---

## 8. Commandes utiles

### Démarrer le backend
```powershell
cd C:\dossier3\nlp
c:\dossier3\nlp\venv_nlp\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

### Démarrer le frontend
```powershell
cd C:\dossier3\nlp\frontend
npm run dev
```

### Vérifier les modèles chargés
```
GET http://localhost:8000/api/status
```

---

## 9. Journal des tests terrain

> Cette section sera enrichie après les tests avec le LoRA V12 en production.

### Tests à effectuer

| # | Question à tester | Objectif |
|---|---|---|
| 1 | "Qui s'est connecté hier ?" | ACTION_NAME='LOGON' + SYSDATE-1 |
| 2 | "Combien d'utilisateurs dans la base ?" | COUNT(DISTINCT DBUSERNAME) |
| 3 | "Quels utilisateurs se sont connectés dans les 48 dernières heures ?" | SYSDATE-48/24 |
| 4 | "Qu'est-ce qui s'est passé en janvier 2026 ?" | TO_DATE bornes |
| 5 | "Quelle table a été la plus modifiée ?" | GROUP BY OBJECT_NAME |
| 6 | "Quelles actions VROMUALD a-t-il effectuées sur EMPLOYEES ?" | Double filtre |
| 7 | "Quel poste a fait le plus de connexions ?" | USERHOST + GROUP BY |
| 8 | "Y a-t-il eu des suppressions de comptes ?" | DROP USER |
| 9 | "Qui a le plus modifié de données ces 30 derniers jours ?" | INSERT/UPDATE/DELETE + SYSDATE-30 |
| 10 | "Connexions entre 22h et 6h ?" | HH24 + nocturne |

### Résultats test terrain V12 — 17 avril 2026

**Score : 3/10 (vs 95% sur benchmark Colab)**

| # | Statut | Temps | SQL généré | Problème |
|---|---|---|---|---|
| Q1 | **KO** | 24.6s | `WHERE TRUNC(EVENT_TIMESTAMP)=TRUNC(SYSDATE-1)` | SQL correct mais **manque `ACTION_NAME='LOGON'`** → retourne 0 lignes car pas de données hier |
| Q2 | **KO** | 36.6s | `SELECT COUNT(*) FROM DBA_USERS` | **Utilise DBA_USERS** au lieu de UNIFIED_AUDIT_DATA. Le SYSTEM_PROMPT backend dit "N'utilise jamais DBA_USERS" mais le modèle est entraîné avec un SYSTEM_PROMPT différent qui mentionne DBA_USERS |
| Q3 | **KO** | 26.1s | `WHERE ACTION_NAME='SELECT' AND EVENT_TIMESTAMP>=SYSDATE-48/24` | Le `/24` est correct ! Mais **ACTION_NAME='SELECT' au lieu de 'LOGON'** pour "connectés" |
| Q4 | **KO** | 31.4s | `WHERE TRUNC(EVENT_TIMESTAMP) >= TO_DATE('2026-01-01','YYYY-MM-DD') AND TR` | **SQL tronqué** — le `max_sql_tokens=80` est trop bas, la requête est coupée |
| Q5 | **OK** | 26.4s | `WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') GROUP BY OBJECT_NAME` | Parfait |
| Q6 | **KO** | 26.5s | `WHERE DBUSERNAME='VROMUALD' AND OBJECT_NAME='EMPLOYEES'` | SQL parfait mais VROMUALD/EMPLOYEES n'existent pas dans la vraie base → 0 résultat (comportement attendu) |
| Q7 | **OK** | 25.0s | `SELECT USERHOST, COUNT(*) GROUP BY USERHOST ORDER BY NB DESC FETCH FIRST 1` | Parfait |
| Q8 | **OK** | 48.3s | `WHERE ACTION_NAME = 'DROP USER'` | Parfait, 10 résultats, synthèse correcte |
| Q9 | **KO** | 27.7s | `WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') AND TRUNC(EVENT_TIMESTAMP)>=TRUNC(SYSDATE-30)` | SQL correct mais 0 résultat (pas de données récentes dans la base) |
| Q10 | **KO** | 33.3s | `WHERE CONNECTED IN (22,6)` | **Colonne CONNECTED n'existe pas**. Devrait utiliser `TO_CHAR(EVENT_TIMESTAMP,'HH24')` |

### Analyse des causes — Écart Colab vs Production

**Cause principale : DIVERGENCE SYSTEM_PROMPT**

Le modèle est entraîné avec un SYSTEM_PROMPT qui dit :
- Table : `ORACLE_AUDIT_TRAIL`
- Colonnes : `ID, DBUSERNAME, EVENT_TIMESTAMP, ACTION_NAME, OBJECT_NAME, USERHOST, RETURNCODE, AUDIT_TYPE, OS_USERNAME`
- Vue : `DBA_USERS`

Mais le backend utilise un SYSTEM_PROMPT différent qui dit :
- Table : `SMART2DSECU.UNIFIED_AUDIT_DATA`
- Colonnes : `ID, AUDIT_TYPE, SESSIONID, OS_USERNAME, USERHOST, TERMINAL, AUTHENTICATION_TYPE, DBUSERNAME, CLIENT_PROGRAM_NAME, OBJECT_SCHEMA, OBJECT_NAME, SQL_TEXT, SQL_BINDS, EVENT_TIMESTAMP, ACTION_NAME, INSTANCE`
- Interdit : `DBA_USERS`

Le modèle a appris avec un contexte, mais tourne avec un autre → **confusion**.

**Autres causes identifiées :**

| Problème | Questions touchées | Solution V13 |
|---|---|---|
| `max_sql_tokens=80` trop bas | Q4 (SQL tronqué) | Passer à `120` |
| ACTION_NAME='SELECT' au lieu de 'LOGON' pour "connecté" | Q3 | Plus d'exemples connexion ≠ SELECT |
| Colonne CONNECTED inventée | Q10 | Plus d'exemples avec TO_CHAR HH24 |
| DBA_USERS malgré interdiction | Q2 | **Aligner le SYSTEM_PROMPT** ou ne pas mentionner DBA_USERS du tout |
| Manque ACTION_NAME='LOGON' | Q1 | Le modèle génère du SQL sans filtre LOGON |

### Failles classées par priorité pour V13

**P1 — CRITIQUE : Aligner les SYSTEM_PROMPT**
Le même SYSTEM_PROMPT doit être utilisé partout : entraînement, benchmark, backend.
Décision : utiliser les **colonnes réelles** de la table Oracle de production dans les 3 endroits.

**P2 — CRITIQUE : max_sql_tokens trop bas**
`max_sql_tokens=80` tronque les requêtes complexes. Passer à **120 minimum**.

**P3 — HAUTE : Connexion = LOGON, pas SELECT**
Le modèle confond parfois "se connecter" avec SELECT. Renforcer avec des exemples ciblés.

**P4 — HAUTE : Horaire nocturne sans TO_CHAR**
Le modèle invente `CONNECTED` au lieu d'utiliser `TO_CHAR(EVENT_TIMESTAMP,'HH24')`.

**P5 — MOYENNE : Supprimer DBA_USERS du vocabulaire**
Ne plus mentionner DBA_USERS dans le SYSTEM_PROMPT d'entraînement car la table n'est pas accessible en production. Remplacer par `COUNT(DISTINCT DBUSERNAME)` sur la table audit.

**P6 — BASSE : Heures /24 (partiellement corrigé)**
Q3 a correctement utilisé `/24` ! Le modèle a appris la règle, mais l'a combinée avec le mauvais ACTION_NAME.

---

## 10. Philosophie du projet

- **Le modèle doit être intelligent** — pas corrigé par des rustines en dur
- **Les erreurs sont normales** — chaque erreur nourrit le prochain entraînement
- **Pas de limitation de ressources** — les modèles utilisent tout le CPU/RAM disponible
- **Messages toujours en français naturel** — jamais de jargon technique visible par l'utilisateur
- **Améliorations progressives** — V9 → V10 → V11 → V12 → V13..., chaque version corrige les failles de la précédente
