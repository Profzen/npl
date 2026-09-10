# Audit AI - Export d'integration

## Contenu principal
- ackend/ : API FastAPI Audit AI.
- rontend/ : interface Next.js / React.
- TinyLlama-1.1B-Chat-v1.0/ : modele de base local, si conserve dans le paquet.
- 	inyllama_oracle_lora/ : adaptateur LoRA SQL Oracle, si conserve dans le paquet.
- phi3-mini-gguf/ : modele de synthese local, si conserve dans le paquet.
- .env.example : modele de configuration sans secrets.
- INTEGRATION_NOTES.md : notes d'integration.

## Demarrage backend
`powershell
cd backend
..\venv_nlp\Scripts\activate  # ou creer un nouvel environnement
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
`

## Demarrage frontend
`powershell
cd frontend
npm install
npm run dev
`

## Points a configurer avant integration
- Renseigner les variables Oracle dans .env a partir de .env.example.
- Verifier l'URL backend utilisee par le frontend.
- Verifier les ports autorises par l'application cible.
- Ne jamais livrer .env, bases SQLite locales, caches, backups ou anciens scripts de patch.
