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
_PERSISTED_KEYS = set(_DEFAULTS) - {"oracle_password"}


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    clean = dict(_DEFAULTS)
    for key, value in payload.items():
        if key in clean:
            clean[key] = value

    clean["oracle_user"] = str(clean["oracle_user"]).strip() or _DEFAULTS["oracle_user"]
    clean["oracle_password"] = str(clean["oracle_password"])
    clean["oracle_host"] = str(clean["oracle_host"]).strip() or _DEFAULTS["oracle_host"]
    clean["oracle_service"] = str(clean["oracle_service"]).strip() or _DEFAULTS["oracle_service"]
    clean["oracle_table"] = str(clean["oracle_table"]).strip() or _DEFAULTS["oracle_table"]
    clean["interface_lang"] = "en" if str(clean["interface_lang"]).lower() == "en" else "fr"

    for key, minimum, maximum in (
        ("oracle_port", 1, 65535),
        ("max_results", 1, 200),
        ("session_duration", 1, 1440),
        ("logs_retention", 1, 3650),
    ):
        try:
            clean[key] = max(minimum, min(maximum, int(clean[key])))
        except Exception:
            clean[key] = int(_DEFAULTS[key])
    return clean


def _load_from_disk() -> dict[str, Any]:
    if not os.path.exists(_SETTINGS_PATH):
        return dict(_DEFAULTS)
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
        if not isinstance(raw, dict):
            return dict(_DEFAULTS)
        # A secret from an old version is deliberately ignored.
        raw.pop("oracle_password", None)
        return _sanitize_payload(raw)
    except Exception:
        return dict(_DEFAULTS)


def _save_to_disk(data: dict[str, Any]) -> None:
    persisted = {key: data[key] for key in _PERSISTED_KEYS}
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as fp:
        json.dump(persisted, fp, ensure_ascii=True, indent=2)


_RUNTIME_SETTINGS = _load_from_disk()


def get_runtime_settings() -> dict[str, Any]:
    with _LOCK:
        return dict(_RUNTIME_SETTINGS)


def get_public_runtime_settings() -> dict[str, Any]:
    public = get_runtime_settings()
    public["oracle_password"] = ""
    return public


def update_runtime_settings(new_values: dict[str, Any]) -> dict[str, Any]:
    global _RUNTIME_SETTINGS
    with _LOCK:
        merged = dict(_RUNTIME_SETTINGS)
        incoming = dict(new_values)
        if not str(incoming.get("oracle_password") or ""):
            incoming.pop("oracle_password", None)
        merged.update(incoming)
        clean = _sanitize_payload(merged)
        _RUNTIME_SETTINGS = clean
        _save_to_disk(clean)
        public = dict(clean)
        public["oracle_password"] = ""
        return public


def reset_runtime_settings() -> dict[str, Any]:
    global _RUNTIME_SETTINGS
    with _LOCK:
        _RUNTIME_SETTINGS = dict(_DEFAULTS)
        _save_to_disk(_RUNTIME_SETTINGS)
        public = dict(_RUNTIME_SETTINGS)
        public["oracle_password"] = ""
        return public


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
    return str(get_runtime_settings()["oracle_table"])


def get_fetch_limit() -> int:
    return int(get_runtime_settings()["max_results"])
