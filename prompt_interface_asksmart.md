PROMPT COMPLET - ASKSMART

Tu es une IA experte en UI/UX et en intégration frontend. Ta mission est de concevoir et produire une interface web complète, élégante et professionnelle pour la plateforme ASKSMART, en partant de zéro, tout en respectant strictement le contexte produit, les workflows métier et les interactions API décrites ci-dessous.

1) Contexte global du projet

Nom du produit :
- Nom retenu par défaut : ASKSMART
- Noms alternatifs possibles, à ne pas utiliser sauf demande explicite : SMART ASK, SMARTD CORTEX, SMARTD TRACE, SMART AuditExplain, SMART AUDEX, QSMART

Vision produit :
- Permettre à des utilisateurs non techniques de poser des questions en français sur des données d'audit Oracle.
- Transformer automatiquement une question métier en SQL Oracle via un modèle local.
- Exécuter la requête sur une seule table d'audit autorisée.
- Restituer une réponse claire en langage naturel, compréhensible par des personnes non informaticiennes.
- Fonctionner localement et hors ligne, sans dépendance à Internet pour l'inférence des modèles.

Objectif métier :
- Répondre clairement à la question : qui a fait quoi, quand et sur quel objet.
- Offrir une interface lisible, fiable, rassurante, avec un statut système transparent.
- Gérer l'authentification, l'administration des utilisateurs, les logs d'activité et les paramètres runtime.

Pile technologique :
- Frontend : React 18 + Vite
- Backend API : FastAPI
- Base de données métier : Oracle
- Authentification et sessions : SQLite local
- Audit applicatif : SQLite local
- NLP SQL : TinyLlama + LoRA
- Synthèse FR : Phi-3 GGUF via llama_cpp_python
- Driver Oracle : python-oracledb

Contraintes techniques fortes :
- Requêtes SQL : SELECT uniquement.
- Une seule table Oracle autorisée : SMART2DSECU.UNIFIED_AUDIT_DATA, configurable en runtime.
- Interdiction des opérations destructives comme INSERT, UPDATE, DELETE et toute autre opération non autorisée.
- Session d'authentification par token HTTP via le header X-Auth-Token.
- Multi-utilisateur avec limitation du nombre de requêtes simultanées par utilisateur.

2) Spécification frontend complète

2.1 Identité visuelle et direction artistique

Direction :
- Interface moderne, propre, premium, mais sobre.
- Sensation de sécurité, de fiabilité et de clarté.
- Éviter tout rendu de type "dashboard générique".

Palette :
- Rouge principal pour les CTA et les états actifs.
- Blanc pour les surfaces.
- Noir ou gris très foncé pour le texte.
- Fond global clair, jamais noir.
- Vert, orange et rouge réservés aux états de connexion Oracle.

Typographie :
- Police sans-serif moderne et lisible.
- Titres avec une hiérarchie claire.
- Contrastes forts pour l'accessibilité.

Animations :
- Transitions douces, entre 150 et 250 ms.
- Micro-animations utiles uniquement, par exemple pour le chargement, le hover et le collapse de la sidebar.
- Pas d'effets tape-à-l'oeil.

2.2 Architecture écran

Structure globale desktop :
- Colonne gauche : sidebar fixe.
- Zone droite : contenu principal scrollable.

Sidebar, obligatoire :
- Header de marque avec logo + ASKSMART.
- Navigation principale uniquement :
  - Accueil
  - Historique
  - Paramètres
  - Administration, visible uniquement pour les administrateurs
- Footer de la sidebar :
  - Badge de statut Oracle, en vert, orange ou rouge
  - Bouton de déconnexion
  - Compte connecté

Burger menu, obligatoire :
- Position : en haut de la sidebar, intégré au header de la sidebar.
- Fonction : réduire ou réafficher la sidebar.
- Comportement :
  - État ouvert : afficher les icônes et les libellés
  - État replié : afficher seulement les icônes
  - État mobile : drawer overlay coulissant
- Ne jamais placer ce bouton hors de la sidebar.

