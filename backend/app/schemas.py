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


class RuntimeSettings(BaseModel):
    oracle_user: str
    oracle_password: str
    oracle_host: str
    oracle_port: int
    oracle_service: str
    oracle_table: str
    interface_lang: str
    max_results: int
    session_duration: int
    logs_retention: int


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AuthUser(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool


class LoginResponse(BaseModel):
    token: str
    user: AuthUser


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    is_admin: bool = False


class UserStatusUpdateRequest(BaseModel):
    is_active: bool


class AdminUser(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: int


class AuditLogEntry(BaseModel):
    id: int
    timestamp: int
    username: str
    action: str
    question: str
    sql_text: str
    result_status: str
    row_count: int
    details: str
