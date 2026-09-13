# Mémoire vivante — Audit AI / ASKSMART

Dernière mise à jour : 13 septembre 2026

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

## 20. État de référence complet pour la reprise et la rédaction technique — 13 septembre 2026

> Cette section est la référence actuelle. Les sections 3 à 12 décrivent en partie l'architecture récupérée avant sa modernisation ; elles sont conservées comme historique expérimental. Le runtime actif est celui décrit ici et dans les lots 15 à 19.

### 20.1 Résumé exécutif

AuditAI, aussi nommé ASKSMART dans certains fichiers historiques, est un assistant local d'analyse des journaux d'audit Oracle destiné à des utilisateurs non informaticiens. L'utilisateur formule librement une question en français. Le système identifie les utilisateurs, objets, actions, périodes et calculs demandés, construit une lecture Oracle sûre, exécute cette lecture avec un compte sans droit d'écriture, puis présente le résultat sous forme de tableau et d'explication simple.

La version récupérée utilisait deux modèles : TinyLlama 1.1B avec un adaptateur LoRA pour générer librement le SQL, puis Phi-3 Mini pour rédiger la synthèse. Les mesures locales ont montré que cette architecture était trop lente sur le PC actuel, consommait inutilement la mémoire et ne sécurisait pas suffisamment l'exécution. Le runtime actif utilise maintenant un seul modèle, Qwen2.5-Coder-1.5B-Instruct Q4_K_M. Qwen comprend la question et produit une intention JSON ; du code déterministe contrôlé produit ensuite le SQL Oracle. Le même Qwen peut résumer les résultats comportant plusieurs lignes. Les résultats simples utilisent une synthèse déterministe pour conserver exactement les valeurs.

Le projet fonctionne localement de bout en bout. Oracle, le modèle, l'API et l'interface ont été testés ensemble. La principale étape scientifique restante est d'élargir l'évaluation aveugle, surtout pour mesurer la qualité des explications destinées aux utilisateurs non techniques. Aucun score actuel ne permet d'affirmer que le système ne commettra jamais d'erreur.

### 20.2 Besoin utilisateur et périmètre fonctionnel

Le public visé comprend les auditeurs, responsables de sécurité, managers et agents métier qui ne connaissent ni SQL ni le schéma physique de la base. L'interface met à leur disposition trois catalogues :

1. les utilisateurs Oracle visibles ;
2. les tables ou objets audités ;
3. les actions observables, accompagnées d'une explication simple.

Les actions telles que SELECT, INSERT, UPDATE, DELETE, GRANT, REVOKE, ALTER ou TRUNCATE désignent des événements déjà enregistrés dans le journal. Elles ne donnent pas à l'application le droit d'exécuter ces opérations.

Exemples de besoins couverts : identifier qui a consulté ou modifié une table, rechercher une suppression, examiner les activités d'un utilisateur, retrouver les connexions échouées, comparer aujourd'hui et hier, rechercher une période telle que vendredi dernier, cette semaine ou les trente derniers jours, compter des utilisateurs distincts et identifier l'action, l'utilisateur, le poste ou l'objet le plus fréquent.

Une question libre n'est pas comparée à une liste de phrases mémorisées. Qwen réalise une interprétation sémantique à chaque demande. Les formulations « Qui a modifié CLIENT hier ? », « Quelle personne a touché à la table CLIENT pendant la journée d'hier ? » et « Y a qui qui a changé CLIENT hier ? » doivent converger vers la même intention. La limite fonctionnelle porte sur les informations réellement présentes dans le journal et les familles d'analyses prises en charge, pas sur une liste fermée de phrases.

### 20.3 Pipeline actif

Le chemin d'exécution actuel est :

~~~text
Navigateur Next.js
    -> API FastAPI authentifiée
    -> lecture des catalogues Oracle
    -> Qwen : question française vers intention JSON
    -> politique d'intention : ancrage, normalisation, clarification ou refus
    -> constructeur SQL Oracle en lecture seule avec paramètres liés
    -> exécution par AUDITAI_READER
    -> tableau exact
    -> synthèse déterministe ou synthèse Qwen contrôlée
    -> réponse française
~~~

L'intention JSON contient : le statut, les utilisateurs, les objets, les actions, la période, l'agrégat, l'indicateur d'échecs uniquement, la limite et un éventuel message de clarification. Les statuts possibles sont query, clarification et refusal.

Le caractère intelligent se situe dans la compréhension de la langue, des synonymes, du contexte et des combinaisons de critères. Le caractère déterministe se situe dans la sécurité, le dialecte Oracle, les paramètres liés et les calculs autorisés. Cette séparation conserve la flexibilité linguistique sans faire confiance à un texte SQL inventé par le modèle.

### 20.4 Pourquoi le SQL libre a été abandonné

Le benchmark de 30 cas avec Qwen2.5-Coder produisant directement du SQL a obtenu un score structurel moyen de 0,564. Seulement 5 requêtes sur 28 devant être exécutées ont réussi dans Oracle. Les erreurs incluaient l'emploi de LIMIT, qui n'est pas le dialecte Oracle attendu, l'interrogation de tables métier au lieu du journal, l'invention d'utilisateurs, d'actions ou de périodes et la mauvaise gestion des ambiguïtés.

Le cas critique « Supprime toutes les lignes de CLIENT » a conduit le modèle à générer DELETE FROM CLIENT malgré une consigne de refus. Le compte AUDITAI_READER aurait bloqué l'écriture, mais cette expérience démontre qu'une consigne textuelle ne constitue pas à elle seule une barrière de sécurité.

La version active ne transmet jamais du SQL libre du modèle à Oracle. Le constructeur n'accepte que le statut query, une liste fermée d'actions, de périodes et d'agrégats, la table SMART2DSECU.UNIFIED_AUDIT_DATA et une limite maximale de 200 lignes. Les valeurs d'utilisateur, d'objet et d'action passent par des paramètres liés ; elles ne sont pas concaténées dans le SQL.

### 20.5 Comparaison des modèles

| Variante | Taille | Usage évalué | Résultat local | Décision |
|---|---:|---|---|---|
| TinyLlama-1.1B + LoRA r=32 | environ 2,2 Go + 101 Mo | SQL libre via PyTorch | aucune réponse après plus de quatre minutes sur ce CPU | retiré du runtime, conservé comme expérience historique |
| Phi-3-mini-4k-instruct Q4_K_M | environ 2,39 Go | synthèse française | charge un second modèle et augmente la pression mémoire | retiré du runtime actif |
| Qwen3-1.7B Q8_0 | environ 1,75 Gio | SQL avec prompt minimal puis enrichi | 51,69 s avec oubli du filtre CLIENT ; 69,22 s avec résultat correct | correct mais trop lent ici |
| Qwen2.5-Coder-1.5B-Instruct Q4_K_M | environ 1,07 Gio | intention et synthèse via llama.cpp | 28,34 s avec chargement ; environ 6 à 10 s avec serveur persistant | modèle actif |

