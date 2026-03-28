from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.schemas import HealthResponse, MetadataResponse, QueryRequest, QueryResponse
from app.services.nlp_service import generate_sql_from_question, model_status
from app.services.oracle_service import execute_sql, fetch_metadata, oracle_status
from app.services.synthesis_service import build_synthesis, phi3_status

app = FastAPI(title="SMART2D Backend API", version="0.1.0")

QUERY_HISTORY: list[dict] = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    oracle = oracle_status()
    tinyllama, _ = model_status()
    phi3, _ = phi3_status()
    return HealthResponse(status="ok", oracle=oracle, tinyllama=tinyllama, phi3=phi3)


@app.get("/api/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    users, objects, db_status = fetch_metadata()
    return MetadataResponse(users=users, objects=objects, db_status=db_status)


@app.get("/api/history")
def history() -> list[dict]:
    return QUERY_HISTORY[-100:]


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    sql = generate_sql_from_question(req.question)
    rows, error = execute_sql(sql)
    blocked = sql.strip().startswith("-- blocked")
    synthesis = build_synthesis(req.question, rows, error)

    entry = {
        "question": req.question,
        "sql": sql,
        "synthesis": synthesis,
        "row_count": len(rows),
        "blocked": blocked,
        "error": error,
    }
    QUERY_HISTORY.append(entry)
    if len(QUERY_HISTORY) > 200:
        del QUERY_HISTORY[:-200]

    return QueryResponse(
        question=req.question,
        sql=sql,
        synthesis=synthesis,
        rows=rows[: settings.default_fetch_limit],
        row_count=len(rows),
        blocked=blocked,
        error=error,
    )
