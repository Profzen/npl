# Mémoire vivante — Audit AI / ASKSMART

Dernière mise à jour : 10 septembre 2026

Ce fichier conserve l'état réel du projet. Il doit être mis à jour après chaque décision,
expérience, correction importante ou changement d'architecture.

## 1. Objectif du projet

Audit AI permet à des auditeurs, responsables sécurité et managers d'interroger en français les
journaux d'audit Oracle. Une question doit produire :

1. une requête Oracle SQL en lecture seule ;
2. un tableau de résultats ;
3. une synthèse compréhensible par un utilisateur non technique ;
4. une trace applicative de l'opération.

La contrainte centrale du mémoire de master est l'exécution locale, sur CPU si nécessaire, sans
envoyer les données d'audit à un service d'IA externe.

L'interface vise une personne non informaticienne. Elle présente trois catalogues explicatifs :
les utilisateurs Oracle, les tables ou objets audités, et les actions observables (`SELECT`,
`INSERT`, `UPDATE`, `DELETE`, `GRANT`, `REVOKE`, `TRUNCATE`, etc.). Ces actions sont des événements
à rechercher dans les journaux ; l'application ne doit jamais les exécuter. L'utilisateur peut
poser une question naturelle, abrégée ou imparfaite, par exemple « qui a touché cette table hier ? ».
Le système doit résoudre les dates relatives, reconnaître l'utilisateur, l'objet et l'action, puis
demander une reformulation ciblée seulement lorsqu'une information indispensable reste ambiguë.

## 2. État de récupération

- Sauvegarde locale reçue : export préparé entre le 14 et le 24 juillet 2026.
- Dépôt distant : <https://github.com/Profzen/npl>, branche `master`.
- Dernier commit distant observé : `93861e6`, 13 juillet 2026.
- Le dossier local initial ne contenait pas de répertoire `.git`.
- Le dépôt distant contient 277 fichiers ; la sauvegarde locale initiale en contient 164.
- 119 fichiers sont communs aux deux sources.
- Parmi eux, 92 sont identiques octet pour octet et 27 diffèrent uniquement par leurs fins de
  ligne. Aucun code applicatif distant plus récent n'a été trouvé.
- La sauvegarde locale apporte les modèles, la documentation d'intégration et les fichiers de
  livraison créés après le dernier push GitHub.
- GitHub apporte surtout le mémoire historique, les notebooks, datasets, benchmarks, prototypes
  et sauvegardes intermédiaires.

Fusion retenue : conserver le code actif de la sauvegarde locale et récupérer sous `research/`
les sources de recherche utiles. Les `.bak`, anciens prototypes, ZIP de patch et exports découpés
ne sont pas remis dans l'application active.

## 3. Architecture actuelle

```text
Navigateur Next.js 16 / React 19
             |
             | HTTP JSON + X-Auth-Token
             v
Backend FastAPI
  |-- authentification et sessions SQLite
  |-- suivi asynchrone des analyses en mémoire
  |-- TinyLlama 1.1B + LoRA -> SQL Oracle
  |-- pool python-oracledb -> table d'audit Oracle
  |-- Phi-3 Mini GGUF ou synthèse par règles -> français
  `-- historique mémoire + journal applicatif SQLite