Qwen2.5-Coder a été choisi pour son compromis entre compréhension, respect du format JSON, vitesse, taille et exécution CPU. La quantification Q4_K_M réduit la mémoire et accélère l'inférence avec une perte de qualité limitée. Le modèle est servi par llama.cpp sur 127.0.0.1:8080, avec un contexte de 2 048 tokens, quatre threads et une requête simultanée.

### 20.6 Signification exacte des scores

La loss est une mesure calculée pendant l'entraînement. Aucun nouvel entraînement de Qwen n'a été réalisé dans cette reprise ; il n'existe donc aucune nouvelle loss Qwen à annoncer. Une loss basse ne suffit pas à prouver la validité Oracle, la sécurité ou la qualité des réponses.

| Évaluation | Cas | Score | Statuts corrects | Exécutions Oracle | SQL dangereux | Latence modèle |
|---|---:|---:|---:|---:|---:|---:|
| SQL libre Qwen | 30 | 0,564 | non mesuré | 5/28 | 1 généré | 15,357 s |
| intention JSON brute | 30 | 0,744 | 86,7 % | 26/28 | 0 | 9,739 s |
| pipeline normalisé, développement | 30 | 1,000 | 100 % | 25/25 | 0 | 8,409 s |
| paraphrases v1 avant correction | 20 | 0,862 | 85 % | 18/18 | 0 | 9,796 s |
| paraphrases v2 avant correction | 12 | 0,819 | 83,3 % | 12/12 | 0 | 6,558 s |
| paraphrases v3 figées, premier passage | 12 | 0,891 | 83,3 % | 12/12 | 0 | 6,770 s |
| v3 après correction, non-régression | 12 | 1,000 | 100 % | 10/10 | 0 | 8,589 s |

Le score 0,891, soit 89,1 %, est la mesure de généralisation à citer actuellement, car elle correspond au premier passage sur le jeu v3 avant adaptation. Le score 1,000 après correction signifie seulement que les cas connus ne régressent plus. Il ne garantit pas une précision universelle de 100 %. Les corpus v1 et v2 ont servi au développement et ne doivent plus être présentés comme tests aveugles.

Le corpus de questions est un banc d'essai versionné associant des questions à des intentions attendues. Il ne constitue pas une base de réponses consultée pendant l'utilisation. Une question jamais vue peut réussir si le modèle en comprend le sens et si la demande appartient au périmètre couvert.

### 20.7 État de la synthèse destinée aux non-informaticiens

Pour zéro ligne, une ligne ou un agrégat, la réponse est construite par des règles. Exemples : « Aucune activité ne correspond à cette demande », « L'action la plus fréquente est SELECT, avec 626 événement(s) » ou une description d'un événement avec utilisateur, action, objet, date et poste. Le test unitaire vérifie que le nom SELECT et le nombre 626 sont conservés. Le test HTTP de bout en bout valide également une réponse agrégée réelle.

Pour plusieurs lignes, Qwen reçoit la question, le nombre total de lignes et au maximum 25 lignes contrôlées. Le prompt lui impose une réponse française de une à cinq phrases, la conservation exacte des noms, nombres, dates, heures et postes, l'absence d'invention et l'absence de jargon SQL. En cas d'échec du modèle, le système revient à une réponse déterministe indiquant le nombre d'événements et renvoie le tableau détaillé.

Cette partie est fonctionnelle mais n'a pas encore reçu un benchmark humain assez large. Il est donc interdit d'affirmer que toutes les synthèses multilignes sont parfaitement fidèles ou accessibles. La prochaine évaluation doit mesurer séparément : fidélité aux lignes Oracle, conservation des nombres et identités, couverture des faits importants, absence d'hallucination, simplicité du français et utilité de la clarification.

### 20.8 Base Oracle locale et données disponibles

L'infrastructure se trouve dans infra/oracle. Docker utilise l'image officielle container-registry.oracle.com/database/free:latest, identifiée pendant les essais comme Oracle AI Database Free 26ai, version rapportée 23.26.3.0.0. Le conteneur s'appelle auditai-oracle, publie le port 1521 et utilise le service FREEPDB1. Le volume Docker auditai_oradata conserve les données. La politique restart: "no" évite de charger Oracle automatiquement et de saturer la machine.

Deux comptes applicatifs ont été créés :

- SMART2DSECU : propriétaire du schéma de démonstration ;
- AUDITAI_READER : compte du backend, autorisé uniquement à ouvrir une session et à lire les deux tables.

La table SMART2DSECU.UNIFIED_AUDIT_DATA contient 5 003 événements simulés répartis sur 90 jours. Son schéma est :

| Colonne | Type | Signification |
|---|---|---|
| ID | NUMBER identity | identifiant technique unique |
| AUDIT_TYPE | VARCHAR2(30) | origine ou catégorie de l'audit |
| SESSIONID | NUMBER | identifiant de session Oracle |
| OS_USERNAME | VARCHAR2(128) | utilisateur du système d'exploitation |
| USERHOST | VARCHAR2(255) | poste, serveur ou hôte source |
| TERMINAL | VARCHAR2(128) | terminal de la session |
| AUTHENTICATION_TYPE | VARCHAR2(64) | méthode d'authentification |
| DBUSERNAME | VARCHAR2(128) | utilisateur Oracle ayant réalisé l'action |
| CLIENT_PROGRAM_NAME | VARCHAR2(255) | outil client, par exemple JDBC, TOAD ou sqlplus |
| OBJECT_SCHEMA | VARCHAR2(128) | schéma propriétaire de l'objet |
| OBJECT_NAME | VARCHAR2(128) | table ou objet concerné |
| SQL_TEXT | VARCHAR2(2000) | texte SQL enregistré dans l'événement simulé |
| SQL_BINDS | VARCHAR2(2000) | valeurs liées éventuellement enregistrées |
| EVENT_TIMESTAMP | TIMESTAMP(6) | date et heure de l'événement |
| ACTION_NAME | VARCHAR2(128) | action auditée |
| RETURNCODE | NUMBER | zéro en cas de succès, valeur non nulle en cas d'échec |
| INSTANCE | NUMBER | instance Oracle concernée |

Des index existent sur EVENT_TIMESTAMP, DBUSERNAME, OBJECT_NAME et ACTION_NAME. Ils accélèrent les principaux filtres employés par l'application.

La table SMART2DSECU.AUDITAI_SEMANTIC_CATALOG contient CATEGORY, CANONICAL_NAME, DESCRIPTION_FR et SYNONYMS_FR. Sa clé primaire est le couple CATEGORY/CANONICAL_NAME. Elle documente les concepts ACTION, TIME, USER et OBJECT avec des descriptions et synonymes français. Elle sert à rapprocher le langage utilisateur des valeurs Oracle ; elle ne contient pas des réponses préfabriquées.

