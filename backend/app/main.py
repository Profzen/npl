import time
from threading import Lock

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.schemas import (
    AdminUser,
    AuditLogEntry,
    AuthUser,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    MetadataResponse,
    QueryRequest,
    QueryResponse,
    RuntimeSettings,
    UserCreateRequest,
    UserStatusUpdateRequest,
)
from app.services.audit_service import init_audit_db, read_audit_logs, write_audit_log
from app.services.auth_service import (
    authenticate_user,
    create_session,
    create_user,
    delete_user,
    ensure_default_admin_access,
    get_user_by_token,
    init_auth_db,
    list_users,
    revoke_session,
    set_user_active,
)
from app.services.nlp_service import generate_sql_from_question, model_status
from app.services.oracle_service import execute_sql, fetch_metadata, oracle_status
from app.services.settings_service import get_fetch_limit, get_runtime_settings, update_runtime_settings
from app.services.synthesis_service import build_synthesis, phi3_status

app = FastAPI(title="SMART2D Backend API", version="0.1.0")

QUERY_HISTORY: list[dict] = []
MAX_CONCURRENT_QUERIES_PER_USER = max(1, settings.max_concurrent_queries_per_user)
_ACTIVE_USER_QUERIES: dict[str, int] = {}
_ACTIVE_USER_QUERIES_LOCK = Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_auth_db()
    init_audit_db()


def _to_auth_user(user: dict) -> AuthUser:
    return AuthUser(
        id=int(user["id"]),
        username=str(user["username"]),
        is_admin=bool(user["is_admin"]),
        is_active=bool(user["is_active"]),
    )


def _acquire_user_query_slot(username: str) -> bool:
    with _ACTIVE_USER_QUERIES_LOCK:
        current = _ACTIVE_USER_QUERIES.get(username, 0)
        if current >= MAX_CONCURRENT_QUERIES_PER_USER:
            return False
        _ACTIVE_USER_QUERIES[username] = current + 1
        return True


def _release_user_query_slot(username: str) -> None:
    with _ACTIVE_USER_QUERIES_LOCK:
        current = _ACTIVE_USER_QUERIES.get(username, 0)
        if current <= 1:
            _ACTIVE_USER_QUERIES.pop(username, None)
        else:
            _ACTIVE_USER_QUERIES[username] = current - 1


def get_current_user(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> dict:
    if not x_auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant",
        )
    user = get_user_by_token(x_auth_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalide ou expiree",
        )
    return user