Page Accueil :
- Grand bandeau principal avec le titre "Posez votre question".
- Champ de saisie central + bouton Interroger.
- Zone de résultat principale :
  - Question
  - SQL généré, dans un bloc code
  - Synthèse textuelle
  - Tableau de résultats
- Colonnes de contexte à droite, conservées :
  - Utilisateurs, avec liste et compteur d'actions
  - Tables / Objets, avec liste et compteur d'actions
  - Actions possibles, sous forme de guide métier lisible
- Disposition attendue en desktop :
  - Grand panneau principal à gauche
  - Trois cartes verticales à droite
- Attendus qualitatifs :
  - Excellente lisibilité
  - Espacements bien gérés
  - Styles harmonieux
  - Rendu premium
  - Adaptabilité de toute la partie de droite selon que la sidebar soit ouverte ou masquée

Page de connexion :
- La page de connexion doit être conçue comme une vraie page d'entrée produit, élégante, rassurante et immédiatement compréhensible.
- Le nom de l'application ASKSMART doit être clairement visible dès l'arrivée sur la page.
- La disposition attendue en desktop est la suivante :
  - Une composition centrée, propre et premium
  - Un grand bloc principal de connexion au centre ou légèrement décalé pour laisser respirer la composition
  - Un fond clair travaillé avec légères variations, dégradés subtils ou formes douces, sans surcharge visuelle
- Le bloc principal de connexion doit contenir :
  - Le logo ou monogramme de l'application
  - Le nom ASKSMART en évidence
  - Un sous-titre court expliquant la finalité de la plateforme, par exemple l'accès aux questions-réponses sur les données d'audit
  - Un champ Identifiant
  - Un champ Mot de passe
  - Un bouton principal de connexion
  - Une zone de message d'erreur proprement intégrée sous le formulaire si l'authentification échoue
- La hiérarchie visuelle doit être très claire :
  - D'abord l'identité produit
  - Ensuite l'explication courte
  - Ensuite le formulaire
  - Enfin les messages d'état
- Le formulaire doit avoir une présentation haut de gamme :
  - Labels bien lisibles
  - Champs larges, alignés et bien espacés
  - Bouton principal rouge, très visible, avec un bon contraste
  - Focus propre sur les champs
  - Retour visuel clair en cas d'erreur
- Le champ mot de passe peut inclure une icône afficher / masquer si jugé pertinent par la proposition visuelle.
- Le texte de la page doit inspirer la confiance, la clarté et le sérieux, sans jargon technique.
- Le style général de la page de connexion doit être cohérent avec le reste de l'application :
  - Rouge, blanc, noir ou gris foncé
  - Aucune ambiance sombre agressive
  - Pas de page vide ou trop minimaliste
- Comportement attendu :
  - Si l'utilisateur renseigne des identifiants valides, il entre dans l'application
  - Si les identifiants sont invalides ou si le compte est suspendu, un message clair et visible doit apparaître sans casser la mise en page
  - Pendant l'envoi, le bouton peut afficher un état de chargement
- En responsive mobile :
  - Le bloc de connexion doit rester centré et très lisible
  - Les champs et le bouton doivent prendre la largeur utile
  - Le nom ASKSMART doit rester immédiatement visible sans scroller

Page Historique :
- Colonne gauche : liste des requêtes exécutées, de la plus récente à la plus ancienne.
- Colonne droite : détail de l'entrée sélectionnée.
- Badges de statut par entrée : OK, Bloqué, Erreur.

Page Paramètres :
- Formulaire complet éditable.
- Sections :
  - Connexion Oracle
  - Analyse
  - Interface
  - Chaque section doit être visuellement séparée dans une carte ou un bloc dédié
- Champs obligatoires à afficher dans la page Paramètres :
  - Utilisateur Oracle
  - Mot de passe Oracle
  - Hôte Oracle
  - Port Oracle
  - Service Oracle
  - Table Oracle interrogée
  - Langue de l'interface
  - Résultats max par requête
  - Durée de session, en minutes
  - Durée de conservation des logs, en jours
