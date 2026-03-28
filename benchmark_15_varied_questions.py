import json
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

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
    "- Pour 'derniere personne' -> retourner DBUSERNAME + ACTION_NAME + EVENT_TIMESTAMP\n"
    "- Pour 'toutes actions' -> ne pas filtrer sur ACTION_NAME sauf si demande\n"
    "- FETCH FIRST N ROWS ONLY pour limiter les resultats Oracle\n"
    "- Filtrage par jour : TRUNC(EVENT_TIMESTAMP) = TRUNC(SYSDATE-N)\n"
    "- Filtrage par periode : TRUNC(EVENT_TIMESTAMP) >= TRUNC(SYSDATE-N)\n"
    "- Filtrage par mois : TRUNC(EVENT_TIMESTAMP,'MM') = TRUNC(SYSDATE,'MM')\n"
    "- Filtrage horaire : TO_NUMBER(TO_CHAR(EVENT_TIMESTAMP,'HH24')) >= N\n"
    "- connexion = LOGON, deconnexion = LOGOFF, lecture = SELECT\n"
    "- Actions DDL : ALTER TABLE, ALTER USER, DROP TABLE, DROP USER, CREATE TABLE, CREATE USER\n"
    "- Actions DCL : GRANT, REVOKE\n"
    "- Ne jamais utiliser de chiffre comme valeur de ACTION_NAME ou OBJECT_NAME\n"
    "Reponds uniquement en SQL Oracle valide."
)

QUESTIONS = [
    "combien d'utilisateur a t'on dans la base",
    "Qui s'est connecté aujourd'hui ?",
    "Qui s'est déconnecté aujourd'hui ?",
    "Montre-moi les 5 personnes qui ont fait le plus d'actions sur les 7 derniers jours.",
    "Quelles sont les 5 tables les plus utilisées cette semaine ?",
    "Y a-t-il eu des créations de comptes sur les 30 derniers jours ?",
    "Y a-t-il eu des suppressions de comptes sur les 30 derniers jours ?",
    "Qui a modifié des droits récemment ?",
    "Quel poste a été le plus actif ce mois-ci ?",
    "Donne les 10 dernières actions enregistrées.",
    "Sur les 48 dernières heures, quels objets ont le plus changé ?",
    "Pour l'utilisateur SYS, montre les 5 dernières actions.",
    "Qui a fait la toute dernière action dans les traces ?",
    "Combien d'actions au total ont été enregistrées hier ?",
    "Quels sont les 3 objets les plus modifiés ?",
]


@dataclass
class EvalResult:
    question: str
    sql: str
    executed: bool
    row_count: int
    oracle_error: str
    issues: List[str]
    passed: bool


def get_oracle_connection():
    if not ORACLE_OK:
        return None, "oracledb non installé"
    try:
        conn = oracledb.connect(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_DSN,
        )
        return conn, None
    except Exception as e:
        return None, str(e)


def normalize_oracle_value(value):
    if value is None:
        return None
    if ORACLE_OK and isinstance(value, oracledb.LOB):
        try:
            return value.read()
        except Exception:
            return None
    return value


def execute_sql(sql: str):
    conn, err = get_oracle_connection()
    if conn is None:
        return None, err
    try:
        cur = conn.cursor()
        cur.execute(sql.rstrip().rstrip(";").rstrip())
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


