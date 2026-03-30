import json
import os
from threading import Lock
from typing import Any

from app.config import WORKSPACE_ROOT, settings


_SETTINGS_PATH = os.path.join(WORKSPACE_ROOT, "backend_runtime_settings.json")
_LOCK = Lock()

_DEFAULTS: dict[str, Any] = {
    "oracle_user": settings.oracle_user,
    "oracle_password": settings.oracle_password,
    "oracle_host": settings.oracle_host,
    "oracle_port": settings.oracle_port,
    "oracle_service": settings.oracle_service,
    "oracle_table": settings.oracle_table,
    "interface_lang": "fr",
    "max_results": 10,
    "session_duration": 30,
    "logs_retention": 90,
}


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    clean = dict(_DEFAULTS)

    for key, value in payload.items():
        if key not in clean:
            continue
        clean[key] = value

    clean["oracle_user"] = str(clean["oracle_user"]).strip() or _DEFAULTS["oracle_user"]
    clean["oracle_password"] = str(clean["oracle_password"])
    clean["oracle_host"] = str(clean["oracle_host"]).strip() or _DEFAULTS["oracle_host"]
    clean["oracle_service"] = str(clean["oracle_service"]).strip() or _DEFAULTS["oracle_service"]
    clean["oracle_table"] = str(clean["oracle_table"]).strip() or _DEFAULTS["oracle_table"]
    clean["interface_lang"] = "en" if str(clean["interface_lang"]).lower() == "en" else "fr"

    try:
        clean["oracle_port"] = int(clean["oracle_port"])
    except Exception:
        clean["oracle_port"] = int(_DEFAULTS["oracle_port"])

    try:
        clean["max_results"] = max(1, min(1000, int(clean["max_results"])))
    except Exception:
        clean["max_results"] = int(_DEFAULTS["max_results"])

    try:
        clean["session_duration"] = max(1, min(1440, int(clean["session_duration"])))
    except Exception:
        clean["session_duration"] = int(_DEFAULTS["session_duration"])

    try:
        clean["logs_retention"] = max(1, min(3650, int(clean["logs_retention"])))
    except Exception:
        clean["logs_retention"] = int(_DEFAULTS["logs_retention"])

    return clean


def _load_from_disk() -> dict[str, Any]:
    if not os.path.exists(_SETTINGS_PATH):
        return dict(_DEFAULTS)

    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
        if not isinstance(raw, dict):
            return dict(_DEFAULTS)
        return _sanitize_payload(raw)
    except Exception:
        return dict(_DEFAULTS)


def _save_to_disk(data: dict[str, Any]) -> None:
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=True, indent=2)


_RUNTIME_SETTINGS = _load_from_disk()


def get_runtime_settings() -> dict[str, Any]:
    with _LOCK:
        return dict(_RUNTIME_SETTINGS)


def update_runtime_settings(new_values: dict[str, Any]) -> dict[str, Any]:
    global _RUNTIME_SETTINGS
    with _LOCK:
        merged = dict(_RUNTIME_SETTINGS)
        merged.update(new_values)
        clean = _sanitize_payload(merged)
        _RUNTIME_SETTINGS = clean
        _save_to_disk(clean)
        return dict(clean)


def reset_runtime_settings() -> dict[str, Any]:
    global _RUNTIME_SETTINGS
    with _LOCK:
        _RUNTIME_SETTINGS = dict(_DEFAULTS)
        _save_to_disk(_RUNTIME_SETTINGS)
        return dict(_RUNTIME_SETTINGS)


def get_oracle_connection_config() -> tuple[str, str, str, int, str]:
    cfg = get_runtime_settings()
    return (
        str(cfg["oracle_user"]),
        str(cfg["oracle_password"]),
        str(cfg["oracle_host"]),
        int(cfg["oracle_port"]),
        str(cfg["oracle_service"]),
    )


def get_oracle_table() -> str:
    cfg = get_runtime_settings()
    return str(cfg["oracle_table"])


def get_fetch_limit() -> int:
    cfg = get_runtime_settings()
    return int(cfg["max_results"])
