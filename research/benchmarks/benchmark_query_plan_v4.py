from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.local_model_service import propose_question_plan
from app.services.query_plan_service import normalize_query_plan
from app.services.safe_sql_builder import build_safe_audit_query
from app.services.oracle_service import execute_sql, fetch_intent_catalog

CASES_PATH = ROOT / "research" / "benchmarks" / "query_plan_holdout_v4.json"
RESULTS_PATH = Path(os.getenv(
    "AUDITAI_RESULTS_PATH",
    str(ROOT / "research" / "benchmarks" / "query_plan_holdout_v4_results.json"),
))


def is_subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and is_subset(value, actual[key]) for key, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if expected and all(isinstance(item, dict) for item in expected):
            return all(any(is_subset(item, candidate) for candidate in actual) for item in expected)
        return expected == actual
    return expected == actual


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8-sig"))
    selected = {item for item in os.getenv("AUDITAI_CASE_IDS", "").split(",") if item}
    if selected:
        cases = [case for case in cases if case["id"] in selected]
    known_users, known_objects = fetch_intent_catalog()
    results: list[dict[str, Any]] = []
    started_all = time.perf_counter()

    for index, case in enumerate(cases, 1):
        started = time.perf_counter()
        raw_intent, warning = propose_question_plan(
            case["question"], known_users, known_objects
        )
        intent = normalize_query_plan(
            case["question"], raw_intent, known_users, known_objects
        )
        raw_checks = {
            key: is_subset(value, raw_intent.get(key))
            for key, value in case["expected"].items()
        }
        checks = {
            key: is_subset(value, intent.get(key))
            for key, value in case["expected"].items()
        }
        sql = ""
        binds: dict[str, Any] = {}
        oracle_ok: bool | None = None
        oracle_error: str | None = None
        if intent.get("status") == "query":
            try:
                safe_query = build_safe_audit_query(intent, default_limit=200)
                sql, binds = safe_query.sql, safe_query.binds
                _, oracle_error = execute_sql(sql, binds)
                oracle_ok = oracle_error is None
            except Exception as exc:
                oracle_ok = False
                oracle_error = f"{type(exc).__name__}: {exc}"
        score = sum(checks.values()) / max(1, len(checks))
        result = {
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "expected": case["expected"],
            "raw_intent": raw_intent,
            "raw_checks": raw_checks,
            "raw_score": round(
                sum(raw_checks.values()) / max(1, len(raw_checks)), 3
            ),
            "intent": intent,
            "checks": checks,
            "score": round(score, 3),
            "sql": sql,
            "binds": binds,
            "oracle_ok": oracle_ok,
            "oracle_error": oracle_error,
            "model_warning": warning,
            "latency_seconds": round(time.perf_counter() - started, 3),
        }
        results.append(result)
        print(
            f"[{index:02d}/{len(cases)}] {case['id']} score={score:.3f} "
            f"oracle={oracle_ok} latency={result['latency_seconds']:.1f}s",
            flush=True,
        )

    scored = [item["score"] for item in results]
    raw_scored = [item["raw_score"] for item in results]
    query_attempts = [item for item in results if item["intent"].get("status") == "query"]
    summary = {
        "model_profile": os.getenv("AUDITAI_MODEL_PROFILE", "unknown"),
        "architecture": "local semantic model + validated deterministic Oracle SELECT compiler",
        "frozen_before_evaluation": True,
        "cases": len(results),
        "mean_raw_model_score": round(
            sum(raw_scored) / max(1, len(raw_scored)), 3
        ),
        "exact_raw_model_matches": sum(score == 1 for score in raw_scored),
        "mean_semantic_score": round(sum(scored) / max(1, len(scored)), 3),
        "exact_plan_matches": sum(score == 1 for score in scored),
        "status_accuracy": round(sum(item["checks"].get("status", False) for item in results) / max(1, len(results)), 3),
        "oracle_success": sum(item["oracle_ok"] is True for item in query_attempts),
        "oracle_attempted": len(query_attempts),
        "dangerous_sql_count": sum(
            bool(item["sql"]) and not item["sql"].lstrip().upper().startswith(("SELECT ", "WITH "))
            for item in results
        ),
        "total_seconds": round(time.perf_counter() - started_all, 3),
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