def post_process_sql(sql: str, question: str) -> str:
    q_lower = question.lower()
    sql = sql.replace("≥", ">=").replace("≤", "<=")
    sql = re.sub(r"\bDB_USER\b", "DBUSERNAME", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bOBJ_NAME\b", "OBJECT_NAME", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bAUDIT_ID\b", "ID", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bOS_HOST\b", "USERHOST", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bUSERNAME\b", "DBUSERNAME", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\b(DBA_USERS|ALL_USERS|USER_USERS)\b", "ORACLE_AUDIT_TRAIL", sql, flags=re.IGNORECASE)

    asks_all = any(token in q_lower for token in ["pour chacun", "chacun", "tous", "toutes", "chaque utilisateur", "chacune"])
    if asks_all and re.search(r"\bGROUP\s+BY\b", sql, re.IGNORECASE):
        sql = re.sub(r"\s+FETCH\s+FIRST\s+1\s+ROWS\s+ONLY", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s+FETCH\s+FIRST\s+1\s+ROW\s+ONLY", "", sql, flags=re.IGNORECASE)

    if ";" in sql:
        sql = sql[: sql.index(";") + 1]
    return sql.strip()


def clean_sql(raw: str, question: str = "") -> str:
    sql = raw.strip()
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
    sql = post_process_sql(sql.strip(), question)
    sql = re.sub(r"\bORACLE_AUDIT_TRAIL\b", ORACLE_TABLE, sql, flags=re.IGNORECASE)
    return sql


def generate_sql(question: str, tokenizer, model, device) -> str:
    prompt = (
        f"<|system|>{SYSTEM_PROMPT}<|end|>"
        f"<|user|>{question}<|end|>"
        f"<|assistant|>"
    )
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024).to(device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=150,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    raw = tokenizer.decode(out[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    return clean_sql(raw, question)


def evaluate_sql(question: str, sql: str, executed: bool, oracle_error: str) -> List[str]:
    issues: List[str] = []
    su = sql.upper()
    ql = question.lower()

    if not su.startswith("SELECT"):
        issues.append("SQL non-SELECT ou invalide")

    forbidden = [" DBA_USERS", " ALL_USERS", " USER_USERS", " V$", " DUAL", " ALL_TABLES", " DBA_"]
    if any(token in " " + su for token in forbidden):
        issues.append("Utilise une vue/table hors périmètre audit")

    if ORACLE_TABLE.upper() not in su:
        issues.append("Ne cible pas SMART2DSECU.UNIFIED_AUDIT_DATA")

    asks_user_count = ("combien" in ql and ("utilisateur" in ql or "personne" in ql))
    if asks_user_count:
        if "COUNT(DISTINCT DBUSERNAME)" not in su:
            issues.append("Ne compte pas les utilisateurs distincts")

    if any(tok in ql for tok in ["ce mois", "mois-ci"]) and "TRUNC(EVENT_TIMESTAMP,'MM')" not in su:
        issues.append("Filtre temporel mensuel absent")

    asks_top_n = (
        re.search(r"\b(?:montre|donne|affiche)\b.*\b\d+\b", ql) is not None
        or re.search(r"\b\d+\s+derni(?:er|ers|ère|ères)\b", ql) is not None
        or re.search(r"\btop\s+\d+\b", ql) is not None
    )
    temporal_pattern = r"\b\d+\s+(?:dernier(?:e|es|s)?\s+)?(jour|jours|heure|heures|semaine|semaines|mois)\b"
    if asks_top_n and re.search(temporal_pattern, ql):
        asks_top_n = False
    if asks_top_n and "FETCH FIRST" not in su:
        issues.append("Limitation du nombre de lignes absente")

    if "poste" in ql and "USERHOST" not in su:
        issues.append("N'utilise pas USERHOST pour une question de poste")

    if "droits" in ql and not ("GRANT" in su or "REVOKE" in su):
        issues.append("Question sur droits sans GRANT/REVOKE")

    asks_objects = any(tok in ql for tok in ["objet", "objets", "table", "tables", "ressource", "ressources"])
    if asks_objects and "OBJECT_NAME" not in su:
        issues.append("Question orientée objet/table sans OBJECT_NAME")

    if "48" in ql and any(tok in ql for tok in ["heure", "heures"]):
        if "SYSDATE-2" not in su and "INTERVAL '48' HOUR" not in su and "INTERVAL '2' DAY" not in su:
            issues.append("Fenêtre 48h mal interprétée")

    if "dernière action" in ql or "toute dernière" in ql:
        if "SYSDATE-1" in su:
            issues.append("Dernière action confondue avec hier")

    if "création" in ql and "compte" in ql:
        if "CREATE USER" not in su:
            issues.append("Question sur création de compte sans CREATE USER")
        if "DELETE USER" in su:
            issues.append("Action invalide DELETE USER au lieu de DROP/CREATE USER")

    if "suppression" in ql and "compte" in ql:
        if "DROP USER" not in su:
            issues.append("Question sur suppression de compte sans DROP USER")
        if "CREATE USER" in su:
            issues.append("Mélange création/suppression dans une question de suppression")

    if not executed:
        issues.append(f"Échec exécution Oracle: {oracle_error}")

    return issues


def load_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    base = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.float32)
    model = PeftModel.from_pretrained(base, LORA_DIR)
    model.eval()
    device = torch.device("cpu")
    model.to(device)
    return tokenizer, model, device


def main():
    tokenizer, model, device = load_model()
    results: List[EvalResult] = []

    for idx, question in enumerate(QUESTIONS, start=1):
        print(f"[{idx}/{len(QUESTIONS)}] {question}")
        sql = generate_sql(question, tokenizer, model, device)
        rows, err = execute_sql(sql)
        executed = rows is not None
        row_count = len(rows) if rows is not None else 0
        issues = evaluate_sql(question, sql, executed, err or "")
        passed = len(issues) == 0
        results.append(
            EvalResult(
                question=question,
                sql=sql,
                executed=executed,
                row_count=row_count,
                oracle_error=err or "",
                issues=issues,
                passed=passed,
            )
        )

    total = len(results)
    passed = sum(1 for item in results if item.passed)
    failed = total - passed

    issue_frequency: Dict[str, int] = {}
    for item in results:
        for issue in item.issues:
            issue_frequency[issue] = issue_frequency.get(issue, 0) + 1

    report: Dict[str, Any] = {
        "benchmark_name": "benchmark_15_varied_questions",
        "total_questions": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "oracle_table": ORACLE_TABLE,
        "details": [asdict(item) for item in results],
        "issue_frequency": dict(sorted(issue_frequency.items(), key=lambda x: x[1], reverse=True)),
    }

    with open("benchmark_15_varied_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n=== Résumé ===")
    print(f"Total: {total} | Réussites: {passed} | Échecs: {failed} | Taux: {report['pass_rate']:.2%}")
    print("Rapport: benchmark_15_varied_report.json")


if __name__ == "__main__":
    main()
