import time
import hashlib
from threading import Lock, Thread, Semaphore
from uuid import uuid4

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
    QueryProgressResponse,
    QueryProgressStep,
    QueryResponse,
    QueryStartResponse,
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
from app.services.oracle_service import execute_sql, fetch_metadata, get_connection, oracle_status
from app.services.settings_service import get_fetch_limit, get_runtime_settings, update_runtime_settings
from app.services.synthesis_service import build_synthesis, phi3_status

app = FastAPI(title="SMART2D Backend API", version="0.1.0")

QUERY_HISTORY: list[dict] = []
MAX_CONCURRENT_QUERIES_PER_USER = max(1, settings.max_concurrent_queries_per_user)
MAX_GLOBAL_CONCURRENT_QUERIES = 1  # Prevent CPU/RAM monopolization: only 1 heavy compute at a time
_ACTIVE_USER_QUERIES: dict[str, int] = {}
_ACTIVE_USER_QUERIES_LOCK = Lock()
_QUERY_PROGRESS: dict[str, dict] = {}
_QUERY_PROGRESS_LOCK = Lock()
_GLOBAL_QUERY_SEMAPHORE = Semaphore(MAX_GLOBAL_CONCURRENT_QUERIES)

# Query response cache (TTL: 3600s = 1 hour)
_QUERY_CACHE: dict[str, tuple[QueryResponse, float]] = {}  # {hash: (response, timestamp)}
_QUERY_CACHE_LOCK = Lock()
_QUERY_CACHE_TTL_SECONDS = 3600

QUERY_STAGE_DEFS = [
    ("generate_sql", "Generation SQL", "Transformation de la question en requete Oracle"),
    ("connect_oracle", "Connexion Oracle", "Ouverture de la connexion a la base d audit"),
    ("execute_sql", "Execution", "Lecture des donnees correspondant a la demande"),
    ("build_synthesis", "Traduction", "Transformation de la reponse brute en resume clair"),
    ("finalize", "Finalisation", "Preparation des resultats pour l interface"),
]

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
    # Warmup: preload models on startup to avoid cold start for first user
    print("[STARTUP] Warming up TinyLlama...")
    try:
        status, err = model_status()
        print(f"[STARTUP] TinyLlama status: {status}" + (f" ({err})" if err else ""))
    except Exception as e:
        print(f"[STARTUP] TinyLlama warmup error: {e}")
    
    print("[STARTUP] Warming up Phi-3...")
    try:
        status, err = phi3_status()
        print(f"[STARTUP] Phi-3 status: {status}" + (f" ({err})" if err else ""))
    except Exception as e:
        print(f"[STARTUP] Phi-3 warmup error: {e}")


def _get_query_cache_key(question: str) -> str:
    """Generate cache key from normalized question."""
    normalized = question.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()


def _get_cached_response(question: str) -> QueryResponse | None:
    """Retrieve cached response if exists and not expired."""
    key = _get_query_cache_key(question)
    with _QUERY_CACHE_LOCK:
        if key in _QUERY_CACHE:
            response, timestamp = _QUERY_CACHE[key]
            elapsed = time.time() - timestamp
            if elapsed < _QUERY_CACHE_TTL_SECONDS:
                print(f"[CACHE_HIT] question (cached {elapsed:.1f}s ago)")
                return response
            else:
                # Expired, remove
                del _QUERY_CACHE[key]
    return None


def _cache_response(question: str, response: QueryResponse) -> None:
    """Store response in cache with timestamp."""
    key = _get_query_cache_key(question)
    with _QUERY_CACHE_LOCK:
        _QUERY_CACHE[key] = (response, time.time())
        # Keep cache size reasonable (max 100 entries)
        if len(_QUERY_CACHE) > 100:
            # Remove oldest entry
            oldest_key = min(_QUERY_CACHE.keys(), key=lambda k: _QUERY_CACHE[k][1])
            del _QUERY_CACHE[oldest_key]


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


def _empty_progress_steps() -> list[dict]:
    return [
        {
            "key": key,
            "label": label,
            "summary": summary,
            "status": "pending",
            "duration_seconds": None,
        }
        for key, label, summary in QUERY_STAGE_DEFS
    ]


def _init_query_progress(request_id: str, username: str, question: str) -> None:
    with _QUERY_PROGRESS_LOCK:
        _QUERY_PROGRESS[request_id] = {
            "request_id": request_id,
            "username": username,
            "question": question,
            "status": "running",
            "current_step": None,
            "current_summary": "Initialisation de l analyse",
            "elapsed_seconds": 0.0,
            "steps": _empty_progress_steps(),
            "result": None,
            "error": None,
            "started_at": time.perf_counter(),
        }


