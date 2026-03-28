# ============================================================
#  SMART2D — Oracle Audit Intelligence  (VERSION PROD)
#
#  ARCHITECTURE :
#  - Login géré en Python (st.session_state.connecte)
#    → survit aux rechargements Streamlit, pas de retour au login
#  - Formulaire Streamlit natif (st.form) pour la question
#    → le champ HTML appelle le formulaire caché via JS
#  - HTML intégré directement dans le .py
#  - Connexion Oracle via oracledb mode Thin (sans Oracle Client)
#  - Pipeline : TinyLlama LoRA → SQL → Oracle → Phi-3 → FR
#
#  Lancer : streamlit run app_queryflow_prod.py
# ============================================================

import os, zipfile, torch, pandas as pd, re
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
from llama_cpp import Llama

try:
    import oracledb
    ORACLE_OK = True
except ImportError:
    ORACLE_OK = False

st.set_page_config(
  page_title="SMART2D — Oracle Audit Intelligence",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════
# CONFIGURATION ORACLE
# ══════════════════════════════════════════════════════════════
ORACLE_USER     = "aziz"
ORACLE_PASSWORD = "aziz"
ORACLE_HOST     = "192.168.132.177"
ORACLE_PORT     = 1791
ORACLE_SERVICE  = "OSCARDB1"
ORACLE_DSN      = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"
ORACLE_TABLE    = "SMART2DSECU.UNIFIED_AUDIT_DATA"

# ══════════════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════════════
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

SYSTEM_PROMPT_FR = (
    "Tu es un assistant qui explique des informations de securite a des responsables non-techniciens.\n"
    "Tu recois une question en francais et le resultat brut d'une interrogation.\n"
    "Ton role : traduire ce resultat en 1 a 3 phrases claires, comprehensibles.\n"
    "\n"
    "Regles strictes :\n"
    "- Ne mentionne JAMAIS : SELECT, INSERT, UPDATE, DELETE, LOGON, LOGOFF, ALTER TABLE,\n"
    "  DROP, GRANT, REVOKE, SQL, Oracle, requete, colonne, table, base de donnees\n"
    "- LOGON=connexion, LOGOFF=deconnexion, SELECT=consultation, INSERT=ajout,\n"
    "  UPDATE=modification, DELETE=suppression, ALTER TABLE=modification de structure,\n"
    "  CREATE USER=creation de compte, DROP USER=suppression de compte,\n"
    "  GRANT=attribution de droits, REVOKE=retrait de droits\n"
    "- Conserve toujours les noms exacts des utilisateurs, tables et objets tels qu'ils apparaissent dans les resultats\n"
    "- Structure : qui a fait quoi, quand\n"
    "- Si activite anormale : signale-le en debut de reponse\n"
    "- Si aucun resultat : dis qu'aucune activite n'a ete detectee\n"
    "- Tu parles uniquement des donnees d'audit observees, jamais de l'ensemble de la base\n"
    "- Ne repete pas la question, ne montre pas le SQL\n"
    "- Francais naturel uniquement\n"
)

# ══════════════════════════════════════════════════════════════
# ORACLE
# ══════════════════════════════════════════════════════════════
def get_oracle_connection():
    if not ORACLE_OK:
        msg = "oracledb non installe — pip install oracledb"
        print(f"[ORACLE] ERREUR : {msg}", flush=True)
        return None, msg
    try:
        print(f"[ORACLE] Tentative connexion : {ORACLE_DSN} (user={ORACLE_USER})", flush=True)
        conn = oracledb.connect(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_DSN
        )
        print(f"[ORACLE] Connexion etablie avec succes", flush=True)
        return conn, None
    except Exception as e:
        print(f"[ORACLE] ECHEC connexion : {e}", flush=True)
        print(f"[ORACLE]   DSN    : {ORACLE_DSN}", flush=True)
        print(f"[ORACLE]   User   : {ORACLE_USER}", flush=True)
        print(f"[ORACLE]   Cause  : {type(e).__name__}", flush=True)
        return None, str(e)

def normalize_oracle_value(value):
    if value is None:
        return None
    if ORACLE_OK and isinstance(value, oracledb.LOB):
        try:
            return value.read()
        except Exception:
            return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat(sep=" ")
        except TypeError:
            return value.isoformat()
    return value

def oracle_cursor_to_dataframe(cur) -> pd.DataFrame:
    cols = [d[0].upper() for d in cur.description]
    rows = cur.fetchall()
    normalized_rows = [
        [normalize_oracle_value(cell) for cell in row]
        for row in rows
    ]
    return pd.DataFrame(normalized_rows, columns=cols)

def executer_sql_oracle(sql: str):
    print(f"[SQL] Execution :\n{sql}", flush=True)
    conn, err = get_oracle_connection()
    if conn is None:
        return None, err
    try:
        cur = conn.cursor()
        # Oracle cursor.execute n'accepte pas le point-virgule final
        sql_exec = sql.rstrip().rstrip(";").rstrip()
        cur.execute(sql_exec)
        df = oracle_cursor_to_dataframe(cur)
        cur.close()
        conn.close()
        print(f"[SQL] Succes : {len(df)} ligne(s) retournee(s)", flush=True)
        return df, None
    except Exception as e:
        print(f"[SQL] ECHEC execution : {e}", flush=True)
        try: conn.close()
        except: pass
        return None, str(e)

# ══════════════════════════════════════════════════════════════
# CHARGEMENT DONNÉES
# ══════════════════════════════════════════════════════════════
def unzip_if_needed(zip_path, target_dir):
    if not os.path.exists(target_dir) and os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(".")

@st.cache_data(ttl=300)
def load_audit_data():
    print(f"[DATA] Chargement {ORACLE_TABLE}...", flush=True)
    conn, err = get_oracle_connection()
    if conn is not None:
        try:
            # Diagnostic : lister les tables accessibles à cet utilisateur
            cur_diag = conn.cursor()
            cur_diag.execute(
                "SELECT owner, table_name FROM all_tables "
                "WHERE UPPER(table_name) LIKE '%AUDIT%' "
                "ORDER BY owner, table_name"
            )
            tables = cur_diag.fetchall()
            if tables:
                print(f"[DATA] Tables AUDIT accessibles :", flush=True)
                for owner, tname in tables:
                    print(f"[DATA]   {owner}.{tname}", flush=True)
            else:
                print("[DATA] Aucune table contenant AUDIT trouvee", flush=True)
                # Lister toutes les tables accessibles
                cur_diag.execute(
                    "SELECT owner, table_name FROM all_tables "
                    "WHERE owner NOT IN ('SYS','SYSTEM','MDSYS','CTXSYS','WMSYS') "
                    "ORDER BY owner, table_name FETCH FIRST 30 ROWS ONLY"
                )
                all_t = cur_diag.fetchall()
                print(f"[DATA] Premieres tables accessibles :", flush=True)
                for owner, tname in all_t:
                    print(f"[DATA]   {owner}.{tname}", flush=True)
            cur_diag.close()
        except Exception as diag_e:
            print(f"[DATA] Diagnostic tables impossible : {diag_e}", flush=True)
        try:
          cur = conn.cursor()
          query = (
            f"SELECT * FROM {ORACLE_TABLE} "
            "ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST 5000 ROWS ONLY"
          )
          print(f"[DATA] Execution : {query[:80]}...", flush=True)
          cur.execute(query.rstrip().rstrip(";").rstrip())
          df = oracle_cursor_to_dataframe(cur)
          cur.close()
          conn.close()
          print(f"[DATA] Succes Oracle : {len(df)} lignes chargees", flush=True)
          return df, "oracle"
        except Exception as e:
          print(f"[DATA] ECHEC chargement Oracle : {e}", flush=True)
          try:
            conn.close()
          except:
            pass
    else:
        print(f"[DATA] Connexion Oracle impossible : {err}", flush=True)
    return pd.DataFrame(), "oracle_error"

# ══════════════════════════════════════════════════════════════
# POST-PROCESSING SQL
# ══════════════════════════════════════════════════════════════
def post_process_sql(sql: str, question: str) -> str:
  q_lower = question.lower()
  sql = sql.replace("≥", ">=").replace("≤", "<=")
  sql = re.sub(r"\bDB_USER\b", "DBUSERNAME", sql, flags=re.IGNORECASE)
  sql = re.sub(r"\bOBJ_NAME\b", "OBJECT_NAME", sql, flags=re.IGNORECASE)
  sql = re.sub(r"\bAUDIT_ID\b", "ID", sql, flags=re.IGNORECASE)
  sql = re.sub(r"\bOS_HOST\b", "USERHOST", sql, flags=re.IGNORECASE)
  sql = re.sub(
    r"SUBSTR\s*\(\s*TIMESTAMP\s*,\s*1\s*,\s*10\s*\)\s*(>=|<=|=|>|<)\s*"
    r"TO_CHAR\s*\(\s*SYSDATE\s*-\s*(\d+)\s*,\s*'YYYY-MM-DD'\s*\)",
    lambda m: f"TRUNC(EVENT_TIMESTAMP) {m.group(1)} TRUNC(SYSDATE-{m.group(2)})",
    sql,
    flags=re.IGNORECASE,
  )

  su = sql.upper()
  if "DBUSERNAME" not in su and "USERNAME" not in su:
    sql = re.sub(
      r"SELECT\s+MAX\(EVENT_TIMESTAMP\)",
      "SELECT DBUSERNAME, ACTION_NAME, MAX(EVENT_TIMESTAMP) AS DERNIERE_ACTION",
      sql,
      flags=re.IGNORECASE,
    )

  if re.search(r"OBJECT_NAME\s*=\s*'\d+'", sql, re.IGNORECASE):
    known = [
      "EMPLOYEES", "VROMUALD", "CLIENTS", "TRANSACTIONS", "ORDERS", "ACCOUNTS",
      "PAYROLL", "JOURNAL", "CONTRACTS", "BUDGET", "PRODUCTS", "SUPPLIERS",
      "INVOICES", "USERS", "PAYMENTS", "AUDIT_LOG", "UNIFIED_AUDIT_DATA", "V$SESSION",
    ]
    found = next((obj for obj in known if obj.lower() in q_lower), "EMPLOYEES")
    sql = re.sub(
      r"OBJECT_NAME\s*=\s*'\d+'",
      "OBJECT_NAME='" + found + "'",
      sql,
      flags=re.IGNORECASE,
    )

  sql = re.sub(r"\bUSERNAME\b", "DBUSERNAME", sql, flags=re.IGNORECASE)
  sql = re.sub(r"\b(DBA_USERS|ALL_USERS|USER_USERS)\b", "ORACLE_AUDIT_TRAIL", sql, flags=re.IGNORECASE)

  asks_all = any(token in q_lower for token in [
    "pour chacun", "chacun", "tous", "toutes", "chaque utilisateur", "chacune",
  ])
  if asks_all and re.search(r"\bGROUP\s+BY\b", sql, re.IGNORECASE):
    sql = re.sub(r"\s+FETCH\s+FIRST\s+1\s+ROWS\s+ONLY", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s+FETCH\s+FIRST\s+1\s+ROW\s+ONLY", "", sql, flags=re.IGNORECASE)

  asks_objects = any(token in q_lower for token in ["objet", "objets"]) and any(
    token in q_lower for token in ["modifi", "modifié", "modifiés", "plus mod"]
  )
  wrong_grouping_users = re.search(r"\bGROUP\s+BY\s+DBUSERNAME\b", sql, re.IGNORECASE) is not None
  if asks_objects and wrong_grouping_users:
    sql = (
      "SELECT OBJECT_NAME, COUNT(*) AS NB_MODIFICATIONS "
      "FROM ORACLE_AUDIT_TRAIL "
      "WHERE ACTION_NAME IN ('CREATE TABLE','ALTER TABLE','DROP TABLE','CREATE USER','ALTER USER','DROP USER') "
      "AND OBJECT_NAME IS NOT NULL "
      "GROUP BY OBJECT_NAME "
      "ORDER BY NB_MODIFICATIONS DESC "
      "FETCH FIRST 5 ROWS ONLY;"
    )

  if ";" in sql:
    sql = sql[:sql.index(";") + 1]
  return sql.strip()


def _strip_sql_comments(sql: str) -> str:
    # Remove inline and block comments before validation.
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def apply_default_row_limit(sql: str, default_limit: int = 200) -> str:
    su = sql.upper()
    if "FETCH FIRST" in su:
      return sql
    if "COUNT(" in su:
      return sql
    if "GROUP BY" in su:
      return sql
    if not su.startswith(("SELECT", "WITH")):
      return sql

    sql_no_sc = sql.rstrip().rstrip(";").rstrip()
    return f"{sql_no_sc} FETCH FIRST {default_limit} ROWS ONLY;"


def validate_sql_guardrails(sql: str) -> tuple[bool, str]:
    normalized = _strip_sql_comments(sql).strip()
    su = normalized.upper()

    if not su:
      return False, "Requete vide apres nettoyage."

    if not su.startswith(("SELECT", "WITH")):
      return False, "Seules les requetes SELECT sont autorisees."

    forbidden = [
      "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "TRUNCATE",
      "CREATE", "GRANT", "REVOKE", "CALL", "EXECUTE", "BEGIN", "COMMIT", "ROLLBACK",
    ]
    for kw in forbidden:
      if re.search(rf"\b{kw}\b", su):
        return False, f"Operation non autorisee detectee: {kw}."

    # Reject chained statements (everything after first ';' must be whitespace).
    first_sc = normalized.find(";")
    if first_sc != -1 and normalized[first_sc + 1:].strip():
      return False, "Plusieurs instructions SQL detectees."

    allowed_table = ORACLE_TABLE.upper()
    table_refs = re.findall(r"\b(?:FROM|JOIN)\s+([A-Z0-9_.$\"]+)", su)
    if not table_refs:
      return False, "Aucune table detectee dans la requete."

    for raw_ref in table_refs:
      ref = raw_ref.strip('"')
      if ref != allowed_table:
        return False, f"Table non autorisee detectee: {ref}."

    return True, "OK"

def clean_sql(raw: str, question: str = "") -> str:
    sql = raw.strip()
    sql = re.sub(r"```sql", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```",    "", sql)
    sql = re.sub(r"^(SQL\s*:|Requ[eê]te\s*:|R[eé]ponse\s*:)\s*", "", sql, flags=re.IGNORECASE)
    for kw in ["SELECT","INSERT","UPDATE","DELETE","WITH","CREATE","DROP","ALTER","GRANT","REVOKE"]:
        idx = sql.upper().find(kw)
        if idx != -1:
            sql = sql[idx:]; break
    if ";" in sql:
        sql = sql[:sql.index(";")+1]
    sql = post_process_sql(sql.strip(), question)
    # Remplacer le nom de table entraîné par le vrai nom en base
    sql = re.sub(r"\bORACLE_AUDIT_TRAIL\b", ORACLE_TABLE, sql, flags=re.IGNORECASE)
    sql = apply_default_row_limit(sql)
    ok, reason = validate_sql_guardrails(sql)
    if not ok:
      return f"-- Requete bloquee par garde-fou: {reason}"
    return sql

# ══════════════════════════════════════════════════════════════
# MODÈLES
# ══════════════════════════════════════════════════════════════
LORA_DIR  = "tinyllama_oracle_lora"
MODEL_DIR = "TinyLlama-1.1B-Chat-v1.0"

@st.cache_resource
def load_tinyllama():
    unzip_if_needed("TinyLlama-1.1B-Chat-v1.0.zip", MODEL_DIR)
    unzip_if_needed("tinyllama_oracle_lora.zip", LORA_DIR)
    if not os.path.exists(MODEL_DIR) or not os.path.exists(LORA_DIR):
        return None, None, None
    tok  = AutoTokenizer.from_pretrained(MODEL_DIR)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.float32)
    mdl  = PeftModel.from_pretrained(base, LORA_DIR)
    mdl.eval()
    mdl.to(torch.device("cpu"))
    return tok, mdl, torch.device("cpu")

@st.cache_resource
def load_phi3():
    unzip_if_needed("phi3-mini-gguf.zip", "phi3-mini-gguf")
    path = os.path.join("phi3-mini-gguf", "Phi-3-mini-4k-instruct-q4.gguf")
    if not os.path.exists(path):
        return None
    return Llama(model_path=path, n_ctx=2048, n_gpu_layers=0, verbose=False)

def generer_sql(question, tokenizer, model, device):
    prompt = (
        f"<|system|>{SYSTEM_PROMPT}<|end|>"
        f"<|user|>{question}<|end|>"
        f"<|assistant|>"
    )
    inputs = tokenizer(prompt, return_tensors="pt",
                       truncation=True, max_length=1024).to(device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=150, do_sample=False,
            pad_token_id=tokenizer.eos_token_id
        )
    raw = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:],
                           skip_special_tokens=True)
    return clean_sql(raw, question)

def traduire_resultat(
  question: str,
  resultat_brut: str,
  phi3,
  allow_no_activity_sentence: bool = True,
) -> str:
    if phi3 is None:
        return ""
    nl = "\n"
    prompt = (
        f"<|system|>{SYSTEM_PROMPT_FR}<|end|>"
        "<|user|>Question : " + question + nl
        + "Resultat : " + resultat_brut[:800] + "<|end|>"
        "<|assistant|>"
    )
    try:
        resp = phi3(
            prompt,
            max_tokens=400,
            temperature=0.15,
            repeat_penalty=1.05,
            stop=["<|end|>", "<|user|>", "Instruction 2", "Instruction:", "Vous êtes un assistant"]
        )
        try:
            st.session_state["last_phi3_raw"] = resp
        except Exception:
            pass
        text = resp.get("choices", [{}])[0].get("text", "")
    except Exception as e:
        return f"Erreur synthèse modèle: {e}"

    text = text.strip()

    # Remove trailing prompt/instruction leakage if present in output
    cut_markers = [
        "Instruction 2", "Instruction:", "Vous êtes un assistant",
        "Tu es un assistant", "Question :", "Résultat brut :", "Resultat brut :"
    ]
    for marker in cut_markers:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx].strip()

    # Remove common prefix leaks
    text = re.sub(r"^\s*Instruction\s*\d*\s*[:\-]?.*$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    if text.lower().startswith("tu es un") or text.lower().startswith("vous êtes un") or text.lower().startswith("vous etes un"):
        parts = re.split(r"\n\s*\n", text, maxsplit=1)
        if len(parts) == 2:
            text = parts[1].strip()

    # Remove tautological or contradictory no-activity phrasing when results exist
    if not allow_no_activity_sentence:
        text = re.sub(
            r"(?i)si\s+aucune\s+activit[ée].*?(?:\.|$)",
            "",
            text,
        ).strip()
        text = re.sub(
            r"(?i)aucune\s+activit[ée]\s+n['’]a\s+[ée]t[ée]\s+d[ée]tect[ée]e.*?(?:\.|$)",
            "",
            text,
        ).strip()

    # Keep output concise and complete for UI
    sentences = re.split(r"(?<=[\.\?\!])\s+", text)
    if len(sentences) > 3:
        text = " ".join(sentences[:3]).strip()

    if not text:
        if not allow_no_activity_sentence:
            return "Aucune information exploitable n'a pu être formulée malgré des résultats présents."
        text = "Aucune activité notable n'a été détectée sur la période analysée."

    # Keep wording aligned with audit scope rather than the whole database.
    text = re.sub(r"(?i)dans la base de donn[ée]es", "dans les données d'audit", text)
    text = re.sub(r"(?i)de la base de donn[ée]es", "des données d'audit", text)
    text = re.sub(r"(?i)il y a (\d+) utilisateurs? dans les données d'audit", r"\1 utilisateurs distincts apparaissent dans les données d'audit", text)
    text = re.sub(r"(?i)le nombre d'utilisateurs", "le nombre d'utilisateurs distincts observés dans l'audit", text)
    return text

def synthese_aucune_activite(question: str) -> str:
    q = (question or "").strip()
    ql = q.lower()

    periode = "sur la période demandée"
    m = re.search(r"(\d+)\s*(jour|jours|semaine|semaines|mois|heure|heures)", ql)
    if m:
        n = m.group(1)
        unit = m.group(2)
        if unit.startswith("semaine"):
            unit = "semaine" if n == "1" else "semaines"
        elif unit.startswith("jour"):
            unit = "jour" if n == "1" else "jours"
        elif unit.startswith("mois"):
            unit = "mois"
        else:
            unit = "heure" if n == "1" else "heures"
        if n == "1":
            periode = f"sur le dernier {unit} demandé"
        else:
            periode = f"sur les {n} {unit} demandés"
    elif "aujourd" in ql:
        periode = "aujourd'hui"
    elif "hier" in ql:
        periode = "hier"
    elif "ce mois" in ql:
        periode = "ce mois-ci"

    sujet = "correspondante"
    if any(k in ql for k in ["connect", "connexion", "logon"]):
        sujet = "de connexion"
    elif any(k in ql for k in ["deconnect", "déconnexion", "logoff"]):
        sujet = "de déconnexion"
    elif any(k in ql for k in ["compte", "user", "utilisateur"]):
        sujet = "liée aux comptes utilisateurs"
    elif any(k in ql for k in ["table", "objet", "schema", "schéma"]):
        sujet = "sur les objets demandés"
    elif any(k in ql for k in ["grant", "revoke", "droit", "permission", "privil"]):
        sujet = "de gestion des droits"
    elif any(k in ql for k in ["select", "insert", "update", "delete", "action"]):
        sujet = "du type demandé"

    # Extraire des cibles explicites depuis la question (utilisateur / objet / table)
    quoted = re.findall(r"[\"'«“]([A-Za-z0-9_.$#-]{2,})[\"'»”]", q)

    user_match = re.search(
      r"(?i)(?:utilisateur|user|compte)\s+([A-Za-z][A-Za-z0-9_.$#-]{1,})",
      q,
    )
    object_match = re.search(
      r"(?i)(?:table|objet|schema|schéma)\s+([A-Za-z][A-Za-z0-9_.$#-]{1,})",
      q,
    )

    ignored_tokens = {
      "QUI", "QUOI", "QUEL", "QUELS", "QUELLE", "QUELLES", "POUR", "SUR", "DANS",
      "LES", "DES", "UNE", "UN", "BASE", "DONNEES", "DONNÉES", "UTILISATEUR", "TABLE",
      "OBJET", "OBJETS", "ACTION", "ACTIONS", "JOUR", "JOURS", "SEMAINE", "SEMAINES",
      "MOIS", "HEURE", "HEURES", "DERNIER", "DERNIERE", "DERNIÈRE", "DERNIERS", "DERNIÈRES",
    }
    upper_tokens = re.findall(r"\b[A-Z][A-Z0-9_.$#-]{2,}\b", q)
    upper_tokens = [t for t in upper_tokens if t.upper() not in ignored_tokens]

    user_target = user_match.group(1) if user_match else None
    object_target = object_match.group(1) if object_match else None
    generic_target = quoted[0] if quoted else (upper_tokens[0] if upper_tokens else None)

    cible = ""
    if user_target and object_target:
      cible = f" pour l'utilisateur {user_target} sur {object_target}"
    elif user_target:
      cible = f" pour l'utilisateur {user_target}"
    elif object_target:
      cible = f" pour {object_target}"
    elif generic_target:
      cible = f" pour {generic_target}"

    if q:
      return f"Aucune activité {sujet}{cible} n'a été observée {periode}, en réponse à votre demande."
    return f"Aucune activité {sujet} n'a été observée {periode}."

def df_to_html_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return '<p style="color:#888;font-size:13px;padding:8px">Aucun résultat.</p>'

    display_df = df.copy()
    # Friendly column names for non-technical users
    col_map = {
        "ID": "Identifiant",
        "EVENT_TIMESTAMP": "Date/Heure",
        "DBUSERNAME": "Utilisateur",
        "ACTION_NAME": "Action",
        "OBJECT_NAME": "Objet",
        "USERHOST": "Poste",
        "SQL_TEXT": "Détail",
        "NB": "Nombre",
        "NB_MODIFICATIONS": "Nombre",
    }
    display_df.rename(columns={c: col_map.get(c, c) for c in display_df.columns}, inplace=True)

    # Friendly action labels
    action_map = {
        "LOGON": "Connexion",
        "LOGOFF": "Déconnexion",
        "SELECT": "Consultation",
        "INSERT": "Ajout",
        "UPDATE": "Modification",
        "DELETE": "Suppression",
        "ALTER TABLE": "Modification de structure",
        "CREATE TABLE": "Création de table",
        "DROP TABLE": "Suppression de table",
        "ALTER USER": "Modification de compte",
        "CREATE USER": "Création de compte",
        "DROP USER": "Suppression de compte",
        "GRANT": "Attribution de droits",
        "REVOKE": "Retrait de droits",
    }
    if "Action" in display_df.columns:
        display_df["Action"] = display_df["Action"].apply(lambda x: action_map.get(str(x), str(x)))

    headers = "".join(f"<th>{c}</th>" for c in display_df.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{v}</td>" for v in row.values) + "</tr>"
        for _, row in display_df.head(100).iterrows()
    )
    return (
        '<div style="overflow-x:auto;margin-top:10px">'
        f'<table class="result-table"><thead><tr>{headers}</tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )

def df_to_nlp_text(df: pd.DataFrame, max_rows: int = 30, max_chars: int = 2500) -> str:
    """Convertit un DataFrame en texte explicite 'clé: valeur' pour éviter
    que Phi-3 confonde les noms de colonnes avec les valeurs."""
    if df is None or df.empty:
        return "Aucun résultat."

    col_map = {
        "ID": "Identifiant",
        "EVENT_TIMESTAMP": "Date/Heure",
        "DBUSERNAME": "Utilisateur",
        "ACTION_NAME": "Action",
        "OBJECT_NAME": "Objet",
        "USERHOST": "Poste",
        "SQL_TEXT": "Détail",
        "NB": "Nombre",
        "NB_MODIFICATIONS": "Nombre",
    }
    action_map = {
        "LOGON": "Connexion",
        "LOGOFF": "Déconnexion",
        "SELECT": "Consultation",
        "INSERT": "Ajout",
        "UPDATE": "Modification",
        "DELETE": "Suppression",
        "ALTER TABLE": "Modification de structure",
        "CREATE TABLE": "Création de table",
        "DROP TABLE": "Suppression de table",
        "ALTER USER": "Modification de compte",
        "CREATE USER": "Création de compte",
        "DROP USER": "Suppression de compte",
        "GRANT": "Attribution de droits",
        "REVOKE": "Retrait de droits",
    }

    work_df = df.head(max_rows).copy()
    lines = []
    for idx, (_, row) in enumerate(work_df.iterrows(), start=1):
        parts = []
        for col in work_df.columns:
            label = col_map.get(str(col).upper(), str(col))
            val = row[col]
            if pd.isna(val):
                continue
            val_str = str(val)
            if str(col).upper() == "ACTION_NAME":
                val_str = action_map.get(val_str, val_str)
            parts.append(f"{label}: {val_str}")
        if parts:
            lines.append(f"Ligne {idx} - " + " | ".join(parts))

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0]
    return text if text else "Aucun résultat."

# ══════════════════════════════════════════════════════════════
# SESSION STATE — clé : tout survit aux rechargements Streamlit
# ══════════════════════════════════════════════════════════════
defaults = {
    "connecte":     False,
    "current_user": "",
    "historique":   [],
    "page":         "home",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Masquer les éléments Streamlit natifs
st.markdown("""
<style>
#MainMenu,footer,header,.stDeployButton,.stDecoration{display:none!important}
.block-container{padding:0!important;max-width:100%!important}
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
  background:
    radial-gradient(1200px 520px at 6% -10%,#ffe8ec 0%,transparent 62%),
    radial-gradient(980px 500px at 95% 8%,#eef3fb 0%,transparent 58%),
    #f6f7f9!important;
}
iframe{background:transparent!important}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# PAGE LOGIN — gérée en Python pur
# Streamlit re-exécute ce bloc à chaque interaction.
# Tant que connecte=False, on affiche le login et on s'arrête.
# ══════════════════════════════════════════════════════════════
if not st.session_state.connecte:
    st.markdown("""
    <style>
    body,.stApp{background:
      radial-gradient(1200px 520px at 6% -10%,#ffe8ec 0%,transparent 62%),
      radial-gradient(980px 500px at 95% 8%,#eef3fb 0%,transparent 58%),
      #f6f7f9!important}
    div[data-testid="stTextInput"] input{
      border-radius:10px!important;border:1.5px solid #d0d6e2!important;
      background:#fff!important;color:#141821!important;font-size:14px!important;height:42px!important}
    div[data-testid="stTextInput"] input:focus{
      border-color:#b30018!important;
      box-shadow:0 0 0 3px rgba(179,0,24,.16)!important}
    div[data-testid="stTextInput"] label{
      font-size:12px!important;font-weight:700!important;
      color:#5c6678!important;text-transform:uppercase!important;
      letter-spacing:.04em!important}
    .stButton>button{
      background:linear-gradient(135deg,#b30018,#7e0a1a)!important;
      color:#fff!important;border:none!important;border-radius:10px!important;
      font-weight:700!important;font-size:14px!important;height:44px!important;
      box-shadow:0 2px 10px rgba(179,0,24,.3)!important}
    .stButton>button:hover{
      background:linear-gradient(135deg,#8f0014,#b30018)!important;
      box-shadow:0 4px 16px rgba(179,0,24,.4)!important}
    </style>
    """, unsafe_allow_html=True)

    # Centrer le formulaire
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("""
        <div style="margin-top:60px"></div>
        <div style="background:#ffffff;border:1px solid #d8dde6;border-radius:18px;
          padding:32px 32px 24px;box-shadow:0 8px 32px rgba(17,24,39,.12)">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:28px">
            <div style="width:40px;height:40px;
              background:linear-gradient(135deg,#b30018,#7e0a1a);
              border-radius:10px;display:flex;align-items:center;justify-content:center">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff"
                stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <ellipse cx="12" cy="5" rx="8" ry="3"/>
                <path d="M4 5v10c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>
                <path d="M4 10c0 1.7 3.6 3 8 3s8-1.3 8-3"/>
              </svg>
            </div>
            <div>
              <div style="font-size:22px;font-weight:800;color:#8f0014;
                letter-spacing:-.02em;line-height:1">SMART2D</div>
              <div style="font-size:11px;color:#5c6678;margin-top:2px">
                &middot; SMART2D</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        user = st.text_input("Identifiant", placeholder="Votre identifiant",
                             key="login_user")
        pwd  = st.text_input("Mot de passe", type="password",
                             placeholder="••••••••", key="login_pass")

        if st.button("Se connecter", use_container_width=True):
            if user.strip() and pwd.strip():
                st.session_state.connecte     = True
                st.session_state.current_user = user.strip()
                st.rerun()
            else:
                st.error("Veuillez renseigner identifiant et mot de passe.")

    st.stop()   # ← rien d'autre n'est rendu tant que non connecté

# ══════════════════════════════════════════════════════════════
# DÉCONNEXION — bouton natif Streamlit dans la sidebar cachée
# ══════════════════════════════════════════════════════════════
if st.sidebar.button("__deconnexion__", key="btn_deconnexion"):
    st.session_state.connecte     = False
    st.session_state.current_user = ""
    st.rerun()

# ══════════════════════════════════════════════════════════════
# CHARGEMENT MODÈLES + DONNÉES
# ══════════════════════════════════════════════════════════════
tok, mdl, dev     = load_tinyllama()
audit_df, data_src = load_audit_data()

# ══════════════════════════════════════════════════════════════
# FORMULAIRE QUESTION — rendu caché, déclenché par le HTML
# Le champ HTML appelle document.getElementById('qf-submit')
# qui est un vrai bouton Streamlit, ce qui déclenche le rerun
# sans perdre la session.
# ══════════════════════════════════════════════════════════════
result_sql      = ""
result_synthese = ""
result_html_out = ""
result_erreur   = ""

with st.form("qf_form", clear_on_submit=True):
    question_input = st.text_input("q", label_visibility="collapsed", key="qf_input")
    submitted      = st.form_submit_button("Envoyer", use_container_width=False)

if submitted and question_input.strip():
    question = question_input.strip()
    now = datetime.now().strftime("%H:%M:%S")

    # ── Étape 1 : TinyLlama génère le SQL ──
    print(f"[NLP] Question : {question}", flush=True)
    if tok is not None:
        # Pas de st.spinner() — le spinner est géré côté HTML/JS
        # pour ne pas griser la page
        result_sql = generer_sql(question, tok, mdl, dev)
        print(f"[NLP] SQL genere : {result_sql}", flush=True)
    else:
        result_sql = "-- Modèle TinyLlama non disponible."
        print("[NLP] ERREUR : TinyLlama non charge", flush=True)

    # ── Étape 2 : Exécution Oracle ──
    res_txt = ""
    result_has_rows = False
    if not result_sql.startswith("--"):
      df_res, err_oracle = executer_sql_oracle(result_sql)
      if df_res is not None:
        result_has_rows = not df_res.empty
        result_html_out = df_to_html_table(df_res)
        res_txt = df_to_nlp_text(df_res)
      else:
        result_erreur = err_oracle or "Erreur inconnue"
        result_html_out = (
          '<div style="background:#fff3f3;border:1px solid #f5c6cb;'
          'border-radius:8px;padding:12px;font-size:13px;margin-top:8px">'
          '<strong>&#9888; La requête n\'a pas pu être exécutée sur la base.</strong><br/>'
          '<span style="color:#666;font-size:12px">' + result_erreur + '</span>'
          '</div>'
        )
        res_txt = "Erreur Oracle : " + result_erreur
    else:
      result_erreur = result_sql

    # ── Étape 3 : Phi-3 traduit en français ──
    if res_txt and "Erreur" not in res_txt:
      if not result_has_rows:
        result_synthese = synthese_aucune_activite(question)
      else:
        phi3_model = load_phi3()
        result_synthese = traduire_resultat(
          question,
          res_txt,
          phi3_model,
          allow_no_activity_sentence=False,
        )

    # ── Stocker dans l'historique ──
    st.session_state.historique.append({
        "question": question,
        "sql":      result_sql,
        "synthese": result_synthese,
        "erreur":   result_erreur,
        "html":     result_html_out,
        "time":     now,
    })

# Récupérer le dernier résultat pour l'affichage
if st.session_state.historique:
    last            = st.session_state.historique[-1]
    result_sql      = last["sql"]
    result_synthese = last["synthese"]
    result_html_out = last["html"]
    result_erreur   = last["erreur"]

# ══════════════════════════════════════════════════════════════
# CONSTRUCTION DES DONNÉES HTML
# ══════════════════════════════════════════════════════════════

# Statut Oracle
if data_src == "oracle":
    statut_db = (
        '<span style="display:inline-flex;align-items:center;gap:6px;font-size:11px;'
        'font-weight:600;color:#1a7a4a;background:#e8f7ef;border:1px solid #b6e5cc;'
        'border-radius:20px;padding:4px 10px">'
        '<span style="width:6px;height:6px;background:#22c55e;border-radius:50%;'
        'display:inline-block;animation:pulse 2s infinite"></span>'
    'Oracle connect&eacute;</span>'
    )
else:
    statut_db = (
        '<span style="font-size:11px;font-weight:600;color:#991b1b;background:#fee2e2;'
        'border:1px solid #fca5a5;border-radius:20px;padding:4px 10px">'
    '&#10060; Oracle indisponible</span>'
    )

# Colonnes de droite (prod): utilisateurs + objets Oracle réels + guide actions
USERS_REELS = []
TABLES_REELLES = []

if not audit_df.empty:
  recent_action_map = {
    "LOGON": "Connexion",
    "LOGOFF": "Déconnexion",
    "SELECT": "Consultation",
    "INSERT": "Ajout",
    "UPDATE": "Modification",
    "DELETE": "Suppression",
    "ALTER TABLE": "Modification de structure",
    "CREATE TABLE": "Création de table",
    "DROP TABLE": "Suppression de table",
    "ALTER USER": "Modification de compte",
    "CREATE USER": "Création de compte",
    "DROP USER": "Suppression de compte",
    "GRANT": "Attribution de droits",
    "REVOKE": "Retrait de droits",
  }
  if "DBUSERNAME" in audit_df.columns:
    user_counts = (
      audit_df["DBUSERNAME"]
      .dropna()
      .astype(str)
      .value_counts()
      .head(100)
    )
    USERS_REELS = [
      {"name": username, "actions": int(count)}
      for username, count in user_counts.items()
    ]

  if "OBJECT_NAME" in audit_df.columns:
    object_counts = (
      audit_df["OBJECT_NAME"]
      .dropna()
      .astype(str)
      .loc[lambda series: series.str.strip() != ""]
      .value_counts()
      .head(100)
    )
    TABLES_REELLES = [
      {"name": object_name, "actions": int(count)}
      for object_name, count in object_counts.items()
    ]

if not USERS_REELS and not TABLES_REELLES:
  print("[DATA] Aucune donnee Oracle exploitable pour les colonnes de droite", flush=True)

users_html = "".join(
  "<li" + (" class='extra-row'" if i >= 20 else "") + "><span>" + u["name"] + "</span>"
  + "<span class='count-pill'>" + str(u["actions"]) + " actions</span></li>"
  for i, u in enumerate(USERS_REELS)
) or "<li><span style='color:#888'>Aucun utilisateur disponible</span></li>"

users_toggle_display = "inline-flex" if len(USERS_REELS) > 20 else "none"

tables_html = "".join(
  "<li" + (" class='extra-row'" if i >= 16 else "") + "><span>" + t["name"] + "</span>"
  + "<span class='count-pill'>" + str(t["actions"]) + " actions</span></li>"
  for i, t in enumerate(TABLES_REELLES)
) or "<li><span style='color:#888'>Aucun objet disponible</span></li>"

tables_toggle_display = "inline-flex" if len(TABLES_REELLES) > 16 else "none"

guide_rows = [
  ("LOGON",   "#22c55e",  "Connexion d'un utilisateur Oracle"),
  ("LOGOFF",  "#4ade80",  "Déconnexion d'un utilisateur"),
  ("SELECT",  "#60a5fa",  "Lecture / consultation de données"),
  ("INSERT",  "#fbbf24",  "Ajout d'une nouvelle ligne"),
  ("UPDATE",  "#fb923c",  "Modification d'une donnée existante"),
  ("DELETE",  "#f87171",  "Suppression d'une ligne de données"),
  ("CREATE",  "#c084fc",  "Création d'un objet (table, user…)"),
  ("ALTER",   "#a78bfa",  "Modification de structure d'objet"),
  ("DROP",    "#f43f5e",  "Suppression définitive d'un objet"),
  ("GRANT",   "#22d3ee",  "Attribution de droits d'accès"),
  ("REVOKE",  "#38bdf8",  "Retrait de droits d'accès"),
]
guide_html = "".join(
  "<li>"
  + "<span class='action-tag' style='background:" + col + "1a;border-color:" + col + "55;color:" + col + "'>" + code + "</span>"
  + "<span style='font-size:11px;color:#2f3a4d;line-height:1.35'>" + desc + "</span>"
  + "</li>"
  for code, col, desc in guide_rows
)

# Bloc résultat
# Bandeau question posée
def question_bandeau(q):
    if not q:
        return ""
    return (
      "<div style='background:#f6f8fb;border:1px solid #d8dde6;border-radius:8px;"
      "padding:10px 14px;margin-bottom:12px;font-size:13px;color:#141821'>"
      "<strong style='color:#b30018;font-size:11px;text-transform:uppercase;"
        "letter-spacing:.05em;display:block;margin-bottom:4px'>Question</strong>"
        + q + "</div>"
    )

if result_sql and not result_sql.startswith("--"):
    result_block = (
        question_bandeau(st.session_state.historique[-1]["question"]
                         if st.session_state.historique else "")
        + "<h3>Requ&ecirc;te g&eacute;n&eacute;r&eacute;e</h3>"
        + "<div class='sql-box'>"
        + result_sql.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        + "</div>"
        + ("<div class='synthese-box'>&#x2705; " + result_synthese + "</div>"
           if result_synthese else "")
        + ("<h3>R&eacute;sultat</h3>" + result_html_out
           if result_html_out else "")
    )
    result_class = "result"
elif result_sql.startswith("--"):
    result_block = (
        question_bandeau(st.session_state.historique[-1]["question"]
                         if st.session_state.historique else "")
        + "<div class='synthese-box' style='background:#fff3f3;"
        "border-color:#f5c6cb;color:#7f1d1d'>"
        "&#9888; " + result_sql + "</div>"
    )
    result_class = "result"
else:
    result_block = (
        "<div>"
        "<div class='empty-icon'>&#x1F50D;</div>"
        "<div style='font-size:14px;font-weight:600;color:#2f3a4d;margin-bottom:6px'>"
        "Aucune question pos&eacute;e</div>"
        "<div style='font-size:12px;color:#657089'>"
        "Saisissez votre question dans le champ ci-dessus</div>"
        "</div>"
    )
    result_class = "result empty"

# Historique
history_rows = ""
for entry in reversed(st.session_state.historique):
    q   = entry["question"].replace('"', "&quot;").replace("'", "&#39;")
    sql = entry["sql"].replace('"', "&quot;").replace("'","&#39;").replace("\n", " ")
    sy  = entry.get("synthese","").replace('"',"&quot;").replace("'","&#39;")
    er  = entry.get("erreur","").replace('"',"&quot;").replace("'","&#39;")
    t   = entry["time"]
    if er and not er.startswith("--"):
        badge = "<span style='color:#c0392b;font-size:11px'>&#9888; Erreur</span>"
    elif sy:
        badge = "<span style='color:#1a7a4a;font-size:11px'>&#x2705; OK</span>"
    else:
        badge = "<span style='color:#888;font-size:11px'>&#x2014;</span>"
    history_rows += (
        f'<tr data-q="{q}" data-sql="{sql}" data-sy="{sy}" data-er="{er}">'
        f"<td>{t}</td><td>{st.session_state.current_user}</td>"
        f"<td>{entry['question'][:55]+('...' if len(entry['question'])>55 else '')}</td>"
        f"<td>{badge}</td></tr>"
    )
if not history_rows:
    history_rows = (
        "<tr><td colspan='4' style='color:#888;padding:12px'>"
        "Aucune requ&ecirc;te ex&eacute;cut&eacute;e.</td></tr>"
    )

model_status = "Op&eacute;rationnel" if tok is not None else "Non disponible"
page         = st.session_state.get("page", "home")
ah = "active" if page == "home"     else ""
aH = "active" if page == "history"  else ""
aS = "active" if page == "settings" else ""

# ══════════════════════════════════════════════════════════════
# HTML COMPLET
# ══════════════════════════════════════════════════════════════
HTML = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"/>
<style>
:root{--bg:#f6f7f9;--surface:#ffffff;--line:#d8dde6;--text:#141821;
  --muted:#5c6678;--accent:#b30018;--accent-strong:#8f0014;
  --accent-light:#f3f5f8;--radius:12px;
  --shadow:0 2px 10px rgba(17,24,39,.08);
  --shadow-lg:0 8px 26px rgba(17,24,39,.14)}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif;
  background:radial-gradient(1200px 520px at 6% -10%,#ffe8ec 0%,transparent 62%),
  radial-gradient(980px 500px at 95% 8%,#eef3fb 0%,transparent 58%),#f6f7f9;
  color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-thumb{background:#c5ccd7;border-radius:3px}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.85)}}
@keyframes spin{to{transform:rotate(360deg)}}
.qf-spinner{
  display:none;position:fixed;top:50%;left:50%;
  transform:translate(-50%,-50%);z-index:9999;
  background:transparent;border:none;
  padding:0;
  box-shadow:none;
  flex-direction:column;align-items:center;gap:14px;
  min-width:auto;text-align:center;
  pointer-events:none}
.qf-spinner.active{display:flex}
.qf-spinner-ring{
  width:40px;height:40px;
  border:3px solid rgba(255,255,255,.25);
  border-top-color:#b30018;
  border-radius:50%;
  animation:spin .7s linear infinite}
.qf-spinner-text{
  font-size:12px;font-weight:700;
  color:#f4dadd;letter-spacing:.01em;
  text-shadow:none}
@keyframes spin{to{transform:rotate(360deg)}}
.icon{width:15px;height:15px;display:inline-block;vertical-align:middle;
  stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;
  stroke-linejoin:round;flex-shrink:0}
.page{display:none}.page.active{display:block}
.app-shell{min-height:100vh;display:flex;flex-direction:column}
.app-main{display:flex;flex:1;min-height:0}
.left-sidebar{width:250px;min-width:250px;background:linear-gradient(180deg,#1b1f27,#12151b);
  color:#f3f4f6;border-right:1px solid #2a2f39;display:flex;flex-direction:column;
  transition:width .2s,min-width .2s,opacity .2s,border .2s;overflow:hidden}
.left-sidebar.collapsed{width:0;min-width:0;opacity:0;border-right:none}
.sidebar-head{height:62px;display:flex;align-items:center;justify-content:center;
  font-size:20px;font-weight:800;color:#fff;border-bottom:1px solid #2a2f39}
.side-nav{padding:12px 10px;display:flex;flex-direction:column;gap:8px}
.side-nav-btn{background:transparent;border:1px solid #3a414d;color:#f3f4f6;
  min-height:38px;border-radius:9px;padding:0 12px;font-weight:700;font-size:12px;
  text-align:left;cursor:pointer;transition:all .15s;white-space:nowrap;overflow:hidden}
.side-nav-btn:hover{background:#272d37;border-color:#545d6d}
.side-nav-btn.active{background:#b30018;border-color:#cc2b3f;color:#fff}
.content-shell{flex:1;min-width:0;display:flex;flex-direction:column}
.topbar{height:62px;background:rgba(255,255,255,.96);backdrop-filter:blur(10px);
  border-bottom:1px solid #d8dde6;display:flex;align-items:center;
  padding:0 18px;gap:14px;position:sticky;top:0;z-index:50;
  box-shadow:0 2px 12px rgba(17,24,39,.08)}
.btn-sidebar-toggle{height:34px;min-width:34px;border-radius:8px;border:1px solid #c8cfdb;
  background:#f4f6f9;color:#20242d;font-weight:800;cursor:pointer}
.brand{display:flex;align-items:center;gap:9px;font-weight:800;
  color:var(--accent-strong);font-size:20px;letter-spacing:-.025em;white-space:nowrap}
.brand-icon{width:32px;height:32px;
  background:linear-gradient(135deg,var(--accent),#7e0a1a);
  border-radius:8px;display:flex;align-items:center;justify-content:center}
.topbar-right{display:flex;align-items:center;gap:10px;white-space:nowrap;margin-left:auto}
.btn-logout{height:36px;border-radius:9px;border:1.5px solid var(--line);
  background:#f2f4f8;color:var(--muted);font-weight:600;font-size:13px;
  padding:0 13px;cursor:pointer;display:inline-flex;align-items:center;
  gap:7px;transition:all .15s}
.btn-logout:hover{color:var(--text);border-color:#8f0014;background:#ffffff}
.page-wrap{width:100%;max-width:none;margin:8px 0;flex:1;padding:0 10px;
  height:calc(100vh - 74px);overflow:hidden}
.home-layout{display:grid;grid-template-columns:2.15fr .95fr .95fr .95fr;
  gap:12px;align-items:stretch;height:100%}
.home-layout > .card{height:100%}
.card{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);box-shadow:var(--shadow);transition:box-shadow .2s,border-color .2s}
.card:hover{box-shadow:var(--shadow-lg);border-color:#8f0014}
.main-card{padding:16px;min-height:0;height:100%;display:flex;flex-direction:column;
  background:#fff}
.main-title{margin:0 0 14px;font-size:20px;font-weight:700;letter-spacing:-.02em;
  display:inline-flex;align-items:center;gap:8px;color:var(--accent-strong)}
.ask-row{display:flex;gap:8px;margin-top:14px}
.ask-input{flex:1;height:44px;border:1.5px solid #c8cfdb;border-radius:10px;
  padding:0 14px;font-size:14px;color:var(--text);background:#fff;
  font-family:inherit;outline:none;transition:border-color .15s,box-shadow .15s}
.ask-input:focus{border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(179,0,24,.14);background:#fff}
.ask-input::placeholder{color:var(--muted)}
.btn-ask{height:44px;border-radius:10px;border:none;
  background:linear-gradient(135deg,var(--accent),#7e0a1a);color:#fff;
  font-weight:700;font-size:14px;padding:0 20px;cursor:pointer;
  display:inline-flex;align-items:center;gap:8px;white-space:nowrap;
  transition:all .15s;box-shadow:0 2px 8px rgba(179,0,24,.24)}
.btn-ask:hover{background:linear-gradient(135deg,var(--accent-strong),var(--accent));
  transform:translateY(-1px);box-shadow:0 4px 10px rgba(179,0,24,.24)}
.btn-ask:active{transform:translateY(0)}
.result{margin-top:4px;border:1.5px solid var(--line);border-radius:10px;
  background:linear-gradient(160deg,#ffffff,#f7f9fc);padding:14px 16px;
  min-height:140px;flex:1;max-height:560px;overflow:auto}
.result.empty{color:var(--muted);display:grid;place-items:center;text-align:center;
  padding:30px;min-height:200px;border-style:dashed;border-color:#c8cfdb}
.empty-icon{font-size:32px;margin-bottom:8px;opacity:.5}
.result h3{margin:0 0 10px;font-size:13px;font-weight:700;color:var(--accent-strong);
  text-transform:uppercase;letter-spacing:.05em}
.synthese-box{background:#f6f8fb;border:1px solid #d4dbe7;border-radius:8px;
  padding:12px 14px;font-size:14px;color:#141821;margin-bottom:12px;line-height:1.6}
.sql-box{border:1px solid #d4dbe7;border-radius:8px;background:#f8fafc;
  padding:10px 14px;font-family:"Consolas","Courier New",monospace;font-size:12px;
  color:#1f3a66;overflow-x:auto;margin-bottom:12px;white-space:pre-wrap}
.result-table{width:100%;border-collapse:collapse;font-size:12px;background:transparent;
  border:1px solid var(--line);border-radius:8px;overflow:hidden}
.result-table th{background:linear-gradient(135deg,#12151b,#20242d);color:#f4f5f7;
  font-weight:700;padding:8px 10px;text-align:left;font-size:11px;
  text-transform:uppercase;letter-spacing:.04em}
.result-table td{border-bottom:1px solid #d8dde6;padding:7px 10px;
  white-space:nowrap;color:#1b2230;background:#fff}
.result-table tbody tr:nth-child(even) td{background:#f7f9fc}
.result-table tbody tr:hover td{background:#edf2f9}
.side-card{min-height:0;height:100%;display:flex;flex-direction:column}
.side-head{padding:11px 12px;font-weight:700;font-size:13px;color:#fff;
  display:inline-flex;align-items:center;gap:8px;
  background:linear-gradient(135deg,#b30018,#8f0014);border-radius:11px 11px 0 0}
.side-body{padding:9px;display:flex;flex-direction:column;flex:1;min-height:0}
.search{height:34px;border:1.5px solid #d0d6e2;border-radius:8px;
  padding:0 10px;font-size:12px;margin-bottom:8px;width:100%;
  background:#fff;color:#1b2230;outline:none;transition:border-color .15s}
.search:focus{border-color:var(--accent)}
.simple-list{list-style:none;overflow:auto;flex:1;
  border:1px solid #d8dde6;border-radius:8px;background:#fff}
.simple-list li{display:flex;align-items:center;justify-content:space-between;
  gap:6px;padding:8px 10px;border-bottom:1px solid #e2e7f0;font-size:12px;
  font-weight:600;color:#1b2230;transition:background .12s}
.simple-list li:last-child{border-bottom:none}
.simple-list li:hover{background:#f3f6fb}
.simple-list li.extra-row{display:none}
.simple-list.expanded li.extra-row{display:flex}
.simple-list{scrollbar-gutter:stable both-edges}
.simple-list::-webkit-scrollbar{width:6px}
.simple-list::-webkit-scrollbar-thumb{background:#c5ccd7;border-radius:999px}
.list-toggle{margin-top:8px;height:30px;border-radius:8px;border:1px solid #d0d6e2;
  background:#f4f6f9;color:#2b3342;font-size:11px;font-weight:700;
  display:inline-flex;align-items:center;justify-content:center;padding:0 10px;cursor:pointer}
.list-toggle:hover{background:#fff;border-color:#8f0014}
.count-pill{font-size:10px;color:#1f2b42;
  background:linear-gradient(135deg,#f2f6fd,#eaf0fb);
  border:1px solid #c7d4ea;border-radius:999px;padding:2px 7px;flex-shrink:0}
.action-tag{font-size:10px;font-weight:700;border-radius:5px;padding:3px 8px;
  flex-shrink:0;text-align:center;border:1px solid transparent;
  letter-spacing:.04em;font-family:"Consolas","Courier New",monospace}
#guide-list{display:flex;flex-direction:column;gap:2px;overflow-y:auto;padding:0}
#guide-list li{display:flex;flex-direction:column;align-items:flex-start;
  border:1px solid #e1e6ef;border-radius:7px;background:#fff;padding:6px 10px;gap:2px;
  transition:background .12s;cursor:default}
#guide-list li:hover{background:#f8fafd;border-color:#c9d2e3}
.history-layout{display:grid;grid-template-columns:1.5fr 1fr;gap:12px;align-items:start}
.history-table-wrap,.history-detail,.settings-card{padding:14px}
.section-title{margin:0 0 12px;font-size:18px;font-weight:700;
  display:inline-flex;align-items:center;gap:8px;color:var(--accent-strong)}
.history-table{width:100%;border-collapse:collapse;font-size:12px;
  border:1px solid var(--line);border-radius:8px;overflow:hidden}
.history-table th{background:linear-gradient(135deg,#12151b,#20242d);color:#f4f5f7;
  font-weight:700;padding:8px 10px;text-align:left;font-size:11px;
  text-transform:uppercase;letter-spacing:.04em}
.history-table td{border-bottom:1px solid #d8dde6;padding:8px 10px;
  vertical-align:top;font-size:12px;color:#1b2230;background:#fff}
.history-table tbody tr:nth-child(even) td{background:#f7f9fc}
.history-table tr:hover td{background:#edf2f9;cursor:pointer}
.detail-box{border:1px solid #d8dde6;border-radius:8px;
  background:linear-gradient(135deg,#fff,#f7f9fc);
  padding:10px;margin-bottom:10px;font-size:13px}
.detail-box h4{margin:0 0 6px;font-size:11px;font-weight:700;color:var(--accent);
  text-transform:uppercase;letter-spacing:.05em}
.detail-pre{margin:0;font-family:"Consolas","Courier New",monospace;
  font-size:12px;white-space:pre-wrap;color:#2a3345}
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.setting-group{border:1px solid #d8dde6;border-radius:10px;padding:12px;
  background:linear-gradient(135deg,#fff,#f7f9fc)}
.setting-group h4{margin:0 0 10px;font-size:13px;font-weight:700;
  color:var(--accent-strong)}
.inline-field{margin-bottom:9px}
.inline-field label{display:block;font-size:11px;color:var(--muted);margin-bottom:4px;
  font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.inline-field input{width:100%;height:36px;border:1.5px solid #d0d6e2;
  border-radius:8px;padding:0 10px;font-size:13px;background:#fff;
  color:var(--text);outline:none;transition:border-color .15s}
.inline-field input:focus{border-color:var(--accent)}
.settings-actions{margin-top:12px;display:flex;gap:8px;justify-content:flex-end}
.btn-save{height:38px;border-radius:9px;border:none;
  background:linear-gradient(135deg,var(--accent),#7e0a1a);color:#fff;
  font-weight:700;font-size:13px;padding:0 16px;cursor:pointer}
.btn-reset{height:38px;border-radius:9px;border:1.5px solid var(--line);
  background:#f2f4f8;color:var(--muted);font-weight:600;font-size:13px;
  padding:0 16px;cursor:pointer}
@media(max-width:1400px){.home-layout{grid-template-columns:2fr 1fr 1fr 1fr}}
@media(max-width:1100px){.home-layout{grid-template-columns:1fr 1fr}
  .main-card{grid-column:1/span 2}}
@media(max-width:900px){.topbar{flex-wrap:wrap;height:auto;padding:12px}
  .left-sidebar{position:fixed;z-index:70;left:0;top:0;bottom:0;width:250px;min-width:250px}
  .left-sidebar.collapsed{transform:translateX(-100%);opacity:1;width:250px;min-width:250px}
  .home-layout{grid-template-columns:1fr}.main-card{grid-column:auto}
  .settings-grid{grid-template-columns:1fr}
  .history-layout{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app-shell">
  <div class="app-main">
    <aside id="left-sidebar" class="left-sidebar">
      <div class="sidebar-head">SMART2D</div>
      <div class="side-nav">
        <button class="side-nav-btn %%AH%%" onclick="showPage('home',this)">
          <span class="lbl">Accueil</span></button>
        <button class="side-nav-btn %%AHH%%" onclick="showPage('history',this)">
          <span class="lbl">Historique</span></button>
        <button class="side-nav-btn %%AS%%" onclick="showPage('settings',this)">
          <span class="lbl">Param&egrave;tres</span></button>
      </div>
    </aside>

    <div class="content-shell">
      <header class="topbar">
        <button class="btn-sidebar-toggle" onclick="toggleSidebar()">☰</button>
        <div class="brand">
          <div class="brand-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff"
              stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <ellipse cx="12" cy="5" rx="8" ry="3"/>
              <path d="M4 5v10c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>
              <path d="M4 10c0 1.7 3.6 3 8 3s8-1.3 8-3"/>
            </svg>
          </div>SMART2D
        </div>
        %%STATUT_DB%%
        <div class="topbar-right">
          <button class="btn-logout" onclick="logout()">
            <svg class="icon" viewBox="0 0 24 24">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/></svg>
            D&eacute;connexion</button>
        </div>
      </header>

      <div class="page-wrap">

    <!-- ACCUEIL -->
    <section id="page-home" class="page %%AH%%">
      <div class="home-layout">

        <article class="card main-card">
          <h2 class="main-title">
            <svg class="icon" viewBox="0 0 24 24" style="width:20px;height:20px">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            Posez votre question</h2>
          <section class="%%RC%%">%%RB%%</section>
          <div class="ask-row">
            <input id="ask-input" class="ask-input" type="text"
              placeholder="Posez votre question en fran&ccedil;ais..."
              onkeydown="if(event.key==='Enter')submitQuestion()"/>
            <button class="btn-ask" onclick="submitQuestion()">
              <svg class="icon" viewBox="0 0 24 24">
                <circle cx="11" cy="11" r="8"/>
                <line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              Interroger</button>
          </div>
        </article>

        <aside id="users-col" class="card side-card">
          <header class="side-head">
            <svg class="icon" viewBox="0 0 24 24">
              <path d="M20 21a8 8 0 1 0-16 0"/>
              <circle cx="12" cy="8" r="4"/></svg>
            Utilisateurs</header>
          <div class="side-body">
            <input id="users-search" class="search" type="search"
              placeholder="Rechercher..."
              oninput="filterList('users-list',this.value)"/>
            <ul id="users-list" class="simple-list">%%USERS%%</ul>
            <button class="list-toggle" style="display:%%USERS_TOGGLE%%"
              onclick="toggleList('users-list',this)">Voir plus</button>
          </div>
        </aside>

        <aside id="tables-col" class="card side-card">
          <header class="side-head">
            <svg class="icon" viewBox="0 0 24 24">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
              <line x1="3" y1="15" x2="21" y2="15"/>
              <line x1="9" y1="3" x2="9" y2="21"/></svg>
            Tables / Objets</header>
          <div class="side-body">
            <input id="tables-search" class="search" type="search"
              placeholder="Rechercher..."
              oninput="filterList('tables-list',this.value)"/>
            <ul id="tables-list" class="simple-list">%%TABLES%%</ul>
            <button class="list-toggle" style="display:%%TABLES_TOGGLE%%"
              onclick="toggleList('tables-list',this)">Voir plus</button>
          </div>
        </aside>

        <aside id="recent-col" class="card side-card">
          <header class="side-head"
            style="background:linear-gradient(135deg,#1e2a42,#0d1830)">
            <svg class="icon" viewBox="0 0 24 24">
              <polyline points="1 4 1 10 7 10"/>
              <path d="M3.5 15a9 9 0 1 0 .5-4"/></svg>
            Actions possibles</header>
          <div class="side-body" style="padding:6px">
            <ul id="guide-list" class="simple-list" style="border:none;background:transparent">
              %%GUIDE%%</ul>
          </div>
        </aside>
      </div>
    </section>

    <!-- HISTORIQUE -->
    <section id="page-history" class="page %%AHH%%">
      <div class="history-layout">
        <article class="card history-table-wrap">
          <h3 class="section-title">
            <svg class="icon" viewBox="0 0 24 24">
              <polyline points="1 4 1 10 7 10"/>
              <path d="M3.5 15a9 9 0 1 0 .5-4"/></svg>
            Historique des requ&ecirc;tes</h3>
          <table class="history-table">
            <thead><tr>
              <th>Heure</th><th>Utilisateur</th>
              <th>Question</th><th>Statut</th>
            </tr></thead>
            <tbody id="history-tbody">%%HISTORY%%</tbody>
          </table>
        </article>
        <article class="card history-detail" style="padding:14px">
          <h3 class="section-title">
            <svg class="icon" viewBox="0 0 24 24">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>D&eacute;tail</h3>
          <div id="hist-detail">
            <div class="detail-box">
              S&eacute;lectionnez une ligne pour voir les d&eacute;tails.</div>
          </div>
        </article>
      </div>
    </section>

    <!-- PARAMÈTRES -->
    <section id="page-settings" class="page %%AS%%">
      <article class="card settings-card">
        <h3 class="section-title">
          <svg class="icon" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="3"/></svg>
          Param&egrave;tres</h3>
        <div class="settings-grid">
          <section class="setting-group">
            <h4>G&eacute;n&eacute;ral</h4>
            <div class="inline-field"><label>Utilisateur Oracle</label>
              <input value="%%DB_USER%%" readonly/></div>
            <div class="inline-field"><label>Mot de passe Oracle</label>
              <input value="%%DB_PASS%%" readonly/></div>
            <div class="inline-field"><label>Table interrog&eacute;e</label>
              <input value="%%DB_TABLE%%" readonly/></div>
            <div class="inline-field"><label>H&ocirc;te Oracle</label>
              <input value="192.168.132.177" readonly/></div>
            <div class="inline-field"><label>Service</label>
              <input value="OSCARDB1" readonly/></div>
          </section>
          <section class="setting-group">
            <h4>Connexion</h4>
            <div class="inline-field"><label>Port</label>
              <input value="1791" readonly/></div>
            <div class="inline-field"><label>Session active (min)</label>
              <input value="30"/></div>
            <div class="inline-field"><label>Conservation logs (jours)</label>
              <input value="90"/></div>
          </section>
        </div>
        <div class="settings-actions">
          <button class="btn-reset">R&eacute;initialiser</button>
          <button class="btn-save">Sauvegarder</button>
        </div>
      </article>
    </section>

      </div>
    </div>
  </div>
</div>

<script>
// Navigation
function showPage(name, btn) {
  document.querySelectorAll('.page').forEach(p =>
    p.classList.toggle('active', p.id === 'page-' + name));
  document.querySelectorAll('.side-nav-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

function toggleSidebar() {
  const side = document.getElementById('left-sidebar');
  if (!side) return;
  side.classList.toggle('collapsed');
}

// Filtrage
function filterList(id, term) {
  document.getElementById(id).querySelectorAll('li').forEach(li =>
    li.style.display =
      li.textContent.toLowerCase().includes(term.toLowerCase()) ? '' : 'none');
}

function toggleList(id, btn) {
  const list = document.getElementById(id);
  if (!list || !btn) return;
  const expanded = list.classList.toggle('expanded');
  btn.textContent = expanded ? 'Réduire' : 'Voir plus';
}

// Déconnexion — appuie sur le bouton Streamlit caché dans la sidebar
function logout() {
  const btns = window.parent.document.querySelectorAll('button');
  for (const b of btns) {
    if (b.textContent.trim() === '__deconnexion__') { b.click(); return; }
  }
  window.parent.location.reload();
}

// Soumettre la question :
// On remplit le champ Streamlit caché et on clique le bouton Streamlit.
// Le formulaire Streamlit (st.form) prend la main, exécute le pipeline,
// et re-rend la page avec le résultat — sans perdre la session.
// ── Spinner inline (sans assombrir la page) ────────────────
function showSpinner() {
  // Afficher le spinner flottant sans griser la page
  let sp = document.getElementById('qf-global-spinner');
  if (!sp) {
    sp = document.createElement('div');
    sp.id = 'qf-global-spinner';
    sp.className = 'qf-spinner';
    sp.innerHTML =
      '<div class="qf-spinner-ring"></div>'
      + '<div class="qf-spinner-text">Analyse en cours...</div>';
    document.body.appendChild(sp);
  }
  sp.classList.add('active');
  // Désactiver le bouton pendant le traitement
  const btn = document.querySelector('.btn-ask');
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }
}
function hideSpinner() {
  const sp = document.getElementById('qf-global-spinner');
  if (sp) sp.classList.remove('active');
  const btn = document.querySelector('.btn-ask');
  if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
}

function submitQuestion() {
  const q = document.getElementById('ask-input').value.trim();
  if (!q) return;

  // Afficher le spinner sans bloquer ni assombrir la page
  showSpinner();

  // Cibler le champ texte du formulaire caché dans le parent Streamlit
  const inputs = window.parent.document.querySelectorAll('input[type="text"]');
  let qfInput = null;
  for (const inp of inputs) {
    const label = inp.getAttribute('aria-label') || '';
    if (label === 'q') { qfInput = inp; break; }
  }
  if (!qfInput) {
    for (const inp of inputs) {
      const rect = inp.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0 ||
          inp.closest('[style*="display:none"]') ||
          inp.closest('[style*="display: none"]')) {
        qfInput = inp; break;
      }
    }
  }
  if (qfInput) {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    setter.call(qfInput, q);
    qfInput.dispatchEvent(new Event('input', {bubbles: true}));
    qfInput.dispatchEvent(new Event('change', {bubbles: true}));
    setTimeout(() => {
      const btns = window.parent.document.querySelectorAll('button');
      for (const b of btns) {
        if (b.textContent.trim() === 'Envoyer') { b.click(); return; }
      }
    }, 100);
  }
}

// Historique — détail au clic
document.getElementById('history-tbody').addEventListener('click', function(e) {
  const row = e.target.closest('tr[data-q]');
  if (!row) return;
  const q = row.dataset.q||'', sql = row.dataset.sql||'',
        sy = row.dataset.sy||'', er = row.dataset.er||'';
  let h = '<div class="detail-box"><h4>Question</h4>' + q + '</div>';
  if (sql) h += '<div class="detail-box"><h4>SQL g&eacute;n&eacute;r&eacute;</h4>'
    + '<pre class="detail-pre">' + sql + '</pre></div>';
  if (sy)  h += '<div class="detail-box"><h4>R&eacute;ponse</h4>' + sy + '</div>';
  if (er)  h += '<div class="detail-box" style="border-color:#fca5a5">'
    + '<h4>Erreur</h4><span style="color:#c0392b">' + er + '</span></div>';
  document.getElementById('hist-detail').innerHTML = h;
});
</script>
</body></html>"""

# Injecter les données
html_final = (HTML
    .replace("%%STATUT_DB%%",    statut_db)
    .replace("%%USER%%",         st.session_state.current_user)
  .replace("%%DB_USER%%",      ORACLE_USER)
  .replace("%%DB_PASS%%",      ORACLE_PASSWORD)
  .replace("%%DB_TABLE%%",     ORACLE_TABLE)
    .replace("%%AH%%",           ah)
    .replace("%%AHH%%",          aH)
    .replace("%%AS%%",           aS)
    .replace("%%RC%%",           result_class)
    .replace("%%RB%%",           result_block)
    .replace("%%USERS%%",        users_html)
    .replace("%%USERS_TOGGLE%%", users_toggle_display)
    .replace("%%TABLES%%",       tables_html)
    .replace("%%TABLES_TOGGLE%%", tables_toggle_display)
    .replace("%%GUIDE%%",        guide_html)
    .replace("%%HISTORY%%",      history_rows)
    .replace("%%MODEL_STATUS%%", model_status)
)

# Masquer le formulaire Streamlit complètement
st.markdown("""
<style>
#MainMenu,footer,header,.stDeployButton,.stDecoration{display:none!important}
.block-container{padding:0!important;max-width:100%!important}
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
  background:
    radial-gradient(1200px 520px at 6% -10%,#ffe8ec 0%,transparent 62%),
    radial-gradient(980px 500px at 95% 8%,#eef3fb 0%,transparent 58%),
    #f6f7f9!important;
  overflow:auto!important;
}
iframe{background:transparent!important}
section[data-testid="stForm"],
div[data-testid="stForm"],
div[data-testid="stFormSubmitButton"],
div[data-testid="stTextInput"],
.stButton,
[data-testid="stSidebar"],
[data-testid="stSidebarContent"]{
  position:absolute!important;
  left:-9999px!important;
  top:-9999px!important;
  width:1px!important;
  height:1px!important;
  overflow:hidden!important;
  opacity:0!important;
  pointer-events:none!important;
  clip:rect(0,0,0,0)!important}
</style>
""", unsafe_allow_html=True)

components.html(html_final, height=940, scrolling=False)
