# SMART2D Backend

## Run

1. Create and activate a Python environment.
2. Install dependencies:
   pip install -r requirements.txt
3. Copy `.env.example` to `.env` and adjust values if needed.
4. Start API:
   uvicorn app.main:app --reload --port 8000

## Endpoints

- `GET /api/health`
- `GET /api/metadata`
- `GET /api/history`
- `POST /api/query`

`/api/health` exposes backend runtime status:

- `oracle`: `connected` or `disconnected`
- `tinyllama`: `loaded` or `fallback`
- `phi3`: `loaded` or `fallback`

`/api/query` behavior:

- Uses TinyLlama + LoRA to generate SQL when model files are available.
- Falls back to deterministic safe SQL generation when model loading fails.
- Applies SQL guardrails (single allowed table, SELECT-only, no multi-statement).
- Runs Phi-3 synthesis when GGUF is available, otherwise returns concise fallback synthesis.

Request body example:

{
  "question": "Qui s'est connecte hier ?"
}
