# Separation Front/Back - Point de depart

Ce workspace contient maintenant:

- `backend/` : API Python FastAPI
- `frontend/` : interface React (Vite)

## Backend

- Installer: `pip install -r backend/requirements.txt`
- Lancer: `uvicorn app.main:app --reload --port 8000` (depuis `backend/`)
- Endpoints:
  - `GET /api/health`
  - `POST /api/query`

## Frontend

- Installer: `npm install` (depuis `frontend/`)
- Lancer: `npm run dev`
- URL dev: `http://localhost:5173`

## Notes

- Le backend est volontairement en base safe (guardrails SQL + execution Oracle).
- La logique LoRA/TinyLlama du monolithe Streamlit peut etre migree dans `backend/app/services/nlp_service.py` lors de la prochaine etape.
- Le monolithe historique `app_queryflow_prod8.py` reste intact pour continuer les tests pendant la migration.
