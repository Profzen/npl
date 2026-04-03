import json
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Tuple

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    import oracledb

    ORACLE_OK = True
except ImportError:
    ORACLE_OK = False


ORACLE_USER = "aziz"
ORACLE_PASSWORD = "aziz"
ORACLE_HOST = "192.168.132.177"
ORACLE_PORT = 1791
ORACLE_SERVICE = "OSCARDB1"
ORACLE_DSN = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"
ORACLE_TABLE = "SMART2DSECU.UNIFIED_AUDIT_DATA"

MODEL_DIR = "TinyLlama-1.1B-Chat-v1.0"
LORA_DIR = "tinyllama_oracle_lora"

SYSTEM_PROMPT = (
    "Tu es un expert Oracle Database specialise en audit SQL.\n"
    "Table principale : SMART2DSECU.UNIFIED_AUDIT_DATA\n"
    "Colonnes reelles : ID, AUDIT_TYPE, SESSIONID, OS_USERNAME, USERHOST, TERMINAL, "
    "AUTHENTICATION_TYPE, DBUSERNAME, CLIENT_PROGRAM_NAME, OBJECT_SCHEMA, OBJECT_NAME, "
    "SQL_TEXT, SQL_BINDS, EVENT_TIMESTAMP, ACTION_NAME, INSTANCE\n"
    "Regles importantes :\n"
    "- Tu ne dois interroger QU'UNE SEULE table : SMART2DSECU.UNIFIED_AUDIT_DATA\n"
    "- N'utilise jamais DBA_USERS, ALL_USERS, USER_USERS ni aucune autre table/vue\n"
    "- Les questions sur les utilisateurs concernent uniquement les utilisateurs visibles dans les donnees d'audit\n"
    "- Pour compter des utilisateurs dans les donnees d'audit, utiliser COUNT(DISTINCT DBUSERNAME) et ignorer les valeurs NULL\n"
    "- Pour lister les utilisateurs presents dans les donnees d'audit, utiliser DBUSERNAME\n"
    "- Pour les evenements/actions/audit -> utiliser SMART2DSECU.UNIFIED_AUDIT_DATA\n"
    "- Colonne utilisateur = DBUSERNAME\n"
    "- Colonne timestamp = EVENT_TIMESTAMP\n"
    "- Colonne objet = OBJECT_NAME\n"
    "- Colonne hote = USERHOST\n"
    "- Colonne identifiant = ID\n"
    "- FETCH FIRST N ROWS ONLY pour limiter les resultats Oracle\n"
    "- Filtrage par jour : TRUNC(EVENT_TIMESTAMP) = TRUNC(SYSDATE-N)\n"
    "- Filtrage par periode : TRUNC(EVENT_TIMESTAMP) >= TRUNC(SYSDATE-N)\n"
    "- Filtrage par mois : TRUNC(EVENT_TIMESTAMP,'MM') = TRUNC(SYSDATE,'MM')\n"
    "- connexion = LOGON, deconnexion = LOGOFF, lecture = SELECT\n"
    "- Actions DDL : ALTER TABLE, ALTER USER, DROP TABLE, DROP USER, CREATE TABLE, CREATE USER\n"
    "- Actions DCL : GRANT, REVOKE\n"
    "- Ne jamais utiliser de chiffre comme valeur de ACTION_NAME ou OBJECT_NAME\n"
    "Reponds uniquement en SQL Oracle valide."
)


@dataclass
class TargetCase:
    id: str
    question: str
    historical_failed: bool
    must_contain: List[str]
    must_not_contain: List[str]


@dataclass
class CaseResult:
    id: str
    question: str
    historical_failed: bool
    sql: str
    executed: bool
    row_count: int
    oracle_error: str
    checks: List[str]
    passed: bool


