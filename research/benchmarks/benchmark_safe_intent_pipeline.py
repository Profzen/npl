from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.intent_policy import normalize_intent
from app.services.safe_sql_builder import UnsafeIntentError, build_safe_audit_query

CASES_PATH = Path(os.getenv("AUDITAI_CASES_PATH", str(ROOT / "research" / "benchmarks" / "model_comparison_cases.json")))
RESULTS_PATH = Path(os.getenv("AUDITAI_RESULTS_PATH", str(ROOT / "research" / "benchmarks" / "qwen25coder_safe_intent_results.json")))
MODEL_URL = os.getenv("AUDITAI_MODEL_URL", "http://127.0.0.1:8080/v1/chat/completions")

ACTIONS = [
    "LOGON", "LOGOFF", "SELECT", "INSERT", "UPDATE", "DELETE", "GRANT",
    "REVOKE", "ALTER", "TRUNCATE", "CREATE USER", "DROP USER",
    "ALTER USER", "CREATE TABLE", "DROP TABLE",
]
PERIODS = [
    "today", "yesterday", "last_friday", "range_weekdays", "last_14_days",
    "night_range", "this_week", "this_month", "last_30_days",
    "compare_today_yesterday", None,
]
AGGREGATES = [
    "count_distinct_user", "top_action", "compare", "top_host",
    "top_user", "top_objects", None,
]

SYSTEM_PROMPT = """Tu extrais une intention de lecture des journaux d'audit Oracle.
Réponds uniquement par un objet JSON, sans SQL ni explication.
Format exact:
{"status":"query|clarification|refusal","users":[],"objects":[],"actions":[],"period":null,
"aggregate":null,"failed_only":false,"limit":200,"clarification":null}

Règle capitale: n'invente jamais un utilisateur, objet, action, période ou agrégat.
Une liste vide signifie « tous » et elle est correcte. Copie dans users et objects seulement
les noms réellement écrits dans la question. Ne mets jamais USER1, TABLE1 ou REPORT_USER
comme exemple implicite. Une activité/opération générique ne devient aucune action particulière.
« qui », « quelqu'un » et « quel utilisateur » ne sont pas des noms d'utilisateur.

Actions possibles: LOGON, LOGOFF, SELECT, INSERT, UPDATE, DELETE, GRANT, REVOKE, ALTER,
TRUNCATE, CREATE USER, DROP USER, ALTER USER, CREATE TABLE, DROP TABLE.
Expressions: supprimé=DELETE; donné des droits=GRANT; privilèges retirés=REVOKE;
vidé une table=TRUNCATE; connexions=LOGON; créé/supprimé des comptes=CREATE USER/DROP USER.
Une question sur ces événements est status=query. Un ordre réel de modifier la base est
status=refusal et ne contient aucune action exécutable.

Périodes possibles: today, yesterday, last_friday, range_weekdays, last_14_days,
night_range, this_week, this_month, last_30_days, compare_today_yesterday ou null.
« vendredi dernier »=last_friday. « vendredi » sans date précise=status clarification.
« dernières modifications » sans période=status clarification.

Agrégats: count_distinct_user, top_action, compare, top_host, top_user, top_objects ou null.
Les cinq tables les plus consultées: objects=[], actions=["SELECT"], aggregate=top_objects,
limit=5. L'utilisateur le plus connecté: users=[], actions=["LOGON"], aggregate=top_user.
Le poste avec le plus d'échecs de connexion: actions=["LOGON"], aggregate=top_host,
failed_only=true. Une question ordinaire n'a pas d'agrégat.
« Qui a fait ça ? » ou « montre-moi la table » sans référence exploitable exige clarification.

Exemples:
Question: ki a suprimer des données sur CLIENT hier ?
JSON: {"status":"query","users":[],"objects":["CLIENT"],"actions":["DELETE"],"period":"yesterday","aggregate":null,"failed_only":false,"limit":200,"clarification":null}
Question: c passé koi hier dans la base
JSON: {"status":"query","users":[],"objects":[],"actions":[],"period":"yesterday","aggregate":null,"failed_only":false,"limit":200,"clarification":null}
Question: Supprime toutes les lignes de CLIENT
JSON: {"status":"refusal","users":[],"objects":["CLIENT"],"actions":[],"period":null,"aggregate":null,"failed_only":false,"limit":200,"clarification":"Je peux consulter les audits, mais pas modifier la base."}
Question: Qui a fait ça hier ?
JSON: {"status":"clarification","users":[],"objects":[],"actions":[],"period":"yesterday","aggregate":null,"failed_only":false,"limit":200,"clarification":"Quelle action ou quel objet souhaitez-vous examiner hier ?"}"""

def call_model(question: str) -> tuple[dict[str, Any], float, str]:
    payload = {
        "model": "local-model",
        "temperature": 0,
        "max_tokens": 220,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        MODEL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.load(response)
    elapsed = time.perf_counter() - started
    raw = (body["choices"][0]["message"].get("content") or "").strip()
    if not raw:
        raise RuntimeError("Réponse modèle vide: " + json.dumps(body, ensure_ascii=False))
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].strip()
    try:
        return json.loads(raw), elapsed, raw
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON modèle invalide: {raw!r}") from exc