- Types de contrôles attendus :
  - Utilisateur Oracle : champ texte simple
  - Mot de passe Oracle : champ mot de passe avec bouton afficher / masquer
  - Hôte Oracle : champ texte
  - Port Oracle : champ numérique
  - Service Oracle : champ texte
  - Table Oracle interrogée : champ texte
  - Langue de l'interface : sélecteur avec au minimum Français / English
  - Résultats max par requête : champ numérique
  - Durée de session, en minutes : champ numérique
  - Durée de conservation des logs, en jours : champ numérique
- Organisation visuelle conseillée :
  - Bloc Connexion Oracle : Utilisateur Oracle, Mot de passe Oracle, Hôte Oracle, Port Oracle, Service Oracle, Table Oracle interrogée
  - Bloc Analyse : Résultats max par requête
  - Bloc Session et journalisation : Durée de session, en minutes, et Durée de conservation des logs, en jours
  - Bloc Interface : Langue de l'interface
- Exigences UX pour la page Paramètres :
  - Tous les champs doivent être réels, modifiables et cohérents avec les données backend
  - Les valeurs chargées doivent venir de l'API /api/settings
  - La sauvegarde doit appeler l'API /api/settings avec tous les champs du formulaire
  - Le bouton Réinitialiser doit restaurer les valeurs actuellement connues du backend
  - Les labels doivent être parfaitement alignés
  - Les champs numériques doivent avoir une présentation propre et uniforme
  - La notification de succès ou d'échec doit apparaître clairement en haut de la page
  - Le mot de passe Oracle ne doit pas être visible par défaut
- Boutons : Réinitialiser / Sauvegarder
- Notification de succès ou d'erreur clairement visible en haut du bloc

Page Administration, admin only :
- Gestion des utilisateurs :
  - Liste des utilisateurs
  - Création d'utilisateur
  - Suspension / activation
  - Suppression
- Tableau des logs d'activité applicative
- Actions de rafraîchissement

2.3 États UI et feedback utilisateur

État de connexion Oracle, badge global :
- Vert = connecté actif
- Orange = connecté mais inactif, connexion non maintenue
- Rouge = indisponible / offline

Règle d'inactivité Oracle :
- Passer en orange après 30 secondes sans activité Oracle.
- Revenir en vert lors d'une nouvelle activité Oracle réussie.
- Passer en rouge si /api/health indique une déconnexion Oracle ou si un appel échoue.

État de chargement de question :
- Spinner + texte "Analyse en cours".
- Désactivation temporaire du bouton d'envoi.

État d'erreur :
- Affichage explicite du message backend.
- Conservation du contexte de la question.

État vide :
- Message pédagogique invitant à poser une question.

2.4 Accessibilité et responsive

Responsive :
- Desktop prioritaire.
- Tablette : les colonnes contextuelles passent sous le bloc principal.
- Mobile : sidebar en drawer, cartes empilées, barre de saisie en pleine largeur.

Accessibilité :
- Contraste suffisant.
- Focus clavier visible.
- Boutons avec libellés explicites.
- Zones cliquables confortables.

3) Spécification backend, APIs, retours, erreurs et interactions front-back

Base URL API :
- /api

Authentification :
- Header obligatoire pour les routes protégées :
  - X-Auth-Token: <token>

3.1 Endpoints Auth

1) POST /api/auth/login
- Body JSON :
  - username : string, de 3 à 64 caractères
  - password : string, de 1 à 128 caractères
- 200 OK :
  - {
      "token": "...",
      "user": {
        "id": 1,
        "username": "admin",
        "is_admin": true,
        "is_active": true
      }
    }
- 401 Unauthorized :
  - detail : "Identifiants invalides ou compte suspendu"
- Effets :
  - Création d'une session SQLite
  - Audit log de l'action auth_login, en succès ou en erreur

2) GET /api/auth/me
- Header : X-Auth-Token
- 200 OK : AuthUser
- 401 Unauthorized :
  - "Token manquant"
  - "Session invalide ou expirée"

