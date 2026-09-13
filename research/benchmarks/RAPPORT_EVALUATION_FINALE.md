# Évaluation du pipeline local sûr

Date : 13 septembre 2026

## Résultats

| Étape | Corpus | Score moyen | Statuts corrects | Oracle | SQL dangereux | Latence modèle |
|---|---:|---:|---:|---:|---:|---:|
| SQL libre Qwen2.5-Coder | 30 | 0,564 | non mesuré | 5/28 | 1 généré | 15,357 s |
| Intention JSON brute | 30 | 0,744 | 86,7 % | 26/28 | 0 | 9,739 s |
| Pipeline normalisé, corpus de développement | 30 | 1,000 | 100 % | 25/25 | 0 | 8,409 s |
| Paraphrases v1 avant correction | 20 | 0,862 | 85 % | 18/18 | 0 | 9,796 s |
| Paraphrases v2 avant correction | 12 | 0,819 | 83,3 % | 12/12 | 0 | 6,558 s |
| Paraphrases v3 figées avant correction | 12 | 0,891 | 83,3 % | 12/12 | 0 | 6,770 s |
| Non-régression v3 après correction | 12 | 1,000 | 100 % | 10/10 | 0 | 8,589 s |

Les corpus v1 et v2 ont servi à enrichir le catalogue sémantique. Le premier passage v3 reste la mesure séparée à citer pour la généralisation : `0,891`. Le passage v3 à `1,000` est un test de non-régression après correction, pas une nouvelle mesure aveugle.

Dans tous les passages hybrides, aucune commande destructive n'a été construite. Même lorsqu'un ordre destructeur a été mal classé avant correction, le constructeur a produit au pire une lecture du journal. Le code final refuse aussi les formulations connues « Supprime... », « Efface... », « Mets à zéro... » et « Purge immédiatement... ».

## Mémoire observée, système complet

- RAM physique : 7,89 Go.
- RAM utilisée : 7,30 Go.
- RAM libre : 0,59 Go.
- Oracle : environ 1,622 Gio dans Docker.
- Qwen/llama-server : environ 0,990 Go de working set.
- WSL/vmmem observé : environ 1,523 Go.
- Next.js : processus Node principal autour de 138 Mo, plus petits processus auxiliaires.
- FastAPI au repos : environ 11 Mo.

La machine de 8 Go exécute le projet, mais elle est à la limite. Le swap améliore la stabilité et dégrade la latence lorsqu'il remplace la RAM physique. Pour une démonstration fluide avec Oracle, Qwen, FastAPI, Next.js et Windows simultanément, 16 Go de RAM physique sont recommandés. Avec 8 Go, arrêter les applications inutiles et Oracle/Qwen après les essais.

