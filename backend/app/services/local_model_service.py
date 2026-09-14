from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.request
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from app.services.query_plan_service import normalize_query_plan


MODEL_URL = os.getenv("AUDITAI_MODEL_URL", "http://127.0.0.1:8080/v1/chat/completions")
MODEL_HEALTH_URL = os.getenv("AUDITAI_MODEL_HEALTH_URL", "http://127.0.0.1:8080/health")
MODEL_TIMEOUT_SECONDS = int(os.getenv("AUDITAI_MODEL_TIMEOUT_SECONDS", "120"))
MODEL_REVIEW_ENABLED = os.getenv("AUDITAI_MODEL_REVIEW_ENABLED", "false").lower() == "true"

_INTENT_PROMPT = """Tu es le moteur sémantique d’AuditAI. Tu aides des personnes non informaticiennes à consulter un journal d’audit Oracle en français, même avec des fautes, des synonymes ou une formulation inhabituelle.
Tu comprends le besoin métier, mais tu ne produis jamais de SQL. Tu réponds uniquement par un objet JSON valide suivant ce contrat :
{"status":"query|clarification|refusal","source":"events|users|objects|actions","dimensions":[],"calculation":null,"filters":[],"time":{"mode":"all"},"comparison_ranges":[],"group_by":[],"order_by":[],"limit":null,"response_mode":"detail|list|ranking|count|comparison","clarification":null}

Champs sémantiques disponibles :
- dimensions : user, object, action, host, program, timestamp, day, return_code.
- calculation : {"operation":"count|count_distinct|min|max|avg","field":"event|user|object|action|host|program|timestamp|day|return_code"}.
- filter : {"field":"...","operator":"eq|ne|contains|in|success|failure","value":"..."}. Une action générique ne crée aucun filtre. Actions précises : LOGON, LOGOFF, SELECT, INSERT, UPDATE, DELETE, GRANT, REVOKE, ALTER, TRUNCATE, CREATE USER, DROP USER, ALTER USER, CREATE TABLE, DROP TABLE, ALTER TABLE.
- time.mode : all, today, yesterday, relative_last, current, previous, between, before, after, previous_weekday.
- relative_last utilise unit minute|hour|day|week|month|year et value=N.
- current/previous utilise unit day|week|month|year. « le mois dernier » = previous month ; « ces 10 derniers jours » = relative_last day 10.
- between utilise start et end au format ISO ; before utilise end ; after utilise start ; previous_weekday utilise weekday en anglais.
- order_by : {"field":"event_count|value|user|object|action|host|program|timestamp|day|return_code","direction":"asc|desc"}.

Règles de raisonnement :
- « qui/quel compte a fait le plus » : source events, group_by user, count event, ordre event_count desc, limite 1, ranking. « le moins » est identique avec ordre asc.
- « dernier utilisateur/personne » : détail des événements, tri timestamp desc, limite demandée ; ne signifie pas compter les utilisateurs.
- « liste des tables/objets » : source objects, dimension object, list. « liste des utilisateurs » : source users. « liste des actions » : source actions.
- Pour comparer plusieurs périodes, response_mode comparison et comparison_ranges avec un libellé et un objet time par période.
- Une demande de consultation d’une suppression reste query. Une demande qui ordonne de modifier réellement la base est refusal. Si le sens nécessaire manque réellement, clarification.
- N’invente aucun utilisateur, objet, nombre ou date. Les valeurs connues sont fournies avec la question.

Exemples de composition du contrat (les nombres et périodes peuvent varier librement) :
- « Quel compte a le plus d’opérations sur les 7 dernières semaines ? » : group_by user, count event, relative_last week 7, ordre event_count desc, limite 1, ranking.
- « Qui est la dernière personne à avoir agi ? » : dimensions user, action, object, timestamp, host ; aucun calcul ni groupement ; ordre timestamp desc ; limite 1 ; detail.
- « Liste les tables auditées » : source objects, dimension object, aucun calcul, list.
- « Quels postes ont eu des échecs pendant les 4 dernières heures ? » : filtre failure, relative_last hour 4, group_by host, count event.
- « Combien de comptes distincts entre 2026-08-01 et 2026-08-15 ? » : count_distinct user, time between avec ces deux dates, count.
"""