3) POST /api/auth/logout
- Header : X-Auth-Token, optionnel mais attendu
- 200 OK : {"status":"ok"}
- Effets :
  - Révocation de session
  - Audit log auth_logout si l'utilisateur a été résolu

3.2 Endpoints Admin

4) GET /api/admin/users
- Auth admin requise
- 200 OK : liste AdminUser[]
- 401 si token absent ou invalide
- 403 si non admin

5) POST /api/admin/users
- Auth admin requise
- Body :
  - username : string, de 3 à 64 caractères
  - password : string, de 6 à 128 caractères
  - is_admin : bool
- 200 OK : AdminUser créé
- 400 Bad Request : username invalide, déjà existant ou règle métier invalide
- 401 / 403 selon l'authentification
- Effets : audit admin_create_user, en succès ou en erreur

6) PATCH /api/admin/users/{user_id}/status
- Auth admin requise
- Body : {"is_active": true|false}
- 200 OK : AdminUser mis à jour
- 400 Bad Request :
  - tentative de suspension de son propre compte admin
- 404 Not Found :
  - utilisateur introuvable
- Effets : audit admin_set_user_status

7) DELETE /api/admin/users/{user_id}
- Auth admin requise
- 200 OK : {"status":"ok"}
- 400 Bad Request :
  - tentative de suppression de son propre compte admin
- 404 Not Found : utilisateur introuvable
- Effets : audit admin_delete_user

8) GET /api/admin/audit-logs?limit=300
- Auth admin requise
- Query :
  - limit : int entre 1 et 2000, défaut 300
- 200 OK : AuditLogEntry[]
- 401 / 403 selon l'authentification

3.3 Endpoints applicatifs protégés

9) GET /api/health
- Header : X-Auth-Token
- 200 OK :
  - {
      "status":"ok",
      "oracle":"connected|disconnected",
      "tinyllama":"loaded|error",
      "phi3":"loaded|error"
    }
- 401 si token absent ou invalide
- Usage frontend :
  - Pilotage du badge Oracle, vert / orange / rouge

10) GET /api/metadata
- Header : X-Auth-Token
- 200 OK :
  - {
      "users": [{"name":"...","actions":123}],
      "objects": [{"name":"...","actions":45}],
      "db_status":"connected|disconnected"
    }
- 401 Unauthorized
- 500 possible si erreur Oracle non gérée en amont

11) GET /api/history
- Header : X-Auth-Token
- 200 OK : list[dict], historique du user courant uniquement, avec 100 entrées récentes maximum
- 401 Unauthorized

12) GET /api/settings
- Header : X-Auth-Token
- 200 OK RuntimeSettings :
  - oracle_user, oracle_password, oracle_host, oracle_port, oracle_service, oracle_table,
    interface_lang, max_results, session_duration, logs_retention
- 401 Unauthorized

13) POST /api/settings
- Header : X-Auth-Token
- Body : RuntimeSettings
- 200 OK : RuntimeSettings appliqués et nettoyés
- 401 Unauthorized
- 500 possible, par exemple en cas d'échec d'écriture JSON
- Effets :
  - Persistance dans backend_runtime_settings.json
  - Audit settings_update
  - Impact direct sur la configuration Oracle et sur la limite de résultats

14) POST /api/query
- Header : X-Auth-Token
- Body :
  - question : string, de 2 à 1500 caractères
- 200 OK QueryResponse :
  - question : string
  - sql : string
  - synthesis : string
  - rows : list[dict], déjà limitées par max_results
  - row_count : int, total avant coupe
  - blocked : bool
  - error : string | null
- 401 Unauthorized
- 429 Too Many Requests :
  - si dépassement de la limite simultanée par utilisateur
- 422 Unprocessable Entity :
  - question invalide selon le schéma Pydantic
- 500 possible :
  - erreur non anticipée côté services ou modèles

3.4 SQL guardrails et pipeline query