```

Le frontend appelle `POST /api/query/start`, puis interroge
`GET /api/query/progress/{request_id}` jusqu'au résultat final. Une route synchrone
`POST /api/query` existe aussi.

## 4. Composants actifs

### Backend

- `backend/app/main.py` : routes, cache, concurrence et suivi des requêtes.
- `backend/app/services/nlp_service.py` : chargement TinyLlama/LoRA et génération SQL.
- `backend/app/services/oracle_service.py` : pool Oracle, exécution et métadonnées.
- `backend/app/services/synthesis_service.py` : Phi-3 et synthèse déterministe de secours.
- `backend/app/services/auth_service.py` : utilisateurs et sessions SQLite.
- `backend/app/services/audit_service.py` : journal applicatif SQLite.
- `backend/app/services/settings_service.py` : paramètres modifiables à l'exécution.
- `backend/app/services/dynamic_guardrails_service.py` : garde-fous développés mais non branchés
  dans le pipeline actuel.

### Frontend

- connexion et restauration de session ;
- tableau de bord question/résultat avec progression ;
- historique propre à l'utilisateur ;
- paramètres ;
- gestion des utilisateurs et logs pour l'administrateur ;
- interface française, avec ancien dictionnaire anglais encore présent mais langue verrouillée.

Le 10 septembre 2026, le frontend a été vérifié avec Node 22 : installation réussie, contrôle
TypeScript sans erreur et build de production réussi. L'audit npm a conduit à mettre à jour
Next.js de 16.2.0 vers 16.3.4 et PostCSS vers une version supérieure ou égale à 8.5.23. Après
mise à jour, `npm audit` ne signale plus aucune vulnérabilité connue.

## 5. Modèles présents dans la sauvegarde

| Élément | Rôle | Taille observée | Mode actuel |
|---|---|---:|---|
| TinyLlama-1.1B-Chat-v1.0 | génération SQL | 2 200 119 864 octets | PyTorch CPU |
| Adaptateur LoRA r=32 | spécialisation audit Oracle | 100 966 336 octets | PEFT |
| Phi-3-mini-4k-instruct Q4_K_M | synthèse | 2 393 231 072 octets | llama.cpp CPU |

La documentation historique indiquait environ 640 Mo pour Phi-3. Cette valeur est fausse : le
fichier de 640 Mo attendu correspond au TinyLlama fusionné puis quantifié, pas à Phi-3 Mini.

Le paramètre `USE_GGUF_MODE` existe dans la configuration, mais `nlp_service.py` ne contient pas
encore de chemin d'inférence GGUF. Le SQL utilise donc toujours le modèle Hugging Face complet et
le LoRA via PyTorch.

## 6. Matériel local observé

- Intel Core i7-4510U à 2,00 GHz : 2 cœurs / 4 processeurs logiques.
- 7,89 Go de RAM ; 1,34 Go disponibles au moment de la mesure.
- Intel HD Graphics 4400 intégrée, mémoire partagée.
- Aucun runtime NVIDIA/CUDA détecté.

La « mémoire GPU 2 Go » annoncée par Windows est de la mémoire partagée de l'iGPU. Elle ne se
comporte pas comme 2 Go de VRAM CUDA et n'accélère pas la pile PyTorch actuelle. Charger en même
temps TinyLlama PyTorch, Phi-3 Q4, Next.js, FastAPI, WSL et Docker est très serré avec 8 Go de RAM.

## 7. Résultats historiques récupérés

| Évaluation | Résultat |
|---|---:|
| Régression V11 ciblée | 4/10, soit 40 % |
| Benchmark varié 15 questions | 8/15, soit 53,33 % |
| Benchmark complexe | 25/50, soit 50 % |
| Benchmark V13, contrôle textuel | 12 OK, 6 avertissements, 2 échecs sur 20 |
| Test terrain V12 | réponses de 24,6 à 48,3 secondes ; plusieurs erreurs SQL |

Les erreurs récurrentes concernent la confusion utilisateur/objet/poste, les connexions `LOGON`,
les périodes en heures ou mois, les agrégations et les noms de colonnes inventés.

Le rapport V15 affiche des scores élevés, mais il ne constitue pas encore une mesure fiable de
généralisation. Il utilise surtout des contrôles de sous-chaînes, contient des cas proches des
données synthétiques et son test du mot `USERNAME` déclenche aussi sur `DBUSERNAME`.

## 8. Dataset et notebook récupérés

- Dataset V15 avec provenance : 17 296 lignes, 17 156 instructions uniques et 3 100 sorties SQL
  uniques.
- Dataset V11 correctif : cinq cas d'erreurs réelles documentés.
- Notebook de référence récupéré : `research/notebooks/tinyllama_oracle_v13_dataset.ipynb`.

Constats sur le notebook V13 :

- TinyLlama est chargé en FP16 sur GPU Colab ;
- LoRA r=32 cible les sept projections principales ;
- 9 500 exemples, longueur 512, batch 2, accumulation 4, quatre époques, LR `1.5e-4` ;
- le prompt utilisateur est masqué dans les labels, ce qui est correct pour l'apprentissage de la
  réponse SQL ;
- aucun jeu de validation séparé ni `eval_dataset` n'est défini ;
- aucune métrique SQL n'est calculée pendant l'entraînement ;
- les sorties conservées montrent le lancement, mais pas la fin de l'entraînement ni un bilan
  reproductible ;
- `prepare_model_for_kbit_training()` est appelé alors que le modèle n'est pas chargé en 4 bits ;
- le dataset V15 plus récent n'est pas intégré dans ce notebook V13.

Conclusion : le notebook est une bonne trace expérimentale, mais il doit être refactorisé avant un
nouvel entraînement de référence.

## 9. Sécurité et défauts techniques connus

1. `validate_sql_guardrails()` retourne toujours `(True, "OK")`.
2. `dynamic_guardrails_service.py` n'est pas appelé par `main.py`.
3. Le SQL généré est envoyé directement à Oracle après un nettoyage superficiel.
4. Des identifiants Oracle de laboratoire et un mot de passe administrateur par défaut sont codés
   dans la configuration et présents dans les données runtime historiques.
5. `GET /api/settings` peut retourner le mot de passe Oracle dans le schéma actuel.
6. Le cache de réponses dure une heure, n'est pas segmenté par utilisateur ni par période et peut
   rendre une réponse temporelle périmée.
7. Les jobs, le cache et l'historique sont en mémoire ; le backend doit rester à un seul worker.
8. La documentation `backend/README.md` annonce un repli SQL déterministe, mais ce repli n'existe
   pas dans `nlp_service.py`.
9. L'interface masque certaines métadonnées, mais cela n'est pas une autorisation de sécurité.

## 10. Décision d'architecture recommandée

Conserver le fine-tuning comme axe de recherche comparatif, mais ne plus faire dépendre la sûreté
du système de la génération libre du modèle.

Pipeline cible, entièrement local et utilisable avec un seul modèle chargé en mémoire :

1. maintenir un catalogue local des vues d'audit, colonnes, types, synonymes et relations ;
2. détecter l'intention, les utilisateurs, objets, actions, dates et limites avec le modèle ;
3. demander une précision si un paramètre indispensable est absent ou contradictoire ;
4. construire un SQL depuis un AST ou des gabarits autorisés ;
5. valider la table, les colonnes, les fonctions et le caractère lecture seule ;
6. exécuter avec un compte Oracle strictement en lecture seule ;
7. rappeler le même modèle avec la question et le résultat contrôlé pour formuler la réponse ;
8. vérifier que la synthèse conserve les nombres, dates et identités retournés par Oracle.

Le modèle recommandé à évaluer en premier est Qwen3-1.7B GGUF Q4_K_M, face à
Qwen2.5-Coder-1.5B GGUF Q4_K_M et au TinyLlama-LoRA actuel. Aucun nouvel entraînement ne sera lancé
avant un benchmark local identique des trois candidats.

Cette stratégie conserve l'intérêt IA du mémoire : comparaison entre modèle seul, prompt seul,
LoRA et pipeline hybride contraint.

## 11. Stratégie locale recommandée

- Priorité 1 : utiliser la synthèse par règles et ne pas charger Phi-3 par défaut.
- Priorité 2 : fusionner TinyLlama + LoRA puis produire un GGUF Q4_K_M d'environ 0,6 à 0,8 Go.
- Priorité 3 : brancher réellement l'inférence GGUF avec `llama.cpp`.
- Priorité 4 : limiter le contexte et les tokens, puis mesurer latence, RAM et exactitude.
- Priorité 5 : comparer TinyLlama-LoRA à un petit modèle orienté code, sans migrer avant un
  benchmark aveugle identique.

Docker et WSL facilitent la reproductibilité et le futur déploiement Oracle Linux, mais ils ne
rendent pas le modèle plus léger. Sur cette machine de 8 Go, l'exécution native Windows ou WSL du
backend et du frontend sera généralement plus économe pendant le développement. Docker doit être
validé ensuite comme cible d'intégration.

## 12. Prochain plan de travail

- [x] Restaurer une base Git locale reliée à `origin` sans pousser les secrets ni les modèles.
- [ ] Créer un environnement Python compatible ; Python 3.14 installé actuellement est trop récent
  pour garantir les versions figées de Torch, PEFT et llama-cpp-python.
- [x] Installer, vérifier les types et construire le frontend sous Windows.
- [ ] Lancer le backend sans Oracle avec des tests unitaires de génération/validation.
- [ ] Réactiver et tester les garde-fous avant toute connexion Oracle.
- [ ] Masquer les secrets et remplacer les identifiants par défaut.
- [ ] Créer un benchmark aveugle versionné avec séparation train/validation/test par gabarit.
- [ ] Refactoriser le notebook V15 et entraîner sur Colab, pas sur ce PC.
- [ ] Convertir le TinyLlama-LoRA retenu en GGUF Q4_K_M.
- [ ] Mesurer trois variantes : règles seules, TinyLlama-LoRA, petit modèle code + contraintes.
- [ ] Tester le déploiement WSL/Docker une fois le chemin natif stable.

## 13. Règles de continuité

- Mettre ce fichier à jour après chaque séance utile.
- Enregistrer les résultats négatifs autant que les succès.
- Ne jamais mélanger les exemples d'entraînement avec le benchmark final.
- Conserver le prompt, la version du dataset, le hash du modèle et les paramètres avec chaque
  résultat.
- Ne pas publier les poids, bases SQLite, `.env`, mots de passe ou données Oracle dans Git.

## 14. Journal de reprise — 12 septembre 2026

### Méthode de continuité

Après chaque lot validé, ce fichier doit recevoir : le résultat obtenu, les décisions, les fichiers concernés, les commandes utiles, les limites et la prochaine action. Il doit permettre une reprise autonome dans une nouvelle discussion.

### Environnement local constaté

- Intel Core i7-4510U : 2 cœurs physiques / 4 threads, environ 8 Go de RAM, Intel HD 4400 partagé, sans CUDA.
- Windows : Python 3.14.6 et Node.js 22.20.
- WSL2 : Oracle Linux 9.5 avec Docker Engine 29.6.1.
- Avant redémarrage, WSL voit environ 3,8 Gio de RAM et 1 Gio de swap. Les 16 Go ajoutés au fichier d'échange SSD amélioreront surtout la stabilité après redémarrage, pas la vitesse du modèle.
- Le démarrage automatique d'Oracle retardait WSL et provoquait des interruptions. Le conteneur a reçu à l'exécution la politique de redémarrage `no`. Le fichier Compose doit encore être aligné. Oracle doit être démarré seulement pendant les essais, puis arrêté pour libérer la mémoire.

### Oracle local créé et validé

- Image officielle Oracle AI Database Free 26ai ; version rapportée `23.26.3.0.0`.
- Conteneur `auditai-oracle`, port `1521`.
- Infrastructure dans `infra/oracle/` : Compose, exemple d'environnement, script de création et documentation.
- Propriétaire : `SMART2DSECU`. Compte applicatif en lecture seule : `AUDITAI_READER`.
- Tables : `SMART2DSECU.UNIFIED_AUDIT_DATA` et `SMART2DSECU.AUDITAI_SEMANTIC_CATALOG`.
- Colonnes d'audit : `ID`, `AUDIT_TYPE`, `SESSIONID`, `OS_USERNAME`, `USERHOST`, `TERMINAL`, `AUTHENTICATION_TYPE`, `DBUSERNAME`, `CLIENT_PROGRAM_NAME`, `OBJECT_SCHEMA`, `OBJECT_NAME`, `SQL_TEXT`, `SQL_BINDS`, `EVENT_TIMESTAMP`, `ACTION_NAME`, `RETURNCODE`, `INSTANCE`.
- Index sur la date, l'utilisateur, l'objet et l'action.
- 5 003 événements simulés sur 90 jours, avec les utilisateurs, objets et actions du travail V15.
- Vérifications : 5 003 événements, 39 aujourd'hui, 79 hier, requête « vendredi dernier » fonctionnelle, et refus d'un `DELETE` par Oracle avec le compte lecteur (`ORA-41900`).
- Exemple validé : « qui a supprimé des données sur CLIENT hier ? » retourne `CYRILLE | DELETE | CLIENT | 2026-09-10 14:00:00 | poste-rh-07`.
- Connexion Windows réussie avec `python-oracledb 3.4.2`. La version épinglée `2.4.1` ne s'installe pas sous Python 3.14 sans compilation MSVC. Il faudra utiliser Python 3.12 avec les anciens verrous ou actualiser les dépendances pour Python 3.14.

### Secrets à corriger

- Le fichier local ignoré `backend_runtime_settings.json` conserve d'anciens identifiants du laboratoire et surcharge les variables d'environnement.
- L'API de paramètres peut actuellement renvoyer et persister `oracle_password` en clair.
- Une tentative d'enregistrer le nouveau mot de passe local a été bloquée automatiquement à cause de cette persistance en clair.
- Solution retenue : mot de passe injecté par variable d'environnement au lancement, jamais renvoyé par l'API et jamais persisté. Cette correction est obligatoire avant l'intégration finale.

### Modèles ajoutés et mesures

- TinyLlama Safetensors existant : environ 2,2 Go ; adaptateur LoRA : environ 101 Mo.
- Phi-3 Mini GGUF Q4 existant : environ 2,39 Go.
- Qwen3-1.7B GGUF Q8_0 ajouté localement : environ 1,75 Gio.
- Qwen2.5-Coder-1.5B-Instruct GGUF Q4_K_M ajouté localement : environ 1,07 Gio.
- Moteur : `llama.cpp` Windows CPU, serveur `127.0.0.1`, contexte 2 048, 4 threads, parallélisme 1.
- Qwen3 Q8, prompt minimal : 51,69 s et filtre `CLIENT` oublié.
- Qwen3 Q8, catalogue sémantique et exemple : SQL correct en 69,22 s, environ 3,1 tokens/s en génération.
- Qwen2.5-Coder Q4, même contexte : SQL correct en 28,34 s, environ 7,4 tokens/s.
- Synthèse Qwen2.5-Coder d'un résultat Oracle : 23,39 s avec chargement ; réponse française correcte.
- Avec un exemple adapté, Qwen2.5-Coder produit une clarification ciblée correcte.
- TinyLlama + LoRA via PyTorch : aucune réponse après plus de quatre minutes sur ce CPU ; exécution interrompue. Cette variante n'est pas exploitable telle quelle sur ce PC.

### Benchmark SQL libre

- Corpus : `research/benchmarks/model_comparison_cases.json`, 30 cas sur dates, actions, utilisateurs, objets, agrégats, ambiguïtés et demandes destructrices.
- Qwen2.5-Coder en génération SQL libre : score structurel moyen `0,564`, seulement `5/28` requêtes exécutées avec succès par Oracle, latence moyenne `15,357 s`.
- Erreurs : `LIMIT` non Oracle, interrogation de tables métier au lieu du journal, utilisateurs/actions/périodes inventés, ambiguïtés mal traitées.
- Échec critique : pour « Supprime toutes les lignes de CLIENT », le modèle a généré `DELETE FROM CLIENT;` malgré la consigne de refus.
- Décision ferme : aucun SQL libre produit par un modèle ne doit atteindre Oracle. Le compte lecteur reste une deuxième barrière.

### Architecture retenue après mesure

Un seul modèle local, actuellement Qwen2.5-Coder-1.5B-Instruct Q4_K_M, est appelé avec deux rôles séparés :

1. produire une intention JSON structurée depuis la question ;
2. synthétiser en français les lignes contrôlées revenues d'Oracle.

Du code déterministe valide l'intention et construit le SQL Oracle. L'intention contient au minimum : statut (`query`, `clarification`, `refusal`), utilisateurs, objets, actions, période normalisée, agrégat, échecs uniquement et clarification. Le constructeur n'autorise que `SELECT` ou `WITH` sur `SMART2DSECU.UNIFIED_AUDIT_DATA`, utilise des paramètres liés, impose une limite et traite `DELETE`, `GRANT`, `TRUNCATE`, etc. comme valeurs de `ACTION_NAME`, jamais comme commandes.

Cette approche garde l'adaptation au langage naturel dans le modèle et confie la syntaxe ainsi que la sécurité à du code testable. Aucun nouveau LoRA ne sera lancé avant la mesure complète de ce pipeline.

### État du code à corriger

- `dynamic_guardrails_service.py` existe mais n'est pas branché au flux principal.
- `nlp_service.validate_sql_guardrails()` retourne toujours `(True, "OK")`.
- Le SQL généré est actuellement envoyé directement à `execute_sql()`.
- Le backend utilise encore TinyLlama + LoRA pour le SQL et Phi-3 pour la synthèse.
- Le frontend compile ; l'audit npm est à zéro après les mises à jour.
- Le backend passe `python -m compileall -q backend/app`.

### Plan restant, dans l'ordre

- [ ] Construire et exécuter le benchmark « intention JSON → SQL sûr » sur les 30 cas avec Oracle.
- [ ] Versionner son rapport et inscrire ses mesures ici.
- [ ] Implémenter le schéma d'intention, la validation, les clarifications et le constructeur SQL Oracle à paramètres liés.
- [ ] Remplacer le flux à deux modèles par un serveur local unique Qwen2.5-Coder via `llama.cpp`, avec prompts séparés.
- [ ] Brancher les garde-fous avant toute exécution et conserver le compte Oracle en lecture seule.
- [ ] Corriger la gestion des secrets et l'API de paramètres.
- [ ] Adapter l'interface aux réponses, refus et clarifications, en gardant les trois catalogues utilisateurs/objets/actions.
- [ ] Exécuter les tests backend, frontend et les scénarios hors ligne de bout en bout.
- [ ] Mesurer RAM, latence, exactitude et stabilité, puis décider si un LoRA est utile.
- [ ] Nettoyer les artefacts temporaires et créer des commits locaux. Ne pas pousser sans demande explicite.
## 15. Lot 1 terminé — pipeline d'intention sûr

Fichiers ajoutés :

- `backend/app/services/safe_sql_builder.py` : constructeur Oracle à paramètres liés, table unique autorisée, listes d'actions/périodes/agrégats fermées, limite maximale 200.
- `backend/app/services/intent_policy.py` : ancrage des utilisateurs et objets dans les catalogues, suppression des entités inventées, normalisation des actions/dates/agrégats, refus des ordres de mutation et clarification des références ambiguës.
- `research/benchmarks/benchmark_safe_intent_pipeline.py` : appel Qwen local, normalisation, construction SQL, exécution avec `AUDITAI_READER` et rapport JSON.
- `research/benchmarks/qwen25coder_safe_intent_results.json` : résultats détaillés.
- `research/benchmarks/RAPPORT_PIPELINE_SUR.md` : comparaison lisible.

Résultats successifs :

1. SQL libre : score 0,564, Oracle 5/28, un `DELETE FROM CLIENT` généré.
2. Intention JSON brute : score 0,744, statut correct 86,7 %, 26/28 exécutions, zéro SQL dangereux, 9,739 s en moyenne.
3. Intention ancrée et normalisée : score 1,000 sur les 30 cas de développement, 25/25 lectures exécutées, quatre clarifications/refus sans SQL, zéro SQL dangereux, 8,409 s de latence modèle moyenne.

Décision : intégrer la troisième architecture. Le score 30/30 n'est pas présenté comme une mesure de généralisation, car les règles ont été corrigées avec ce corpus. Un corpus de paraphrases séparé reste nécessaire.

Prochaine reprise précise : brancher `normalize_intent()` et `build_safe_audit_query()` dans FastAPI, faire accepter les paramètres liés par `oracle_service`, puis remplacer l'appel TinyLlama par le serveur Qwen local.

## 16. Lot 2 terminé — intégration backend, interface et secrets

### Changements backend

- `local_model_service.py` appelle le serveur Qwen local sur `127.0.0.1:8080` pour extraire l'intention JSON et, pour les résultats multiples, produire une synthèse française.
- Les réponses à zéro ou une ligne et les agrégats utilisent une synthèse déterministe afin de conserver exactement les nombres et identités. Exemple vérifié : « L'action la plus fréquente est SELECT, avec 626 événement(s). »
- `oracle_service.execute_sql()` accepte maintenant un dictionnaire de paramètres liés.
- `fetch_intent_catalog()` récupère tous les utilisateurs et objets Oracle afin d'ancrer les entités.
- `main.py` n'appelle plus TinyLlama ni Phi-3. Il exécute : catalogue → intention Qwen → normalisation → SQL sûr → Oracle → synthèse.
- Les réponses API exposent `intent_status` (`query`, `clarification`, `refusal`) et `clarification`.
- Une clarification ne produit aucun SQL. Un refus ne produit aucun SQL et pose `blocked=true`.
- Le cache a été ramené d'une heure à 60 secondes pour limiter les réponses temporelles périmées.
- L'état de santé expose le serveur de modèle unique.

### Secrets

- Les valeurs locales par défaut sont désormais `AUDITAI_READER@127.0.0.1:1521/FREEPDB1`.
- Le mot de passe par défaut est vide.
- `settings_service.py` ignore tout ancien mot de passe sur disque, ne persiste jamais `oracle_password` et renvoie toujours ce champ vide à l'interface.
- Un mot de passe saisi par un administrateur peut vivre en mémoire pendant le processus, sans être écrit.
- Le fichier local `backend_runtime_settings.json` a été nettoyé de tout champ mot de passe et pointe vers Oracle local.
- Les tests injectent `ORACLE_PASSWORD` uniquement dans l'environnement du processus.

### Interface

- Le frontend conserve le vrai champ `blocked` au lieu de le forcer à `false`.
- Les cartes de résultat distinguent visuellement une réponse, une clarification et un refus.
- Le champ de mot de passe vide signifie « conserver la valeur courante ».
- Les trois colonnes utilisateurs, objets et actions restent disponibles.

### Validations

- Trois branches du pipeline central testées : lecture paramétrée, clarification sans Oracle, refus destructeur sans SQL.
- Test Oracle agrégé réel : `SELECT` est l'action la plus fréquente avec 626 événements.
- `backend/tests/test_safe_pipeline.py` : 8 tests passés, couvrant ancrage des entités, refus, ambiguïté, paramètres liés, limite, dialecte Oracle, action inconnue et fidélité des agrégats.
- `python -m compileall -q backend/app` : réussi.
- `npm run build` : réussi.
- `npx tsc --noEmit` : réussi.

Prochaine reprise précise : créer des lanceurs locaux qui démarrent Oracle, `llama-server`, FastAPI et Next.js avec les secrets uniquement en environnement ; aligner Compose sur `restart: "no"` ; tester les routes HTTP authentifiées puis l'arrêt propre.

## 17. Lot 3 terminé — lancement local reproductible

### Fichiers et dépendances

- `scripts/start-local.ps1` démarre WSL/Oracle, Qwen avec llama.cpp, FastAPI et Next.js, tous liés à `127.0.0.1`.
- `scripts/test-local.ps1` réalise un contrôle HTTP authentifié de bout en bout.
- `scripts/stop-local.ps1` arrête les processus applicatifs et Oracle.
- `LOCAL_RUN.md` documente les trois commandes.
- Les 52 fichiers llama.cpp, environ 65,2 Mo, ont été copiés dans `tools/llama.cpp/`, dossier ignoré par Git, afin de ne plus dépendre du dossier temporaire Windows.
- `backend/requirements.txt` ne contient plus Torch, Transformers, PEFT, llama-cpp-python ni Pandas. Le runtime actif utilise FastAPI, Uvicorn, Pydantic, python-dotenv et `oracledb>=3.4.2,<4`.
- Les dépendances historiques d'entraînement sont conservées dans `research/requirements-legacy-training.txt`.
- `infra/oracle/compose.yaml` utilise maintenant `restart: "no"`.

### Compte administrateur

- Le mot de passe `Admin@123` n'est plus codé en dur.
- Le compte initial lit `AUDITAI_ADMIN_USERNAME` et `AUDITAI_ADMIN_PASSWORD`.
- Le lanceur crée au besoin un mot de passe aléatoire dans `infra/oracle/.env`, fichier ignoré par Git, sans l'afficher à l'écran.
- Le mécanisme historique de restauration du compte ne fonctionne que si cette variable secrète est définie.

### Test réel réussi

La commande `scripts/test-local.ps1` a validé :

- API : OK ;
- Oracle : connecté ;
- modèle : chargé ;
- 9 utilisateurs et 14 objets visibles dans les catalogues filtrés de l'interface ;
- mot de passe Oracle masqué dans `GET /api/settings` ;
- frontend : HTTP 200 ;
- lecture agrégée : une ligne ;
- ambiguïté : `clarification`, sans SQL ;
- ordre destructeur : `refusal`, `blocked=true`, sans SQL.

Le script PowerShell doit conserver un BOM UTF-8 pour que Windows PowerShell 5 transmette correctement les questions accentuées. Cette contrainte a été corrigée et testée.

Le cycle d'arrêt a libéré les ports 3000, 8000, 8080 et 1521.

Prochaine reprise précise : construire un corpus de paraphrases jamais utilisé pour corriger les règles, mesurer la généralisation du pipeline, puis relever la RAM et les temps du système complet.

## 18. Lot 4 terminé — généralisation, performance et décision finale

### Paraphrases séparées

- v1, 20 formulations nouvelles avant correction : score 0,862 ; statuts 85 % ; Oracle 18/18 ; zéro SQL dangereux ; 9,796 s.
- v2, 12 formulations nouvelles avant correction : score 0,819 ; statuts 83,3 % ; Oracle 12/12 ; zéro SQL dangereux ; 6,558 s.
- v3, 12 formulations figées avant correction : score 0,891 ; statuts 83,3 % ; Oracle 12/12 ; zéro SQL dangereux ; 6,770 s.
- Les résultats v1/v2 ont servi à élargir le catalogue sémantique. Le premier score v3 de 0,891 est la mesure de généralisation à citer.
- Après correction des écarts v3, la non-régression repasse à 1,000, avec 10/10 lectures Oracle, deux clarifications/refus sans SQL, zéro SQL dangereux et 8,589 s. Ce dernier chiffre valide les corrections mais n'est pas présenté comme aveugle.
- Le modèle comprend utilement des synonymes inconnus des règles. La politique accepte désormais ses périodes, actions et agrégats uniquement lorsque la question contient un indice correspondant et que la valeur appartient à une liste fermée.

### RAM du système complet

Mesure avec Windows, WSL, Oracle, Qwen, FastAPI et Next.js démarrés :

- 7,89 Go de RAM physique ;
- 7,30 Go utilisés et seulement 0,59 Go libres ;
- Oracle Docker : environ 1,622 Gio ;
- Qwen llama-server : environ 0,990 Go de working set ;
- WSL/vmmem : environ 1,523 Go observé ;
- processus Node principal : environ 138 Mo, plus auxiliaires ;
- FastAPI au repos : environ 11 Mo.

Conclusion matérielle : le projet fonctionne avec 8 Go mais n'est pas confortable. Les 16 Go de swap SSD ajoutés éviteront certains arrêts après redémarrage, mais ne rendront pas l'inférence plus rapide. Pour une exécution fluide de toute la pile, viser 16 Go de RAM physique. Avec 8 Go, fermer les autres applications et démarrer les services uniquement pour la démonstration.

### Validation finale HTTP

Après rechargement du code final, le test HTTP authentifié confirme : API OK, Oracle connecté, modèle chargé, catalogues remplis, secret masqué, frontend HTTP 200, agrégat exécuté, ambiguïté clarifiée et « Purge immédiatement CLIENT » refusé sans SQL.

Fichier de synthèse : `research/benchmarks/RAPPORT_EVALUATION_FINALE.md`.

Prochaine reprise précise : nettoyer les artefacts temporaires, vérifier Git et toutes les validations une dernière fois, mettre à jour la documentation racine, créer un commit local, puis arrêter les services.
## 19. Clôture de la reprise du 13 septembre 2026

Le plan de reprise défini dans les sections 14 à 18 est exécuté :

- base Oracle locale créée, nourrie et protégée par un lecteur sans privilège d'écriture ;
- modèle unique Qwen2.5-Coder Q4 choisi après comparaison locale ;
- génération SQL libre supprimée du chemin actif ;
- intention JSON, ancrage sémantique, clarifications et refus intégrés ;
- constructeur Oracle déterministe à paramètres liés intégré ;
- synthèse exacte pour les agrégats et modèle local pour les résultats multiples ;
- TinyLlama/Phi-3 retirés du runtime actif et conservés comme recherche historique ;
- secrets retirés des valeurs codées en dur, du fichier runtime et des réponses API ;
- scripts de démarrage, test et arrêt locaux validés ;
- frontend adapté et trois catalogues conservés ;
- benchmarks de développement, paraphrases et non-régression versionnés ;
- mémoire physique mesurée et recommandation de 16 Go documentée.

Dernières validations :

- `python -m compileall -q backend/app` : réussi ;
- `python -m unittest discover -s tests -v` : 10/10 tests réussis ;
- `npx tsc --noEmit` : réussi ;
- `npm run build` : réussi ;
- test HTTP authentifié complet : réussi ;
- `git diff --check` : réussi ;
- recherche des anciens identifiants dans le runtime actif : aucune occurrence ;
- services arrêtés après validation pour libérer la RAM.

Pour reprendre : lire d'abord les sections 14 à 19, puis `LOCAL_RUN.md`. La commande normale est `powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1`. Le projet est prêt pour les essais utilisateur et la préparation de la soutenance. Les améliorations futures doivent ajouter un nouveau corpus aveugle avant toute modification sémantique, afin de conserver une mesure honnête.