Les données simulées comprennent quatorze utilisateurs dans la génération, quinze objets et seize branches d'actions. Le filtrage d'affichage testé expose actuellement neuf utilisateurs et quatorze objets dans l'interface. Trois événements ciblés facilitent les démonstrations : une suppression de CLIENT par CYRILLE hier à 14 h, un GRANT sur EMPLOYEES par SYSTEM aujourd'hui à 9 h et une consultation d'EMPLOYEES par REPORT_USER le vendredi précédent.

### 20.9 Topologie d'exécution, Docker et consommation mémoire

La topologie actuellement validée privilégie la consommation réduite :

- Oracle s'exécute dans Docker sous Oracle Linux WSL2 ;
- llama-server et Qwen s'exécutent nativement sous Windows ;
- FastAPI s'exécute avec Python sous Windows ;
- Next.js s'exécute avec Node.js sous Windows ;
- tous les services écoutent uniquement sur 127.0.0.1, sauf le port Oracle publié localement par Docker.

Docker améliore l'isolation, la reproductibilité et le transport vers une autre machine. Il ne rend ni Oracle ni Qwen moins gourmands. Sous Windows, une conteneurisation complète peut ajouter la mémoire de WSL2, du moteur Docker, des images et des couches réseau. Le choix actuel est donc cohérent pour le développement sur 8 Go.

Pour la livraison, un profil Docker Compose complet pourra être ajouté afin de démarrer Oracle, le modèle, l'API et l'interface par une seule commande. Ce profil devra rester optionnel. La version légère déjà validée doit être conservée pour les machines modestes. La cohérence d'une soutenance repose aussi sur les scripts reproductibles et la documentation ; elle n'exige pas que tous les processus soient conteneurisés.

La mesure de la pile complète sur le PC actuel donne 7,89 Go de RAM physique, 7,30 Go utilisés et 0,59 Go libres. Oracle représente environ 1,622 Gio, Qwen environ 0,990 Go de working set, WSL/vmmem environ 1,523 Go, le processus Node principal environ 138 Mo plus ses auxiliaires et FastAPI environ 11 Mo au repos.

Huit gigaoctets permettent l'exécution mais laissent très peu de marge. Les 16 Go de fichier d'échange ajoutés sur le SSD amélioreront la stabilité après redémarrage, mais le swap est beaucoup plus lent que la RAM physique et n'accélère pas l'inférence. Seize gigaoctets de RAM physique sont recommandés pour une démonstration fluide. Vingt-quatre ou trente-deux gigaoctets offriraient davantage de confort pour développer et comparer des modèles plus lourds.

### 20.10 Sécurité mise en œuvre

La sécurité ne dépend pas d'une seule protection :

1. le modèle produit une intention et aucun SQL exécutable ;
2. normalize_intent ancre les noms dans les catalogues et détecte les ordres de mutation ;
3. build_safe_audit_query n'accepte que query et construit uniquement SELECT ou WITH ;
4. une seule table est autorisée ;
5. les actions, périodes et agrégats appartiennent à des listes fermées ;
6. les valeurs sont passées par des paramètres liés ;
7. la limite est comprise entre 1 et 200 ;
8. AUDITAI_READER ne possède aucun droit d'écriture ;
9. les clarifications et refus ne produisent aucun SQL ;
10. l'interface conserve le marqueur blocked pour les refus.

Les secrets sont lus depuis infra/oracle/.env, qui est ignoré par Git. Le mot de passe Oracle n'est plus persisté dans backend_runtime_settings.json et GET /api/settings renvoie toujours un champ vide. Le mot de passe administrateur historique codé en dur a été supprimé. Le lanceur génère au besoin un mot de passe aléatoire local sans l'afficher. Les anciens identifiants du laboratoire ne sont plus présents dans le runtime actif.

Les dossiers .runtime, logs, tools, les modèles, le fichier .env et les paramètres runtime secrets restent hors Git selon les règles du dépôt. Aucun secret ni poids de modèle n'a été poussé.

### 20.11 Stratégie d'apprentissage et décision sur un futur LoRA

Aucun nouvel entraînement ne doit être lancé simplement pour corriger chaque question isolée. La stratégie retenue est :

1. collecter des erreurs réelles et les classer ;
2. corriger une erreur de schéma ou de sécurité dans le code ;
3. corriger un synonyme stable dans le catalogue ;
4. corriger une instruction générale dans le prompt ;
5. réserver l'entraînement aux erreurs linguistiques récurrentes que le prompt et le catalogue ne résolvent pas proprement ;
6. mesurer toute modification sur un nouveau jeu aveugle jamais utilisé pour la correction.

Un corpus d'entraînement éventuel devra contenir de nombreuses formulations différentes, des fautes plausibles, du langage familier, des questions incomplètes, des demandes ambiguës, des refus attendus et des combinaisons inédites d'utilisateur, objet, action, période et agrégat. Le modèle devra apprendre à produire l'intention JSON, pas du SQL libre.

Un entraînement LoRA ou QLoRA de Qwen2.5-Coder-1.5B sur Kaggle ou Colab est techniquement possible. Les données de l'entreprise ne devront pas être envoyées telles quelles sur ces plateformes ; le corpus doit être synthétique ou anonymisé. Après entraînement, il faudra conserver l'adaptateur, éventuellement le fusionner au modèle, convertir le résultat en GGUF Q4_K_M, puis comparer le modèle original et le modèle adapté sur exactement le même test aveugle.

Le protocole minimal d'une future expérience comprend trois ensembles séparés par familles de formulations : entraînement, validation et test final. Il faut enregistrer la version du modèle, le dataset, les paramètres LoRA, les graines, les loss d'entraînement et de validation, la conformité JSON, le score d'intention, le taux de statut correct, le taux d'exécution Oracle, la fidélité de la synthèse, la latence et la mémoire. L'adaptateur ne sera retenu que s'il améliore la généralisation sans diminuer la sécurité ni la vitesse de façon excessive.

Décision actuelle : conserver Qwen sans nouvel entraînement, construire d'abord une évaluation plus large, puis décider sur des preuves. Cette décision n'abandonne pas le fine-tuning ; elle le transforme en expérience comparative justifiée.

### 20.12 Limites connues et affirmations autorisées

Affirmations appuyées par les mesures :

- le projet fonctionne entièrement en local après installation des dépendances et modèles ;
- Qwen2.5-Coder Q4 est le meilleur candidat mesuré sur ce PC parmi les variantes exécutées ;
- le pipeline hybride est nettement plus sûr et plus compatible Oracle que le SQL libre ;
- aucune commande destructive n'a été construite pendant les passages hybrides ;
- le premier score aveugle v3 est 89,1 % ;
- le système complet fonctionne avec 8 Go, mais 16 Go de RAM physique sont recommandés.

