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

Pipeline cible :

1. détecter l'intention, les utilisateurs, objets, actions, dates et limites ;
2. construire un SQL depuis un AST ou des gabarits autorisés ;
3. valider la table, les colonnes, les fonctions et le caractère lecture seule ;
4. exécuter avec un compte Oracle strictement en lecture seule ;
5. produire d'abord une synthèse déterministe ;
6. employer un petit modèle local uniquement pour reformuler les cas complexes.

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
