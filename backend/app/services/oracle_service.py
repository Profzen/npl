try:
    import oracledb

    _ORACLE_DRIVER_OK = True
except Exception:
    oracledb = None
    _ORACLE_DRIVER_OK = False

from app.config import settings


def get_connection():
    if not _ORACLE_DRIVER_OK:
        raise RuntimeError("oracledb package is not installed")
    return oracledb.connect(
        user=settings.oracle_user,
        password=settings.oracle_password,
        dsn=settings.oracle_dsn,
    )


def execute_sql(sql: str) -> tuple[list[dict], str | None]:
    if sql.strip().startswith("-- blocked"):
        return [], sql.strip()[10:]

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

        user_sql = (
            f"SELECT DBUSERNAME, COUNT(*) AS ACTIONS FROM {settings.oracle_table} "
            "WHERE DBUSERNAME IS NOT NULL "
            "GROUP BY DBUSERNAME ORDER BY ACTIONS DESC FETCH FIRST 100 ROWS ONLY"
        )
        cur.execute(user_sql)
        users = [{"name": str(r[0]), "actions": int(r[1])} for r in cur.fetchall()]

        obj_sql = (
            f"SELECT OBJECT_NAME, COUNT(*) AS ACTIONS FROM {settings.oracle_table} "
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