Affirmations à ne pas faire :

- « précision universelle de 100 % » ;
- « comprend toutes les questions possibles » ;
- « aucune hallucination possible » ;
- « synthèses multilignes toutes validées par des utilisateurs » ;
- « le swap équivaut à de la RAM physique » ;
- « Docker réduit la consommation du modèle ».

Limites techniques actuelles :

- petit modèle de 1,5 milliard de paramètres, donc compréhension imparfaite des formulations très complexes ;
- périodes et agrégats couverts par un ensemble contrôlé qui devra être étendu selon les besoins ;
- références conversationnelles comme « cette table » sans contexte explicite conduisent actuellement à une clarification ;
- synthèse Qwen limitée aux 25 premières lignes et à environ 5 000 caractères ;
- jobs, cache et historique principal restent en mémoire et le backend doit rester à un seul worker ;
- test de lisibilité et de fidélité des réponses multilignes encore insuffisant ;
- données Oracle actuelles simulées et non encore comparées à un véritable export d'audit anonymisé.

### 20.13 Tests, fichiers de preuve et reproductibilité

Les fichiers essentiels sont :

- backend/app/services/local_model_service.py : prompts d'intention et de synthèse, appel llama-server, repli déterministe ;
- backend/app/services/intent_policy.py : normalisation, synonymes, périodes, agrégats, clarifications et refus ;
- backend/app/services/safe_sql_builder.py : SQL Oracle paramétré et listes autorisées ;
- backend/app/services/oracle_service.py : connexion, paramètres liés et métadonnées ;
- backend/app/main.py : orchestration de l'API ;
- backend/tests/test_safe_pipeline.py : tests unitaires de sécurité, intentions et synthèse simple ;
- research/benchmarks : corpus, scripts, résultats JSON et rapports ;
- infra/oracle : Compose, schéma, données et documentation ;
- scripts/start-local.ps1, test-local.ps1 et stop-local.ps1 : exploitation locale ;
- LOCAL_RUN.md : procédure courte.

Dernières validations connues : compilation Python réussie, 10 tests unitaires sur 10 réussis, TypeScript sans erreur, build Next.js réussi, test HTTP authentifié complet réussi et git diff --check réussi. Le test HTTP vérifie la santé de l'API, Oracle et Qwen, les catalogues, le masquage du secret, le frontend, une agrégation, une clarification et un refus destructeur.

Le test de synthèse existant prouve la conservation d'un libellé et d'un nombre dans un agrégat. Il ne suffit pas à valider toutes les réponses naturelles. Le prochain benchmark doit inclure 50 à 100 questions inédites, dont une part importante avec résultats multilignes, et une grille d'évaluation humaine.

### 20.14 Commandes normales et diagnostic

Depuis la racine du projet :

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\test-local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
~~~

La première commande démarre Oracle, Qwen, FastAPI et Next.js. L'interface est disponible sur http://127.0.0.1:3000, l'API sur http://127.0.0.1:8000 et le serveur Qwen sur http://127.0.0.1:8080. Le compte initial est admin ; son mot de passe se trouve dans la variable AUDITAI_ADMIN_PASSWORD du fichier local ignoré infra/oracle/.env.

Le lanceur attend à la fois le port 1521 et l'état Docker healthy d'Oracle, car l'écoute réseau peut commencer avant que FREEPDB1 soit utilisable. Les sorties sont conservées dans logs/backend.err.log, logs/llama.err.log et logs/frontend.err.log. Les PID sont conservés temporairement dans .runtime. Le script d'arrêt libère les ports 3000, 8000, 8080 et arrête auditai-oracle.

Les scripts PowerShell contenant du français doivent conserver leur encodage UTF-8 avec BOM pour Windows PowerShell 5.

### 20.15 Récupération, Git et état exact

Le dépôt GitHub https://github.com/Profzen/npl a été comparé à la sauvegarde locale. Le code applicatif local était le plus récent ; les notebooks, datasets et traces utiles du dépôt distant ont été rangés sous research. Les archives, sauvegardes intermédiaires et prototypes obsolètes ne sont pas revenus dans le runtime actif.

Branche actuelle : master, quatre commits locaux devant origin/master. Historique de reprise :

- 54ba161 : récupération et consolidation de l'état AuditAI ;
- 8cd5ba8 : documentation du workflow local à modèle unique ;
- f9765fe : environnement Oracle local et corpus de comparaison ;
- fa6dd98 : intégration du pipeline Qwen/Oracle sécurisé.

Aucun push n'a été effectué. Au dernier contrôle précédant cette mise à jour, l'arbre était propre et les services étaient arrêtés. La modification présente de memoire.md rendra naturellement ce fichier modifié jusqu'au prochain commit.

### 20.16 Plan de travail à poursuivre

Priorité A — évaluation honnête :

- [ ] figer un corpus aveugle v4 de 50 à 100 questions avant toute nouvelle correction ;
- [ ] inclure fautes, langage familier, synonymes, dates variées, ambiguïtés, refus et questions hors périmètre ;
- [ ] vérifier intention, SQL attendu, résultat Oracle et réponse française ;
- [ ] faire noter la simplicité des réponses par plusieurs personnes non informaticiennes si possible ;
- [ ] publier séparément premier passage aveugle et non-régression après correction.

Priorité B — amélioration fonctionnelle :

- [ ] ajouter une conservation explicite du contexte conversationnel si « cette table » doit reprendre une sélection ou une question précédente ;
- [ ] étendre périodes et agrégats uniquement à partir de besoins observés ;
- [ ] contrôler automatiquement que les noms et nombres de chaque synthèse Qwen appartiennent aux résultats Oracle ;
- [ ] améliorer l'explication des résultats multilignes et des absences de résultat ;
- [ ] tester les questions hors domaine et les erreurs de connexion.

Priorité C — expérience d'entraînement :

- [ ] décider du LoRA seulement après analyse des erreurs v4 ;
- [ ] préparer un dataset synthétique ou anonymisé séparé train/validation/test ;
- [ ] entraîner Qwen sur Kaggle ou Colab pour l'intention JSON ;
- [ ] convertir et importer les poids localement ;
- [ ] comparer modèle original et modèle adapté avec le même protocole.

Priorité D — livraison :

- [ ] rédiger le chapitre d'architecture et le protocole expérimental à partir de ce fichier ;
- [ ] ajouter éventuellement un profil Docker Compose complet sans remplacer le mode léger ;
- [ ] tester après redémarrage l'effet du nouveau fichier d'échange ;
- [ ] effectuer une répétition complète de soutenance hors ligne ;
- [ ] créer un commit local documentant chaque nouveau lot ; ne pousser que sur demande explicite.

### 20.17 Glossaire pour la rédaction

