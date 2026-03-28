from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1500)


class QueryResponse(BaseModel):
    question: str
    sql: str
    synthesis: str
    rows: list[dict[str, Any]]
    row_count: int
    blocked: bool = False
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    oracle: str
    tinyllama: str
    phi3: str


class MetadataResponse(BaseModel):
    users: list[dict[str, Any]]
    objects: list[dict[str, Any]]
    db_status: str