def _update_query_progress(
    request_id: str,
    *,
    stage_key: str | None = None,
    stage_status: str | None = None,
    duration_seconds: float | None = None,
    current_summary: str | None = None,
    status: str | None = None,
    result: QueryResponse | None = None,
    error: str | None = None,
) -> None:
    with _QUERY_PROGRESS_LOCK:
        payload = _QUERY_PROGRESS.get(request_id)
        if payload is None:
            return

        now_elapsed = max(0.0, time.perf_counter() - payload["started_at"])
        payload["elapsed_seconds"] = now_elapsed

        if status is not None:
            payload["status"] = status
        if current_summary is not None:
            payload["current_summary"] = current_summary
        if error is not None:
            payload["error"] = error
        if result is not None:
            payload["result"] = result.model_dump()

        if stage_key is not None:
            payload["current_step"] = stage_key
            for step in payload["steps"]:
                if step["key"] == stage_key:
                    if stage_status is not None:
                        step["status"] = stage_status
                    if duration_seconds is not None:
                        step["duration_seconds"] = round(duration_seconds, 3)
                    break


def _query_progress_response(payload: dict) -> QueryProgressResponse:
    steps = [QueryProgressStep(**step) for step in payload["steps"]]
    result = QueryResponse(**payload["result"]) if payload.get("result") else None
    return QueryProgressResponse(
        request_id=str(payload["request_id"]),
        status=str(payload["status"]),
        current_step=payload.get("current_step"),
        current_summary=payload.get("current_summary"),
        elapsed_seconds=float(payload.get("elapsed_seconds") or 0.0),
        steps=steps,
        result=result,
        error=payload.get("error"),
    )


def _execute_sql_with_progress(sql: str, request_id: str) -> tuple[list[dict], str | None]:
    conn = None
    cur = None
    t_connect_start = time.perf_counter()
    try:
        _update_query_progress(
            request_id,
            stage_key="connect_oracle",
            stage_status="running",
            current_summary="Connexion a Oracle en cours",
        )
        conn = get_connection()
        t_connect_end = time.perf_counter()
        _update_query_progress(
            request_id,
            stage_key="connect_oracle",
            stage_status="completed",
            duration_seconds=t_connect_end - t_connect_start,
            current_summary="Connexion Oracle etablie",
        )

        _update_query_progress(
            request_id,
            stage_key="execute_sql",
            stage_status="running",
            current_summary="Execution de la requete sur les donnees d audit",
        )
        t_exec_start = time.perf_counter()
        cur = conn.cursor()
        cur.execute(sql.rstrip().rstrip(";"))
        cols = [d[0].upper() for d in cur.description]
        rows = cur.fetchall()
        payload = [dict(zip(cols, row)) for row in rows]
        t_exec_end = time.perf_counter()
        _update_query_progress(
            request_id,
            stage_key="execute_sql",
            stage_status="completed",
            duration_seconds=t_exec_end - t_exec_start,
            current_summary=f"Execution terminee, {len(payload)} ligne(s) trouvee(s)",
        )
        return payload, None
    except Exception as exc:
        current_key = "execute_sql" if conn is not None else "connect_oracle"
        _update_query_progress(
            request_id,
            stage_key=current_key,
            stage_status="error",
            current_summary="Erreur pendant l acces Oracle",
            error=str(exc),
        )
        return [], str(exc)
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def _execute_query_pipeline(req: QueryRequest, username: str, request_id: str | None = None) -> QueryResponse:
    """Execute query pipeline with global semaphore to prevent CPU/RAM monopolization.
    Only 1 heavy compute (SQL generation + Phi-3 synthesis) allowed at a time.
    Others block and wait their turn.
    """
    # Acquire global slot (blocks if another query is running)
    _GLOBAL_QUERY_SEMAPHORE.acquire()
    try:
        t0 = time.perf_counter()

        if request_id is not None:
            _update_query_progress(
                request_id,
                stage_key="generate_sql",
                stage_status="running",
                current_summary="Generation de la requete SQL en cours",
            )

        t_sql_start = time.perf_counter()
        sql = generate_sql_from_question(req.question)
        t_sql_end = time.perf_counter()

        if request_id is not None:
            _update_query_progress(
                request_id,
                stage_key="generate_sql",
                stage_status="completed",
                duration_seconds=t_sql_end - t_sql_start,
                current_summary="Requete SQL generee",
            )

        if request_id is not None:
            rows, error = _execute_sql_with_progress(sql, request_id)
        else:
            rows, error = execute_sql(sql)

        blocked = False

        if request_id is not None:
            _update_query_progress(
                request_id,
                stage_key="build_synthesis",
                stage_status="running",
                current_summary="Traduction de la reponse brute en langage clair",
            )

        t_syn_start = time.perf_counter()
        synthesis = build_synthesis(req.question, rows, error)
        t_syn_end = time.perf_counter()

        if request_id is not None:
            _update_query_progress(
                request_id,
                stage_key="build_synthesis",
                stage_status="completed",
                duration_seconds=t_syn_end - t_syn_start,
                current_summary="Synthese terminee",
            )
            _update_query_progress(
                request_id,
                stage_key="finalize",
                stage_status="running",
                current_summary="Preparation de la reponse finale",
            )

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

        response = QueryResponse(
            question=req.question,
            sql=sql,
            synthesis=synthesis,
            rows=rows[:fetch_limit],
            row_count=len(rows),
            blocked=blocked,
            error=error,
        )

        t_post_end = time.perf_counter()
        t_total = t_post_end - t0
        print(
            "[QUERY_TIMING] "
            f"user={username} "
            f"question_len={len(req.question)} "
            f"total={t_total:.3f}s "
            f"generate_sql={t_sql_end - t_sql_start:.3f}s "
            f"execute_oracle={t_syn_start - t_sql_end:.3f}s "
            f"build_synthesis={t_syn_end - t_syn_start:.3f}s "
            f"history_audit={t_post_end - t_post_start:.3f}s "
            f"rows={len(rows)} "
            f"error={'yes' if error else 'no'}"
        )

        if request_id is not None:
            _update_query_progress(
                request_id,
                stage_key="finalize",
                stage_status="completed",
                duration_seconds=t_post_end - t_post_start,
                current_summary="Analyse terminee",
                status="completed",
                result=response,
            )

        return response
    finally:
        # Always release global semaphore so next queued query can proceed
        _GLOBAL_QUERY_SEMAPHORE.release()