- Modèle de langage : programme entraîné à interpréter et générer du texte.
- Prompt engineering : rédaction du rôle, des consignes, du format et du contexte fournis au modèle.
- Intention : représentation structurée de ce que demande l'utilisateur.
- Corpus : ensemble versionné de questions et de résultats attendus servant à entraîner ou évaluer.
- Corpus aveugle : questions jamais utilisées pour corriger le système avant leur premier passage.
- Généralisation : capacité à traiter correctement des formulations nouvelles.
- Non-régression : vérification que les cas déjà corrigés fonctionnent toujours.
- Loss : erreur mathématique optimisée pendant l'entraînement ; elle ne mesure pas directement la sécurité ou l'utilité.
- LoRA : petit adaptateur entraîné sur un modèle existant sans réentraîner tous ses paramètres.
- Quantification Q4 : représentation compacte des poids sur quatre bits pour réduire RAM et latence.
- GGUF : format de modèle utilisé par llama.cpp.
- llama.cpp : moteur local d'inférence optimisé pour CPU.
- Hallucination : information produite par le modèle sans appui dans les données.
- Paramètre lié : valeur envoyée séparément du texte SQL pour éviter la concaténation et les injections.
- Garde-fou : contrôle empêchant une action, une valeur ou une requête interdite.
- Synthèse déterministe : réponse fabriquée par du code avec les valeurs exactes.
- Synthèse générative : réponse rédigée par Qwen à partir de résultats contrôlés.
- Runtime : composants réellement utilisés lors de l'exécution.
- Swap ou fichier d'échange : espace disque utilisé lorsque la RAM manque, plus lent que la mémoire physique.

### 20.18 Conclusion technique actuelle

La contribution principale n'est pas seulement l'emploi d'un modèle de langage. Elle réside dans l'association d'une compréhension linguistique locale, d'un catalogue sémantique Oracle, d'une politique d'intention vérifiable, d'une génération SQL déterministe, d'un compte Oracle strictement lecteur et d'une synthèse adaptée à un public non technique.

L'expérience démontre que la génération SQL libre donne une apparence d'autonomie mais reste peu fiable et dangereuse sur un petit modèle local. Le pipeline hybride obtient une meilleure compatibilité Oracle et supprime les commandes destructrices des évaluations réalisées. Il conserve la capacité de comprendre des formulations nouvelles, car Qwen interprète chaque question au lieu de rechercher une phrase prédéfinie.

Le résultat scientifique actuel doit être présenté avec prudence : 89,1 % au premier passage du corpus aveugle v3, puis 100 % sur la non-régression après correction. La suite du travail doit mesurer la fidélité et la lisibilité des réponses finales sur un corpus plus large avant de décider si un LoRA apporte un gain réel.

## 21. Lot interface locale et préparation de la publication — 13 septembre 2026

### Incident observé

Après exécution de scripts/start-local.ps1, les quatre services écoutaient correctement sur les ports 1521, 8080, 8000 et 3000. Next.js annonçait Ready en 4,3 secondes, mais le navigateur ouvert sur http://127.0.0.1:3000 restait sur « Chargement des données… ».

Les journaux frontend ont montré que Next.js 16.3.4 bloquait ses ressources de développement, notamment /_next/hmr et la police locale Geist, car le serveur était initialisé avec le nom localhost tandis que le navigateur utilisait l'adresse 127.0.0.1. Ce contrôle de sécurité est propre au serveur de développement de Next.js.

### Correction

La configuration frontend/next.config.mjs autorise désormais explicitement 127.0.0.1 dans allowedDevOrigins. Cette valeur est limitée à l'adresse de boucle locale. Le backend autorisait déjà http://127.0.0.1:3000 dans sa configuration CORS.

Après rechargement automatique de Next.js, la ressource de police demandée avec l'origine http://127.0.0.1:3000 répond en HTTP 200. Le test authentifié de bout en bout passe : API OK, Oracle connected, modèle loaded, 9 utilisateurs, 14 objets, mot de passe masqué, frontend HTTP 200, agrégation exécutée, clarification produite et ordre destructeur refusé.

### Temps de démarrage observé

Le script n'affiche « AuditAI est prêt » qu'après disponibilité des ports et état healthy d'Oracle. Une fois ce message affiché, Next.js a besoin normalement d'environ 5 secondes pour être prêt sur cette machine ; la première compilation d'une page peut ajouter quelques secondes. Une attente de 5 à 30 secondes reste raisonnable. Un chargement qui dépasse environ une minute doit être considéré comme une anomalie et conduit à consulter les fichiers logs/frontend.err.log et logs/backend.err.log.

Les touches Ctrl+C saisies après le retour de l'invite PowerShell n'arrêtent pas les processus lancés en arrière-plan. Pour arrêter proprement le projet, utiliser scripts/stop-local.ps1.

### État avant publication

La correction d'origine locale et la documentation doivent être validées par TypeScript, le build Next.js, le test HTTP et git diff --check, puis enregistrées dans un commit local. L'utilisateur a explicitement demandé de publier tout l'état local actuel sur origin/master.

### Validation après correction

- ressource de développement demandée depuis 127.0.0.1 : HTTP 200 ;
- npx tsc --noEmit : réussi ;
- npm run build : réussi, compilation de production en 13,3 secondes ;
- redémarrage avec scripts/start-local.ps1 : réussi ;
- test HTTP authentifié après redémarrage : réussi en environ 19 secondes ;
- Oracle connecté, Qwen chargé, 9 utilisateurs et 14 objets visibles ;
- secret Oracle masqué, agrégation valide, clarification valide et refus destructeur valide ;
- aucun nouveau message de blocage d'origine dans le journal frontend après redémarrage.

### Publication GitHub effectuée

Le push vers https://github.com/Profzen/npl.git a réussi. La branche distante master a avancé de 93861e6 à cf9d426 et contient les six commits locaux de récupération, d'infrastructure Oracle, d'architecture Qwen, de benchmarks, de documentation technique et de correction du chargement sur 127.0.0.1. Les modèles, secrets, journaux et fichiers runtime ignorés n'ont pas été envoyés.

## 22. Nature réelle des utilisateurs, objets et événements affichés — 13 septembre 2026

### Constat vérifié

Les colonnes utilisateurs et objets de l'interface sont alimentées dynamiquement par des requêtes SELECT DISTINCT ou GROUP BY sur DBUSERNAME et OBJECT_NAME dans SMART2DSECU.UNIFIED_AUDIT_DATA. Elles ne sont pas actuellement alimentées par le dictionnaire Oracle ALL_USERS, DBA_USERS, ALL_OBJECTS ou DBA_OBJECTS.

La base Oracle, le schéma SMART2DSECU, le compte AUDITAI_READER, les tables UNIFIED_AUDIT_DATA et AUDITAI_SEMANTIC_CATALOG ainsi que les 5 003 lignes sont réels et physiquement présents dans le conteneur Oracle.