_PLAN_REVIEW_PROMPT = """Tu contrôles le plan sémantique produit par AuditAI à partir de la question d’origine.
Retourne uniquement le JSON complet corrigé, dans le même contrat. Ne produis jamais de SQL.
Vérifie chaque contrainte exprimée : source demandée, calcul, distinct, regroupement, plus/moins, ordre,
quantité de résultats, période relative ou absolue, action, objet, utilisateur, succès ou échec.
Un nombre qui mesure une durée ne devient jamais une limite de résultats.
Supprime tout filtre, dimension ou groupement que la question ne demande pas.
Une liste de tables utilise source=objects et ne retourne pas des événements.
Une personne qui a agi en dernier utilise order_by timestamp desc et limit=1, sans compter les événements.
Un classement par activité utilise count event, group_by et order_by event_count.
Si le plan exprime fidèlement la question, recopie-le sans changement."""

_SYNTHESIS_PROMPT = """Tu expliques un résultat d'audit Oracle à une personne non informaticienne.
Réponds en français, directement, en 1 à 5 phrases, avec une formulation naturelle adaptée à la question.
Conserve exactement les noms, nombres, dates, heures et postes fournis.
N'invente aucun fait. Ne parle ni de SQL, ni de colonnes, ni de modèle, ni de lignes techniques.
Attribue une action uniquement aux utilisateurs fournis. Ne dis jamais que l'audit, le journal, la base ou le système a effectué une action.
Résume les faits pertinents. Mentionne le nombre d'événements seulement s'il aide directement à répondre.
Ne présente jamais une limite technique de résultats comme un fait métier."""

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
        today = date.today().isoformat()
        context = (
            f"Date locale actuelle : {today}\n"
            f"Utilisateurs connus : {json.dumps(list(known_users), ensure_ascii=False)}\n"
            f"Objets connus : {json.dumps(list(known_objects), ensure_ascii=False)}\n"
            f"Question : {question}"
        )
        content = _chat(_INTENT_PROMPT, context, max_tokens=160, json_mode=True)
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            raw_intent = parsed
            if MODEL_REVIEW_ENABLED:
                review_content = (
                    f"{context}\n"
                    f"Plan proposé : {json.dumps(raw_intent, ensure_ascii=False)}"
                )
                reviewed = json.loads(
                    _chat(_PLAN_REVIEW_PROMPT, review_content, max_tokens=520, json_mode=True)
                )
                if isinstance(reviewed, dict):
                    raw_intent = reviewed
        else:
            model_error = "L'intention du modèle n'est pas un objet JSON"
    except Exception as exc:
        model_error = str(exc)
    return normalize_query_plan(question, raw_intent, known_users, known_objects), model_error


def _is_latest_user_question(question: str, intent: Mapping[str, Any] | None = None) -> bool:
    if intent and intent.get("aggregate") == "latest_users":
        return True
    normalized = unicodedata.normalize("NFKD", question)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char)).upper()
    return bool(
        re.search(r"\b(DERNIERS?|DERNIERES?|RECENTS?|RECENTES?)\b", normalized)
        and re.search(r"\b(USERS?|UTILISATEURS?|COMPTES?)\b", normalized)
    )


