import re
from typing import Any

from app.config import settings

try:
    from llama_cpp import Llama

    _PHI3_STACK_AVAILABLE = True
except Exception:
    Llama = None
    _PHI3_STACK_AVAILABLE = False

SYSTEM_PROMPT_FR = (
    "Tu es un assistant qui explique des informations de securite a des responsables non-techniciens.\\n"
    "Tu recois une question en francais et TOUTES les lignes du resultat d une interrogation.\\n"
    "Ton role : resumer ce resultat en 2 a 5 phrases claires en mentionnant TOUS les elements.\\n"
    "OBLIGATOIRE : si plusieurs lignes, cite chaque element (utilisateur, action, date) ou precise le nombre exact.\\n"
    "Regles strictes :\\n"
    "- Ne mentionne jamais SQL, requete, table, colonne, base de donnees\\n"
    "- LOGON=connexion, LOGOFF=deconnexion, SELECT=consultation, INSERT=ajout\\n"
    "- UPDATE=modification, DELETE=suppression, GRANT=attribution de droits\\n"
    "- REVOKE=retrait de droits, ALTER=modification de structure\\n"
    "- Si aucun resultat: dis qu'aucune activite n'a ete detectee\\n"
    "- Ne repete pas la question"
)

_PHI3_MODEL: Any = None
_PHI3_ERROR: str | None = None


def phi3_status() -> tuple[str, str | None]:
    global _PHI3_MODEL, _PHI3_ERROR

    if _PHI3_MODEL is not None:
        return "loaded", None
    if _PHI3_ERROR:
        return "fallback", _PHI3_ERROR
    if not _PHI3_STACK_AVAILABLE:
        _PHI3_ERROR = "llama_cpp indisponible"
        return "fallback", _PHI3_ERROR

    try:
        _PHI3_MODEL = Llama(model_path=settings.phi3_path, n_ctx=2048, n_gpu_layers=0, verbose=False)
        return "loaded", None
    except Exception as exc:
        _PHI3_ERROR = str(exc)
        _PHI3_MODEL = None
        return "fallback", _PHI3_ERROR


def _rows_to_nlp_text(rows: list[dict], max_rows: int = 25, max_chars: int = 2600) -> str:
    if not rows:
        return "Aucun resultat."

    action_map = {
        "LOGON": "Connexion",
        "LOGOFF": "Deconnexion",
        "SELECT": "Consultation",
        "INSERT": "Ajout",
        "UPDATE": "Modification",
        "DELETE": "Suppression",
        "GRANT": "Attribution de droits",
        "REVOKE": "Retrait de droits",
    }

    lines: list[str] = []
    for idx, row in enumerate(rows[:max_rows], start=1):
        parts: list[str] = []
        for k, v in row.items():
            if v is None:
                continue
            value = str(v)
            if str(k).upper() == "ACTION_NAME":
                value = action_map.get(value, value)
            parts.append(f"{k}: {value}")
        if parts:
            lines.append(f"Ligne {idx} - " + " | ".join(parts))

    txt = "\n".join(lines)
    if len(txt) > max_chars:
        txt = txt[:max_chars].rsplit("\n", 1)[0]
    return txt if txt else "Aucun resultat."


