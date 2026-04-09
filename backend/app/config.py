import os
from dataclasses import dataclass, field


WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_workspace_path(path_value: str) -> str:
    if os.path.isabs(path_value):
        return path_value
    return os.path.abspath(os.path.join(WORKSPACE_ROOT, path_value))


@dataclass
class Settings:
    oracle_user: str = os.getenv("ORACLE_USER", "aziz")
    oracle_password: str = os.getenv("ORACLE_PASSWORD", "aziz")
    oracle_host: str = os.getenv("ORACLE_HOST", "192.168.132.177")
    oracle_port: int = int(os.getenv("ORACLE_PORT", "1791"))
    oracle_service: str = os.getenv("ORACLE_SERVICE", "OSCARDB1")
    oracle_table: str = os.getenv("ORACLE_TABLE", "SMART2DSECU.UNIFIED_AUDIT_DATA")
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "BACKEND_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
    )
    model_dir: str = field(
        default_factory=lambda: _resolve_workspace_path(
            os.getenv("MODEL_DIR", "TinyLlama-1.1B-Chat-v1.0")
        )
    )
    lora_dir: str = field(
        default_factory=lambda: _resolve_workspace_path(
            os.getenv("LORA_DIR", "tinyllama_oracle_lora")
        )
    )
    phi3_path: str = field(
        default_factory=lambda: _resolve_workspace_path(
            os.getenv("PHI3_PATH", "phi3-mini-gguf/Phi-3-mini-4k-instruct-q4.gguf")
        )
    )
    max_sql_tokens: int = int(os.getenv("MAX_SQL_TOKENS", "80"))
    default_fetch_limit: int = int(os.getenv("DEFAULT_FETCH_LIMIT", "10"))
    dashboard_row_cap: int = int(os.getenv("DASHBOARD_ROW_CAP", "5000"))
    oracle_pool_min: int = int(os.getenv("ORACLE_POOL_MIN", "1"))
    oracle_pool_max: int = int(os.getenv("ORACLE_POOL_MAX", "8"))
    oracle_pool_increment: int = int(os.getenv("ORACLE_POOL_INCREMENT", "1"))
    max_concurrent_queries_per_user: int = int(os.getenv("MAX_CONCURRENT_QUERIES_PER_USER", "2"))
    # Optimization V12 — Phi-3 synthesis
    phi3_n_ctx: int = int(os.getenv("PHI3_N_CTX", "512"))
    phi3_max_tokens: int = int(os.getenv("PHI3_MAX_TOKENS", "150"))
    phi3_n_threads: int = int(os.getenv("PHI3_N_THREADS", "2"))
    use_rule_synthesis_fallback: bool = os.getenv("USE_RULE_SYNTHESIS_FALLBACK", "true").lower() == "true"
    # GGUF mode for TinyLlama (prepared for V12 from Colab)
    use_gguf_mode: bool = os.getenv("USE_GGUF_MODE", "false").lower() == "true"
    gguf_model_path: str = field(
        default_factory=lambda: _resolve_workspace_path(
            os.getenv("GGUF_MODEL_PATH", "tinyllama_oracle_v12_q4.gguf")
        )
    )

    @property
    def oracle_dsn(self) -> str:
        return f"{self.oracle_host}:{self.oracle_port}/{self.oracle_service}"


settings = Settings()