def _rule_synthesis(
    rows: list[dict[str, Any]],
    error: str | None = None,
    question: str = "",
    intent: Mapping[str, Any] | None = None,
) -> str:
    if error:
        return "La recherche n'a pas abouti. Vérifiez la connexion locale puis reformulez la demande."
    if not rows:
        return "Aucune activité ne correspond à cette demande."

    source = str((intent or {}).get("source") or "")
    if source in {"users", "objects", "actions"}:
        key = {"users": "DBUSERNAME", "objects": "OBJECT_NAME", "actions": "ACTION_NAME"}[source]
        values = list(dict.fromkeys(
            str(row[key]) for row in rows if row.get(key) not in (None, "")
        ))
        labels = {"users": "utilisateurs", "objects": "tables ou objets audités", "actions": "actions auditées"}
        if not values:
            return f"Aucun élément n’a été trouvé dans la liste des {labels[source]}."
        return f"Voici les {labels[source]} : " + ", ".join(values) + "."

    if len(rows) == 1:
        row = {str(key).upper(): value for key, value in rows[0].items() if value is not None}
        period_keys = sorted(key for key in row if re.fullmatch(r"PERIOD_\d+_COUNT", key))
        if period_keys:
            ranges = (intent or {}).get("comparison_ranges") or []
            parts = []
            for index, key in enumerate(period_keys):
                label = (
                    str(ranges[index].get("label"))
                    if index < len(ranges) and isinstance(ranges[index], Mapping)
                    else f"Période {index + 1}"
                )
                parts.append(f"{label} : {row[key]} événement(s)")
            return ". ".join(parts) + "."
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
                order = (intent or {}).get("order_by") or []
                ascending = bool(order and isinstance(order[0], Mapping) and order[0].get("direction") == "asc")
                qualifier = "le moins actif" if ascending else "le plus actif"
                return f"L'utilisateur {qualifier} est {row['DBUSERNAME']}, avec {count} événement(s)."
            if row.get("USERHOST"):
                return f"Le poste le plus concerné est {row['USERHOST']}, avec {count} événement(s)."
            if row.get("OBJECT_NAME"):
                return f"L'objet le plus concerné est {row['OBJECT_NAME']}, avec {count} événement(s)."
        action = _ACTION_FR.get(
            str(row.get("ACTION_NAME") or "").upper(),
            str(row.get("ACTION_NAME") or "activité"),
        )
        actor = (
            f"L'utilisateur {row['DBUSERNAME']}"
            if row.get("DBUSERNAME")
            else "Un utilisateur"
        )
        detail = f"{actor} a réalisé l'opération « {action} »"
        if row.get("OBJECT_NAME"):
            detail += f" sur {row['OBJECT_NAME']}"
        if row.get("EVENT_TIMESTAMP"):
            detail += f" le {_json_default(row['EVENT_TIMESTAMP'])}"
        if row.get("USERHOST"):
            detail += f" depuis {row['USERHOST']}"
        if row.get("RETURNCODE") not in (None, 0, "0"):
            detail += f", avec le code d'échec {row['RETURNCODE']}"
        if _is_latest_user_question(question, intent) and row.get("DBUSERNAME"):
            return f"Le dernier utilisateur correspondant est {row['DBUSERNAME']}. {detail}."
        return f"Un événement correspond à la demande. {detail}."
    if len(rows) <= 3:
        descriptions: list[str] = []
        for raw_row in rows:
            row = {str(key).upper(): value for key, value in raw_row.items() if value is not None}
            if "EVENT_COUNT" in row:
                if row.get("OBJECT_NAME"):
                    descriptions.append(f"{row['OBJECT_NAME']} totalise {row['EVENT_COUNT']} événement(s)")
                elif row.get("ACTION_NAME"):
                    descriptions.append(f"{row['ACTION_NAME']} totalise {row['EVENT_COUNT']} événement(s)")
                elif row.get("DBUSERNAME"):
                    descriptions.append(f"{row['DBUSERNAME']} totalise {row['EVENT_COUNT']} événement(s)")
                elif row.get("USERHOST"):
                    descriptions.append(f"{row['USERHOST']} totalise {row['EVENT_COUNT']} événement(s)")
                else:
                    descriptions.append(f"{row['EVENT_COUNT']} événement(s)")
                continue

            action = _ACTION_FR.get(
                str(row.get("ACTION_NAME") or "").upper(),
                str(row.get("ACTION_NAME") or "activité"),
            )
            actor = (
                f"L'utilisateur {row['DBUSERNAME']}"
                if row.get("DBUSERNAME")
                else "Un utilisateur"
            )
            detail = f"{actor} a réalisé l'opération « {action} »"
            if row.get("OBJECT_NAME"):
                detail += f" sur {row['OBJECT_NAME']}"
            if row.get("EVENT_TIMESTAMP"):
                detail += f" le {_json_default(row['EVENT_TIMESTAMP'])}"
            if row.get("USERHOST"):
                detail += f" depuis {row['USERHOST']}"
            if row.get("RETURNCODE") not in (None, 0, "0"):
                detail += f", avec le code d'échec {row['RETURNCODE']}"
            descriptions.append(detail)

        count_label = "Deux" if len(rows) == 2 else "Trois"
        if _is_latest_user_question(question, intent):
            return f"Voici les {count_label.lower()} derniers utilisateurs concernés. " + ". ".join(descriptions) + "."
        return f"{count_label} événements correspondent à la demande. " + ". ".join(descriptions) + "."
    normalized_rows = [
        {str(key).upper(): value for key, value in raw_row.items() if value is not None}
        for raw_row in rows
    ]
    if normalized_rows and all("EVENT_COUNT" in row for row in normalized_rows):
        label_key = next(
            (key for key in ("DBUSERNAME", "OBJECT_NAME", "ACTION_NAME", "USERHOST", "EVENT_DAY") if any(row.get(key) for row in normalized_rows)),
            None,
        )
        if label_key:
            ranking = ", ".join(
                f"{row.get(label_key, '-')} ({row['EVENT_COUNT']})" for row in normalized_rows
            )
            return f"Classement par nombre d’événements : {ranking}."
    users = list(dict.fromkeys(
        str(row["DBUSERNAME"]) for row in normalized_rows if row.get("DBUSERNAME")
    ))
    actions = list(dict.fromkeys(
        _ACTION_FR.get(str(row["ACTION_NAME"]).upper(), str(row["ACTION_NAME"]))
        for row in normalized_rows if row.get("ACTION_NAME")
    ))
    objects = list(dict.fromkeys(
        str(row["OBJECT_NAME"]) for row in normalized_rows if row.get("OBJECT_NAME")
    ))
    if users:
        context = "Pour les événements correspondants"
        if len(actions) == 1:
            context = f"Pour l'opération « {actions[0]} »"
        if len(objects) == 1:
            context += f" sur {objects[0]}"
        return f"{context}, les utilisateurs concernés sont : {', '.join(users)}."
    return "Plusieurs événements correspondent à la demande. Consultez le tableau pour le détail exact."