CASES: List[TargetCase] = [
    TargetCase(
        id="q1_user_count",
        question="combien d'utilisateur a t'on dans la base",
        historical_failed=True,
        must_contain=[
            r"COUNT\s*\(\s*DISTINCT\s+DBUSERNAME\s*\)",
            r"FROM\s+SMART2DSECU\.UNIFIED_AUDIT_DATA",
        ],
        must_not_contain=[r"FROM\s+DISTINCT\s+DBUSERNAME"],
    ),
    TargetCase(
        id="q5_tables_week",
        question="Quelles sont les 5 tables les plus utilisees cette semaine ?",
        historical_failed=True,
        must_contain=[
            r"OBJECT_NAME",
            r"GROUP\s+BY\s+OBJECT_NAME",
            r"FETCH\s+FIRST\s+5\s+ROWS\s+ONLY",
        ],
        must_not_contain=[r"GROUP\s+BY\s+DBUSERNAME"],
    ),
    TargetCase(
        id="q6_create_accounts_30d",
        question="Y a-t-il eu des creations de comptes sur les 30 derniers jours ?",
        historical_failed=True,
        must_contain=[r"CREATE\s+USER", r"SYSDATE\s*-\s*30|SYSDATE-30"],
        must_not_contain=[r"DELETE\s+USER"],
    ),
    TargetCase(
        id="q9_most_active_host_month",
        question="Quel poste a ete le plus actif ce mois-ci ?",
        historical_failed=True,
        must_contain=[r"USERHOST", r"GROUP\s+BY\s+USERHOST", r"TRUNC\s*\(\s*EVENT_TIMESTAMP\s*,\s*'MM'\s*\)"],
        must_not_contain=[r"GROUP\s+BY\s+DBUSERNAME"],
    ),
    TargetCase(
        id="q11_objects_48h",
        question="Sur les 48 dernieres heures, quels objets ont le plus change ?",
        historical_failed=True,
        must_contain=[r"OBJECT_NAME", r"GROUP\s+BY\s+OBJECT_NAME", r"SYSDATE\s*-\s*2|SYSDATE-2|INTERVAL\s*'48'\s*HOUR"],
        must_not_contain=[r"GROUP\s+BY\s+DBUSERNAME", r"SYSDATE\s*-\s*7|SYSDATE-7"],
    ),
    TargetCase(
        id="q13_last_action",
        question="Qui a fait la toute derniere action dans les traces ?",
        historical_failed=True,
        must_contain=[r"ORDER\s+BY\s+EVENT_TIMESTAMP\s+DESC", r"FETCH\s+FIRST\s+1\s+ROWS\s+ONLY"],
        must_not_contain=[r"TRUNC\s*\(\s*EVENT_TIMESTAMP\s*\)\s*=\s*TRUNC\s*\(\s*SYSDATE\s*-\s*1\s*\)"],
    ),
    TargetCase(
        id="q15_top3_objects",
        question="Quels sont les 3 objets les plus modifies ?",
        historical_failed=True,
        must_contain=[r"OBJECT_NAME", r"GROUP\s+BY\s+OBJECT_NAME", r"FETCH\s+FIRST\s+3\s+ROWS\s+ONLY"],
        must_not_contain=[r"GROUP\s+BY\s+DBUSERNAME"],
    ),
    TargetCase(
        id="v1_top5_objects_week",
        question="Donne les 5 objets les plus utilises sur les 7 derniers jours.",
        historical_failed=False,
        must_contain=[r"OBJECT_NAME", r"GROUP\s+BY\s+OBJECT_NAME", r"FETCH\s+FIRST\s+5\s+ROWS\s+ONLY"],
        must_not_contain=[r"GROUP\s+BY\s+DBUSERNAME"],
    ),
    TargetCase(
        id="v2_host_month",
        question="Quel USERHOST est le plus actif ce mois ?",
        historical_failed=False,
        must_contain=[r"USERHOST", r"GROUP\s+BY\s+USERHOST", r"FETCH\s+FIRST\s+1\s+ROWS\s+ONLY"],
        must_not_contain=[r"GROUP\s+BY\s+DBUSERNAME"],
    ),
    TargetCase(
        id="v3_last_event_no_day_filter",
        question="Donne la derniere action globale en base, sans filtrer sur hier.",
        historical_failed=False,
        must_contain=[r"ORDER\s+BY\s+EVENT_TIMESTAMP\s+DESC", r"FETCH\s+FIRST\s+1\s+ROWS\s+ONLY"],
        must_not_contain=[r"SYSDATE\s*-\s*1|SYSDATE-1"],
    ),
]


def get_oracle_connection() -> Tuple[Any, str | None]:
    if not ORACLE_OK:
        return None, "oracledb non installe"
    try:
        conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=ORACLE_DSN)
        return conn, None
    except Exception as e:
        return None, str(e)


def execute_sql(sql: str) -> Tuple[List[Tuple[Any, ...]] | None, str | None]:
    conn, err = get_oracle_connection()
    if conn is None:
        return None, err
    try:
        cur = conn.cursor()
        cur.execute(sql.rstrip().rstrip(";"))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows, None
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return None, str(e)