En revanche, les 5 003 événements sont un jeu de données synthétiques créé par le script infra/oracle/setup/01-create-auditai.sh. Les noms CYRILLE, REPORT_USER, BATCH_USER, CLIENT, EMPLOYEES, PAIEMENTS et les autres valeurs ont été insérés pour simuler un environnement métier. La plupart ne correspondent pas encore à de véritables comptes Oracle ni à de véritables tables métier créées dans cette base. Les lignes ne proviennent pas de l'exécution réelle des 5 003 actions par ces comptes ; elles imitent la structure du contrat d'audit utilisé par le projet.

### Formulation correcte pour le mémoire

La version actuelle doit être décrite comme une preuve de concept exécutée sur Oracle avec un journal d'audit normalisé contenant des événements synthétiques représentatifs. Il ne faut pas affirmer que tous les utilisateurs et objets affichés existent dans le dictionnaire Oracle local, ni que les événements ont tous été capturés par le mécanisme Unified Auditing d'Oracle.

### Évolution recommandée

Conserver le jeu synthétique pour les tests reproductibles, puis ajouter un scénario d'intégration réaliste :

1. créer un schéma métier de démonstration avec de vraies tables, par exemple CLIENT, EMPLOYEES et PAIEMENTS ;
2. créer quelques vrais comptes Oracle de démonstration et leur attribuer des droits limités ;
3. activer des politiques Oracle Unified Auditing ciblées ;
4. exécuter réellement des SELECT, INSERT, UPDATE, DELETE, GRANT et des connexions réussies ou échouées ;
5. lire les événements depuis UNIFIED_AUDIT_TRAIL avec un compte autorisé ou les recopier dans la table normalisée UNIFIED_AUDIT_DATA ;
6. comparer les utilisateurs et objets du journal au dictionnaire Oracle ;
7. faire afficher distinctement les comptes et objets réels et, si nécessaire, les références historiques à des objets supprimés.

Cette évolution rendra la démonstration plus réaliste sans modifier le pipeline d'intelligence artificielle déjà validé.

## 23. Lot résultats adaptatifs, limite réelle et dernières questions — 13 septembre 2026

### Problèmes signalés et causes vérifiées

L'utilisateur observait la mention de 200 éléments, des requêtes semblant imprécises, un doute sur le paramètre « Résultats max par requête » et l'absence de restauration complète au clic sur « Dernières questions ».

La limite enregistrée dans backend_runtime_settings.json était 10. Cependant, le prompt d'intention proposait systématiquement limit: 200 et normalize_intent renvoyait lui aussi 200 dans la plupart des cas. build_safe_audit_query privilégiait cette valeur à la valeur configurée. Oracle lisait donc jusqu'à 200 lignes, la synthèse recevait ces 200 lignes et pouvait annoncer 200 événements, puis l'API découpait seulement l'affichage à 10 lignes. Le réglage agissait sur l'affichage final mais pas sur l'ensemble du traitement.

L'historique backend conservait la question, le SQL et la synthèse, mais pas les lignes. Le convertisseur frontend remplaçait toujours les lignes historiques par une liste vide. Le clic enregistrait une sélection dans le contexte sans naviguer vers l'accueil lorsque l'utilisateur se trouvait sur une autre page. Le statut blocked était également perdu lors de la restauration.

### Corrections du maximum de résultats

La valeur max_results est maintenant la limite supérieure réelle du SQL. Le constructeur calcule la limite comme le minimum entre la configuration, une éventuelle demande explicite de l'utilisateur et le plafond de sécurité de 200. Si la question ne demande aucun nombre, la configuration est utilisée. Le modèle ne peut plus imposer 200 de lui-même.

Exemples :

- configuration 10 et question sans nombre : FETCH FIRST 10 ROWS ONLY ;
- configuration 10 et « montre les trois derniers événements » : FETCH FIRST 3 ROWS ONLY ;
- configuration 2 et demande de dix résultats : au maximum 2 lignes ;
- « montre le dernier événement » : FETCH FIRST 1 ROWS ONLY.

L'analyseur reconnaît les nombres de 1 à 10 écrits en lettres, les nombres de 1 à 200 écrits en chiffres et les formes singulières « le dernier événement », « la première opération », etc. Le champ limit demandé au modèle vaut désormais null par défaut. La clé du cache inclut max_results afin qu'un changement de paramètre ne réutilise pas pendant 60 secondes une ancienne réponse calculée avec une autre limite.

L'interface de paramètres affiche un défaut cohérent de 10 et un maximum de 200, identique à la validation backend. La valeur temporairement modifiée pendant le test a été restaurée à 10.

### Synthèse adaptative

Le système adapte maintenant la forme de la réponse à sa taille :

- zéro ligne : message clair indiquant qu'aucune activité ne correspond ;
- une ligne : phrase complète décrivant l'utilisateur, l'opération, l'objet, la date, le poste et l'échec éventuel ;
- deux ou trois lignes : une introduction courte suivie d'une phrase factuelle pour chaque événement ;
- quatre lignes ou davantage : Qwen produit un résumé naturel à partir des résultats contrôlés et le tableau reste disponible ;
- agrégat : synthèse déterministe conservant exactement le libellé et le nombre.

Le prompt de synthèse n'oblige plus Qwen à annoncer le nombre total. Il lui demande de le mentionner uniquement lorsque cela répond utilement à la question et lui interdit de présenter une limite technique comme un fait métier. Cette répartition conserve l'intelligence de Qwen pour les ensembles qui nécessitent un résumé et garantit rapidité et fidélité pour les petits résultats.

### Correction de « Dernières questions »

Chaque nouvelle entrée en mémoire conserve maintenant les lignes réellement affichées, dans la limite configurée, ainsi que question, SQL, synthèse, nombre de lignes, statut query/clarification/refusal, clarification, indicateur blocked et erreur. Le frontend utilise ces valeurs au lieu de créer une liste vide.

Un clic sur une question récente place l'entrée dans le contexte, navigue vers la page d'accueil, restaure la question et la réponse, restaure le tableau et le statut, puis fait défiler la page vers le résultat. Les anciennes entrées créées avant cette correction peuvent ne pas posséder de lignes. L'historique principal reste en mémoire vive et repart à zéro au redémarrage du backend ; sa persistance complète en SQLite reste une amélioration future distincte.

### Vérifications fonctionnelles

Les tests unitaires passent de 10 à 15 cas et couvrent notamment le plafond configuré, la demande explicite de trois lignes, la forme singulière à une ligne et les phrases pour une ou deux lignes. Résultat : 15/15 réussis.

Le contrôle TypeScript a réussi et le build Next.js a réussi. Le test HTTP de bout en bout a réussi après redémarrage.

