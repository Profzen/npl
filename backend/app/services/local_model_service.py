from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, datetime
from typing import Any, Iterable

from app.services.intent_policy import normalize_intent


MODEL_URL = os.getenv("AUDITAI_MODEL_URL", "http://127.0.0.1:8080/v1/chat/completions")
MODEL_HEALTH_URL = os.getenv("AUDITAI_MODEL_HEALTH_URL", "http://127.0.0.1:8080/health")
MODEL_TIMEOUT_SECONDS = int(os.getenv("AUDITAI_MODEL_TIMEOUT_SECONDS", "120"))

_INTENT_PROMPT = """Tu extrais une intention de lecture des journaux d'audit Oracle.
Réponds uniquement par un objet JSON, sans SQL ni explication:
{"status":"query|clarification|refusal","users":[],"objects":[],"actions":[],
"period":null,"aggregate":null,"failed_only":false,"limit":200,"clarification":null}
N'invente aucune entité. Une liste vide signifie tous.
Périodes: today, yesterday, last_friday, range_weekdays, last_14_days, night_range,
this_week, this_month, last_30_days, compare_today_yesterday ou null.
Agrégats: count_distinct_user, top_action, compare, top_host, top_user, top_objects ou null.
Actions: LOGON, LOGOFF, SELECT, INSERT, UPDATE, DELETE, GRANT, REVOKE, ALTER, TRUNCATE,
CREATE USER, DROP USER, ALTER USER, CREATE TABLE, DROP TABLE.
Une question sur une suppression ou un droit est une consultation d'audit.
Un ordre réel de modifier les données est refusal.
Une référence inexploitable ou une date ambiguë est clarification."""

_SYNTHESIS_PROMPT = """Tu expliques un résultat d'audit Oracle à une personne non informaticienne.
Réponds en français, directement, en 1 à 5 phrases.
Conserve exactement les noms, nombres, dates, heures et postes fournis.
N'invente aucun fait. Ne parle ni de SQL, ni de colonnes, ni de modèle.
Si plusieurs lignes sont fournies, indique le nombre et résume les faits pertinents."""

_ACTION_FR = {
    "LOGON": "connexion",
    "LOGOFF": "déconnexion",
    "SELECT": "consultation",
    "INSERT": "ajout",
    "UPDATE": "modification",
    "DELETE": "suppression",
    "GRANT": "attribution de droits",
    "REVOKE": "retrait de droits",
    "ALTER": "modification de structure",
    "TRUNCATE": "vidage de table",
    "CREATE USER": "création de compte",
    "DROP USER": "suppression de compte",
}


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat(sep=" ")
    return str(value)


def _strip_fences(content: str) -> str:
    text = (content or "").strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith(fence):
            text = text.rstrip()[:-3]
    return text.strip()


def _chat(system_prompt: str, user_content: str, *, max_tokens: int, json_mode: bool = False) -> str:
    payload: dict[str, Any] = {
        "model": "local-model",
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        MODEL_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=MODEL_TIMEOUT_SECONDS) as response:
        body = json.load(response)
    content = body.get("choices", [{}])[0].get("message", {}).get("content") or ""
    text = _strip_fences(content)
    if not text:
        raise RuntimeError("Le modèle local a renvoyé une réponse vide")
    return text


def local_model_status() -> tuple[str, str | None]:
    try:
        with urllib.request.urlopen(MODEL_HEALTH_URL, timeout=2) as response:
            if 200 <= response.status < 300:
                return "loaded", None
        return "error", "serveur local indisponible"
    except Exception as exc:
        return "error", str(exc)


def interpret_question(
    question: str,
    known_users: Iterable[str],
    known_objects: Iterable[str],
) -> tuple[dict[str, Any], str | None]:
    raw_intent: dict[str, Any] = {}
    model_error: str | None = None
    try:
        content = _chat(_INTENT_PROMPT, question, max_tokens=220, json_mode=True)
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            raw_intent = parsed
        else:
            model_error = "L'intention du modèle n'est pas un objet JSON"
    except Exception as exc:
        model_error = str(exc)
    return normalize_intent(question, raw_intent, known_users, known_objects), model_error


def _rule_synthesis(rows: list[dict[str, Any]], error: str | None = None) -> str:
    if error:
        return "La recherche n'a pas abouti. Vérifiez la connexion locale puis reformulez la demande."
    if not rows:
        return "Aucune activité ne correspond à cette demande."
    if len(rows) == 1:
        row = {str(key).upper(): value for key, value in rows[0].items() if value is not None}
        if "TODAY_COUNT" in row and "YESTERDAY_COUNT" in row:
            return (
                f"Aujourd'hui : {row['TODAY_COUNT']} événement(s). "
                f"Hier : {row['YESTERDAY_COUNT']} événement(s)."
            )
        count_key = next(
            (key for key in row if key.endswith("_COUNT") or key in {"COUNT", "TOTAL"}),
            None,
        )
        if count_key and len(row) == 1:
            return f"Le résultat est {row[count_key]}."
        if "EVENT_COUNT" in row:
            count = row["EVENT_COUNT"]
            if row.get("ACTION_NAME"):
                return f"L'action la plus fréquente est {row['ACTION_NAME']}, avec {count} événement(s)."
            if row.get("DBUSERNAME"):
                return f"L'utilisateur le plus actif est {row['DBUSERNAME']}, avec {count} événement(s)."
            if row.get("USERHOST"):
                return f"Le poste le plus concerné est {row['USERHOST']}, avec {count} événement(s)."
            if row.get("OBJECT_NAME"):
                return f"L'objet le plus concerné est {row['OBJECT_NAME']}, avec {count} événement(s)."
        parts = []
        if row.get("DBUSERNAME"):
            parts.append(f"utilisateur {row['DBUSERNAME']}")
        if row.get("ACTION_NAME"):
            parts.append(_ACTION_FR.get(str(row["ACTION_NAME"]).upper(), str(row["ACTION_NAME"])))
        if row.get("OBJECT_NAME"):
            parts.append(f"sur {row['OBJECT_NAME']}")
        if row.get("EVENT_TIMESTAMP"):
            parts.append(f"le {_json_default(row['EVENT_TIMESTAMP'])}")
        if row.get("USERHOST"):
            parts.append(f"depuis {row['USERHOST']}")
        if row.get("RETURNCODE") not in (None, 0, "0"):
            parts.append(f"code d'échec {row['RETURNCODE']}")
        return "Un événement a été trouvé : " + ", ".join(parts) + "."
    return f"{len(rows)} événements correspondent à la demande. Consultez le tableau pour le détail exact."


def build_local_synthesis(question: str, rows: list[dict[str, Any]], error: str | None) -> str:
    if error or not rows or len(rows) == 1:
        return _rule_synthesis(rows, error)
    compact_rows = rows[:25]
    user_content = (
        f"Question: {question}\n"
        f"Nombre total de lignes: {len(rows)}\n"
        "Résultats contrôlés: "
        + json.dumps(compact_rows, ensure_ascii=False, default=_json_default)
    )
    try:
        return _chat(_SYNTHESIS_PROMPT, user_content[:5000], max_tokens=180)
    except Exception:
        return _rule_synthesis(rows, error)