def clean_sql(raw: str) -> str:
    sql = raw.strip()
    sql = re.sub(r"```sql", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```", "", sql)
    sql = re.sub(r"^(SQL\s*:|Requete\s*:|Reponse\s*:)\s*", "", sql, flags=re.IGNORECASE)

    for kw in ["SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "GRANT", "REVOKE"]:
        idx = sql.upper().find(kw)
        if idx != -1:
            sql = sql[idx:]
            break

    if ";" in sql:
        sql = sql[: sql.index(";") + 1]

    sql = re.sub(r"\bORACLE_AUDIT_TRAIL\b", ORACLE_TABLE, sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bUSERNAME\b", "DBUSERNAME", sql, flags=re.IGNORECASE)
    return sql.strip()


def generate_sql(question: str, tokenizer: Any, model: Any, device: torch.device) -> str:
    prompt = f"<|system|>{SYSTEM_PROMPT}<|end|><|user|>{question}<|end|><|assistant|>"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024).to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=160, do_sample=False, pad_token_id=tokenizer.eos_token_id)
    raw = tokenizer.decode(out[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    return clean_sql(raw)


def validate_case(case: TargetCase, sql: str, executed: bool, oracle_error: str) -> Tuple[List[str], bool]:
    checks: List[str] = []
    sql_up = sql.upper()

    if not sql_up.startswith("SELECT"):
        checks.append("FAIL: SQL non SELECT")

    if ORACLE_TABLE.upper() not in sql_up:
        checks.append("FAIL: table cible absente")

    for pattern in case.must_contain:
        if re.search(pattern, sql_up, flags=re.IGNORECASE):
            checks.append(f"PASS: contient /{pattern}/")
        else:
            checks.append(f"FAIL: manque /{pattern}/")

    for pattern in case.must_not_contain:
        if re.search(pattern, sql_up, flags=re.IGNORECASE):
            checks.append(f"FAIL: contient interdit /{pattern}/")
        else:
            checks.append(f"PASS: interdit absent /{pattern}/")

    if executed:
        checks.append("PASS: execution Oracle OK")
    else:
        checks.append(f"FAIL: execution Oracle KO ({oracle_error})")

    passed = all(not line.startswith("FAIL:") for line in checks)
    return checks, passed


def load_model() -> Tuple[Any, Any, torch.device]:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    base = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.float32)
    model = PeftModel.from_pretrained(base, LORA_DIR)
    model.eval()
    device = torch.device("cpu")
    model.to(device)
    return tokenizer, model, device


def main() -> None:
    tokenizer, model, device = load_model()
    results: List[CaseResult] = []

    for idx, case in enumerate(CASES, start=1):
        print(f"[{idx}/{len(CASES)}] {case.id} -> {case.question}")
        sql = generate_sql(case.question, tokenizer, model, device)
        rows, err = execute_sql(sql)
        executed = rows is not None
        row_count = len(rows) if rows is not None else 0
        checks, passed = validate_case(case, sql, executed, err or "")

        results.append(
            CaseResult(
                id=case.id,
                question=case.question,
                historical_failed=case.historical_failed,
                sql=sql,
                executed=executed,
                row_count=row_count,
                oracle_error=err or "",
                checks=checks,
                passed=passed,
            )
        )

    total = len(results)
    passed = sum(1 for item in results if item.passed)

    hist = [item for item in results if item.historical_failed]
    hist_total = len(hist)
    hist_passed = sum(1 for item in hist if item.passed)

    variants = [item for item in results if not item.historical_failed]
    var_total = len(variants)
    var_passed = sum(1 for item in variants if item.passed)

    report: Dict[str, Any] = {
        "benchmark_name": "benchmark_regression_v11_targeted",
        "total_questions": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "historical_failed_subset": {
            "total": hist_total,
            "passed": hist_passed,
            "failed": hist_total - hist_passed,
            "pass_rate": round(hist_passed / hist_total, 4) if hist_total else 0.0,
            "baseline_previous_lora_pass_rate": 0.0,
        },
        "similar_variant_subset": {
            "total": var_total,
            "passed": var_passed,
            "failed": var_total - var_passed,
            "pass_rate": round(var_passed / var_total, 4) if var_total else 0.0,
        },
        "oracle_table": ORACLE_TABLE,
        "details": [asdict(item) for item in results],
    }

    out_file = "benchmark_regression_v11_targeted_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n=== Resume benchmark cible V11 ===")
    print(f"Global: {passed}/{total} ({report['pass_rate']:.2%})")
    print(
        "Historiques echouees (ancien LoRA): "
        f"{hist_passed}/{hist_total} ({report['historical_failed_subset']['pass_rate']:.2%})"
    )
    print(f"Variantes proches: {var_passed}/{var_total} ({report['similar_variant_subset']['pass_rate']:.2%})")
    print(f"Rapport: {out_file}")


if __name__ == "__main__":
    main()