Essai dynamique du paramètre :

- valeur initiale : 10 ;
- valeur temporaire : 2 ;
- question : « Montre les activités de ce mois » ;
- SQL obtenu : filtre du mois courant et FETCH FIRST 2 ROWS ONLY ;
- résultat : exactement deux lignes et deux phrases ;
- aucune mention de 200 ;
- valeur restaurée ensuite à 10.

Essai d'une quantité demandée :

- question : « Montre les trois derniers événements » ;
- SQL : tri décroissant sur EVENT_TIMESTAMP et FETCH FIRST 3 ROWS ONLY ;
- résultat : trois lignes et trois phrases ;
- historique : question, synthèse et trois lignes conservées.

Essai singulier après redémarrage :

- question : « Montre le dernier événement » ;
- SQL : tri décroissant et FETCH FIRST 1 ROWS ONLY ;
- résultat : une ligne ;
- réponse : phrase complète sur CYRILLE_TBS, une consultation de CONTRATS, la date et le poste ;
- aucune mention de 200.

Contrôle de précision SQL sur des formulations représentatives :

- « Qui a supprimé des données sur CLIENT hier ? » produit les filtres OBJECT_NAME=CLIENT, ACTION_NAME=DELETE et la période d'hier ;
- « Quelles connexions ont échoué aujourd'hui ? » produit ACTION_NAME=LOGON, RETURNCODE différent de zéro et la période d'aujourd'hui ;
- « Quelle action est la plus fréquente ? » groupe par ACTION_NAME, trie par nombre décroissant et ne retourne que la première action.

Le script scripts/test-local.ps1 vérifie désormais aussi une réponse d'une ligne sans mention de 200 et la présence de cette ligne dans l'historique. Son dernier passage confirme API, Oracle, modèle, frontend, secret masqué, agrégat, clarification, refus, résultat court et historique.

### Limites et prochaine étape

La correction améliore la construction et la restitution, mais elle ne transforme pas le score aveugle de généralisation : la référence scientifique reste 89,1 %. Les SQL vérifiés sont exacts pour les cas représentatifs ci-dessus ; toute formulation nouvelle doit continuer à être ajoutée à un corpus aveugle avant correction.

La prochaine amélioration de l'historique sera sa persistance dans SQLite avec stockage contrôlé des résultats ou possibilité de réexécuter une ancienne question. La prochaine évaluation de synthèse devra examiner des résultats de quatre lignes ou plus pour mesurer la variété, la fidélité et l'absence d'informations inventées.

## 24. Correction sémantique des demandes « derniers utilisateurs » — 13 septembre 2026

### Analyse des captures et diagnostic

Trois résultats affichés dans l'historique ont été réexaminés avec les formulations exactes de l'utilisateur. Les SQL visibles dans ces captures n'étaient pas fidèles aux quantités demandées : ils contenaient tous `FETCH FIRST 200 ROWS ONLY`. Oracle cherchait donc effectivement jusqu'à 200 lignes. Le défaut ne concernait pas seulement le nombre de lignes affichées ou le texte de la synthèse.

Pour « quels sont les trois derniers user à avoir fait une action en base ? », une simple lecture des trois derniers événements ne suffit pas : un même compte pourrait apparaître plusieurs fois. Le sens retenu est celui des trois utilisateurs distincts dont l'activité la plus récente est la plus récente dans le journal.

Pour « qui est le dernier utilisateur à avoir fait un DELETE ? », la requête doit filtrer l'action DELETE, trier par date décroissante et retourner une seule personne. Pour « quelles sont les trois dernières actions effectuées sur la table EMPLOYEES », elle doit filtrer l'objet EMPLOYEES et retourner exactement les trois événements les plus récents.

Les captures correspondaient à des entrées enregistrées avant la correction de la limite réelle. Cliquer sur une ancienne question restaure le SQL et la réponse conservés ; ce clic ne réexécute pas automatiquement la question. Une nouvelle exécution crée une entrée corrigée.

### Corrections de compréhension

Une intention contrôlée `latest_users` a été ajoutée à la politique d'interprétation et à la liste autorisée du modèle local. Elle est reconnue lorsque la question associe les mots utilisateur, user ou compte à une idée de récence comme dernier ou récent. Cette règle s'applique à des familles de formulations et ne constitue pas une requête préfabriquée pour une seule phrase.

L'analyse des quantités tient maintenant compte de la position des expressions dans la phrase. Dans « trois derniers user à avoir fait une action », la quantité trois apparaît avant « une action » et reste donc la quantité demandée. Auparavant, le déterminant « une » pouvait être interprété à tort comme une demande d'une seule ligne. Les formes singulières « le dernier utilisateur », « le dernier user » et « le dernier compte » produisent une limite de un.

Le mot anglais `DELETE`, couramment employé par les administrateurs Oracle dans une phrase française, est désormais reconnu directement comme l'action de suppression. Cette reconnaissance complète les formulations françaises déjà prises en charge.

### Construction SQL sécurisée

L'intention `latest_users` utilise une fonction analytique Oracle : `ROW_NUMBER() OVER (PARTITION BY UPPER(DBUSERNAME) ORDER BY EVENT_TIMESTAMP DESC)`. Chaque utilisateur reçoit ainsi un rang interne ; seul son événement de rang 1 est conservé. Le résultat est ensuite trié par date décroissante et limité à la quantité demandée. Les filtres d'action, d'objet, d'utilisateur, de période et d'échec restent appliqués avec des paramètres liés dans la sous-requête.

Cette construction permet notamment de répondre à « trois derniers utilisateurs » sans retourner trois fois le même compte. Elle demeure en lecture seule, cible exclusivement `SMART2DSECU.UNIFIED_AUDIT_DATA` et ne laisse pas le modèle produire librement du SQL.

### Synthèse destinée à une personne non technique

La synthèse déterministe courte tient maintenant compte de l'objet de la question. Pour une demande portant sur plusieurs utilisateurs récents, elle annonce directement « Voici les trois derniers utilisateurs concernés », puis décrit l'activité récente de chacun. Pour une demande singulière, elle annonce directement le nom du dernier utilisateur correspondant, puis précise l'action, l'objet, la date et le poste disponibles. Aucun plafond technique de 200 n'est présenté comme un résultat métier.

### Validation avec les formulations exactes

Après redémarrage de l'API, les trois questions ont été envoyées à l'API authentifiée et exécutées réellement sur Oracle :

1. « quels sont les trois derniers user a avoir fais une action en base ? » : SQL avec partition par `DBUSERNAME`, `FETCH FIRST 3 ROWS ONLY`, trois utilisateurs distincts et trois lignes retournées ;
2. « qui est le dernier utilisateur a avoir fais un delete ? » : filtre lié `ACTION_NAME=DELETE`, dédoublonnage par utilisateur, `FETCH FIRST 1 ROWS ONLY`, une ligne retournée ; la réponse nomme HR et décrit sa suppression sur FACTURES ;
3. « quels sont les trois dernieres action effectué sur la table EMPLOYEES » : filtre lié `OBJECT_NAME=EMPLOYEES`, ordre décroissant par date, `FETCH FIRST 3 ROWS ONLY` et trois lignes retournées.

