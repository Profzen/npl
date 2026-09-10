# Test local TinyLlama + LoRA Oracle SQL (aucune connexion requise)
# Placez tous les fichiers zip et csv dans le même dossier que ce script

import os
import zipfile
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
import pandas as pd

# Dézipper les modèles si besoin
def unzip_if_needed(zip_path, extract_dir):
    if not os.path.exists(extract_dir):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
            print(f"Dézippé : {zip_path} -> {extract_dir}")

unzip_if_needed('TinyLlama-1.1B-Chat-v1.0.zip', 'TinyLlama-1.1B-Chat-v1.0')
unzip_if_needed('tinyllama_oracle_lora.zip', 'tinyllama_oracle_lora')

# Charger le tokenizer et le modèle de base
MODEL_DIR = 'TinyLlama-1.1B-Chat-v1.0'
LORA_DIR = 'tinyllama_oracle_lora'
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)

# CORRECTION : device_map=None + float32 pour éviter l'offload sur disque/meta device
base_model = AutoModelForCausalLM.from_pretrained(
    MODEL_DIR,
    torch_dtype=torch.float32,
    device_map=None
)

# Charger l'adapter LoRA
model = PeftModel.from_pretrained(base_model, LORA_DIR)
model.eval()

# Déterminer le device utilisé
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)
print(f"Modèle chargé sur : {device}")

# Charger la table d'audit simulée (optionnel)
audit_df = pd.read_csv('oracle_audit_trail.csv')
print("\nExtrait de la table d'audit simulée :")
print(audit_df.head())

# Charger quelques exemples de test (FR->SQL)
dataset = pd.read_csv('oracle_nlp_dataset.csv')
print(f"\n{len(dataset)} exemples dans le dataset d'entraînement.")

# Tester le modèle sur quelques exemples
for i, row in dataset.sample(5, random_state=42).iterrows():
    prompt = f"[INST] Transforme la question en requête SQL Oracle sécurisée.\nQuestion: {row['instruction']}\n[/INST]"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=256)
    for k in inputs:
        inputs[k] = inputs[k].to(device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=64,
            temperature=0.3,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )
    sql = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print("\nQuestion:", row['instruction'])
    print("SQL généré:", sql.split("[/INST]")[-1].strip())

print("\nTest local terminé. Le modèle fonctionne sans connexion internet ni accès distant.")