"""Benchmark V13 — 20 questions de stress-test.

Pose chaque question au backend, capture SQL + synthèse, analyse les écueils
connus, et produit un bilan V13 OK / V13.5 / V14.
"""
import json
import sys
import time
import io
import re
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8000"
LOGIN = "admin"
PASSWORD = "Admin@123"
ORACLE_TABLE = "SMART2DSECU.UNIFIED_AUDIT_DATA"

QUESTIONS = [
    # Bloc A — Connexions / sessions
    ("A1", "Qui s'est connecté ce matin ?", ["ACTION_NAME", "LOGON"]),
    ("A2", "Combien de connexions ont eu lieu cette semaine ?", ["COUNT", "LOGON", "SYSDATE-7"]),
    ("A3", "Liste les utilisateurs ayant fait au moins 10 connexions sur les 30 derniers jours.", ["HAVING", "LOGON", "GROUP BY"]),
    # Bloc B — Top-N / agrégations
    ("B4", "Quels sont les 5 utilisateurs les plus actifs ce mois-ci ?", ["DBUSERNAME", "GROUP BY", "FETCH FIRST 5"]),
    ("B5", "Donne le top 10 des objets les plus consultés cette semaine.", ["OBJECT_NAME", "GROUP BY", "FETCH FIRST 10"]),
    ("B6", "Quelle est l'action la plus fréquente sur les 7 derniers jours ?", ["ACTION_NAME", "COUNT", "FETCH FIRST 1"]),
    # Bloc C — Postes / machines (faille connue)
    ("C7", "Quel poste a fait le plus d'actions ce mois-ci ?", ["USERHOST"]),
    ("C8", "Depuis quelle machine vient la majorité des connexions ?", ["USERHOST", "LOGON"]),
    ("C9", "Liste les 3 machines les plus actives la semaine dernière.", ["USERHOST", "FETCH FIRST 3"]),
    # Bloc D — Objets / tables (faille connue)
    ("D10", "Quelle table a été le plus modifiée cette semaine ?", ["OBJECT_NAME", "INSERT", "UPDATE", "DELETE"]),
    ("D11", "Sur les 48 dernières heures, quels objets ont le plus changé ?", ["OBJECT_NAME", "INTERVAL", "48"]),
    ("D12", "Quels sont les 3 objets les plus supprimés ce mois ?", ["OBJECT_NAME", "DROP", "FETCH FIRST 3"]),
    # Bloc E — Fenêtres temporelles
    ("E13", "Donne les actions des dernières 48 heures.", ["48"]),
    ("E14", "Quelle a été la toute dernière action enregistrée ?", ["ORDER BY", "DESC", "FETCH FIRST 1"]),
    ("E15", "Combien d'événements entre 14h et 18h aujourd'hui ?", ["14", "18", "SYSDATE"]),
    # Bloc F — Sécurité / nuances métier
    ("F16", "Y a-t-il eu des tentatives de connexion suspectes la nuit ?", ["LOGON", "EXTRACT"]),
    ("F17", "Quels utilisateurs ont fait du LOGOFF juste après LOGON ?", ["LOGOFF", "LOGON"]),
    ("F18", "Quels comptes ont reçu de nouveaux privilèges récemment ?", ["GRANT", "DBUSERNAME"]),
    # Bloc G — Comptage
    ("G19", "Combien d'utilisateurs distincts apparaissent dans les logs ?", ["DISTINCT", "DBUSERNAME"]),
    ("G20", "Combien d'actions par utilisateur en moyenne sur le mois ?", ["AVG", "GROUP BY"]),
]


def http(method: str, path: str, token: str | None = None, body: dict | None = None,
         timeout: int = 240) -> dict:
    url = API + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Auth-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def login() -> str:
    r = http("POST", "/api/auth/login", body={"username": LOGIN, "password": PASSWORD})
    return r["token"]


