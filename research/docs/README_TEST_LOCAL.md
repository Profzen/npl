# Test local TinyLlama Oracle LoRA (NLP→SQL)

Ce dossier contient tout le nécessaire pour tester localement la génération de requêtes SQL Oracle à partir de questions en français, sans connexion internet ni accès distant.

## Fichiers requis (à placer dans ce dossier)
- `TinyLlama-1.1B-Chat-v1.0.zip` : modèle de base TinyLlama
- `tinyllama_oracle_lora.zip` : adapter LoRA fine-tuné
- `oracle_audit_trail.csv` : table d'audit Oracle simulée (optionnel)
- `oracle_nlp_dataset.csv` : dataset d'entraînement (pour exemples de test)
- `rapport_performance_modele.csv` : rapport de performance (optionnel)
- `test_tinyllama_oracle_lora_local.py` : script de test local

## Prérequis Python
- Python 3.10+ recommandé
- Installez les librairies suivantes (versions compatibles) :

```bash
pip install "transformers==5.0.0" "peft==0.18.1" "accelerate==0.29.3" "datasets==2.19.0" "numpy>=2.0" pandas torch
```

> **Astuce** : Pour CPU, torch>=2.1.0 fonctionne. Pour GPU, adaptez selon votre carte (voir https://pytorch.org/get-started/locally/).

## Exécution du test local
1. Placez tous les fichiers listés ci-dessus dans le même dossier.
2. Dézipez les modèles si besoin, ou laissez le script le faire automatiquement.
3. Lancez le script de test :

```bash
python test_tinyllama_oracle_lora_local.py
```

Le script va :
- Charger le modèle de base et l'adapter LoRA
- Charger la table d'audit simulée et le dataset
- Générer des requêtes SQL Oracle à partir de questions du dataset
- Afficher les résultats pour vérification

## Limites
- Ce test ne nécessite aucune connexion internet ni accès à une vraie base Oracle.
- Pour tester sur une vraie base Oracle, il faudra adapter le script (connexion via cx_Oracle ou SQLAlchemy).

## Contact
Pour toute question ou problème, contactez l'auteur du notebook ou ouvrez une issue sur le dépôt associé.
