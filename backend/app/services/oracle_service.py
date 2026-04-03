try:
    import oracledb

    _ORACLE_DRIVER_OK = True
except Exception:
    oracledb = None
    _ORACLE_DRIVER_OK = False

from threading import Lock

from app.config import settings

from app.services.settings_service import get_oracle_connection_config, get_oracle_table


_POOL = None
_POOL_CFG: tuple[str, str, str, int, str] | None = None
_POOL_LOCK = Lock()


def _build_connection_config() -> tuple[str, str, str, int, str]:
    user, password, host, port, service = get_oracle_connection_config()
    return user, password, host, int(port), service


def _create_pool(cfg: tuple[str, str, str, int, str]):
    user, password, host, port, service = cfg
    dsn = f"{host}:{port}/{service}"
    return oracledb.create_pool(
        user=user,
        password=password,
        dsn=dsn,
        min=max(1, settings.oracle_pool_min),
        max=max(2, settings.oracle_pool_max),
        increment=max(1, settings.oracle_pool_increment),
    )


def _get_pool():
    global _POOL, _POOL_CFG
    cfg = _build_connection_config()

    with _POOL_LOCK:
        if _POOL is None or _POOL_CFG != cfg:
            if _POOL is not None:
                try:
                    _POOL.close(force=True)
                except Exception:
                    pass
            _POOL = _create_pool(cfg)
            _POOL_CFG = cfg
        return _POOL


def get_connection():
    if not _ORACLE_DRIVER_OK:
        raise RuntimeError("oracledb package is not installed")
    pool = _get_pool()
    return pool.acquire()


def execute_sql(sql: str) -> tuple[list[dict], str | None]:

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql.rstrip().rstrip(";"))
        cols = [d[0].upper() for d in cur.description]
        rows = cur.fetchall()
        payload = [dict(zip(cols, row)) for row in rows]
        return payload, None
    except Exception as exc:
        return [], str(exc)
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def oracle_status() -> str:
    conn = None
    try:
        conn = get_connection()
        return "connected"
    except Exception:
        return "disconnected"
    finally:
        if conn is not None:
            conn.close()


def fetch_metadata() -> tuple[list[dict], list[dict], str]:
    conn = None
    cur = None
    users: list[dict] = []
    objects: list[dict] = []
    status = "disconnected"
    try:
        conn = get_connection()
        cur = conn.cursor()
        oracle_table = get_oracle_table()

        user_sql = (
            f"SELECT DBUSERNAME, COUNT(*) AS ACTIONS FROM {oracle_table} "
            "WHERE DBUSERNAME IS NOT NULL "
            "GROUP BY DBUSERNAME ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"
        )
        cur.execute(user_sql)
        users = [{"name": str(r[0]), "actions": int(r[1])} for r in cur.fetchall()]

        obj_sql = (
            f"SELECT OBJECT_NAME, COUNT(*) AS ACTIONS FROM {oracle_table} "
            "WHERE OBJECT_NAME IS NOT NULL "
            "GROUP BY OBJECT_NAME ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"
        )
        cur.execute(obj_sql)
        objects = [{"name": str(r[0]), "actions": int(r[1])} for r in cur.fetchall()]

        status = "connected"
    except Exception:
        status = "disconnected"
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()

    return users, objects, status