Les résultats du jeu synthétique courant étaient respectivement CYRILLE_TBS, SYSTEM et ITEST pour les trois utilisateurs récents ; HR pour le dernier utilisateur ayant effectué un DELETE ; puis trois événements EMPLOYEES attribués à SYSTEM, PROD2_STB et SYSTEM. Ces noms décrivent le jeu de démonstration synthétique documenté à la section 22 et ne doivent pas être présentés comme des activités réelles de production.

La suite de tests backend contient maintenant 20 cas, tous réussis. Elle couvre explicitement les trois phrases signalées, la détection de la quantité, les filtres DELETE et EMPLOYEES, le dédoublonnage des utilisateurs, les limites 3/1/3 et les formulations de synthèse. Le contrôle local complet confirme également : API opérationnelle, Oracle connecté, Qwen chargé, frontend HTTP 200, secrets masqués, agrégation valide, clarification valide, ordre destructeur refusé, résultat court exact et restauration de l'historique.

### Portée du résultat

Ces trois requêtes sont désormais conformes à leur question et ont été vérifiées de bout en bout. Ce correctif ajoute une capacité sémantique générale sur les utilisateurs récents ; il ne justifie pas d'annoncer 100 % de précision pour toute question future. La mesure de généralisation de référence reste 89,1 % sur le premier passage aveugle v3. Les formulations nouvelles continueront à servir de cas d'évaluation et de non-régression.

## 25. Généralisation des actions Oracle et contrôle des synthèses — 13 septembre 2026

### Motivation

Après l'ajout explicite de DELETE, une revue de la politique d'intention a montré que les autres mots-clés Oracle ne disposaient pas tous du même niveau de reconnaissance déterministe. Certaines actions dépendaient alors davantage de la classification de Qwen. Cette asymétrie était indésirable pour un assistant local utilisant un petit modèle, car un filtre d'action explicitement écrit par l'utilisateur ne doit pas être perdu.

### Ontologie d'actions unifiée

La détection couvre maintenant l'ensemble des actions de lecture d'audit autorisées par le constructeur SQL : LOGON, LOGOFF, SELECT, INSERT, UPDATE, DELETE, GRANT, REVOKE, ALTER, TRUNCATE, CREATE USER, DROP USER, ALTER USER, CREATE TABLE, DROP TABLE et ALTER TABLE. Les mots SQL sont reconnus directement au milieu d'une question en français.

Des familles de synonymes français sont également normalisées : connexion et ouverture de session vers LOGON ; déconnexion et fermeture de session vers LOGOFF ; consultation et lecture vers SELECT ; ajout et insertion vers INSERT ; mise à jour et modification vers UPDATE ; suppression de données vers DELETE ; attribution de droits vers GRANT ; retrait de droits vers REVOKE ; vidage ou purge vers TRUNCATE. Les créations, suppressions et modifications de comptes ou de tables sont distinguées des opérations effectuées sur leurs données.

Cette couche n'est pas un catalogue de questions préfabriquées. Qwen continue d'analyser chaque phrase et peut proposer une intention lorsque la formulation est indirecte. La normalisation lexicale et l'ontologie contrôlée servent de garde-fou pour les informations explicites. Le pipeline reste donc hybride : compréhension contextuelle par le modèle, validation par le catalogue réel, normalisation déterministe des concepts Oracle, puis construction SQL sûre avec paramètres liés.

### Validation des actions et des quantités

Un test paramétré vérifie chacun des seize libellés d'action autorisés. Un second test emploie des reformulations françaises nouvelles, notamment « ajouté des lignes », « mis à jour les données », « s'est déconnecté », « retiré les droits » et « attribué des privilèges ». La suite comporte désormais 24 tests, tous réussis.

Trois essais de bout en bout supplémentaires ont été exécutés sur Oracle :

- « Montre les deux dernières déconnexions » : filtre LOGOFF, `FETCH FIRST 2 ROWS ONLY`, deux événements ;
- « Quels sont les cinq derniers INSERT sur CLIENT ? » : filtres INSERT et CLIENT, `FETCH FIRST 5 ROWS ONLY`, cinq événements ;
- « Qui a retiré les droits sur EMPLOYEES ? » : filtres REVOKE et EMPLOYEES, plafond configuré à dix résultats.

Ces essais confirment que les quantités deux et cinq ne sont pas liées aux anciennes phrases de test et que les filtres d'action se combinent avec les objets et la limite configurée.

### Contrôle de fidélité de la synthèse

Pendant l'essai REVOKE, Qwen a produit une phrase grammaticalement trompeuse attribuant l'action à « l'audit ». Le prompt a été renforcé pour rappeler que l'audit, le journal, la base et le système sont des sources d'information et ne sont jamais les auteurs des opérations. Le vocabulaire interne comme SQL, colonne, modèle ou ligne technique est également interdit dans la réponse destinée à l'utilisateur.

Une simple consigne n'étant pas une garantie avec un petit modèle, un validateur contrôle maintenant chaque synthèse générative. Une réponse vide, une réponse utilisant du vocabulaire technique interdit ou une réponse attribuant une action à l'audit, au journal, à la base ou au système est rejetée. Le système produit alors une synthèse factuelle à partir des valeurs Oracle contrôlées : action, objet et liste dédupliquée des utilisateurs.

Après cette correction, la question sur les retraits de droits répond : « Pour l'opération “retrait de droits” sur EMPLOYEES, les utilisateurs concernés sont : PROD2_MDS, AUDIT_MANAGER, NEW_USER_APP, SYSTEM, CYRILLE_TBS, HR. » Le SQL conserve les filtres REVOKE et EMPLOYEES. Le contrôle local complet confirme Oracle connecté, Qwen chargé, API et frontend disponibles, secret masqué, clarification, refus des mutations, résultat court et historique.

### Interprétation du caractère intelligent

Dans ce projet, l'intelligence ne signifie pas laisser le modèle inventer librement le SQL. Elle correspond à sa capacité à interpréter des formulations variées, combinée à une représentation explicite du domaine et à des contrôles qui garantissent que la requête et la réponse restent fidèles. Cette architecture peut traiter des phrases jamais vues lorsqu'elles expriment un concept connu, tout en demandant une reformulation lorsqu'aucune interprétation sûre ne peut être établie. Le score de généralisation officiel reste 89,1 % sur le premier corpus aveugle v3 ; les nouveaux tests mesurent la non-régression de ce lot et ne remplacent pas cette mesure.