def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not bool(current_user["is_admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve administrateur",
        )
    return current_user


@app.post("/api/auth/login", response_model=LoginResponse)
def auth_login(payload: LoginRequest) -> LoginResponse:
    ensure_default_admin_access(payload.username, payload.password)
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        write_audit_log(
            username=payload.username,
            action="auth_login",
            result_status="error",
            details="Identifiants invalides ou compte suspendu",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides ou compte suspendu",
        )
    token = create_session(int(user["id"]))
    write_audit_log(
        username=str(user["username"]),
        action="auth_login",
        result_status="ok",
        details="Connexion reussie",
    )
    return LoginResponse(token=token, user=_to_auth_user(user))


@app.get("/api/auth/me", response_model=AuthUser)
def auth_me(current_user: dict = Depends(get_current_user)) -> AuthUser:
    return _to_auth_user(current_user)


@app.post("/api/auth/logout")
def auth_logout(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> dict:
    user = get_user_by_token(x_auth_token or "") if x_auth_token else None
    if x_auth_token:
        revoke_session(x_auth_token)
    if user is not None:
        write_audit_log(
            username=str(user["username"]),
            action="auth_logout",
            result_status="ok",
            details="Deconnexion utilisateur",
        )
    return {"status": "ok"}


@app.get("/api/admin/users", response_model=list[AdminUser])
def admin_list_users(_: dict = Depends(get_admin_user)) -> list[AdminUser]:
    return [AdminUser(**u) for u in list_users()]


@app.post("/api/admin/users", response_model=AdminUser)
def admin_create_user(payload: UserCreateRequest, current_admin: dict = Depends(get_admin_user)) -> AdminUser:
    try:
        created = create_user(payload.username, payload.password, payload.is_admin)
        write_audit_log(
            username=str(current_admin["username"]),
            action="admin_create_user",
            result_status="ok",
            details=f"Utilisateur cree: {payload.username}",
        )
    except ValueError as exc:
        write_audit_log(
            username=str(current_admin["username"]),
            action="admin_create_user",
            result_status="error",
            details=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AdminUser(**created)


@app.patch("/api/admin/users/{user_id}/status", response_model=AdminUser)
def admin_set_user_status(
    user_id: int,
    payload: UserStatusUpdateRequest,
    current_admin: dict = Depends(get_admin_user),
) -> AdminUser:
    if int(current_admin["id"]) == user_id and not payload.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Impossible de suspendre votre propre compte")

    updated = set_user_active(user_id, payload.is_active)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    write_audit_log(
        username=str(current_admin["username"]),
        action="admin_set_user_status",
        result_status="ok",
        details=f"User={updated['username']} status={'active' if payload.is_active else 'suspended'}",
    )
    return AdminUser(**updated)


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, current_admin: dict = Depends(get_admin_user)) -> dict:
    if int(current_admin["id"]) == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Impossible de supprimer votre propre compte")

    ok = delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    write_audit_log(
        username=str(current_admin["username"]),
        action="admin_delete_user",
        result_status="ok",
        details=f"User id supprime={user_id}",
    )
    return {"status": "ok"}


@app.get("/api/admin/audit-logs", response_model=list[AuditLogEntry])
def admin_audit_logs(
    limit: int = Query(default=300, ge=1, le=2000),
    _: dict = Depends(get_admin_user),
) -> list[AuditLogEntry]:
    return [AuditLogEntry(**row) for row in read_audit_logs(limit)]


@app.get("/api/health", response_model=HealthResponse)
def health(_: dict = Depends(get_current_user)) -> HealthResponse:
    oracle = oracle_status()
    tinyllama, _ = model_status()
    phi3, _ = phi3_status()
    return HealthResponse(status="ok", oracle=oracle, tinyllama=tinyllama, phi3=phi3)


@app.get("/api/metadata", response_model=MetadataResponse)
def metadata(_: dict = Depends(get_current_user)) -> MetadataResponse:
    users, objects, db_status = fetch_metadata()
    return MetadataResponse(users=users, objects=objects, db_status=db_status)


@app.get("/api/history")
def history(current_user: dict = Depends(get_current_user)) -> list[dict]:
    user_entries = [h for h in QUERY_HISTORY if h.get("username") == current_user["username"]]
    return user_entries[-100:]


@app.get("/api/settings", response_model=RuntimeSettings)
def read_settings(_: dict = Depends(get_current_user)) -> RuntimeSettings:
    return RuntimeSettings(**get_runtime_settings())


@app.post("/api/settings", response_model=RuntimeSettings)
def write_settings(payload: RuntimeSettings, current_user: dict = Depends(get_current_user)) -> RuntimeSettings:
    updated = update_runtime_settings(payload.model_dump())
    write_audit_log(
        username=str(current_user["username"]),
        action="settings_update",
        result_status="ok",
        details="Parametres mis a jour",
    )
    return RuntimeSettings(**updated)


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest, current_user: dict = Depends(get_current_user)) -> QueryResponse:
    username = str(current_user["username"])
    t0 = time.perf_counter()

    try:
        t_sql_start = time.perf_counter()
        sql = generate_sql_from_question(req.question)
        t_sql_end = time.perf_counter()

        t_exec_start = time.perf_counter()
        rows, error = execute_sql(sql)
        t_exec_end = time.perf_counter()

        blocked = False

        t_syn_start = time.perf_counter()
        synthesis = build_synthesis(req.question, rows, error)
        t_syn_end = time.perf_counter()

        t_post_start = time.perf_counter()
        fetch_limit = get_fetch_limit()

        entry = {
            "timestamp": int(time.time()),
            "username": username,
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

        status_value = "ok"
        detail_value = "Execution terminee"
        if error:
            status_value = "error"
            detail_value = error

        write_audit_log(
            username=username,
            action="query_execute",
            result_status=status_value,
            question=req.question,
            sql_text=sql,
            row_count=len(rows),
            details=detail_value,
        )

        t_post_end = time.perf_counter()
        t_total = t_post_end - t0
        print(
            "[QUERY_TIMING] "
            f"user={username} "
            f"question_len={len(req.question)} "
            f"total={t_total:.3f}s "
            f"generate_sql={t_sql_end - t_sql_start:.3f}s "
            f"execute_oracle={t_exec_end - t_exec_start:.3f}s "
            f"build_synthesis={t_syn_end - t_syn_start:.3f}s "
            f"history_audit={t_post_end - t_post_start:.3f}s "
            f"rows={len(rows)} "
            f"error={'yes' if error else 'no'}"
        )

        return QueryResponse(
            question=req.question,
            sql=sql,
            synthesis=synthesis,
            rows=rows[:fetch_limit],
            row_count=len(rows),
            blocked=blocked,
            error=error,
        )
    except Exception as exc:
        t_err = time.perf_counter() - t0
        print(
            "[QUERY_TIMING] "
            f"user={username} "
            f"failed_after={t_err:.3f}s "
            f"error={type(exc).__name__}: {exc}"
        )
        raise
    finally:
        _release_user_query_slot(username)