def _cleanup_phi3_text(text: str) -> str:
    cleaned = (text or "").strip()
    markers = [
        "Instruction 2",
        "Instruction:",
        "Vous etes un assistant",
        "Vous êtes un assistant",
        "Question :",
        "Resultat :",
    ]
    for marker in markers:
        idx = cleaned.find(marker)
        if idx != -1:
            cleaned = cleaned[:idx].strip()

    cleaned = re.sub(r"^\s*Instruction\s*\d*\s*[:\-]?.*$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE).strip()
    sentences = re.split(r"(?<=[\?\.\!])\s+", cleaned)
    if len(sentences) > 10:
        cleaned = " ".join(sentences[:10]).strip()
    return cleaned


_ACTION_FR = {
    "LOGON": "connexion",
    "LOGOFF": "deconnexion",
    "SELECT": "consultation",
    "INSERT": "ajout",
    "UPDATE": "modification",
    "DELETE": "suppression",
    "GRANT": "attribution de droits",
    "REVOKE": "retrait de droits",
    "CREATE TABLE": "creation de table",
    "CREATE": "creation",
    "ALTER": "modification de structure",
    "DROP": "suppression d objet",
    "AUDIT": "audit",
}


def _action_fr(raw: str) -> str:
    raw = (raw or "").strip().upper()
    return _ACTION_FR.get(raw, raw.lower()) if raw else ""


def _rule_synthesis(rows: list[dict]) -> str:
    """Always-correct rule-based synthesis that enumerates every row."""
    n = len(rows)
    if n == 0:
        return "Aucune activite detectee."

    # Single row — might be an aggregate (COUNT(*)) or a single record
    if n == 1:
        row = rows[0]
        cols = {k.upper(): v for k, v in row.items() if v is not None}
        non_null = {k: v for k, v in cols.items() if str(v).strip() not in ("", "None")}

        # Pure COUNT result
        if len(non_null) == 1:
            k, v = next(iter(non_null.items()))
            if any(x in k for x in ("COUNT", "TOTAL", "NB", "NUMBER")):
                return f"Le resultat est : {v}."

        action = _action_fr(str(non_null.get("ACTION_NAME", "") or ""))
        user = str(non_null.get("DBUSERNAME") or non_null.get("USERNAME") or "")
        date = str(non_null.get("EVENT_TIMESTAMP", "") or "")[:10]
        obj = str(non_null.get("OBJECT_NAME", "") or "")

        parts = ["1 resultat trouve."]
        if action:
            parts.append(f"Action : {action}.")
        if user:
            parts.append(f"Utilisateur : {user}.")
        if obj:
            parts.append(f"Objet : {obj}.")
        if date:
            parts.append(f"Date : {date}.")
        return " ".join(parts)

    # Multiple rows — enumerate all of them (cap at 20 for very large sets)
    MAX_ENUM = 20
    items: list[str] = []
    for i, row in enumerate(rows[:MAX_ENUM], start=1):
        cols = {k.upper(): v for k, v in row.items() if v is not None}
        non_null = {k: v for k, v in cols.items() if str(v).strip() not in ("", "None")}

        action = _action_fr(str(non_null.get("ACTION_NAME", "") or ""))
        user = str(non_null.get("DBUSERNAME") or non_null.get("USERNAME") or "")
        date = str(non_null.get("EVENT_TIMESTAMP", "") or "")[:10]
        obj = str(non_null.get("OBJECT_NAME", "") or "")
        host = str(non_null.get("USERHOST", "") or "")

        parts: list[str] = []
        if action:
            parts.append(action)
        if user:
            parts.append(f"par {user}")
        if obj:
            parts.append(f"sur {obj}")
        if date:
            parts.append(f"le {date}")
        if host and not user:
            parts.append(f"depuis {host}")

        # Fallback: first non-null value
        if not parts:
            first_val = next(iter(non_null.values()), None)
            if first_val is not None:
                parts.append(str(first_val))

        items.append(f"{i}. {' '.join(parts)}" if parts else f"{i}. (ligne {i})")

    suffix = f" (et {n - MAX_ENUM} autres)" if n > MAX_ENUM else ""
    return f"{n} resultats trouves{suffix} : " + " — ".join(items) + "."


def build_synthesis(question: str, rows: list[dict], error: str | None) -> str:
    if error:
        return f"La requete n'a pas pu etre executee: {error}"
    if not rows:
        return "Aucune activite detectee pour cette demande."

    n = len(rows)
    rule = _rule_synthesis(rows)

    # For multiple rows, the rule-based synthesis is always complete and correct.
    # LLM models consistently truncate enumerations, so we only use LLM for n==1.
    if n > 1:
        return rule

    status, _ = phi3_status()
    if status != "loaded":
        return rule

    # LLM only for single-row explanations where it excels
    resultat_brut = _rows_to_nlp_text(rows)
    prompt = (
        f"<|system|>{SYSTEM_PROMPT_FR}<|end|>"
        f"<|user|>Question : {question}\n"
        f"Resultat : {resultat_brut[:1200]}<|end|>"
        "<|assistant|>"
    )

    try:
        resp = _PHI3_MODEL(
            prompt,
            max_tokens=300,
            temperature=0.15,
            repeat_penalty=1.05,
            stop=["<|end|>", "<|user|>", "Instruction 2", "Instruction:"],
        )
        text = resp.get("choices", [{}])[0].get("text", "")
        cleaned = _cleanup_phi3_text(text)
        if cleaned:
            return cleaned
    except Exception:
        pass

    return rule
