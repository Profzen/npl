import requests, json, time

TOKEN = "720e_1IlRdX4uaXrXI9zqhqPaowx7WTebcmEX8DkgGY"
H = {"X-Auth-Token": TOKEN}
BASE = "http://127.0.0.1:8000/api/query"

QUESTIONS = [
    "Qui s'est connecte hier ?",
    "Combien d'utilisateurs dans la base ?",
    "Quels utilisateurs se sont connectes dans les 48 dernieres heures ?",
    "Qu'est-ce qui s'est passe en janvier 2026 ?",
    "Quelle table a ete la plus modifiee ?",
    "Quelles actions VROMUALD a-t-il effectuees sur la table EMPLOYEES ?",
    "Quel poste de travail a effectue le plus de connexions ?",
    "Y a-t-il eu des suppressions de comptes utilisateurs ?",
    "Qui a le plus change d'informations au cours des 30 derniers jours ?",
    "Quels utilisateurs se sont connectes entre 22h et 6h du matin ?",
]

results = []
for i, q in enumerate(QUESTIONS, 1):
    print(f"\n{'='*60}")
    print(f"  Q{i}: {q}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        r = requests.post(BASE, json={"question": q, "username": "admin"}, headers=H, timeout=300)
        d = r.json()
        dt = time.time() - t0
        sql = d.get("sql", "")
        synthesis = d.get("synthesis", "")
        rows = len(d.get("rows", []))
        error = d.get("error", "")
        print(f"  SQL: {sql}")
        print(f"  Synthese: {synthesis[:200]}")
        print(f"  Lignes: {rows}")
        print(f"  Temps: {dt:.1f}s")
        if error:
            print(f"  ERREUR: {error}")
        results.append({"id": f"Q{i}", "question": q, "sql": sql, "synthesis": synthesis[:150], "rows": rows, "time": round(dt,1), "error": error})
    except Exception as e:
        dt = time.time() - t0
        print(f"  EXCEPTION: {e}")
        results.append({"id": f"Q{i}", "question": q, "sql": "", "synthesis": "", "rows": 0, "time": round(dt,1), "error": str(e)})

print(f"\n\n{'='*60}")
print("  BILAN DES 10 QUESTIONS")
print(f"{'='*60}")
ok = 0
ko = 0
for r in results:
    status = "OK" if r["rows"] > 0 and not r["error"] else "KO"
    if status == "OK":
        ok += 1
    else:
        ko += 1
    print(f"  {r['id']:4s} [{status}] {r['time']:5.1f}s | {r['rows']:3d} lignes | {r['question']}")
    if r["error"]:
        print(f"        ERR: {r['error'][:100]}")
    print(f"        SQL: {r['sql'][:120]}")
print(f"\n  Score: {ok}/{len(results)} OK")

# Save results
with open("test_v12_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("  Resultats sauvegardes: test_v12_results.json")