Pipeline logique de POST /api/query :
1. Vérifier le slot de concurrence utilisateur.
2. TinyLlama + LoRA génère le SQL.
3. Nettoyage SQL + normalisation.
4. Garde-fous :
   - SELECT / WITH seulement
   - Interdiction des opérations destructives
   - Une seule table autorisée
   - Pas de multi-statements
5. Exécution Oracle, via pool de connexions, non persistante par requête.
6. Synthèse FR via Phi3.
7. Écriture dans l'historique mémoire + audit log.
8. Retour JSON standardisé.

Comportement si SQL bloqué :
- sql commence par "-- blocked: ..."
- rows = []
- blocked = true
- error peut contenir la raison
- synthesis adaptée au cas

3.5 Interaction frontend-backend, workflow par action

Workflow A - Login :
- Le frontend envoie POST /api/auth/login.
- Si 200 : stocker le token en localStorage, puis charger le profil via /api/auth/me.
- Si 401 : afficher un message de login invalide.

Workflow B - Chargement de l'application après login :
- Appels en parallèle :
  - /api/health
  - /api/metadata
  - /api/history
  - /api/settings
  - Endpoints admin supplémentaires si le rôle est admin
- Toute réponse 401 entraîne un clear de session puis un retour à l'écran de login.

Workflow C - Poser une question :
- POST /api/query.
- Puis refresh de :
  - /api/history
  - /api/metadata
  - /api/health
- Gestion des cas :
  - 200 nominal
  - 200 avec erreur métier Oracle
  - 200 avec blocked
  - 429 throttling
  - 401 session expirée

Workflow D - Modifier les paramètres :
- GET /api/settings pour pré-remplir.
- POST /api/settings pour sauvegarder.
- Si 200 : rafraîchir health + metadata.
- Si erreur : afficher une notification d'échec.

Workflow E - Administration des utilisateurs :
- GET /api/admin/users
- POST /api/admin/users
- PATCH /api/admin/users/{id}/status
- DELETE /api/admin/users/{id}
- Refresh de la liste et des logs après chaque action
- Gestion explicite des erreurs 400 / 404 / 403

Workflow F - Consultation des logs admin :
- GET /api/admin/audit-logs?limit=300
- Afficher un tableau chronologique récent

Workflow G - Logout :
- POST /api/auth/logout
- Purger le token local
- Retour à l'écran de login

3.6 Gestion des codes HTTP côté frontend

Règles d'affichage :
- 200 : afficher le contenu
- 400 : afficher le message métier détaillé
- 401 : déconnecter automatiquement et afficher l'écran de login
- 403 : message "Accès réservé administrateur"
- 404 : message ressource introuvable
- 422 : message de validation de formulaire
- 429 : message "Trop de requêtes simultanées"
- 500 : message générique + suggestion de réessayer

4) Exigences de réalisation frontend

Produire :
- Des composants React propres et modulaires
- Une structure CSS moderne et maintenable
- Des états clairs, loading, empty, error, success
- Aucune régression sur les fonctionnalités métier

Livrables attendus :
- Une arborescence frontend complète, avec une interface complète prête de bout en bout
- Le code des pages Accueil, Historique, Paramètres, Admin et Login
- Un service API centralisé, fetch wrapper, gestion du token, gestion du 401
- Des composants UI réutilisables, par exemple Badge, Card, Table, Alert, Modal
- Des variables de thème CSS, rouge / blanc / noir clair
- Un rendu responsive desktop / tablette / mobile

Critères qualité :
- Interface élégante et attractive
- Lisibilité optimale pour des non-techniciens
- Navigation fluide
- Statuts système compréhensibles
- Cohérence visuelle globale

5) Notes de cohérence métier

- Le système ne maintient pas une connexion Oracle permanente au niveau de la session utilisateur.
- Le statut Oracle visible en UI doit refléter l'activité récente, pas seulement un ping unique.
- La table Oracle cible est configurable, mais les garde-fous doivent rester stricts.
- Les logs admin sont sensibles et visibles uniquement pour le rôle admin.
