# Rapport global de récupération et diagnostic

Date : 10 septembre 2026

## Résultat de la récupération

La sauvegarde locale est la meilleure base pour continuer le projet. Le dépôt GitHub
`Profzen/npl` s'arrête au commit `93861e6` du 13 juillet 2026, alors que l'export local comprend des
éléments créés jusqu'au 24 juillet.

La comparaison donne :

- 277 fichiers distants ;
- 164 fichiers dans la sauvegarde initiale ;
- 119 chemins communs ;
- 92 contenus strictement identiques ;
- 27 différences limitées aux fins de ligne Windows/Linux ;
- aucune fonctionnalité plus récente dans le code actif distant.

Les éléments utiles absents localement ont été récupérés sous `research/` : mémoire historique,
notebook V13, dataset V15 avec provenance, cas correctifs, scripts et résultats de benchmark. Les
anciens prototypes, sauvegardes `.bak`, ZIP de patch et exports intermédiaires ont été écartés de
la version active.

## État fonctionnel réel

Le projet est déjà bien avancé sur le plan applicatif : authentification, rôles, sessions,
administration, journalisation, paramètres, pool Oracle, suivi asynchrone, cache, interface
Next.js et deux étapes NLP sont implémentés.

Le principal risque est au centre du pipeline. Le modèle génère une chaîne SQL qui est envoyée à
Oracle sans validation active. Le fichier de garde-fous est développé mais déconnecté, et la
fonction de validation actuellement appelée retourne systématiquement vrai. Avant une démonstration
sur une base réelle, il faut rendre le contrôle SQL obligatoire et utiliser un compte Oracle en
lecture seule.

Le frontend a été installé et contrôlé avec Node 22. Le contrôle TypeScript et le build de
production passent. L'audit npm initial signalait six dépendances vulnérables, dont Next.js 16.2.0 ;
la fusion met donc Next.js à niveau vers 16.3.4 et PostCSS vers une version corrigée. Le second
audit retourne zéro vulnérabilité connue.

## Qualité du modèle

Les mesures les plus proches du terrain se situent entre 40 et 53 %. Le test V12 montre aussi une
latence de 25 à 48 secondes par demande sur la machine de laboratoire. Les principales erreurs sont
sémantiques : utilisateur confondu avec objet, poste confondu avec utilisateur, mauvaise action
Oracle, période mal traduite ou colonne inventée.

Le dataset V15 est plus large et mieux traçable, mais le rapport V15 ne suffit pas à prouver un
gain. Une évaluation fiable doit réserver des formulations et des structures SQL jamais vues à
l'entraînement, vérifier le SQL avec un parseur/AST et, si possible, comparer le résultat exécuté
à une réponse attendue.

## Analyse du notebook

Le notebook V13 documente correctement le prompt, le masquage des labels et le LoRA. Il ne contient
cependant pas de validation séparée, pas de métrique SQL pendant l'entraînement et pas de preuve
complète de fin d'exécution. Il mélange aussi une préparation « k-bit » avec un chargement FP16 sans
quantification 4 bits. Enfin, il entraîne sur 9 500 exemples tandis que le dataset V15 récupéré en
contient 17 296.

Il faut produire un notebook V15 propre avec : versions figées, seed unique, découpage par familles
de gabarits, validation à chaque époque, arrêt anticipé, sauvegarde du meilleur checkpoint,
benchmark aveugle, génération déterministe et export GGUF reproductible.

## Faisabilité sur le PC actuel

Le PC dispose d'un i7-4510U, de quatre processeurs logiques, de 7,89 Go de RAM et d'un Intel HD 4400.
Il n'a pas de GPU NVIDIA/CUDA. La mémoire graphique annoncée est partagée avec la RAM et ne peut pas
être considérée comme une VRAM de calcul de 2 Go pour cette pile.

L'exécution est possible, mais la configuration actuelle est trop lourde : environ 2,2 Go pour
TinyLlama, 101 Mo pour le LoRA et 2,39 Go pour Phi-3 Q4, auxquels s'ajoutent PyTorch, les caches,
Python, Node, Windows, WSL et éventuellement Docker.

La meilleure cible locale est : TinyLlama fusionné avec le LoRA en GGUF Q4_K_M, contexte court,
un seul worker et synthèse déterministe. Phi-3 ne devrait être chargé qu'en mode optionnel. Le
fichier Phi-3 présent est bien un Q4 d'environ 2,2 Go selon la carte officielle Microsoft ; les
anciennes notes du projet qui annoncent 640 Mo doivent être corrigées.

## Entraînement, prompt engineering ou approche hybride

Abandonner complètement l'entraînement ferait perdre une partie intéressante du travail de
recherche. Continuer uniquement à grossir le dataset synthétique risque toutefois de mémoriser les
gabarits sans améliorer la généralisation.

Le meilleur protocole pour la soutenance est une comparaison expérimentale :

1. règles et gabarits déterministes ;
2. TinyLlama avec prompt seulement ;
3. TinyLlama + LoRA ;
4. pipeline hybride : extraction d'intention par modèle, construction et validation déterministes ;
5. éventuellement Qwen2.5-Coder-1.5B-Instruct quantifié comme second modèle de référence.

Qwen2.5-Coder-1.5B est orienté génération et raisonnement sur le code, avec 1,54 milliard de
paramètres. Il est légèrement plus lourd que TinyLlama, mais reste testable en Q4. Il ne faut pas le
choisir sur sa réputation : il doit passer exactement le même benchmark aveugle et les mêmes
contraintes de latence et mémoire.

## WSL et Docker

Docker apporte isolation, reproductibilité et proximité avec Oracle Linux. Il ne réduit ni le
nombre de paramètres ni la RAM nécessaire à l'inférence. Sur 8 Go, la VM WSL, Docker, Windows et les
deux modèles peuvent provoquer du swap et augmenter fortement la latence.

Pour le développement, stabiliser d'abord le frontend et le backend en natif ou dans WSL, avec le
code stocké dans le système de fichiers Linux si des bind mounts Docker sont utilisés. Ajouter
ensuite les conteneurs comme preuve de portabilité, avec limites CPU/RAM explicites et modèles
montés en lecture seule.

## Priorités recommandées

1. Restaurer Git et protéger les secrets.
2. Réactiver la validation SQL et écrire les tests de sécurité.
3. Rendre Phi-3 optionnel et mesurer le mode règles seules.
4. Construire le GGUF TinyLlama-LoRA Q4 et brancher le mode prévu dans la configuration.
5. Créer le benchmark aveugle et corriger le notebook V15.
6. Comparer TinyLlama-LoRA au pipeline hybride et à un petit modèle code.
7. Seulement ensuite finaliser Docker/Oracle Linux et les mesures de soutenance.

## Sources techniques externes

- TinyLlama : <https://github.com/jzhang38/TinyLlama>
- Phi-3 Mini GGUF : <https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf>
- Qwen2.5-Coder-1.5B-Instruct : <https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct>
- llama.cpp : <https://github.com/ggml-org/llama.cpp>
- Docker avec WSL 2 : <https://docs.docker.com/desktop/features/wsl/>
- Bonnes pratiques Docker/WSL : <https://docs.docker.com/desktop/features/wsl/best-practices/>
