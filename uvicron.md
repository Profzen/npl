# Uvicorn ("unicorne") — fonctionnement et alternatives

## 1) C'est quoi Uvicorn ?

Uvicorn est un **serveur ASGI** (Asynchronous Server Gateway Interface) pour applications Python modernes (FastAPI, Starlette, Quart, etc.).

- WSGI (Flask/Django classique) = modèle synchrone historique.
- ASGI = modèle natif async, **HTTP + WebSocket + connexions longues**.

En pratique, FastAPI expose une application ASGI, et Uvicorn est le processus qui reçoit les connexions réseau, exécute l'app, et renvoie les réponses.

---

## 2) Pourquoi Uvicorn est asynchrone (WSGI vs ASGI)

| Sujet | WSGI (ancien modèle) | ASGI (modèle moderne) |
|---|---|---|
| Contrat serveur/app | Appel de fonction synchrone | Coroutine async (`await app(scope, receive, send)`) |
| Concurrence | 1 thread/process par requête active | 1 boucle événementielle gère beaucoup de requêtes I/O |
| Attente BDD/API | Bloque le worker | Rend la main via `await` |
| Protocoles | HTTP classique | HTTP + WebSocket + streaming |
| Stack typique | Flask + Gunicorn/uWSGI | FastAPI + Uvicorn/Hypercorn |

En une ligne: avec ASGI, un worker peut "jongler" entre de nombreuses requêtes en attente d'I/O, au lieu d'être bloqué par chacune.

---

## 3) Comment Uvicorn fonctionne (vue technique simplifiée)

### Chaîne de traitement d'une requête

1. Le socket écoute sur `host:port`.
2. Uvicorn parse la requête HTTP (via `httptools` ou `h11`).
3. Il construit le scope ASGI (`type`, `method`, `path`, headers, etc.).
4. Il appelle l'application ASGI avec le triplet `(scope, receive, send)`.
5. L'app produit des événements ASGI (headers, body, streaming).
6. Uvicorn sérialise et renvoie la réponse au client.

### Concurrence

- Uvicorn s'appuie sur `asyncio` (ou `uvloop` si disponible).
- Une seule boucle événementielle peut servir de nombreuses connexions I/O-bound.
- Pour le CPU-bound, on scale par **workers** (plusieurs processus) ou externalisation (queues/background workers).

