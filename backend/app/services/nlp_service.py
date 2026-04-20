import os
import re
from typing import Any

from app.config import settings
from app.services.settings_service import get_fetch_limit, get_oracle_table

try:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    
    _MODEL_STACK_AVAILABLE = True
except Exception:
    torch = None
    PeftModel = None
    AutoModelForCausalLM = None
    AutoTokenizer = None
    _MODEL_STACK_AVAILABLE = False

def _system_prompt(table_name: str) -> str:
    return (
        "Tu es un expert Oracle Database specialise en audit SQL.\\n"
        f"Table principale : {table_name}\\n"
        "Colonnes reelles : ID, AUDIT_TYPE, SESSIONID, OS_USERNAME, USERHOST, TERMINAL, "
        "AUTHENTICATION_TYPE, DBUSERNAME, CLIENT_PROGRAM_NAME, OBJECT_SCHEMA, OBJECT_NAME, "
        "SQL_TEXT, SQL_BINDS, EVENT_TIMESTAMP, ACTION_NAME, INSTANCE\\n"
        "Regles importantes :\\n"
        f"- Tu ne dois interroger QU'UNE SEULE table : {table_name}\\n"
        "- N'utilise jamais DBA_USERS, ALL_USERS, USER_USERS ni aucune autre table/vue\\n"
        "- Pour compter des utilisateurs, utiliser COUNT(DISTINCT DBUSERNAME) et ignorer NULL\\n"
        "- Colonne utilisateur = DBUSERNAME\\n"
        "- Colonne timestamp = EVENT_TIMESTAMP\\n"
        "- Colonne objet = OBJECT_NAME\\n"
        "- Colonne hote = USERHOST\\n"
        "- connexion = LOGON, deconnexion = LOGOFF, lecture = SELECT\\n"
        "- Reponds uniquement en SQL Oracle valide."
    )

_TOKENIZER: Any = None
_MODEL: Any = None
_DEVICE: Any = None
_MODEL_ERROR: str | None = None


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def model_status() -> tuple[str, str | None]:
    global _TOKENIZER, _MODEL, _DEVICE, _MODEL_ERROR

    if _MODEL is not None and _TOKENIZER is not None:
        return "loaded", None
    if _MODEL_ERROR:
        return "error", _MODEL_ERROR
    if not _MODEL_STACK_AVAILABLE:
        _MODEL_ERROR = "torch/transformers/peft indisponibles"
        return "error", _MODEL_ERROR

    try:
        _TOKENIZER = AutoTokenizer.from_pretrained(settings.model_dir)
        if _TOKENIZER.pad_token is None:
            _TOKENIZER.pad_token = _TOKENIZER.eos_token

        base = AutoModelForCausalLM.from_pretrained(settings.model_dir)
        _MODEL = PeftModel.from_pretrained(base, settings.lora_dir)
        _MODEL.eval()
        _DEVICE = torch.device("cpu")
        _MODEL.to(_DEVICE)
        return "loaded", None
    except Exception as exc:
        _MODEL_ERROR = str(exc)
        _TOKENIZER = None
        _MODEL = None
        _DEVICE = None
        return "error", _MODEL_ERROR


def apply_default_row_limit(sql: str, default_limit: int = 200) -> str:
    su = sql.upper()
    if "FETCH FIRST" in su or "COUNT(" in su or "GROUP BY" in su:
        return sql
    if not su.startswith(("SELECT", "WITH")):
        return sql
    sql_no_sc = sql.rstrip().rstrip(";").rstrip()
    return f"{sql_no_sc} FETCH FIRST {default_limit} ROWS ONLY"


def _post_process_sql(sql: str) -> str:
    # Normalize trained placeholder table names to runtime Oracle table.
    return re.sub(r"\bORACLE_AUDIT_TRAIL\b", get_oracle_table(), sql, flags=re.IGNORECASE)


def _clean_sql(raw: str, question: str = "") -> str:
    sql = (raw or "").strip()
    sql = re.sub(r"```sql", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```", "", sql)
    sql = re.sub(r"^(SQL\s*:|Requ[eê]te\s*:|R[eé]ponse\s*:)\s*", "", sql, flags=re.IGNORECASE)

    for kw in ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "CREATE", "DROP", "ALTER", "GRANT", "REVOKE"]:
        idx = sql.upper().find(kw)
        if idx != -1:
            sql = sql[idx:]
            break

    if ";" in sql:
        sql = sql[: sql.index(";") + 1]

    sql = _post_process_sql(sql.strip())
    sql = apply_default_row_limit(sql, get_fetch_limit())
    return sql.rstrip().rstrip(";") + ";"


def _generate_sql_with_model(question: str) -> str:
    status, err = model_status()
    if status != "loaded":
        raise RuntimeError(f"TinyLlama indisponible ({err})")

    oracle_table = get_oracle_table()
    prompt = (
        f"<|system|>{_system_prompt(oracle_table)}<|end|>"
        f"<|user|>{question}<|end|>"
        "<|assistant|>"
    )
    inputs = _TOKENIZER(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=1024,
    ).to(_DEVICE)
    with torch.no_grad():
        out = _MODEL.generate(
            **inputs,
            max_new_tokens=settings.max_sql_tokens,
            do_sample=False,
            pad_token_id=_TOKENIZER.eos_token_id,
        )

    raw = _TOKENIZER.decode(out[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    return _clean_sql(raw, question)


def validate_sql_guardrails(sql: str) -> tuple[bool, str]:
    # Garde-fous désactivés temporairement
    return True, "OK"


def generate_sql_from_question(question: str) -> str:
    return _generate_sql_with_model(question)