def grade(sql: str, expected_keywords: list[str], synthesis: str,
          row_count: int, error: str | None) -> tuple[str, list[str]]:
    """Note ✅ / ⚠️ / ❌ + liste des problèmes détectés."""
    issues = []
    s = sql.upper()

    if error:
        issues.append(f"Erreur Oracle: {error[:80]}")
    if ORACLE_TABLE.upper() not in s:
        issues.append(f"N'utilise pas {ORACLE_TABLE}")

    missing = [kw for kw in expected_keywords if kw.upper() not in s]
    if missing:
        issues.append(f"Mots-clés manquants: {missing}")

    # Heuristiques de qualité
    if "FROM DBA_USERS" in s or "FROM USER_" in s:
        issues.append("Cible une vue système interdite")
    if "RETURNCODE" in s:
        issues.append("Référence colonne RETURNCODE (inexistante)")

    if not synthesis or len(synthesis.strip()) < 5:
        issues.append("Synthèse Phi-3 vide ou trop courte")

    if error or any("Erreur Oracle" in i or "interdite" in i or "inexistante" in i for i in issues):
        return "❌", issues
    if not issues:
        return "✅", []
    if len(issues) == 1 and "Mots-clés manquants" in issues[0]:
        return "⚠️", issues
    return "⚠️", issues


def main():
    print("=" * 80)
    print("  BENCHMARK V13 — 20 questions de stress-test")
    print("=" * 80)

    print("\n[auth] Login admin...")
    token = login()
    print("[auth] OK\n")

    results = []
    for tag, q, expected in QUESTIONS:
        t0 = time.time()
        print(f"[{tag}] {q[:70]}", flush=True)
        try:
            r = http("POST", "/api/query", token=token, body={"question": q})
            sql = r.get("sql", "")
            synthesis = r.get("synthesis", "")
            rows = r.get("rows", [])
            row_count = r.get("row_count", 0)
            error = r.get("error")
            blocked = r.get("blocked", False)
        except Exception as e:
            print(f"  ⛔  HTTP error: {e}\n")
            results.append({
                "tag": tag, "question": q, "sql": "", "synthesis": "",
                "row_count": 0, "error": str(e), "verdict": "❌",
                "issues": ["HTTP error"], "duration": time.time() - t0,
            })
            continue
        dt = time.time() - t0
        verdict, issues = grade(sql, expected, synthesis, row_count, error)
        print(f"  SQL       : {sql[:160]}")
        print(f"  Synthèse  : {synthesis[:140]}")
        print(f"  Lignes    : {row_count}  |  {dt:.1f}s  |  Verdict : {verdict}")
        if issues:
            for i in issues:
                print(f"     - {i}")
        print()
        results.append({
            "tag": tag, "question": q, "sql": sql, "synthesis": synthesis,
            "row_count": row_count, "error": error, "blocked": blocked,
            "verdict": verdict, "issues": issues, "duration": dt,
        })

    # Bilan
    ok = sum(1 for r in results if r["verdict"] == "✅")
    warn = sum(1 for r in results if r["verdict"] == "⚠️")
    ko = sum(1 for r in results if r["verdict"] == "❌")
    total = len(results)

    print("=" * 80)
    print("  BILAN V13")
    print("=" * 80)
    print(f"  ✅ OK         : {ok:>2}/{total}  ({ok/total*100:.0f}%)")
    print(f"  ⚠️  Acceptable : {warn:>2}/{total}  ({warn/total*100:.0f}%)")
    print(f"  ❌ KO         : {ko:>2}/{total}  ({ko/total*100:.0f}%)")
    print()
    if ok >= 16:
        verdict = "V13 SUFFISANT → production"
    elif ok >= 12:
        verdict = "V13.5 → 2-3 patchs ciblés du dataset"
    else:
        verdict = "V14 JUSTIFIÉE → ré-équilibrage majeur"
    print(f"  >>> VERDICT : {verdict}")
    print()

    # Détail par bloc
    print("  Détail par bloc :")
    blocs = {}
    for r in results:
        b = r["tag"][0]
        blocs.setdefault(b, []).append(r["verdict"])
    bloc_names = {
        "A": "Connexions / sessions",
        "B": "Top-N / agrégations",
        "C": "Postes / machines",
        "D": "Objets / tables",
        "E": "Fenêtres temporelles",
        "F": "Sécurité / nuances",
        "G": "Comptage",
    }
    for k, vs in sorted(blocs.items()):
        oks = vs.count("✅")
        print(f"    {k} — {bloc_names[k]:<30} : {oks}/{len(vs)} OK")

    out = Path("benchmark_v13_20q_report.json")
    out.write_text(json.dumps({
        "total": total, "ok": ok, "warn": warn, "ko": ko,
        "verdict": verdict, "details": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Rapport JSON : {out}")


if __name__ == "__main__":
    main()