`uvloop` apporte souvent un gain de performance notable en Linux (souvent mesuré entre x1.5 et x4 selon la charge et le type d'I/O).

### Options importantes

- `--reload` : reload auto en dev (à éviter en prod).
- `--workers N` : parallélisme multi-processus en prod.
- `--loop uvloop` : loop plus performante (Linux surtout).
- `--http httptools` : parsing HTTP rapide.
- `--proxy-headers` : respect des headers reverse-proxy (X-Forwarded-*).
- `--timeout-keep-alive` : contrôle des connexions persistantes.

---

## 4) Async réel vs faux async (point critique)

Uvicorn n'est performant que si le code applicatif est effectivement non bloquant.

| Code dans la route | Effet réel |
|---|---|
| `async def` + appels `await` non bloquants | Excellent: forte concurrence I/O |
| `def` synchrone | Exécuté via threadpool: fonctionne, mais scalabilité réduite |
| `async def` avec appels bloquants (`time.sleep`, DB sync) | Bloque le worker malgré la syntaxe async |

Exemple court:

```python
@app.get("/sync")
def sync_route():
	time.sleep(2)  # bloque
	return {"mode": "sync"}

@app.get("/async")
async def async_route():
	await asyncio.sleep(2)  # non bloquant
	return {"mode": "async"}
```

---

## 5) Cas Oracle: mode sync vs mode async

Pour profiter pleinement de Uvicorn, la couche base de donnees doit aussi etre non bloquante.

- Mode sync: `oracledb.connect()` + curseurs sync -> bloque un worker pendant l'attente Oracle.
- Mode async: pool/connexion/cursor async + `await cursor.execute(...)` -> le worker reste disponible.

Exemple type:

```python
import oracledb

pool = oracledb.create_pool_async(...)

@app.get("/data")
async def get_data():
	async with pool.acquire() as conn:
		cursor = await conn.cursor()
		await cursor.execute("SELECT * FROM dual")
		row = await cursor.fetchone()
		return {"row": row}
```

---

## 6) Quand Uvicorn est un bon choix

- API FastAPI/Starlette avec endpoints async.
- Besoin WebSocket/streaming SSE.
- Déploiement conteneurisé simple (1 process ASGI par container).
- Stack Python moderne orientée I/O.

---

## 7) Uvicorn vs Gunicorn (sur l'async)

| Mode | Avantage | Limite |
|---|---|---|
| `uvicorn app:app --workers N` | Simple, direct, peu de couches | Moins riche en gestion process avancée |
| `gunicorn -k uvicorn.workers.UvicornWorker -w N app:app` | Supervision process robuste (signaux, restart, pratiques ops) | Configuration plus lourde |

Important: Gunicorn seul (WSGI worker classique) ne fournit pas le modele async ASGI de FastAPI.

---

## 8) Alternatives à Uvicorn — tableau comparatif

| Solution | Type | Avantages | Inconvénients | Cas d'usage typique |
|---|---|---|---|---|
| **Uvicorn** | ASGI | Léger, rapide, très intégré FastAPI, simple à opérer | Peu de fonctionnalités "serveur applicatif" avancées (vs Gunicorn manager) | API async moderne, microservices |
| **Hypercorn** | ASGI | Support HTTP/1.1, HTTP/2, WebSocket, config flexible | Écosystème moins standard que Uvicorn dans FastAPI | Besoin HTTP/2 natif côté serveur |
| **Daphne** | ASGI | Historique Django Channels, bon support protocoles ASGI temps réel | Moins utilisé avec FastAPI, perfs souvent moins mises en avant | Projets Channels/WebSocket centrés Django |
| **Gunicorn + UvicornWorker** | Pré-fork manager + ASGI workers | Gestion robuste des workers/signaux, pratique en prod Linux | Une couche en plus, tuning plus complexe | Prod Linux classique avec supervision process mature |
| **Granian** | ASGI | Très performant (Rust), faible overhead | Moins répandu, écosystème/outillage plus jeune | Recherche de performance maximale ASGI |
| **Waitress** | WSGI | Stable, simple, cross-platform | Pas ASGI natif, pas WebSocket natif | Apps WSGI sync (Flask/Pyramid) |
| **uWSGI** | WSGI (principalement) | Très riche, mature, options nombreuses | Complexe, configuration réputée difficile, moins adapté ASGI natif | Legacy WSGI enterprise |
| **Nginx + Uvicorn** | Reverse proxy + ASGI | TLS, buffering, compression, sécurité edge, static files | Nécessite 2 composants à opérer | Production Internet exposée |

---

## 9) Avantages et limites de Uvicorn (résumé)

| Aspect | Avantage Uvicorn | Limite / attention |
|---|---|---|
| Performance I/O | Très bon débit/latence sur endpoints async | Le CPU-bound bloque si mal isolé |
| Simplicité | Démarrage immédiat, peu de config | Peut nécessiter reverse proxy pour prod Internet |
| FastAPI | Intégration native de fait | Peu pertinent si app purement WSGI legacy |
| WebSocket | Support natif ASGI | Nécessite architecture correcte (timeouts, sticky session selon infra) |
| Exploitation | Paramètres clairs (`workers`, `reload`, timeouts) | Mauvais réglages workers/timeouts peuvent dégrader la stabilité |

---

## 10) Recommandation générale de déploiement

### Développement local

- `uvicorn app:app --reload`

### Production minimale

- `uvicorn app:app --host 0.0.0.0 --port 8000 --workers 2`
- Derrière un reverse proxy (Nginx/Traefik/Caddy) pour TLS et headers.

### Production robuste Linux

- `gunicorn -k uvicorn.workers.UvicornWorker -w 2 app:app`
- Plus facile à intégrer avec supervision process mature.

---

## 11) Règles pratiques de choix

1. FastAPI async standard : **Uvicorn** (ou Gunicorn+UvicornWorker en prod Linux).
2. Besoin HTTP/2 natif côté app server : **Hypercorn**.
3. Legacy WSGI existant : **Waitress/uWSGI/Gunicorn WSGI** selon contexte.
4. Très haute perf expérimentale ASGI : **Granian** (après benchmark réel).
5. Si la BDD/API reste synchrone, la valeur de l'async diminue fortement.

---

## 12) Erreurs de conception fréquentes

- Lancer du CPU-heavy dans endpoints async sans worker dédié.
- Utiliser `--reload` en production.
- Exposer Uvicorn directement sur Internet sans proxy/TLS.
- Ignorer `X-Forwarded-*` derrière proxy (URLs/schéma erronés).
- Sous-dimensionner ou surdimensionner le nombre de workers sans mesures.
- Croire que `async def` suffit alors que les appels internes restent bloquants.

---

## 13) En une phrase

Uvicorn est le choix ASGI pragmatique pour FastAPI: **simple et performant** si la chaine applicative est vraiment non bloquante (routes, clients HTTP, acces base, I/O).