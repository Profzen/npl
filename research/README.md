# Sources de recherche récupérées

Ce dossier contient les éléments utiles récupérés depuis la branche `master` du dépôt
<https://github.com/Profzen/npl>, dernier commit distant observé :
`93861e6102ebf1f65558c58af9c0f2acc1771f9f` du 13 juillet 2026.

Les anciens prototypes, fichiers `.bak`, ZIP de patch et exports intermédiaires n'ont pas été
réintégrés dans la version active. Ils restent disponibles dans l'historique GitHub.

- `notebooks/` : notebook V13 retenu comme référence historique la plus récente.
- `datasets/` : dataset V15 traçable et paires correctives V11.
- `benchmarks/` : scripts et résultats historiques nécessaires pour mesurer la progression.
- `docs/` : documents techniques récupérés, dont l'ancien `memoire.md` archivé sans modification.

Le notebook et les rapports sont des artefacts de travail. Ils ne prouvent pas à eux seuls la
qualité du modèle : le protocole d'évaluation doit utiliser un jeu de test séparé, jamais vu
pendant l'entraînement, et vérifier la validité SQL ainsi que la conformité métier.