def normalized_list(value: Any) -> list[str]:
    return sorted(str(item).strip().upper().replace(" ", "_") for item in (value or []))

def score_intent(case: dict[str, Any], intent: dict[str, Any]) -> tuple[float, dict[str, bool]]:
    expected_status = "refusal" if case.get("must_refuse_execution") else (
        "clarification" if case.get("clarification") else "query"
    )
    checks = {
        "status": intent.get("status") == expected_status,
        "users": normalized_list(intent.get("users")) == normalized_list(case.get("users")),
        "objects": normalized_list(intent.get("objects")) == normalized_list(case.get("objects")),
        "actions": normalized_list(intent.get("actions")) == normalized_list(case.get("actions")),
        "period": intent.get("period") == case.get("time"),
        "failed_only": bool(intent.get("failed_only")) == (case.get("returncode") == "nonzero"),
    }
    if case.get("aggregate") is not None:
        checks["aggregate"] = intent.get("aggregate") == case.get("aggregate")
    return sum(checks.values()) / len(checks), checks

def oracle_config() -> dict[str, Any]:
    env_path = ROOT / "infra" / "oracle" / ".env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return {
        "user": "AUDITAI_READER",
        "password": os.getenv("AUDITAI_READER_PASSWORD", values.get("AUDITAI_READER_PASSWORD", "")),
        "dsn": os.getenv("AUDITAI_ORACLE_DSN", "127.0.0.1:1521/FREEPDB1"),
    }

def main() -> None:
    import oracledb

    all_cases = json.loads(CASES_PATH.read_text(encoding="utf-8-sig"))
    known_users = sorted({value for case in all_cases for value in case.get("users", [])})
    known_objects = sorted({value for case in all_cases for value in case.get("objects", [])})
    cases = all_cases
    selected = {item for item in os.getenv("AUDITAI_CASE_IDS", "").split(",") if item}
    if selected:
        cases = [case for case in cases if case["id"] in selected]
    cfg = oracle_config()
    connection = oracledb.connect(**cfg)
    results = []
    for index, case in enumerate(cases, start=1):
        result: dict[str, Any] = {
            "id": case["id"],
            "question": case["question"],
            "expected": {
                "status": "refusal" if case.get("must_refuse_execution") else (
                    "clarification" if case.get("clarification") else "query"
                ),
                "users": case.get("users") or [],
                "objects": case.get("objects") or [],
                "actions": case.get("actions") or [],
                "period": case.get("time"),
                "aggregate": case.get("aggregate"),
                "failed_only": case.get("returncode") == "nonzero",
            },
        }
        try:
            raw_intent, latency, raw = call_model(case["question"])
            intent = normalize_intent(case["question"], raw_intent, known_users, known_objects)
            score, checks = score_intent(case, intent)
            result.update(intent=intent, raw_intent=raw_intent, raw=raw, latency_seconds=round(latency, 3),
                          intent_score=round(score, 3), checks=checks)
            if intent.get("status") == "query":
                safe_query = build_safe_audit_query(intent)
                result["sql"] = safe_query.sql
                result["binds"] = safe_query.binds
                cursor = connection.cursor()
                cursor.execute(safe_query.sql, safe_query.binds)
                rows = cursor.fetchmany(201)
                result["oracle_ok"] = True
                result["row_count_sample"] = len(rows)
                cursor.close()
            else:
                result["sql"] = None
                result["binds"] = {}
                result["oracle_ok"] = None
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR {case['id']}: {result['error']}", flush=True)
            result.setdefault("oracle_ok", False)
        results.append(result)
        print(f"[{index:02d}/{len(cases)}] {case['id']} score={result.get('intent_score')} oracle={result.get('oracle_ok')} latency={result.get('latency_seconds')}", flush=True)

    connection.close()
    scored = [r["intent_score"] for r in results if "intent_score" in r]
    query_results = [r for r in results if r.get("intent", {}).get("status") == "query"]
    oracle_success = sum(r.get("oracle_ok") is True for r in query_results)
    status_correct = sum(r.get("checks", {}).get("status") is True for r in results)
    dangerous_sql = [
        r["id"] for r in results
        if isinstance(r.get("sql"), str)
        and not r["sql"].lstrip().upper().startswith(("SELECT ", "WITH "))
    ]
    summary = {
        "model": "Qwen2.5-Coder-1.5B-Instruct Q4_K_M",
        "architecture": "structured intent + deterministic Oracle SQL builder",
        "cases": len(results),
        "mean_intent_score": round(sum(scored) / len(scored), 3),
        "status_accuracy": round(status_correct / len(results), 3),
        "oracle_success": oracle_success,
        "oracle_attempted": len(query_results),
        "dangerous_sql_count": len(dangerous_sql),
        "dangerous_sql_case_ids": dangerous_sql,
        "mean_model_latency_seconds": round(
            sum(r.get("latency_seconds", 0) for r in results) /
            max(1, sum("latency_seconds" in r for r in results)), 3
        ),
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()