def _run_tracked_query(request_id: str, req: QueryRequest, username: str) -> None:
    try:
        result = _execute_query_pipeline(req, username, request_id=request_id)
        _update_query_progress(request_id, status="completed", result=result)
    except Exception as exc:
        _update_query_progress(
            request_id,
            status="error",
            current_summary="Analyse interrompue",
            error=str(exc),
        )
    finally:
        _release_user_query_slot(username)


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
    
    # Check response cache first (no compute needed)
    cached_response = _get_cached_response(req.question)
    if cached_response is not None:
        return cached_response
    
    if not _acquire_user_query_slot(username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Une autre analyse est deja en cours pour cet utilisateur",
        )

    try:
        response = _execute_query_pipeline(req, username)
        # Cache the response for future identical questions
        _cache_response(req.question, response)
        return response
    except Exception as exc:
        print(
            "[QUERY_TIMING] "
            f"user={username} "
            f"error={type(exc).__name__}: {exc}"
        )
        raise
    finally:
        _release_user_query_slot(username)


@app.post("/api/query/start", response_model=QueryStartResponse)
def query_start(req: QueryRequest, current_user: dict = Depends(get_current_user)) -> QueryStartResponse:
    username = str(current_user["username"])
    if not _acquire_user_query_slot(username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Une autre analyse est deja en cours pour cet utilisateur",
        )

    request_id = uuid4().hex
    _init_query_progress(request_id, username, req.question)
    thread = Thread(target=_run_tracked_query, args=(request_id, req, username), daemon=True)
    thread.start()
    return QueryStartResponse(request_id=request_id)


@app.get("/api/query/progress/{request_id}", response_model=QueryProgressResponse)
def query_progress(request_id: str, current_user: dict = Depends(get_current_user)) -> QueryProgressResponse:
    username = str(current_user["username"])
    with _QUERY_PROGRESS_LOCK:
        payload = _QUERY_PROGRESS.get(request_id)
        if payload is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suivi introuvable")
        if str(payload.get("username")) != username:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acces refuse a ce suivi")
        payload["elapsed_seconds"] = max(0.0, time.perf_counter() - payload["started_at"])
        return _query_progress_response(payload)
