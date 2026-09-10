# memoire.md — Projet ASKSMART (NLP → SQL Oracle Audit)

> Ce fichier est la **mémoire long-terme** de l'agent IA qui travaille sur ce projet.
> Il doit être lu en premier à chaque nouvelle session pour reprendre le contexte sans perte.
> Il est mis à jour au fil des découvertes / décisions importantes.

Dernière mise à jour : 2026-05-05

---

## 1. Vision produit

**ASKSMART** (anciennement « Oracle NLP » / « QueryFlow ») est une **plateforme conversationnelle**
qui permet à des utilisateurs **non techniques** (auditeurs, RSSI, managers) d'**interroger les
journaux d'audit Oracle en langage naturel** (français) et d'obtenir :

1. La requête SQL générée
2. Les résultats sous forme de tableau
3. Une **synthèse en français naturel** lisible par un non-informaticien

Cible matérielle : machines clients **CPU-only** (pas de GPU à l'inférence).

### Préférences utilisateur (à respecter STRICTEMENT)

- **Français naturel non technique** dans toutes les formulations user-facing.
- **Éviter le jargon SQL** dans les prompts visibles, exemples, tests, datasets.
- Pas d'emojis sauf demande explicite.

---

## 2. Architecture globale

```
┌──────────────────┐      HTTP/JSON      ┌────────────────────┐     oracledb     ┌───────────┐
│  Frontend Next 16│ ──────────────────► │  Backend FastAPI   │ ───────────────► │ Oracle DB │
│  (React 19, TS)  │ ◄────────────────── │   (Python 3.11)    │ ◄─────────────── │  (UAT)    │
└──────────────────┘                     └─────────┬──────────┘                  └───────────┘
                                                   │
                                ┌──────────────────┼─────────────────────┐
                                ▼                  ▼                     ▼
                       ┌────────────────┐ ┌──────────────┐    ┌────────────────────┐
                       │ TinyLlama+LoRA │ │ Phi-3-mini   │    │ SQLite local       │
                       │ (NL → SQL)     │ │ GGUF (synth.)│    │ auth + audit logs  │
                       └────────────────┘ └──────────────┘    └────────────────────┘
```

### Pipeline d'une requête utilisateur

1. **Frontend** envoie `POST /api/query/start` avec `{ question }`
2. **Backend** lance un job async, renvoie `query_id`
3. Frontend poll `GET /api/query/progress/{id}` (étapes : gen_sql → connect → exec → translate → finalize)
4. **NLP service** (TinyLlama+LoRA) traduit la question en SQL Oracle
5. **Oracle service** exécute la requête sur la table `SMART2DSECU.UNIFIED_AUDIT_DATA`
6. **Synthesis service** (Phi-3 GGUF) génère un résumé en français naturel
7. Frontend affiche les 3 blocs : SQL, résultats tabulaires, synthèse

---

## 3. Stack technique

### Backend ([backend/](backend/))

- **Python 3.11** dans `venv_nlp/`
- **FastAPI 0.116** + **Uvicorn 0.31** (ASGI, async natif)
- **oracledb 2.4.1** (mode `thin` par défaut, async via `asyncio.to_thread`)
- **transformers 5.2 + peft 0.18 + torch 2.10** (TinyLlama + adaptateur LoRA)
- **llama-cpp-python 0.3.16** (Phi-3 GGUF quantisé Q4)
- **SQLite** local pour `auth` et `audit_trail` (pas de PG/MySQL)
- Lancement : `cd backend && uvicorn app.main:app --reload --port 8000`

### Frontend ([frontend/](frontend/))

- **Next.js 16.2** (App Router) + **React 19** + **TypeScript**
- **Tailwind CSS** + **shadcn/ui** (composants Radix UI)
- **lucide-react** pour les icônes
- Lancement : `cd frontend && npm run dev` (port 3000)

### Modèles IA

| Modèle | Rôle | Format | Taille | Emplacement |
|--------|------|--------|--------|-------------|
| TinyLlama-1.1B-Chat-v1.0 | Base NL→SQL | safetensors | ~2.2 Go | [TinyLlama-1.1B-Chat-v1.0/](TinyLlama-1.1B-Chat-v1.0/) |
| LoRA adapter (V12/V13) | Spécialisation Oracle audit | safetensors | ~15 Mo | [tinyllama_oracle_lora/](tinyllama_oracle_lora/) |
| Phi-3-mini-4k-instruct | Synthèse FR | GGUF Q4 | ~640 Mo | [phi3-mini-gguf/](phi3-mini-gguf/) |

> **IMPORTANT** : les poids (.safetensors, .gguf, .pt, .bin, checkpoints) sont **gitignored** (limite GitHub 100 Mo).
> Seuls la config / tokenizer / README du LoRA sont versionnés.
> Pour reproduire : ré-entraîner via le notebook Colab et placer les poids manuellement.

---

## 4. Organisation du code

### Backend — [backend/app/](backend/app/)

| Fichier | Rôle |
|---------|------|
| [main.py](backend/app/main.py) | Routes FastAPI (auth, query, settings, admin), cache, jobs async |
| [config.py](backend/app/config.py) | Settings dataclass (Oracle, modèles, pool, seuils) |
| [schemas.py](backend/app/schemas.py) | Modèles Pydantic (request/response) |
| [services/nlp_service.py](backend/app/services/nlp_service.py) | TinyLlama + LoRA, `generate_sql_from_question()` |
| [services/synthesis_service.py](backend/app/services/synthesis_service.py) | Phi-3 GGUF, fallback règles |
| [services/oracle_service.py](backend/app/services/oracle_service.py) | Pool oracledb, exécution SQL, métadonnées |
| [services/audit_service.py](backend/app/services/audit_service.py) | SQLite : journal d'audit applicatif |
| [services/auth_service.py](backend/app/services/auth_service.py) | SQLite : utilisateurs, sessions, tokens |
| [services/settings_service.py](backend/app/services/settings_service.py) | Settings runtime modifiables via UI admin |

### Frontend — [frontend/](frontend/)

| Chemin | Rôle |
|--------|------|
| [app/layout.tsx](frontend/app/layout.tsx) | Layout racine + métadonnées |
| [app/login/page.tsx](frontend/app/login/page.tsx) | Page de connexion (logo Smart2D, sans cadre) |
| [app/(dashboard)/layout.tsx](frontend/app/(dashboard)/layout.tsx) | AppShell avec sidebar |
| [app/(dashboard)/page.tsx](frontend/app/(dashboard)/page.tsx) | Dashboard principal (HomePage) — input question, étapes, résultats |
| [app/(dashboard)/history/page.tsx](frontend/app/(dashboard)/history/page.tsx) | Historique des requêtes |
| [app/(dashboard)/settings/page.tsx](frontend/app/(dashboard)/settings/page.tsx) | Paramètres (Oracle, analyse, session, interface) |
| [app/(dashboard)/admin/page.tsx](frontend/app/(dashboard)/admin/page.tsx) | Gestion utilisateurs + logs activité |
| [components/app-shell.tsx](frontend/components/app-shell.tsx) | Provider `useAppData` (settings, metadata, history) |
| [components/app-sidebar.tsx](frontend/components/app-sidebar.tsx) | Sidebar (nav + Oracle status + dernières questions) |
| [lib/api.ts](frontend/lib/api.ts) | Wrapper fetch + ApiError |
| [lib/auth-context.tsx](frontend/lib/auth-context.tsx) | Auth React context |
| [lib/i18n.ts](frontend/lib/i18n.ts) | Système i18n custom FR/EN (~100 clés) |
| [lib/types.ts](frontend/lib/types.ts) | Types partagés |

---

## 5. Internationalisation (i18n)

Système **maison** sans lib externe, dans [lib/i18n.ts](frontend/lib/i18n.ts).

- 2 dictionnaires : `FR` et `EN`, mêmes clés
- Namespaces : `app.*`, `oracle.*`, `nav.*`, `sidebar.*`, `login.*`, `dashboard.*`, `step.*`, `audit.*`, `col.*`, `history.*`, `status.*`, `admin.*`, `settings.*`
- API exportée :
  - `useT()` : hook React, lit `settings.interface_lang` via `useAppData()`
  - `useLang()` : retourne 'fr'|'en'
  - `translate(lang, key)` : fonction pure (SSR/non-context)
  - `getStandaloneLang()` + `tStandalone(key)` : pour pages hors AppShell (login)
- Persistance : `RuntimeSettings.interface_lang` côté backend + `localStorage.asksmart_lang` côté login
- **Règle** : aucune chaîne user-visible ne doit être codée en dur en français. Toujours passer par `t('namespace.key')`.

---

## 6. Modèle Oracle ciblé

Table prod : `SMART2DSECU.UNIFIED_AUDIT_DATA`
Table logique d'entraînement : `ORACLE_AUDIT_TRAIL` (alias stable)

> **Stratégie alias V13** (importante !) : le LoRA est entraîné avec `Table : ORACLE_AUDIT_TRAIL` dans son SYSTEM_PROMPT et tous les SQL outputs du dataset utilisent `FROM ORACLE_AUDIT_TRAIL`. Le **backend** rewrites ensuite via `_post_process_sql()` → vers la vraie table `get_oracle_table()` (= `SMART2DSECU.UNIFIED_AUDIT_DATA`). Cela permet de changer la table prod sans réentraîner le modèle. Le `SYSTEM_PROMPT` du backend doit donc dire `Table : ORACLE_AUDIT_TRAIL` (et non la vraie table), pour rester strictement aligné sur l'entraînement.

Colonnes principales utilisées par le LoRA :
`ID, AUDIT_TYPE, SESSIONID, OS_USERNAME, USERHOST, TERMINAL, AUTHENTICATION_TYPE, DBUSERNAME,
CLIENT_PROGRAM_NAME, OBJECT_SCHEMA, OBJECT_NAME, SQL_TEXT, SQL_BINDS, EVENT_TIMESTAMP, ACTION_NAME, INSTANCE`

Règles du SYSTEM_PROMPT (V12/V13 — alignement strict Colab ↔ inference ↔ backend) :
1. Une seule table : `UNIFIED_AUDIT_DATA`
2. **Jamais** DBA_USERS, ALL_USERS, USER_USERS
3. Compter utilisateurs : `COUNT(DISTINCT DBUSERNAME)` en ignorant NULL
4. Connexions : `WHERE ACTION_NAME='LOGON'` ; déconnexions : `LOGOFF`
5. Heures : `SYSDATE-N/24` ; Jours : `SYSDATE-N` ; Minutes : `SYSDATE-N/1440`
6. Poste/machine : `USERHOST`
7. Horaire nocturne : `TO_CHAR(EVENT_TIMESTAMP,'HH24')`
8. SQL Oracle valide UNIQUEMENT, sans explication
9. SELECT uniquement
10. Tri par date : `ORDER BY EVENT_TIMESTAMP DESC`
11. Limite : `FETCH FIRST N ROWS ONLY`

> Le prompt **doit rester identique** dans : notebook Colab (cellule 10), `nlp_service.py` (`_system_prompt`), et docs benchmarks.

---

## 7. Workflow d'entraînement (Colab)

Notebooks de référence :
- [tinyllama_oracle_v12_dataset (2).ipynb](tinyllama_oracle_v12_dataset%20(2).ipynb) — version stable V12
- [tinyllama_oracle_v13_dataset.ipynb](tinyllama_oracle_v13_dataset.ipynb) — V13 en cours (évolutions sur dataset)

Datasets :
- [oracle_nlp_dataset_v11.csv](oracle_nlp_dataset_v11.csv) (~production V12/V13)
- [oracle_error_driven_pairs_v11.csv](oracle_error_driven_pairs_v11.csv) (paires correctives)

Étapes notebook :
1. Charger TinyLlama-1.1B-Chat
2. Appliquer LoRA (PEFT) avec dataset CSV
3. Train ~4500 steps (4 checkpoints sauvegardés)
4. Évaluer
5. **Quantization GGUF Q4_K_M** (~640 Mo au lieu de 2.2 Go) — décisive pour CPU client
6. Export adapter → coller dans `tinyllama_oracle_lora/`

---

## 8. Authentification & sécurité

- Login basique username/password → token bearer
- Sessions stockées dans `backend_auth.sqlite3`
- Audit applicatif (qui a fait quoi) dans `backend_audit.sqlite3`
- Rôles : `is_admin` boolean → page `/admin` réservée
- Compte par défaut auto-créé : `admin / admin` (à changer via UI Admin)
- CORS : configurable via `BACKEND_CORS_ORIGINS`

---

## 9. Lancement local (développement)

### 1. Backend
```powershell
cd c:\dossier3\nlp
.\venv_nlp\Scripts\Activate.ps1
cd backend
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend
```powershell
cd c:\dossier3\nlp\frontend
npm run dev
# http://localhost:3000
```

### Variables d'environnement utiles (sinon défauts dans config.py)
- `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE`, `ORACLE_TABLE`
- `MODEL_DIR`, `LORA_DIR`, `PHI3_PATH`
- `USE_GGUF_MODE=true` + `GGUF_MODEL_PATH=...` pour activer TinyLlama GGUF
- `MAX_CONCURRENT_QUERIES_PER_USER=2`
- `BACKEND_CORS_ORIGINS=http://localhost:3000`

---

## 10. Identité visuelle

- **Logo** : `frontend/public/smart2d_logo.jpeg` (Smart2D Services — rouge & noir)
- Affichage :
  - Login : centré, `h-16`, sans cadre/fond
  - Dashboard header : à droite de « Posez votre question », `h-9`, sans cadre
  - Sidebar : **pas de logo** (seulement le texte ASKSMART)
- Brand : `ASKSMART` (toujours en majuscules)
- Tagline login : aucune (épurée à la demande utilisateur)

---

## 11. Conventions / décisions importantes

- **Format chemins** : tous les liens markdown utilisent des chemins relatifs (pas de `file://`).
- **Pas de docstrings/commentaires ajoutés** sauf si le code n'est pas auto-explicatif.
- **Pas de fichiers MD de récap** créés sans demande explicite (sauf [memoire.md](memoire.md) lui-même et docs métier).
- **Frontend** : préférer `multi_replace_string_in_file` pour batch de traductions.
- **Bordures importantes UI** : `border-2 border-foreground/20` pour les cartes critiques (login).
- Le prompt SYSTEM doit être copié **à l'identique** entre Colab/inférence/backend (sinon performance dégrade).

---

## 12. Historique condensé (jalons)

| Date | Jalon |
|------|-------|
| Avr 17-20 | V12 LoRA déployée — 3/10 succès sur 10 questions de test |
| Avr 22 | Doc [uvicron.md](uvicron.md) (WSGI/ASGI, Oracle async, Uvicorn vs Gunicorn) |
| Avr 23–Mai 4 | V13 préparé : suppression DBA_USERS, alignement prompts, GGUF Q4 |
| Mai 5 | Logo Smart2D, refonte UI (login/dashboard/sidebar), i18n FR/EN complet |
| Mai 5 | Push GitHub `d5e3e33` |
| Mai 5 | V13 finalisé : RETURNCODE retiré du dataset, alignement strict SYSTEM_PROMPT backend↔notebook (alias `ORACLE_AUDIT_TRAIL` + rewriter prod) |

---

## 13. À faire / pistes d'amélioration

- [ ] Héberger les poids LoRA sur HuggingFace Hub (pour cloner sans Colab)
- [ ] Activer Git LFS si on veut versionner les .safetensors
- [ ] Étendre i18n à d'éventuels nouveaux écrans
- [ ] Streaming des étapes via SSE plutôt que polling (optimisation UX)
- [ ] Tests d'intégration end-to-end (frontend ↔ backend ↔ Oracle mock)

---

## 14. Notes méta (pour l'agent IA)

- L'utilisateur travaille sur **Windows / PowerShell 5.1** (pas de `&&`, utiliser `;`).
- Workspace racine : `c:\dossier3\nlp`
- Repo distant : `https://github.com/Profzen/npl.git` (branche `master`)
- Si erreur TS « Cannot find module '@/lib/i18n' » → faux positif du serveur TS, le fichier existe.
- Toujours **vérifier `.gitignore`** avant de paniquer sur des fichiers manquants côté repo (modèles, .env, venv).
- Les notebooks `.ipynb` sont commités, mais lourds (datasets en sortie) — éviter de les rouvrir/sauver inutilement.