def _generated_synthesis_is_acceptable(answer: str) -> bool:
    normalized = unicodedata.normalize("NFKD", answer)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char)).upper()
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized).strip()
    if not normalized:
        return False
    if re.search(r"\b(SQL|COLONNES?|MODELES?|LIGNES?)\b", normalized):
        return False
    return not re.search(
        r"\b(L AUDIT|LE JOURNAL|LA BASE|LE SYSTEME)\s+A\b",
        normalized,
    )


def build_local_synthesis(
    question: str,
    rows: list[dict[str, Any]],
    error: str | None,
    intent: Mapping[str, Any] | None = None,
) -> str:
    deterministic_modes = {"ranking", "count", "comparison"}
    if (
        error
        or not rows
        or len(rows) <= 3
        or str((intent or {}).get("source") or "") in {"users", "objects", "actions"}
        or str((intent or {}).get("response_mode") or "") in deterministic_modes
    ):
        return _rule_synthesis(rows, error, question, intent)
    compact_rows = rows[:25]
    user_content = (
        f"Question: {question}\n"
        f"Nombre total de lignes: {len(rows)}\n"
        "Résultats contrôlés: "
        + json.dumps(compact_rows, ensure_ascii=False, default=_json_default)
    )
    try:
        answer = _chat(_SYNTHESIS_PROMPT, user_content[:5000], max_tokens=180)
        if _generated_synthesis_is_acceptable(answer):
            return answer
        return _rule_synthesis(rows, error, question, intent)
    except Exception:
        return _rule_synthesis(rows, error, question, intent)

