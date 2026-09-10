# Audit AI — Documentation technique d’intégration

> Ce document décrit l’architecture réelle, le démarrage, les flux, les services backend, l’interface, les modèles locaux, la connexion Oracle, les données SQLite, les procédures de déploiement, de mise à jour et de dépannage de la plateforme **Audit AI**.
>
> Il est destiné à la personne chargée d’intégrer, déployer, exploiter ou maintenir le projet. Il doit rester à la racine du dossier livré.

---

## Table des matières

1. [Objet du projet](#1-objet-du-projet)
2. [Périmètre fonctionnel](#2-périmètre-fonctionnel)
3. [Architecture générale](#3-architecture-générale)
4. [Arborescence du dossier livré](#4-arborescence-du-dossier-livré)
5. [Rôle de chaque composant](#5-rôle-de-chaque-composant)
6. [Séquence de démarrage](#6-séquence-de-démarrage)
7. [Flux complet d’une question](#7-flux-complet-dune-question)
8. [Backend FastAPI](#8-backend-fastapi)
9. [Authentification, sessions et rôles](#9-authentification-sessions-et-rôles)
10. [Gestion des utilisateurs et journal applicatif](#10-gestion-des-utilisateurs-et-journal-applicatif)
11. [Service NLP TinyLlama + LoRA](#11-service-nlp-tinyllama--lora)
12. [Construction et nettoyage du SQL](#12-construction-et-nettoyage-du-sql)
13. [Service Oracle](#13-service-oracle)
14. [Métadonnées d’aide de l’interface](#14-métadonnées-daide-de-linterface)
15. [Service de synthèse Phi-3](#15-service-de-synthèse-phi-3)
16. [Historique, suivi, cache et concurrence](#16-historique-suivi-cache-et-concurrence)
17. [Paramètres d’exécution](#17-paramètres-dexécution)
18. [Frontend Next.js](#18-frontend-nextjs)
19. [Contrat API](#19-contrat-api)
20. [Prérequis techniques](#20-prérequis-techniques)
21. [Configuration de l’environnement](#21-configuration-de-lenvironnement)
22. [Installation](#22-installation)
23. [Lancement en développement](#23-lancement-en-développement)
24. [Déploiement d’intégration ou de production](#24-déploiement-dintégration-ou-de-production)
25. [Mise à jour du LoRA](#25-mise-à-jour-du-lora)
26. [Mise à jour de Phi-3](#26-mise-à-jour-de-phi-3)
27. [Configuration Oracle requise](#27-configuration-oracle-requise)
28. [Tests de validation après intégration](#28-tests-de-validation-après-intégration)
29. [Sauvegarde et retour arrière](#29-sauvegarde-et-retour-arrière)
30. [Dépannage](#30-dépannage)
31. [Sécurité et durcissement obligatoire](#31-sécurité-et-durcissement-obligatoire)
32. [Limites connues](#32-limites-connues)
33. [Guide de maintenance par besoin](#33-guide-de-maintenance-par-besoin)
34. [Contenu du ZIP de livraison](#34-contenu-du-zip-de-livraison)
35. [Checklist finale d’intégration](#35-checklist-finale-dintégration)

---

## 1. Objet du projet

**Audit AI** est une plateforme locale de questionnement des données d’audit Oracle en français naturel.

L’utilisateur pose une question comme :

```text
Quelle est la dernière action effectuée par SYSTEM ?
```

Le système :

1. authentifie l’utilisateur ;
2. transforme la question en SQL Oracle avec **TinyLlama 1.1B + adaptateur LoRA** ;
3. exécute le SQL sur la table d’audit configurée ;
4. convertit les lignes Oracle en objets JSON ;
5. produit une synthèse en français avec **Phi-3 Mini GGUF** ;
6. retourne le SQL, les résultats, la synthèse et les informations de suivi au frontend ;
7. journalise l’opération dans SQLite.

La solution est prévue pour fonctionner **localement**, sans API d’intelligence artificielle externe.

---

## 2. Périmètre fonctionnel

La version livrée couvre les fonctions suivantes :

- connexion et déconnexion des utilisateurs de l’application ;
- sessions locales par jeton ;
- rôles utilisateur et administrateur ;
- gestion des utilisateurs par l’administrateur ;
- questionnement en français ;
- génération de SQL Oracle ;
- exécution de requêtes sur les données d’audit ;
- affichage des lignes retournées ;
- synthèse en langage naturel ;
- suivi étape par étape d’une analyse ;
- historique récent des questions par utilisateur ;
- journal persistant des opérations applicatives ;
- page de paramètres ;
- état de santé d’Oracle, TinyLlama et Phi-3 ;
- colonnes d’aide contenant les utilisateurs et objets observés dans les données d’audit.

Audit AI n’administre pas la politique d’audit Oracle. Il consulte uniquement les événements déjà présents dans la source configurée.

---

## 3. Architecture générale

### 3.1 Vue logique

```text
┌─────────────────────────────────────────────────────────────┐
│                        Utilisateur                          │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP/JSON
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Frontend Next.js / React / TypeScript                       │
│ - authentification                                          │
│ - saisie de question                                        │
│ - polling du suivi                                          │
│ - affichage SQL, résultat et synthèse                       │
│ - historique, paramètres, administration                    │
└──────────────────────────────┬──────────────────────────────┘
                               │ API /api/*
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Backend FastAPI                                             │
│                                                             │
│  Auth ─► Pipeline requête ─► Audit applicatif               │
│                │                                            │
│                ├──► TinyLlama + LoRA : français → SQL       │
│                ├──► Oracle : exécution et métadonnées       │
│                └──► Phi-3 GGUF : résultats → synthèse FR    │
│                                                             │
│  SQLite Auth     SQLite Audit     Paramètres runtime         │
└───────────────┬─────────────────────────┬───────────────────┘
                │                         │
                ▼                         ▼
┌──────────────────────────┐   ┌──────────────────────────────┐
│ Oracle Database          │   │ Fichiers locaux             │
│ UNIFIED_AUDIT_DATA       │   │ modèles, SQLite, JSON       │
└──────────────────────────┘   └──────────────────────────────┘
```

### 3.2 Responsabilités séparées

| Couche | Responsabilité |
|---|---|
| Frontend | Interaction utilisateur, navigation, stockage du jeton, appels API et rendu des résultats |
| FastAPI | Authentification, orchestration du pipeline, contrôle des rôles, cache et suivi |
| TinyLlama + LoRA | Conversion de la question française en SQL Oracle |
| Oracle | Source réelle des événements d’audit |
| Phi-3 Mini | Reformulation des lignes Oracle en réponse claire |
| SQLite Auth | Utilisateurs, mots de passe hachés et sessions |
| SQLite Audit | Journal persistant des opérations applicatives |
| Paramètres runtime | Connexion Oracle et options modifiables depuis l’application |

---

## 4. Arborescence du dossier livré

L’organisation attendue est la suivante. Les noms des trois dossiers de modèles doivent rester cohérents avec les chemins configurés.

```text
AuditAI/
├── README.md
├── .env.example
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── schemas.py
│       └── services/
│           ├── auth_service.py
│           ├── audit_service.py
│           ├── nlp_service.py
│           ├── oracle_service.py
│           ├── settings_service.py
│           ├── synthesis_service.py
│           └── ...
├── frontend/
│   ├── package.json
│   ├── package-lock.json             # si présent dans la livraison
│   ├── next.config.*
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── public/
├── TinyLlama-1.1B-Chat-v1.0/
│   ├── config.json
│   ├── model.safetensors
│   ├── tokenizer.json                # selon l’export
│   ├── tokenizer_config.json
│   └── ...
├── tinyllama_oracle_lora/
│   ├── adapter_config.json
│   ├── adapter_model.safetensors
│   └── ...
├── phi3-mini-gguf/
│   └── Phi-3-mini-4k-instruct-q4.gguf
├── backend_auth.sqlite3              # facultatif, voir section SQLite
├── backend_audit.sqlite3             # facultatif, voir section SQLite
└── backend_runtime_settings.json     # facultatif et à assainir avant livraison
```

### 4.1 Dossiers à ne pas livrer

Les éléments suivants sont reconstruits à l’installation et doivent être exclus du ZIP :

```text
venv_nlp/
.venv/
venv/
node_modules/
frontend/.next/
__pycache__/
.pytest_cache/
.ipynb_checkpoints/
.cache/
logs temporaires
checkpoints Colab
fichiers .env contenant des secrets
caches de téléchargement Hugging Face
```

---

## 5. Rôle de chaque composant

### 5.1 Backend

| Fichier | Rôle technique |
|---|---|
| `backend/app/main.py` | Déclare FastAPI, CORS, routes, pipeline de question, suivi, cache et contrôle de concurrence |
| `backend/app/config.py` | Charge la configuration initiale et les variables d’environnement |
| `backend/app/schemas.py` | Définit les modèles Pydantic des requêtes et réponses HTTP |
| `services/auth_service.py` | Initialise la base d’authentification, hache les mots de passe, crée et valide les sessions |
| `services/audit_service.py` | Initialise et alimente le journal applicatif SQLite |
| `services/nlp_service.py` | Charge TinyLlama et le LoRA, construit le prompt, génère et nettoie le SQL |
| `services/oracle_service.py` | Gère le pool Oracle, exécute le SQL et récupère les métadonnées d’aide |
| `services/settings_service.py` | Lit, valide et persiste les paramètres modifiables à l’exécution |
| `services/synthesis_service.py` | Charge Phi-3 GGUF et synthétise les résultats Oracle |

### 5.2 Frontend

| Chemin | Rôle technique |
|---|---|
| `frontend/app/layout.tsx` | Layout racine Next.js |
| `frontend/app/login/page.tsx` | Formulaire d’authentification |
| `frontend/app/(dashboard)/layout.tsx` | Layout protégé avec barre latérale |
| `frontend/app/(dashboard)/page.tsx` | Tableau de bord et cycle de questionnement |
| `frontend/app/(dashboard)/history/page.tsx` | Historique récent |
| `frontend/app/(dashboard)/settings/page.tsx` | Paramètres d’exécution |
| `frontend/app/(dashboard)/admin/page.tsx` | Utilisateurs et journal applicatif réservés à l’administrateur |
| `frontend/components/app-shell.tsx` | Chargement global des données utiles au dashboard |
| `frontend/components/app-sidebar.tsx` | Navigation, statut Oracle et raccourcis |
| `frontend/lib/api.ts` | Wrapper HTTP et gestion des erreurs API |
| `frontend/lib/auth-context.tsx` | État de session React, stockage et envoi du jeton |
| `frontend/lib/i18n.ts` | Textes d’interface ; l’interface livrée est utilisée en français |
| `frontend/lib/types.ts` | Types TypeScript communs aux réponses backend |

---

## 6. Séquence de démarrage

Au démarrage du processus FastAPI, la fonction `startup()` de `backend/app/main.py` réalise les opérations suivantes :

```text
Démarrage Uvicorn
      │
      ├── init_auth_db()
      │     └── création/migration des tables utilisateurs et sessions
      │
      ├── init_audit_db()
      │     └── création du journal applicatif SQLite
      │
      ├── model_status()
      │     ├── chargement du tokenizer TinyLlama
      │     ├── chargement du modèle de base
      │     ├── chargement de l’adaptateur LoRA
      │     └── passage du modèle en mode évaluation sur CPU
      │
      └── phi3_status()
            └── chargement ou vérification du modèle Phi-3 GGUF
```

Le préchargement des modèles évite que le premier utilisateur supporte seul le temps de chargement initial.

### 6.1 Conséquence opérationnelle

Le démarrage peut prendre plusieurs secondes ou minutes selon le processeur, le disque et la mémoire. Le backend ne doit pas être considéré comme pleinement prêt tant que les statuts TinyLlama et Phi-3 n’ont pas été vérifiés dans les logs ou via `/api/health`.

### 6.2 Un seul processus Uvicorn

La version actuelle conserve le suivi, l’historique récent, le cache et le contrôle de concurrence en mémoire Python. Elle doit donc être lancée avec **un seul worker**.

Ne pas utiliser :

```bash
uvicorn app.main:app --workers 4
```

Utiliser :

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Plusieurs workers dupliqueraient les modèles en mémoire et rendraient le suivi incohérent : une demande pourrait être créée par un worker puis interrogée sur un autre, provoquant `Suivi introuvable`.

---

## 7. Flux complet d’une question

### 7.1 Mode utilisé par l’interface : démarrage + polling

```text
1. Utilisateur saisit une question
2. Frontend POST /api/query/start
3. Backend vérifie X-Auth-Token
4. Backend vérifie le cache de réponse
5. Backend réserve un créneau de calcul pour l’utilisateur
6. Backend crée request_id et état de suivi en mémoire
7. Backend démarre un Thread daemon
8. Frontend reçoit request_id
9. Frontend poll GET /api/query/progress/{request_id}
10. TinyLlama + LoRA génère le SQL
11. Le service Oracle ouvre/acquiert une connexion
12. Oracle exécute le SQL
13. Les lignes sont converties en dictionnaires Python
14. Phi-3 synthétise la réponse
15. Le backend écrit l’historique mémoire et le journal SQLite
16. Le backend place le résultat final dans le suivi
17. Le frontend affiche SQL, synthèse, tableau et statut
```

### 7.2 Étapes de suivi exposées au frontend

| Clé | Libellé | Description |
|---|---|---|
| `generate_sql` | Génération SQL | Transformation de la question en requête Oracle |
| `connect_oracle` | Connexion Oracle | Acquisition d’une connexion depuis le pool |
| `execute_sql` | Exécution | Lecture des données d’audit |
| `build_synthesis` | Traduction | Transformation des résultats en résumé clair |
| `finalize` | Finalisation | Mise en forme et journalisation de la réponse |

Chaque étape possède un statut, une durée et un résumé courant.

### 7.3 Mode synchrone

`POST /api/query` exécute le même pipeline dans la requête HTTP et retourne directement le résultat final. Ce mode est utile pour des tests techniques, mais le mode suivi est préférable dans l’interface, car les modèles locaux peuvent prendre du temps sur CPU.

---

## 8. Backend FastAPI

### 8.1 Application

L’application est déclarée dans `backend/app/main.py` :

```python
app = FastAPI(title="SMART2D Backend API", version="0.1.0")
```

Le titre interne historique n’a pas d’incidence sur le nom affiché **Audit AI**. Il peut être renommé si la documentation Swagger doit porter le nouveau nom.

### 8.2 CORS

Les origines autorisées sont lues depuis `settings.cors_origins`.

Le middleware autorise :

- les credentials ;
- toutes les méthodes ;
- tous les headers ;
- uniquement les origines configurées.

En production, la liste des origines doit contenir uniquement l’URL réelle du frontend.

### 8.3 Modèles Pydantic

`backend/app/schemas.py` définit les contrats de données. Les principaux objets sont :

- `LoginRequest`, `LoginResponse`, `AuthUser` ;
- `QueryRequest`, `QueryResponse` ;
- `QueryStartResponse`, `QueryProgressResponse`, `QueryProgressStep` ;
- `MetadataResponse`, `HealthResponse` ;
- `RuntimeSettings` ;
- `UserCreateRequest`, `UserStatusUpdateRequest`, `AdminUser` ;
- `AuditLogEntry`.

Les validations de longueur et de type sont appliquées avant l’entrée dans les fonctions de route.

### 8.4 Gestion des erreurs

Trois catégories doivent être distinguées :

1. **Erreur HTTP de contrôle** : token absent, rôle insuffisant, utilisateur introuvable, concurrence dépassée ; le backend retourne un code 4xx.
2. **Erreur Oracle pendant une analyse** : l’exécution retourne une liste vide et un champ `error` dans `QueryResponse`. La réponse HTTP peut rester en 200 afin que l’interface affiche une explication.
3. **Erreur non gérée du pipeline** : l’analyse suivie passe au statut `error` ; le mode synchrone peut retourner une erreur serveur.

---

## 9. Authentification, sessions et rôles

### 9.1 Stockage

Le service `auth_service.py` utilise SQLite. La base courante est généralement :

```text
backend_auth.sqlite3
```

Elle contient au minimum :

- les utilisateurs ;
- le hash du mot de passe ;
- le sel individuel ;
- le rôle administrateur ;
- l’état actif/suspendu ;
- les sessions et leurs jetons ;
- les dates de création et mise à jour.

### 9.2 Hash des mots de passe

Les mots de passe ne sont pas stockés en clair dans SQLite. Le service utilise :

```python
hashlib.pbkdf2_hmac(...)
```

avec un sel propre à chaque utilisateur.

### 9.3 Jeton de session

Après une authentification réussie :

1. `authenticate_user()` vérifie l’utilisateur et le mot de passe ;
2. `create_session()` crée un jeton ;
3. le frontend stocke ce jeton localement ;
4. chaque requête protégée envoie :

```http
X-Auth-Token: <token>
```

Le backend valide le jeton avec `get_user_by_token()`.

### 9.4 Réponses d’authentification

- Header absent : HTTP 401, `Token manquant`.
- Jeton invalide ou expiré : HTTP 401, `Session invalide ou expiree`.
- Utilisateur non administrateur sur une route admin : HTTP 403, `Acces reserve administrateur`.

### 9.5 Compte administrateur initial

Le service contient des constantes de compte administrateur par défaut :

```text
_DEFAULT_ADMIN_USERNAME
_DEFAULT_ADMIN_PASSWORD
```

`init_auth_db()` crée ce compte s’il n’existe pas et `ensure_default_admin_access()` peut rétablir son accès lors d’une connexion avec les identifiants par défaut.

**Avant toute exposition réseau**, remplacer ces valeurs, supprimer ce mécanisme de restauration ou créer un administrateur propre puis désactiver le compte initial.

### 9.6 Déconnexion

`POST /api/auth/logout` révoque la session reçue dans `X-Auth-Token`. Le frontend doit ensuite supprimer le jeton local.

---

## 10. Gestion des utilisateurs et journal applicatif

### 10.1 Utilisateurs

Les routes administrateur permettent :

- lister les utilisateurs ;
- créer un utilisateur ;
- choisir son rôle administrateur ou simple ;
- suspendre ou réactiver un compte ;
- supprimer un compte.

Protections existantes :

- mot de passe d’un nouvel utilisateur : au moins 6 caractères dans le service actuel ;
- impossibilité pour un administrateur de suspendre son propre compte ;
- impossibilité pour un administrateur de supprimer son propre compte.

### 10.2 Journal applicatif

Le fichier courant est généralement :

```text
backend_audit.sqlite3
```

Il ne s’agit pas du journal Oracle. Il enregistre les actions effectuées **dans Audit AI**, par exemple :

- connexion réussie ou refusée ;
- déconnexion ;
- création, suspension ou suppression d’un utilisateur ;
- mise à jour de paramètres ;
- exécution d’une question ;
- statut, SQL produit, nombre de lignes et erreur éventuelle.

Les administrateurs consultent ces entrées via :

```http
GET /api/admin/audit-logs?limit=300
```

La limite admise est comprise entre 1 et 2000.

---

## 11. Service NLP TinyLlama + LoRA

Le service est implémenté dans :

```text
backend/app/services/nlp_service.py
```

### 11.1 Chargement

Le chargement se fait une seule fois par processus grâce à des variables globales :

```text
_TOKENIZER
_MODEL
_DEVICE
_MODEL_ERROR
```

Séquence réelle :

```python
_TOKENIZER = AutoTokenizer.from_pretrained(settings.model_dir)
base = AutoModelForCausalLM.from_pretrained(settings.model_dir)
_MODEL = PeftModel.from_pretrained(base, settings.lora_dir)
_MODEL.eval()
_MODEL.to(torch.device("cpu"))
```

Le modèle de base et le LoRA restent séparés. Le LoRA est appliqué au modèle de base au chargement ; aucun fichier fusionné n’est requis.

### 11.2 Dossiers attendus

Modèle de base :

```text
TinyLlama-1.1B-Chat-v1.0/
```

Adaptateur spécialisé :

```text
tinyllama_oracle_lora/
```

Fichiers minimaux indispensables dans le LoRA :

```text
adapter_config.json
adapter_model.safetensors
```

Le tokenizer est chargé depuis le modèle de base, pas depuis le dossier LoRA.

### 11.3 Appareil de calcul

La version actuelle force :

```python
torch.device("cpu")
```

Le déploiement n’exige donc pas de GPU. L’inférence peut néanmoins être lente selon le processeur.

### 11.4 Cache d’erreur du modèle

Si le chargement échoue, le message est mémorisé dans `_MODEL_ERROR`. Corriger un chemin ou un fichier pendant que le processus tourne ne suffit pas : **le backend doit être redémarré** pour retenter le chargement.

### 11.5 Prompt système

Le prompt présente au modèle une table logique stable :

```text
ORACLE_AUDIT_TRAIL
```

Il décrit les colonnes réelles :

```text
ID
AUDIT_TYPE
SESSIONID
OS_USERNAME
USERHOST
TERMINAL
AUTHENTICATION_TYPE
DBUSERNAME
CLIENT_PROGRAM_NAME
OBJECT_SCHEMA
OBJECT_NAME
SQL_TEXT
SQL_BINDS
EVENT_TIMESTAMP
ACTION_NAME
INSTANCE
```

Principales règles enseignées :

- une seule table logique ;
- ne jamais utiliser `DBA_USERS`, `ALL_USERS`, `USER_USERS` ou une autre vue ;
- utiliser `DBUSERNAME` pour l’utilisateur Oracle ;
- connexions = `ACTION_NAME='LOGON'` ;
- déconnexions = `ACTION_NAME='LOGOFF'` ;
- heures = `SYSDATE-N/24` ;
- jours = `SYSDATE-N` ;
- minutes = `SYSDATE-N/1440` ;
- machine ou poste = `USERHOST` ;
- tri temporel = `ORDER BY EVENT_TIMESTAMP DESC` ;
- réponse SQL uniquement ;
- intention de lecture uniquement.

### 11.6 Alignement entraînement / backend

Le prompt utilisé dans le notebook d’entraînement et celui de `_system_prompt()` doivent rester cohérents.

Une nouvelle version de LoRA peut produire de moins bons résultats si elle a été entraînée avec :

- une autre liste de colonnes ;
- un autre nom de table logique ;
- d’autres balises de conversation ;
- des règles différentes ;
- un autre modèle de base.

Pour le LoRA V15, conserver avec la livraison le fichier `auditai_system_prompt_v15.txt`. Lors du remplacement, comparer ce fichier à `_system_prompt()` et aligner le backend si nécessaire.

### 11.7 Format du prompt d’inférence

Le service construit actuellement :

```text
<|system|>{prompt système}<|end|>
<|user|>{question}<|end|>
<|assistant|>
```

Le tokenizer applique :

- `return_tensors="pt"` ;
- `truncation=True` ;
- `max_length=1024`.

La génération applique :

- `do_sample=False` : génération déterministe ;
- `max_new_tokens=settings.max_sql_tokens` ;
- token de padding = token de fin.

---

## 12. Construction et nettoyage du SQL

### 12.1 Sortie brute

Le modèle peut retourner du SQL avec des balises Markdown ou un préfixe. `_clean_sql()` :

- retire les balises de blocs de code Markdown ;
- retire les préfixes `SQL:`, `Requête:` ou `Réponse:` ;
- recherche le premier mot-clé SQL connu ;
- coupe la sortie au premier point-virgule ;
- remplace la table logique ;
- ajoute éventuellement une limite de lignes.

### 12.2 Remplacement de la table logique

Le modèle génère :

```sql
SELECT ... FROM ORACLE_AUDIT_TRAIL
```

Le backend remplace automatiquement cet alias par la valeur runtime de :

```python
get_oracle_table()
```

Exemple final :

```sql
SELECT ... FROM SMART2DSECU.UNIFIED_AUDIT_DATA
```

Cette stratégie permet de changer la table physique sans réentraîner le LoRA, à condition que son schéma reste compatible.

### 12.3 Limite automatique

Si le SQL :

- commence par `SELECT` ou `WITH` ;
- ne contient pas déjà `FETCH FIRST` ;
- ne contient pas `COUNT(` ;
- ne contient pas `GROUP BY` ;

le service ajoute :

```sql
FETCH FIRST <max_results> ROWS ONLY
```

La limite vient de `get_fetch_limit()`.

### 12.4 Point de sécurité critique

La fonction actuelle :

```python
validate_sql_guardrails(sql)
```

retourne toujours :

```python
True, "OK"
```

et le pipeline stable ne l’appelle pas avant l’exécution. Les règles `SELECT uniquement` sont donc principalement portées par le prompt et le LoRA, pas par une barrière d’exécution fiable.

En conséquence :

- le compte Oracle d’Audit AI doit être strictement **lecture seule** ;
- il ne doit posséder aucun droit DDL ou DML ;
- un validateur SQL réel doit être ajouté avant une mise en production sensible.

Voir [Sécurité et durcissement obligatoire](#31-sécurité-et-durcissement-obligatoire).

---

## 13. Service Oracle

Le service est implémenté dans :

```text
backend/app/services/oracle_service.py
```

### 13.1 Pilote

Le backend utilise le package Python :

```text
oracledb
```

Le code fonctionne en mode thin lorsque le package le permet, sans exiger systématiquement Oracle Instant Client. Les contraintes du serveur Oracle ou du chiffrement peuvent toutefois imposer le mode thick dans certains environnements.

### 13.2 Configuration de connexion

La configuration runtime contient :

```text
oracle_user
oracle_password
oracle_host
oracle_port
oracle_service
oracle_table
```

Le DSN construit est :

```text
host:port/service
```

### 13.3 Pool de connexions

Le pool est global et créé à la première utilisation :

```python
oracledb.create_pool(
    user=user,
    password=password,
    dsn=dsn,
    min=max(1, settings.oracle_pool_min),
    max=max(2, settings.oracle_pool_max),
    increment=max(1, settings.oracle_pool_increment),
)
```

Le service conserve également le tuple de configuration actif. Si l’utilisateur administrateur change la connexion Oracle, le prochain accès détecte le changement, ferme l’ancien pool et en crée un nouveau.

### 13.4 Cycle d’une exécution

```text
execute_sql(sql)
    │
    ├── get_connection()
    │     └── pool.acquire()
    ├── conn.cursor()
    ├── cur.execute(sql sans ; final)
    ├── lecture de cur.description
    ├── noms de colonnes en majuscules
    ├── cur.fetchall()
    ├── conversion en list[dict]
    ├── fermeture curseur
    └── restitution de la connexion au pool
```

Exemple de résultat Python :

```python
[
    {
        "DBUSERNAME": "SYSTEM",
        "ACTION_NAME": "LOGON",
        "OBJECT_NAME": None,
        "EVENT_TIMESTAMP": "..."
    }
]
```

### 13.5 Gestion des erreurs

`execute_sql()` ne lève pas l’erreur Oracle vers la route dans le flux normal. Il retourne :

```python
([], "message ORA-...")
```

Le pipeline transmet ensuite ce message au service de synthèse et au journal applicatif.

### 13.6 État Oracle

`oracle_status()` tente d’acquérir une connexion et retourne :

```text
connected
```

ou :

```text
disconnected
```

---

## 14. Métadonnées d’aide de l’interface

### 14.1 Objectif

La route `/api/metadata` alimente les colonnes d’aide. Dans l’implémentation backend actuelle, elle retourne dynamiquement :

- les utilisateurs Oracle observés dans `DBUSERNAME` ;
- les objets observés dans `OBJECT_NAME` ;
- l’état de la connexion Oracle.

La liste des actions affichée par l’interface n’est pas retournée par cette version de `fetch_metadata()` ; elle est gérée séparément côté interface ou par la configuration du frontend.

### 14.2 Requêtes utilisées

Utilisateurs :

```sql
SELECT DBUSERNAME, COUNT(*) AS ACTIONS
FROM <oracle_table>
WHERE <filtres d’affichage utilisateurs>
GROUP BY DBUSERNAME
ORDER BY ACTIONS DESC
FETCH FIRST 500 ROWS ONLY
```

Objets :

```sql
SELECT OBJECT_NAME, COUNT(*) AS ACTIONS
FROM <oracle_table>
WHERE <filtres d’affichage objets>
GROUP BY OBJECT_NAME
ORDER BY ACTIONS DESC
FETCH FIRST 500 ROWS ONLY
```

### 14.3 Filtres d’affichage

Les ensembles `HIDDEN_USERS_EXACT`, `HIDDEN_OBJECTS_EXACT` et `HIDDEN_OBJECTS_LIKE` masquent certains comptes ou objets techniques dans les colonnes d’aide.

Ces filtres :

- servent uniquement à nettoyer l’affichage ;
- ne doivent jamais être injectés dans le SQL généré pour une vraie question ;
- n’empêchent pas l’utilisateur d’interroger explicitement un élément masqué.

Les nouveaux utilisateurs et objets apparaissent automatiquement s’ils sont présents dans la table d’audit et ne correspondent pas aux règles de masquage.

### 14.4 Cache de métadonnées

Les métadonnées sont conservées en mémoire pendant :

```text
300 secondes
```

La première requête interroge Oracle. Les suivantes utilisent le cache jusqu’à expiration.

Après création d’une nouvelle table ou apparition d’un nouvel utilisateur dans la source d’audit, l’interface peut donc attendre jusqu’à cinq minutes avant de l’afficher, sauf redémarrage ou appel explicite à `clear_metadata_cache()`.

### 14.5 Erreur de connexion

En cas d’échec Oracle :

- le backend écrit `[METADATA_ERROR] ...` dans les logs ;
- retourne des listes vides ;
- indique `db_status="disconnected"` ;
- conserve ce résultat dans le cache de métadonnées pour sa durée de vie.

---

## 15. Service de synthèse Phi-3

Le service est implémenté dans :

```text
backend/app/services/synthesis_service.py
```

### 15.1 Rôle

Il reçoit :

```python
build_synthesis(question, rows, error)
```

et produit une réponse française destinée à l’utilisateur.

Il n’exécute pas de SQL et ne décide pas quelles lignes Oracle doivent être récupérées. Il reformule uniquement le résultat déjà obtenu.

### 15.2 Modèle

Le fichier attendu est un modèle GGUF local, par exemple :

```text
phi3-mini-gguf/Phi-3-mini-4k-instruct-q4.gguf
```

Le chargement est réalisé avec `llama-cpp-python` dans la conception actuelle.

### 15.3 Cas traités

Le service doit produire une réponse pour :

- une ou plusieurs lignes Oracle ;
- aucun résultat ;
- une erreur Oracle ;
- une indisponibilité du modèle Phi-3, avec une synthèse de secours si prévue par le service.

### 15.4 Taille du fichier

Le nom `q4` ne garantit pas à lui seul que le fichier est correctement quantifié. Le fichier actuellement manipulé peut atteindre environ 2,2 Go. Vérifier l’espace disque et la taille réelle avant la copie.

### 15.5 État du modèle

`phi3_status()` est appelé au démarrage et par `/api/health`. Une erreur de chemin ou un fichier incomplet doit être corrigé puis le backend redémarré.

---

## 16. Historique, suivi, cache et concurrence

Quatre mécanismes distincts existent. Ils ne doivent pas être confondus.

### 16.1 Historique récent en mémoire

`QUERY_HISTORY` conserve les dernières analyses du processus FastAPI :

- maximum global : 200 entrées ;
- `/api/history` filtre par nom d’utilisateur ;
- maximum retourné : 100 entrées ;
- contenu perdu au redémarrage.

Il s’agit de l’historique affiché à l’utilisateur, pas du journal persistant administrateur.

### 16.2 Journal applicatif persistant

`backend_audit.sqlite3` conserve durablement les opérations écrites par `write_audit_log()`. Ce journal survit au redémarrage et est destiné à l’administrateur.

### 16.3 Suivi des analyses

`_QUERY_PROGRESS` est un dictionnaire en mémoire indexé par `request_id`.

Chaque suivi contient :

- utilisateur propriétaire ;
- question ;
- état global ;
- étape courante ;
- étapes et durées ;
- résultat final ;
- erreur ;
- heure de départ.

Conséquences :

- le suivi disparaît au redémarrage ;
- il n’est pas partagé entre plusieurs workers ;
- un utilisateur ne peut pas lire le suivi d’un autre ;
- un identifiant inconnu renvoie HTTP 404 `Suivi introuvable`.

### 16.4 Limitation de concurrence

`_ACTIVE_USER_QUERIES` compte les analyses en cours par utilisateur. La limite est :

```text
settings.max_concurrent_queries_per_user
```

Si elle est atteinte :

```http
HTTP 429
Une autre analyse est deja en cours pour cet utilisateur
```

Le créneau est libéré dans un bloc `finally`, même en cas d’erreur.

### 16.5 Cache de réponses

Le backend conserve les réponses complètes en mémoire :

- clé : MD5 de la question mise en minuscules et nettoyée ;
- TTL : 3600 secondes ;
- taille cible maximale approximative : 256 Mo ;
- si la limite est dépassée, suppression de la moitié la plus ancienne.

Un cache hit évite TinyLlama, Oracle et Phi-3.

### 16.6 Limite importante du cache actuel

La clé ne contient actuellement que la question. Elle ne contient pas :

- l’utilisateur ;
- la configuration Oracle ;
- la table ;
- la version du LoRA ;
- la date ou l’heure ;
- un identifiant de version des données.

Ainsi, une question relative comme « aujourd’hui » peut retourner pendant une heure une réponse devenue ancienne. Une réponse calculée avant un changement de modèle peut aussi être réutilisée après ce changement tant que le processus n’a pas été redémarré.

Pour un usage d’audit strict, désactiver ce cache ou enrichir sa clé avec la configuration, la version du modèle et une fenêtre temporelle adaptée.

---

## 17. Paramètres d’exécution

### 17.1 Sources de configuration

Le projet utilise deux niveaux :

1. configuration initiale dans `backend/app/config.py` et variables d’environnement ;
2. paramètres runtime gérés par `settings_service.py`, généralement persistés dans :

```text
backend_runtime_settings.json
```

### 17.2 Paramètres principaux

Les champs importants comprennent :

```text
oracle_user
oracle_password
oracle_host
oracle_port
oracle_service
oracle_table
interface_lang
max_results
session_duration
logs_retention
```

La configuration statique expose également notamment :

```text
model_dir
lora_dir
phi3_path
max_sql_tokens
oracle_pool_min
oracle_pool_max
oracle_pool_increment
max_concurrent_queries_per_user
cors_origins
```

### 17.3 Mise à jour via l’API

`POST /api/settings` persiste les paramètres.

Un utilisateur simple peut modifier les champs non sensibles, mais le backend réinjecte les valeurs Oracle courantes pour empêcher qu’il ne remplace :

```text
oracle_user
oracle_password
oracle_host
oracle_port
oracle_service
oracle_table
```

### 17.4 Point de confidentialité

Dans le snapshot backend stable, `GET /api/settings` retourne le modèle `RuntimeSettings` complet à tout utilisateur authentifié. Même si l’interface masque les champs Oracle pour les utilisateurs simples, une protection backend supplémentaire doit masquer le mot de passe et les paramètres sensibles dans la réponse non-administrateur.

### 17.5 Effet d’un changement Oracle

Le pool Oracle se recrée automatiquement quand le tuple de connexion change. Le cache de métadonnées, lui, peut rester valable jusqu’à cinq minutes. Le cache de réponses peut rester valable jusqu’à une heure. Pour un changement d’environnement propre :

1. arrêter le backend ;
2. modifier la configuration ;
3. redémarrer ;
4. tester `/api/health` ;
5. tester `/api/metadata` ;
6. exécuter une question de validation.

---

## 18. Frontend Next.js

### 18.1 Stack

Le frontend utilise :

- Next.js avec App Router ;
- React ;
- TypeScript ;
- Tailwind CSS ;
- composants UI basés sur Radix/shadcn selon les fichiers présents ;
- `lucide-react` pour les icônes.

### 18.2 Authentification côté navigateur

`auth-context.tsx` :

1. envoie les identifiants à `/api/auth/login` ;
2. stocke le token dans le stockage local du navigateur ;
3. ajoute `X-Auth-Token` aux appels API ;
4. appelle `/api/auth/me` pour restaurer la session ;
5. efface la session et redirige vers la connexion en cas de 401.

Le token n’est pas un cookie HttpOnly dans la version actuelle.

### 18.3 AppShell

`app-shell.tsx` centralise les données communes au dashboard :

- santé des services ;
- métadonnées ;
- historique ;
- paramètres ;
- rafraîchissements après certaines actions.

### 18.4 Tableau de bord

Le tableau de bord :

1. lit la question ;
2. appelle `/api/query/start` ;
3. conserve le `request_id` ;
4. poll `/api/query/progress/{request_id}` ;
5. met à jour les étapes visuelles ;
6. affiche le SQL, la synthèse et les lignes ;
7. recharge l’historique si nécessaire.

### 18.5 Administration

La page admin utilise les routes `/api/admin/*`. Le contrôle visuel du frontend ne remplace pas le contrôle `get_admin_user()` du backend.

### 18.6 Langue

L’interface livrée est fixée à l’usage français. `i18n.ts` peut encore contenir des dictionnaires ou mécanismes historiques, mais l’option anglaise est masquée dans l’interface tant que le modèle n’est pas validé pour répondre en anglais.

### 18.7 URL du backend

Vérifier `frontend/lib/api.ts` et les variables Next.js éventuelles pour confirmer l’URL API. En développement, la cible attendue est généralement :

```text
http://127.0.0.1:8000
```

En production, utiliser une variable publique ou un reverse proxy ; ne pas laisser une URL locale codée en dur si le frontend est servi depuis une autre machine.

---

## 19. Contrat API

Toutes les routes ci-dessous, sauf la connexion, utilisent `X-Auth-Token` lorsqu’elles sont protégées.

### 19.1 Authentification

| Méthode | Route | Accès | Fonction |
|---|---|---|---|
| POST | `/api/auth/login` | Public | Authentifie et retourne token + utilisateur |
| GET | `/api/auth/me` | Authentifié | Retourne l’utilisateur courant |
| POST | `/api/auth/logout` | Token facultatif | Révoque la session |

Exemple de connexion PowerShell :

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/auth/login" `
  -ContentType "application/json" `
  -Body '{"username":"<ADMIN>","password":"<MOT_DE_PASSE>"}'

$token = $login.token
$headers = @{ "X-Auth-Token" = $token }
```

### 19.2 Santé et données communes

| Méthode | Route | Accès | Fonction |
|---|---|---|---|
| GET | `/api/health` | Authentifié | États Oracle, TinyLlama et Phi-3 |
| GET | `/api/metadata` | Authentifié | Utilisateurs, objets et statut Oracle |
| GET | `/api/history` | Authentifié | 100 dernières entrées mémoire de l’utilisateur |
| GET | `/api/settings` | Authentifié | Paramètres runtime |
| POST | `/api/settings` | Authentifié | Met à jour les paramètres autorisés |

Exemple :

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8000/api/health" `
  -Headers $headers
```

Réponse attendue :

```json
{
  "status": "ok",
  "oracle": "connected",
  "tinyllama": "loaded",
  "phi3": "loaded"
}
```

### 19.3 Question synchrone

```http
POST /api/query
```

Payload :

```json
{
  "question": "Quelle est la dernière action effectuée par SYSTEM ?"
}
```

Réponse :

```json
{
  "question": "...",
  "sql": "SELECT ...;",
  "synthesis": "...",
  "rows": [],
  "row_count": 0,
  "blocked": false,
  "error": null
}
```

### 19.4 Question suivie

Démarrage :

```http
POST /api/query/start
```

Réponse :

```json
{
  "request_id": "..."
}
```

Suivi :

```http
GET /api/query/progress/{request_id}
```

Réponse simplifiée :

```json
{
  "request_id": "...",
  "status": "running",
  "current_step": "execute_sql",
  "current_summary": "Execution de la requete sur les donnees d audit",
  "elapsed_seconds": 4.7,
  "steps": [],
  "result": null,
  "error": null
}
```

Quand `status` vaut `completed`, `result` contient le `QueryResponse` final.

### 19.5 Administration

| Méthode | Route | Fonction |
|---|---|---|
| GET | `/api/admin/users` | Liste des utilisateurs |
| POST | `/api/admin/users` | Création d’un utilisateur |
| PATCH | `/api/admin/users/{user_id}/status` | Activation ou suspension |
| DELETE | `/api/admin/users/{user_id}` | Suppression |
| GET | `/api/admin/audit-logs?limit=300` | Journal applicatif |

Création :

```json
{
  "username": "auditeur1",
  "password": "mot_de_passe_solide",
  "is_admin": false
}
```

Changement de statut :

```json
{
  "is_active": false
}
```

### 19.6 Documentation automatique

Une fois le backend lancé :

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/redoc
```

Ces pages reflètent les schémas Pydantic réellement présents dans la version livrée.

---

## 20. Prérequis techniques

### 20.1 Logiciels

- Windows 10/11 ou Linux 64 bits ;
- Python 3.11 recommandé ;
- Node.js 20 ou version compatible avec le `package.json` ;
- npm ;
- accès réseau au serveur Oracle ;
- espace disque suffisant pour les modèles et les dépendances ;
- mémoire suffisante pour charger TinyLlama, LoRA, Phi-3, Python et Next.js.

### 20.2 Ressources conseillées

Pour un fonctionnement CPU local :

- 16 Go de RAM minimum pratique ;
- 24 à 32 Go recommandés pour plus de marge ;
- plusieurs cœurs CPU ;
- au moins 10 Go libres avant installation, davantage pour les caches et environnements ;
- disque SSD recommandé.

Les tailles réelles doivent être vérifiées dans le dossier livré. TinyLlama et Phi-3 peuvent représenter plusieurs gigaoctets.

### 20.3 Réseau

Le serveur backend doit pouvoir joindre :

```text
<ORACLE_HOST>:<ORACLE_PORT>
```

Le navigateur doit pouvoir joindre le frontend et le frontend doit pouvoir appeler le backend ou son reverse proxy.

---

## 21. Configuration de l’environnement

Créer un fichier `.env` local à partir de `.env.example`. Ne jamais mettre le `.env` réel dans le ZIP envoyé par mail ou dans un dépôt public.

Exemple :

```dotenv
# Oracle
ORACLE_USER=AUDIT_AI_READONLY
ORACLE_PASSWORD=CHANGE_ME
ORACLE_HOST=127.0.0.1
ORACLE_PORT=1521
ORACLE_SERVICE=ORCLPDB1
ORACLE_TABLE=SMART2DSECU.UNIFIED_AUDIT_DATA

# Modèles — chemins absolus recommandés sur Windows
MODEL_DIR=C:/AuditAI/TinyLlama-1.1B-Chat-v1.0
LORA_DIR=C:/AuditAI/tinyllama_oracle_lora
PHI3_PATH=C:/AuditAI/phi3-mini-gguf/Phi-3-mini-4k-instruct-q4.gguf

# API et performances
BACKEND_CORS_ORIGINS=http://localhost:3000
MAX_CONCURRENT_QUERIES_PER_USER=1
MAX_SQL_TOKENS=256
ORACLE_POOL_MIN=1
ORACLE_POOL_MAX=5
ORACLE_POOL_INCREMENT=1
```

### 21.1 Chemins Windows

Utiliser :

```text
C:/AuditAI/...
```

ou des doubles antislashs dans les contextes où ils sont nécessaires. Les chemins absolus évitent les erreurs liées au répertoire depuis lequel Uvicorn est lancé.

### 21.2 Paramètres runtime existants

Si `backend_runtime_settings.json` est livré, il peut écraser certaines valeurs initiales du `.env`. Avant le premier démarrage :

- ouvrir ce fichier ;
- supprimer tout mot de passe réel ;
- vérifier les chemins ;
- ou le supprimer pour repartir des valeurs de configuration par défaut si le service le recrée.

---

## 22. Installation

### 22.1 Backend sous Windows PowerShell

Depuis la racine du projet :

```powershell
cd C:\AuditAI
python -m venv venv_nlp
.\venv_nlp\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r .\backend\requirements.txt
```

Si PowerShell bloque l’activation :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv_nlp\Scripts\Activate.ps1
```

### 22.2 Backend sous Linux

```bash
cd /opt/auditai
python3.11 -m venv venv_nlp
source venv_nlp/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 22.3 Frontend

```powershell
cd C:\AuditAI\frontend
npm ci
```

Si aucun lockfile compatible n’est livré :

```powershell
npm install
```

### 22.4 `llama-cpp-python`

L’installation de `llama-cpp-python` peut nécessiter un wheel compatible ou des outils de compilation. Vérifier immédiatement après installation :

```powershell
python -c "from llama_cpp import Llama; print('llama-cpp-python OK')"
```

### 22.5 Pile TinyLlama

Vérifier :

```powershell
python -c "import torch, transformers, peft; print(torch.__version__, transformers.__version__, peft.__version__)"
```

### 22.6 Pilote Oracle

Vérifier :

```powershell
python -c "import oracledb; print(oracledb.__version__)"
```

---

## 23. Lancement en développement

### 23.1 Backend depuis la racine

```powershell
cd C:\AuditAI
.\venv_nlp\Scripts\Activate.ps1
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --workers 1
```

Pour rechargement automatique uniquement en développement :

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Le reloader redémarre le processus et recharge les modèles après chaque changement Python ; cela est coûteux.

### 23.2 Backend depuis `backend/`

```powershell
cd C:\AuditAI\backend
..\venv_nlp\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

### 23.3 Frontend

Dans un second terminal :

```powershell
cd C:\AuditAI\frontend
npm run dev
```

URL habituelle :

```text
http://localhost:3000
```

### 23.4 Vérification initiale

1. ouvrir le frontend ;
2. se connecter ;
3. consulter le statut des trois services ;
4. vérifier `/api/health` ;
5. vérifier que les métadonnées se chargent ;
6. exécuter une question simple.

---

## 24. Déploiement d’intégration ou de production

### 24.1 Principes

- utiliser un environnement virtuel propre ;
- construire le frontend ;
- lancer FastAPI avec un seul worker ;
- protéger le backend derrière un reverse proxy si exposé ;
- ne jamais livrer les secrets dans le code ou le ZIP ;
- faire tourner le service Oracle avec un compte lecture seule ;
- prévoir suffisamment d’espace pour les modèles.

### 24.2 Build frontend

```powershell
cd C:\AuditAI\frontend
npm ci
npm run build
npm run start
```

### 24.3 Backend sans reload

```powershell
cd C:\AuditAI
.\venv_nlp\Scripts\Activate.ps1
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --workers 1
```

### 24.4 Reverse proxy

Le reverse proxy doit :

- terminer HTTPS ;
- transmettre les appels `/api/` vers FastAPI ;
- servir ou rediriger le frontend ;
- conserver le header `X-Auth-Token` ;
- autoriser des délais suffisamment longs pour les appels d’analyse ;
- ne pas répartir les requêtes entre plusieurs processus backend dans la version actuelle.

### 24.5 Ordre de démarrage

1. Oracle accessible ;
2. backend ;
3. vérification des modèles et du pool ;
4. frontend ;
5. test d’acceptation.

### 24.6 Arrêt propre

Arrêter le frontend puis Uvicorn. Un `Ctrl+C` peut produire sous Windows un message natif `forrtl: error (200)` provenant d’une dépendance ; vérifier que le processus Uvicorn est réellement arrêté avant de redémarrer.

---

## 25. Mise à jour du LoRA

### 25.1 Le LoRA actuel peut être livré

Oui. Le dossier LoRA actuel peut être utilisé pour l’intégration initiale. L’intégrateur déploie toute l’architecture avec cette version, puis la nouvelle intelligence peut être installée plus tard sans modifier le frontend, Oracle ou SQLite.

### 25.2 Conditions de compatibilité

Le remplacement simple fonctionne si le nouveau LoRA :

- est entraîné sur le même modèle de base TinyLlama ;
- utilise une architecture PEFT compatible ;
- contient `adapter_config.json` et `adapter_model.safetensors` valides ;
- utilise le même contrat de prompt ou si le backend est aligné ;
- cible le même schéma logique Oracle.

### 25.3 Procédure exacte

1. Arrêter le backend.
2. Sauvegarder le dossier actuel :

```powershell
Rename-Item .\tinyllama_oracle_lora .\tinyllama_oracle_lora_backup
```

3. Copier le nouveau dossier sous le nom exact :

```text
tinyllama_oracle_lora
```

4. Vérifier :

```powershell
Test-Path .\tinyllama_oracle_lora\adapter_config.json
Test-Path .\tinyllama_oracle_lora\adapter_model.safetensors
```

5. Comparer `auditai_system_prompt_v15.txt` avec `_system_prompt()` dans `nlp_service.py`.
6. Mettre à jour le prompt backend seulement s’il diffère du prompt d’entraînement.
7. Redémarrer le backend.
8. Vérifier `/api/health` : `tinyllama="loaded"`.
9. Exécuter le jeu de tests de référence.
10. Conserver le LoRA précédent jusqu’à validation complète.

### 25.4 Aucun hot reload du modèle

Le modèle est mis en cache dans les variables globales Python. Remplacer les fichiers pendant que FastAPI tourne ne change pas le modèle déjà chargé. Le redémarrage est obligatoire.

### 25.5 Cache après remplacement

Le redémarrage vide le cache en mémoire. C’est souhaitable, car les réponses de l’ancien LoRA ne doivent pas être renvoyées par le nouveau déploiement.

---

## 26. Mise à jour de Phi-3

1. Arrêter le backend.
2. Sauvegarder le fichier GGUF actuel.
3. Copier le nouveau GGUF.
4. Conserver le même nom ou mettre à jour `PHI3_PATH`.
5. Vérifier que le fichier n’est pas partiel.
6. Redémarrer.
7. Vérifier `/api/health`.
8. Tester : résultat normal, zéro ligne et erreur Oracle.

Sur Windows, vérifier l’espace libre avant copie :

```powershell
Get-PSDrive C
Get-Item .\phi3-mini-gguf\*.gguf | Select-Object Name,Length
```

---

## 27. Configuration Oracle requise

### 27.1 Source principale

La configuration actuelle cible :

```text
SMART2DSECU.UNIFIED_AUDIT_DATA
```

Colonnes essentielles pour les questions courantes :

```text
DBUSERNAME
OBJECT_NAME
ACTION_NAME
EVENT_TIMESTAMP
```

Le prompt connaît également les autres colonnes citées dans la section NLP.

### 27.2 Privilèges minimaux

Créer un compte dédié, par exemple `AUDIT_AI_READONLY`, avec uniquement :

- droit de créer une session ;
- droit de lecture sur la table ou vue d’audit nécessaire.

Principe :

```sql
GRANT CREATE SESSION TO AUDIT_AI_READONLY;
GRANT SELECT ON SMART2DSECU.UNIFIED_AUDIT_DATA TO AUDIT_AI_READONLY;
```

Ne pas accorder :

- `INSERT`, `UPDATE`, `DELETE` ;
- création ou suppression d’objet ;
- privilèges DBA ;
- `SELECT ANY TABLE` si une autorisation ciblée suffit.

### 27.3 Vérification manuelle

Depuis le compte utilisé par Audit AI :

```sql
SELECT DBUSERNAME,
       OBJECT_NAME,
       ACTION_NAME,
       EVENT_TIMESTAMP
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
ORDER BY EVENT_TIMESTAMP DESC
FETCH FIRST 10 ROWS ONLY;
```

### 27.4 Dépendance à l’audit source

Audit AI ne peut pas afficher une action absente de la source.

Exemple diagnostiqué : si `VROMUALD` n’a que des événements `LOGON` dans `UNIFIED_AUDIT_TRAIL` et `SMART2DSECU.UNIFIED_AUDIT_DATA`, les opérations DDL/DML ne sont pas auditées à la source. Le problème ne vient ni du modèle ni de l’interface.

### 27.5 Diagnostic en deux niveaux

1. Vérifier la source Oracle native :

```sql
SELECT DBUSERNAME, OBJECT_SCHEMA, OBJECT_NAME, ACTION_NAME, EVENT_TIMESTAMP
FROM UNIFIED_AUDIT_TRAIL
WHERE UPPER(DBUSERNAME) = 'VROMUALD'
ORDER BY EVENT_TIMESTAMP DESC
FETCH FIRST 30 ROWS ONLY;
```

2. Vérifier la table alimentée pour Audit AI :

```sql
SELECT DBUSERNAME, OBJECT_NAME, ACTION_NAME, EVENT_TIMESTAMP
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE UPPER(DBUSERNAME) = 'VROMUALD'
ORDER BY EVENT_TIMESTAMP DESC
FETCH FIRST 30 ROWS ONLY;
```

Interprétation :

- absent des deux : politique d’audit Oracle à corriger ;
- présent dans `UNIFIED_AUDIT_TRAIL` mais absent de `UNIFIED_AUDIT_DATA` : alimentation ou rafraîchissement de la table à corriger ;
- présent dans la table mais absent de l’interface : connexion, cache, requête générée ou filtre d’affichage à examiner.

---

## 28. Tests de validation après intégration

### 28.1 Santé

Attendu :

```json
{
  "status": "ok",
  "oracle": "connected",
  "tinyllama": "loaded",
  "phi3": "loaded"
}
```

### 28.2 Authentification

- connexion valide ;
- mot de passe incorrect refusé ;
- utilisateur suspendu refusé ;
- déconnexion puis accès protégé refusé ;
- utilisateur simple refusé sur `/api/admin/users`.

### 28.3 Métadonnées

- utilisateurs visibles ;
- objets visibles ;
- `db_status=connected` ;
- nouveaux éléments visibles après expiration ou vidage du cache ;
- éléments masqués uniquement dans les aides, pas dans les requêtes réelles.

### 28.4 Questions NLP minimales

Tester au minimum :

```text
Quelle est la dernière action effectuée par SYSTEM ?
Quelles actions ont été effectuées par SYS aujourd’hui ?
Quelles actions concernent la table EMPLOYEES ?
Qui s’est connecté hier ?
Combien d’utilisateurs distincts apparaissent dans les données d’audit ?
```

Vérifications :

- `DBUSERNAME`, jamais `USERNAME` ;
- table physique correctement remappée ;
- SQL de lecture uniquement ;
- filtres utilisateur et objet corrects ;
- limite de lignes raisonnable ;
- synthèse cohérente avec les lignes.

### 28.5 Suivi

- `/api/query/start` retourne un identifiant ;
- les cinq étapes évoluent ;
- le résultat final apparaît ;
- un autre utilisateur ne peut pas lire le suivi ;
- aucune erreur `Suivi introuvable` sans redémarrage.

### 28.6 Administration

- création d’utilisateur ;
- suspension/réactivation ;
- suppression ;
- impossibilité de se supprimer ou de se suspendre soi-même ;
- actions visibles dans le journal applicatif.

### 28.7 Redémarrage

- SQLite conservée ;
- historique visuel mémoire réinitialisé ;
- cache vidé ;
- modèles rechargés ;
- sessions selon leur logique de persistance et d’expiration.

---

## 29. Sauvegarde et retour arrière

### 29.1 Éléments à sauvegarder

Avant toute mise à jour :

```text
tinyllama_oracle_lora/
phi3-mini-gguf/
backend_runtime_settings.json
backend_auth.sqlite3
backend_audit.sqlite3
.env local
version du code backend/frontend
```

### 29.2 Retour arrière LoRA

1. arrêter FastAPI ;
2. supprimer ou renommer le nouveau dossier ;
3. remettre la sauvegarde sous `tinyllama_oracle_lora` ;
4. remettre le prompt backend associé à cette version ;
5. redémarrer ;
6. relancer le benchmark court.

### 29.3 Bases SQLite

Copier les fichiers SQLite uniquement lorsque le backend est arrêté afin d’éviter une sauvegarde incohérente.

### 29.4 Paramètres

Versionner un fichier exemple sans secrets. Ne pas versionner le fichier runtime contenant un mot de passe réel.

---

## 30. Dépannage

### 30.1 `ORA-01017: invalid username/password; logon denied`

Causes :

- utilisateur ou mot de passe incorrect ;
- ancien mot de passe conservé dans `backend_runtime_settings.json` ;
- mauvais service Oracle ;
- compte verrouillé ou expiré.

Actions :

1. tester les identifiants avec Toad/SQL*Plus ;
2. vérifier `.env` et paramètres runtime ;
3. corriger via un administrateur ;
4. redémarrer le backend ;
5. vérifier `/api/health`.

### 30.2 `TinyLlama indisponible`

Vérifier :

```text
MODEL_DIR
LORA_DIR
model.safetensors
adapter_config.json
adapter_model.safetensors
```

Puis vérifier les imports `torch`, `transformers`, `peft`. Redémarrer obligatoirement après correction.

### 30.3 Phi-3 en erreur

- chemin `PHI3_PATH` incorrect ;
- GGUF incomplet ;
- disque plein pendant la copie ;
- `llama-cpp-python` incompatible ;
- mémoire insuffisante.

Comparer la taille du fichier source et destination.

### 30.4 `Suivi introuvable`

Causes :

- backend redémarré ;
- plusieurs workers ;
- mauvais `request_id` ;
- polling vers une autre instance ;
- suivi créé avant un reload de développement.

Correction : lancer un seul worker et recommencer la question.

### 30.5 HTTP 429

Une analyse est déjà en cours pour ce compte ou la limite de concurrence est atteinte. Attendre la fin ou vérifier qu’un thread n’est pas bloqué.

### 30.6 `ORA-00904: "USERNAME": invalid identifier`

Le modèle a utilisé une colonne inexistante. La colonne correcte du projet est :

```text
DBUSERNAME
```

Actions :

- vérifier le LoRA chargé ;
- vérifier l’alignement du prompt ;
- ajouter le cas au benchmark ;
- améliorer le dataset ;
- ne pas masquer l’erreur avec une réécriture métier rigide générale.

### 30.7 Aucun résultat pour un utilisateur connu

1. exécuter manuellement le SQL ;
2. vérifier `DBUSERNAME` exact ;
3. vérifier `UNIFIED_AUDIT_TRAIL` ;
4. vérifier `SMART2DSECU.UNIFIED_AUDIT_DATA` ;
5. vérifier la période ;
6. vérifier l’alimentation de la table ;
7. vérifier le cache de réponse.

### 30.8 Nouvelles tables non visibles dans l’aide

- l’objet doit exister dans `OBJECT_NAME` de la table d’audit ;
- attendre cinq minutes ;
- vérifier les règles `HIDDEN_OBJECTS_*` ;
- vider le cache ou redémarrer ;
- vérifier que la politique d’audit enregistre l’action.

### 30.9 Réponse ancienne pour « aujourd’hui »

Le cache de réponses a un TTL d’une heure et sa clé ne tient pas compte du temps. Redémarrer pour vider le cache ou corriger sa stratégie.

### 30.10 Frontend reçoit 401

- jeton absent du localStorage ;
- session expirée ;
- header non transmis par le reverse proxy ;
- backend ou SQLite réinitialisé.

Se reconnecter puis vérifier `X-Auth-Token` dans les outils réseau du navigateur.

### 30.11 CORS

Vérifier que l’origine exacte du frontend est présente dans `BACKEND_CORS_ORIGINS`, protocole et port compris.

### 30.12 Disque insuffisant

Les modèles font plusieurs gigaoctets. Supprimer les caches et builds, puis vérifier :

```powershell
Get-PSDrive
```

Ne pas copier un GGUF si l’espace disponible est inférieur à la taille du fichier plus une marge de sécurité.

---

## 31. Sécurité et durcissement obligatoire

Les points suivants doivent être traités avant une exposition à des utilisateurs de production.

### 31.1 Compte Oracle lecture seule

C’est la protection principale de la version actuelle. L’utilisateur Oracle ne doit posséder que les privilèges indispensables de lecture.

### 31.2 Validation SQL réelle

Implémenter une validation avant `execute_sql()` :

- retirer les commentaires ;
- accepter uniquement une instruction unique ;
- exiger `SELECT` ou éventuellement `WITH ... SELECT` ;
- refuser `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `REVOKE`, blocs PL/SQL et appels dangereux ;
- limiter la table aux sources autorisées ;
- utiliser un parseur SQL Oracle lorsque possible ;
- conserver le compte Oracle lecture seule même après ajout du validateur.

### 31.3 Paramètres sensibles

- masquer `oracle_password` dans toute réponse API ;
- réserver lecture et écriture des paramètres Oracle aux administrateurs ;
- ne pas écrire les secrets dans les logs ;
- ne pas livrer `.env` ni un JSON runtime non assaini.

### 31.4 Administrateur initial

- changer le compte et le mot de passe initiaux ;
- désactiver le mécanisme de restauration automatique ;
- imposer un mot de passe fort ;
- renouveler les sessions existantes.

### 31.5 Jetons navigateur

La version actuelle utilise le stockage local et un header personnalisé. Pour une exposition web sensible :

- préférer un cookie `HttpOnly`, `Secure`, `SameSite` ;
- mettre HTTPS ;
- appliquer une politique CSP ;
- réduire la durée des sessions ;
- prévoir rotation et révocation.

### 31.6 Cache inter-utilisateurs

Le cache actuel est indexé uniquement par la question. Pour éviter qu’une réponse soit partagée dans un contexte différent :

- inclure l’environnement Oracle et le périmètre d’accès dans la clé ;
- ou désactiver le cache ;
- ne jamais utiliser ce cache pour des utilisateurs ayant des droits de données différents.

### 31.7 CORS et réseau

- limiter CORS à l’URL officielle ;
- ne pas exposer le port Oracle au navigateur ;
- placer FastAPI derrière HTTPS ;
- filtrer les IP si l’application est interne ;
- ne pas publier `/docs` si la politique interne l’interdit.

### 31.8 Logs

- contrôler la rétention ;
- éviter de conserver des données d’audit sensibles inutilement ;
- restreindre l’accès au fichier SQLite ;
- sauvegarder et purger selon la politique de l’organisation.

---

## 32. Limites connues

1. Le suivi et l’historique utilisateur sont en mémoire ; ils disparaissent au redémarrage.
2. Le backend doit fonctionner avec un seul worker.
3. Le cache peut retourner une réponse ancienne pendant une heure.
4. Le cache n’est pas segmenté par utilisateur ou configuration.
5. Les garde-fous SQL ne sont pas actifs dans le snapshot stable.
6. Le mot de passe Oracle doit être davantage masqué côté API.
7. Les modèles tournent sur CPU et peuvent être lents.
8. La qualité SQL dépend du LoRA, du prompt et du dataset.
9. Les données disponibles dépendent entièrement de la politique d’audit Oracle et de l’alimentation de `UNIFIED_AUDIT_DATA`.
10. La route métadonnées retourne utilisateurs et objets, pas nécessairement une liste dynamique des actions.
11. Les filtres de colonnes d’aide sont définis dans le code et nécessitent une maintenance.
12. Le changement de modèle exige un redémarrage.
13. La version actuelle n’utilise pas de système distribué pour les jobs ou le cache.

---

## 33. Guide de maintenance par besoin

| Besoin | Fichier ou zone à modifier | Action |
|---|---|---|
| Changer la table Oracle | Paramètres runtime / `ORACLE_TABLE` | Garder le schéma compatible, redémarrer et tester |
| Changer les identifiants Oracle | `.env` ou Paramètres admin | Redémarrer recommandé |
| Changer le LoRA | `tinyllama_oracle_lora/` | Remplacer le dossier, aligner le prompt, redémarrer |
| Changer le modèle de base | `MODEL_DIR` + code si architecture différente | Vérifier la compatibilité du LoRA |
| Changer Phi-3 | `PHI3_PATH` | Remplacer GGUF, redémarrer |
| Modifier le prompt SQL | `services/nlp_service.py::_system_prompt()` | Garder identique au prompt d’entraînement |
| Modifier le nettoyage SQL | `services/nlp_service.py::_clean_sql()` | Ajouter tests de non-régression |
| Ajouter un validateur SQL | Avant `execute_sql()` dans le pipeline | Bloquer toute opération non-SELECT |
| Changer le pool Oracle | `config.py` / variables `ORACLE_POOL_*` | Redémarrer |
| Masquer un utilisateur de l’aide | `oracle_service.py::HIDDEN_USERS_EXACT` | N’affecte pas les vraies requêtes |
| Masquer un objet de l’aide | `HIDDEN_OBJECTS_EXACT/LIKE` | Vider cache ou redémarrer |
| Modifier le TTL métadonnées | `_METADATA_CACHE_TTL_SECONDS` | Redémarrer |
| Modifier le cache réponses | `main.py::_QUERY_CACHE_*` | Revoir clé et invalidation |
| Persister l’historique utilisateur | Remplacer `QUERY_HISTORY` par SQLite | Adapter `/api/history` |
| Persister les jobs | Remplacer `_QUERY_PROGRESS` par stockage partagé | Nécessaire pour multi-worker |
| Ajouter une route | `main.py` + `schemas.py` | Mettre à jour frontend/types/tests |
| Modifier les textes UI | `frontend/lib/i18n.ts` | Garder le français cohérent |
| Modifier l’URL backend | `frontend/lib/api.ts` / variable d’environnement | Rebuild frontend |
| Modifier les rôles | `auth_service.py`, dépendances FastAPI, frontend admin | Tester les contrôles backend |
| Modifier la durée de session | Settings/auth service | Révoquer les anciennes sessions si nécessaire |

---

## 34. Contenu du ZIP de livraison

### 34.1 Obligatoire

```text
backend/
frontend/
TinyLlama-1.1B-Chat-v1.0/
tinyllama_oracle_lora/
phi3-mini-gguf/
README.md
.env.example
backend/requirements.txt
frontend/package.json
frontend/package-lock.json ou autre lockfile présent
```

### 34.2 SQLite

Deux options sont possibles.

**Livraison avec comptes de démonstration :**

- conserver `backend_auth.sqlite3` ;
- assainir les comptes et mots de passe ;
- conserver ou vider `backend_audit.sqlite3` selon la confidentialité.

**Livraison vierge :**

- supprimer les deux fichiers ;
- laisser les fonctions d’initialisation les recréer ;
- documenter la procédure du premier administrateur.

### 34.3 Paramètres runtime

Livrer `backend_runtime_settings.json` uniquement s’il ne contient aucun secret réel. Sinon, livrer un modèle ou laisser l’application le recréer.

### 34.4 Vérification des modèles avant compression

```powershell
Get-Item .\TinyLlama-1.1B-Chat-v1.0\model.safetensors
Get-Item .\tinyllama_oracle_lora\adapter_config.json
Get-Item .\tinyllama_oracle_lora\adapter_model.safetensors
Get-Item .\phi3-mini-gguf\*.gguf
```

### 34.5 Vérification de l’absence de secrets

Rechercher avant le ZIP :

```powershell
Get-ChildItem -Recurse -File | Select-String -Pattern "ORACLE_PASSWORD|PASSWORD=|Admin@|BEGIN PRIVATE KEY" -ErrorAction SilentlyContinue
```

Examiner les résultats manuellement. Ne pas supprimer les noms de variables ou exemples légitimes ; supprimer uniquement les valeurs réelles.

### 34.6 Compression

Depuis le dossier parent :

```powershell
Compress-Archive `
  -Path .\AuditAI\* `
  -DestinationPath .\AuditAI_integration.zip `
  -CompressionLevel Optimal
```

Pour de très gros modèles, 7-Zip est généralement plus fiable que `Compress-Archive`.

---

## 35. Checklist finale d’intégration

### Dossier

- [ ] `README.md` à la racine
- [ ] backend complet
- [ ] frontend complet
- [ ] modèle TinyLlama complet
- [ ] LoRA complet
- [ ] Phi-3 GGUF complet
- [ ] aucun `node_modules`, `.next`, venv ou cache
- [ ] aucun secret réel

### Backend

- [ ] dépendances installées
- [ ] Uvicorn démarre avec un worker
- [ ] SQLite initialisée
- [ ] TinyLlama chargé
- [ ] LoRA chargé
- [ ] Phi-3 chargé
- [ ] `/api/health` correct

### Oracle

- [ ] réseau accessible
- [ ] identifiants valides
- [ ] compte strictement lecture seule
- [ ] table configurée accessible
- [ ] colonnes attendues présentes
- [ ] requête manuelle de contrôle réussie

### Frontend

- [ ] dépendances installées
- [ ] build réussi
- [ ] URL API correcte
- [ ] CORS correct
- [ ] connexion réussie
- [ ] session restaurée après actualisation

### Fonctionnel

- [ ] question suivie terminée
- [ ] SQL correct
- [ ] lignes Oracle affichées
- [ ] synthèse cohérente
- [ ] historique visible
- [ ] administration protégée
- [ ] journal applicatif alimenté

### Sécurité avant production

- [ ] compte administrateur initial remplacé
- [ ] mot de passe Oracle masqué côté API
- [ ] validateur SQL actif
- [ ] compte Oracle lecture seule
- [ ] HTTPS actif
- [ ] CORS restreint
- [ ] stratégie du cache revue
- [ ] politique de sauvegarde et rétention définie

---

**Le dossier peut être considéré comme correctement intégré lorsque les trois statuts de santé sont opérationnels, qu’une question complète traverse les cinq étapes, que le SQL est exécuté avec un compte Oracle lecture seule et que le test de remplacement/retour arrière du LoRA est documenté et reproductible.**


---

# Annexe — Déploiement natif sur Oracle Linux 7.9 et 8.x

> Cette annexe complète le README sans modifier l’architecture actuelle. Aucun Docker, Podman ou autre conteneur n’est utilisé. Le déploiement conserve FastAPI/Uvicorn, Next.js, les modèles locaux TinyLlama/LoRA et Phi-3, SQLite et la connexion Oracle.

## 1. Compatibilité

| Plateforme | Statut | Condition |
|---|---|---|
| Oracle Linux 8.x x86_64 | Recommandé | Python 3.11 et Node.js compatibles disponibles |
| Oracle Linux 7.9 x86_64 | Possible sous conditions | Python 3.11 et Node.js installés séparément sans remplacer les composants système |

Sur Oracle Linux 7.9, ne jamais remplacer `/usr/bin/python`, les bibliothèques système ou les outils utilisés par le système d’exploitation. Installer les runtimes applicatifs dans des chemins isolés, par exemple `/opt/python311` et `/opt/node20`.

## 2. Fichiers qui font foi

Avant l’installation, vérifier obligatoirement :

```text
backend/requirements.txt
frontend/package.json
frontend/package-lock.json, s’il existe
backend/app/config.py
frontend/lib/api.ts
```

Les versions exactes des bibliothèques Python et JavaScript sont déterminées par ces fichiers. Le README ne doit pas inventer de versions absentes de la livraison.

## 3. Précontrôle du serveur

```bash
cat /etc/os-release
uname -m
uname -r
nproc
free -h
df -h
getenforce
sudo firewall-cmd --state
```

Prévoir au minimum 16 Go de RAM et 12 Go libres après copie du projet ; 20 Go libres sont recommandés.

Tester l’accès Oracle :

```bash
nc -vz <ORACLE_HOST> <ORACLE_PORT>
```

## 4. Paquets système

### Oracle Linux 8

```bash
sudo dnf install -y \
  python3.11 python3.11-pip python3.11-devel \
  gcc gcc-c++ make cmake git curl jq unzip tar gzip \
  nginx nmap-ncat firewalld policycoreutils-python-utils
```

Installer ensuite une version Node.js compatible avec `frontend/package.json`, puis vérifier :

```bash
python3.11 --version
python3.11 -m pip --version
node --version
npm --version
```

### Oracle Linux 7.9

```bash
sudo yum install -y \
  gcc gcc-c++ make cmake git curl jq unzip tar gzip \
  nginx nmap-ncat firewalld policycoreutils-python
```

Python 3.11 et Node.js doivent être fournis par une source approuvée par l’organisation, dans des chemins isolés, par exemple :

```text
/opt/python311/bin/python3.11
/opt/node20/bin/node
/opt/node20/bin/npm
```

Vérifier avant de poursuivre :

```bash
/opt/python311/bin/python3.11 --version
/opt/python311/bin/python3.11 -m pip --version
/opt/node20/bin/node --version
/opt/node20/bin/npm --version
```

## 5. Installation du projet

```bash
sudo useradd --system --home-dir /opt/auditai --shell /sbin/nologin auditai 2>/dev/null || true
sudo mkdir -p /opt/auditai /etc/auditai /var/backups/auditai
sudo unzip -q /tmp/AuditAI_Integration_v1.zip -d /opt/auditai
sudo chown -R auditai:auditai /opt/auditai
sudo chmod 750 /opt/auditai
```

Vérifier la structure :

```bash
sudo -u auditai test -f /opt/auditai/backend/app/main.py
sudo -u auditai test -f /opt/auditai/backend/requirements.txt
sudo -u auditai test -f /opt/auditai/frontend/package.json
sudo -u auditai test -f /opt/auditai/TinyLlama-1.1B-Chat-v1.0/model.safetensors
sudo -u auditai test -f /opt/auditai/tinyllama_oracle_lora/adapter_config.json
sudo -u auditai test -f /opt/auditai/tinyllama_oracle_lora/adapter_model.safetensors
sudo -u auditai test -f /opt/auditai/phi3-mini-gguf/Phi-3-mini-4k-instruct-q4.gguf
```

## 6. Configuration

```bash
sudo tee /etc/auditai/auditai.env >/dev/null <<'AUDITAI_ENV'
ORACLE_USER=AUDIT_AI_READONLY
ORACLE_PASSWORD=CHANGE_ME
ORACLE_HOST=<ORACLE_HOST>
ORACLE_PORT=1521
ORACLE_SERVICE=<ORACLE_SERVICE>
ORACLE_TABLE=SMART2DSECU.UNIFIED_AUDIT_DATA
MODEL_DIR=/opt/auditai/TinyLlama-1.1B-Chat-v1.0
LORA_DIR=/opt/auditai/tinyllama_oracle_lora
PHI3_PATH=/opt/auditai/phi3-mini-gguf/Phi-3-mini-4k-instruct-q4.gguf
BACKEND_CORS_ORIGINS=https://<NOM_DNS_AUDITAI>
MAX_CONCURRENT_QUERIES_PER_USER=1
MAX_SQL_TOKENS=256
ORACLE_POOL_MIN=1
ORACLE_POOL_MAX=5
ORACLE_POOL_INCREMENT=1
PYTHONUNBUFFERED=1
TOKENIZERS_PARALLELISM=false
AUDITAI_ENV

sudo chown root:auditai /etc/auditai/auditai.env
sudo chmod 640 /etc/auditai/auditai.env
sudo rm -f /opt/auditai/backend_runtime_settings.json
```

## 7. Installation du backend

Oracle Linux 8 :

```bash
sudo -u auditai python3.11 -m venv /opt/auditai/venv_nlp
```

Oracle Linux 7.9 :

```bash
sudo -u auditai /opt/python311/bin/python3.11 -m venv /opt/auditai/venv_nlp
```

Puis, pour les deux systèmes :

```bash
sudo -u auditai /opt/auditai/venv_nlp/bin/python -m pip install --upgrade pip setuptools wheel
sudo -u auditai /opt/auditai/venv_nlp/bin/pip install --no-cache-dir -r /opt/auditai/backend/requirements.txt
sudo -u auditai /opt/auditai/venv_nlp/bin/pip check
```

Contrôle des imports :

```bash
sudo -u auditai /opt/auditai/venv_nlp/bin/python -c "import fastapi,uvicorn,torch,transformers,peft,oracledb; from llama_cpp import Llama; print('Imports backend OK')"
```

Un échec de `llama-cpp-python` doit être traité à partir de la version réellement épinglée dans `backend/requirements.txt`, du compilateur et du processeur du serveur.

## 8. Test Oracle

```bash
set -a
source /etc/auditai/auditai.env
set +a

sudo -E -u auditai /opt/auditai/venv_nlp/bin/python -c "import os,oracledb; dsn=f'{os.environ[\"ORACLE_HOST\"]}:{os.environ[\"ORACLE_PORT\"]}/{os.environ[\"ORACLE_SERVICE\"]}'; c=oracledb.connect(user=os.environ['ORACLE_USER'],password=os.environ['ORACLE_PASSWORD'],dsn=dsn); cur=c.cursor(); cur.execute('SELECT DBUSERNAME, OBJECT_NAME, ACTION_NAME, EVENT_TIMESTAMP FROM SMART2DSECU.UNIFIED_AUDIT_DATA ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST 1 ROWS ONLY'); print(cur.fetchone()); cur.close(); c.close()"
```

## 9. Installation du frontend

Vérifier l’URL API réellement utilisée :

```bash
grep -RInE '127\.0\.0\.1:8000|localhost:8000|http://[^\"]+:8000' \
  /opt/auditai/frontend/app \
  /opt/auditai/frontend/components \
  /opt/auditai/frontend/lib || true
```

Le navigateur doit utiliser une URL accessible, par exemple `/api` derrière Nginx. Le nom d’une variable Next.js éventuelle doit être lu dans `frontend/lib/api.ts`.

Oracle Linux 8 :

```bash
cd /opt/auditai/frontend
if [ -f package-lock.json ]; then sudo -u auditai npm ci; else sudo -u auditai npm install; fi
sudo -u auditai npm run build
```

Oracle Linux 7.9 avec Node.js dans `/opt/node20` :

```bash
cd /opt/auditai/frontend
sudo -u auditai env PATH=/opt/node20/bin:/usr/bin:/bin /opt/node20/bin/npm ci
sudo -u auditai env PATH=/opt/node20/bin:/usr/bin:/bin /opt/node20/bin/npm run build
```

Vérifier :

```bash
test -f /opt/auditai/frontend/.next/BUILD_ID
```

## 10. Service systemd du backend

```bash
sudo tee /etc/systemd/system/auditai-backend.service >/dev/null <<'BACKEND_SERVICE'
[Unit]
Description=Audit AI - Backend FastAPI
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=auditai
Group=auditai
WorkingDirectory=/opt/auditai
EnvironmentFile=/etc/auditai/auditai.env
ExecStart=/opt/auditai/venv_nlp/bin/python -m uvicorn app.main:app --app-dir /opt/auditai/backend --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=10
TimeoutStartSec=900
TimeoutStopSec=90
KillSignal=SIGINT
NoNewPrivileges=true
PrivateTmp=true
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
BACKEND_SERVICE
```

Un seul worker est obligatoire.

## 11. Service systemd du frontend

Vérifier d’abord :

```bash
command -v npm
```

Oracle Linux 8, exemple :

```bash
sudo tee /etc/systemd/system/auditai-frontend.service >/dev/null <<'FRONTEND_SERVICE'
[Unit]
Description=Audit AI - Frontend Next.js
Wants=network-online.target
After=network-online.target auditai-backend.service

[Service]
Type=simple
User=auditai
Group=auditai
WorkingDirectory=/opt/auditai/frontend
Environment=NODE_ENV=production
Environment=HOSTNAME=127.0.0.1
Environment=PORT=3000
ExecStart=/usr/bin/npm run start
Restart=on-failure
RestartSec=5
TimeoutStartSec=120
TimeoutStopSec=30
KillSignal=SIGINT
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
FRONTEND_SERVICE
```

Sur Oracle Linux 7.9, remplacer `ExecStart` par le chemin réel, par exemple :

```text
ExecStart=/opt/node20/bin/npm run start
```

## 12. Démarrage

```bash
sudo systemctl daemon-reload
sudo systemctl enable auditai-backend auditai-frontend
sudo systemctl start auditai-backend auditai-frontend
sudo systemctl status auditai-backend auditai-frontend --no-pager
sudo journalctl -u auditai-backend -n 200 --no-pager
sudo journalctl -u auditai-frontend -n 100 --no-pager
```

## 13. Nginx

```bash
sudo tee /etc/nginx/conf.d/auditai.conf >/dev/null <<'NGINX_CONF'
server {
    listen 80;
    server_name <NOM_DNS_AUDITAI>;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Auth-Token $http_x_auth_token;
        proxy_read_timeout 300s;
        proxy_buffering off;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_buffering off;
    }
}
NGINX_CONF

sudo nginx -t
sudo systemctl enable --now nginx
```

## 14. SELinux et pare-feu

```bash
sudo setsebool -P httpd_can_network_connect 1
sudo systemctl enable --now firewalld
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

Ne pas ouvrir publiquement les ports 3000 et 8000.

## 15. Tests d’acceptation

```bash
curl -I http://127.0.0.1:3000
curl -I http://127.0.0.1
```

Après connexion applicative, vérifier :

```bash
curl -sS -H "X-Auth-Token: <TOKEN>" http://127.0.0.1:8000/api/health | jq
curl -sS -X POST -H 'Content-Type: application/json' -H "X-Auth-Token: <TOKEN>" -d '{"question":"Quelle est la dernière action effectuée par SYSTEM ?"}' http://127.0.0.1:8000/api/query | jq
```

Le SQL doit utiliser `DBUSERNAME`, cibler `SMART2DSECU.UNIFIED_AUDIT_DATA`, rester en lecture seule et produire une synthèse cohérente.

## 16. Sauvegarde

```bash
sudo systemctl stop auditai-backend
BACKUP="/var/backups/auditai/auditai-$(date +%Y%m%d-%H%M%S).tar.gz"
sudo tar -czf "$BACKUP" /etc/auditai/auditai.env /opt/auditai/backend_auth.sqlite3 /opt/auditai/backend_audit.sqlite3 /opt/auditai/backend_runtime_settings.json /opt/auditai/tinyllama_oracle_lora 2>/dev/null || true
sudo chmod 600 "$BACKUP"
sudo systemctl start auditai-backend
```

## 17. Checklist Oracle Linux 7/8

- [ ] `backend/requirements.txt` présent et relu
- [ ] `frontend/package.json` présent et relu
- [ ] lockfile npm présent ou absence documentée
- [ ] `backend/app/config.py` comparé au fichier d’environnement
- [ ] `frontend/lib/api.ts` vérifié avant le build
- [ ] Python 3.11 disponible sans remplacement du Python système
- [ ] Node.js et npm disponibles
- [ ] `pip check` réussi
- [ ] imports FastAPI, Torch, Transformers, PEFT, Oracle et llama-cpp réussis
- [ ] `npm ci` ou `npm install` réussi
- [ ] `npm run build` réussi
- [ ] backend lancé avec un seul worker
- [ ] services systemd actifs
- [ ] `nginx -t` réussi
- [ ] SELinux et firewalld configurés
- [ ] ports 3000 et 8000 non exposés publiquement
- [ ] `/api/health` opérationnel
- [ ] question complète testée
- [ ] sauvegarde et retour arrière testés

## 18. Limite de validation documentaire

La validation définitive des versions exactes dépend du contenu réel de `backend/requirements.txt`, `frontend/package.json`, du lockfile npm, de `backend/app/config.py` et de `frontend/lib/api.ts`. Ces fichiers doivent rester inclus dans le ZIP et être utilisés comme sources de vérité lors de l’installation.
