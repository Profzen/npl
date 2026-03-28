# ============================================================
#  Oracle NLP → SQL  |  QueryFlow — Interface HTML intégrée
#  Modèle : TinyLlama-1.1B + LoRA fine-tuné V4
#           Phi-3 mini Q4 local (SQL→FR) — llama-cpp-python 0.2.90
#  Interface : queryflow_template.html (template séparé)
#              injection via .replace() — ZERO SyntaxError backslash
#  Lancer : streamlit run app_oracle_nlp_int_pro4.py
#  Fichiers requis : queryflow_template.html dans le même dossier
# ============================================================

import os, zipfile, torch, pandas as pd, re, json
from datetime import datetime
import streamlit as st
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
from llama_cpp import Llama

st.set_page_config(
    page_title="QueryFlow — Oracle NLP · SQL",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════
# PROMPTS & DICTIONNAIRE ERREURS
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = (
    "Tu es un expert Oracle Database specialise en audit SQL.\n"
    "Table principale : ORACLE_AUDIT_TRAIL\n"
    "Colonnes reelles : ID, AUDIT_TYPE, SESSIONID, OS_USERNAME, USERHOST, TERMINAL, "
    "AUTHENTICATION_TYPE, DBUSERNAME, CLIENT_PROGRAM_NAME, OBJECT_SCHEMA, OBJECT_NAME, "
    "SQL_TEXT, SQL_BINDS, EVENT_TIMESTAMP, ACTION_NAME, INSTANCE\n"
    "Vue systeme : DBA_USERS (colonnes : USERNAME, USER_ID, ACCOUNT_STATUS, LOCK_DATE, "
    "EXPIRY_DATE, DEFAULT_TABLESPACE, TEMPORARY_TABLESPACE, CREATED, PROFILE)\n"
    "Regles importantes :\n"
    "- Pour compter les utilisateurs EXISTANTS dans la base -> utiliser DBA_USERS\n"
    "- Pour les evenements/actions/audit -> utiliser ORACLE_AUDIT_TRAIL\n"
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
    "Tu recois une question en francais et le resultat brut d'une interrogation de la base de donnees.\n"
    "Ton role : traduire ce resultat en 1 a 3 phrases claires, comprehensibles par quelqu'un\n"
    "qui ne connait pas l'informatique.\n"
    "\n"
    "Regles strictes :\n"
    "- Ne mentionne JAMAIS : SELECT, INSERT, UPDATE, DELETE, LOGON, LOGOFF, ALTER TABLE, DROP, GRANT,\n"
    "  REVOKE, SQL, Oracle, requete, colonne, table, base de donnees, FETCH, WHERE, ORDER BY\n"
    "- Traduis les actions techniques en langage courant :\n"
    "  LOGON = s est connecte, LOGOFF = s est deconnecte\n"
    "  SELECT = a consulte, INSERT = a ajoute des donnees\n"
    "  UPDATE = a modifie des donnees, DELETE = a supprime des donnees\n"
    "  ALTER TABLE = a modifie la structure, CREATE USER = a cree un compte\n"
    "  DROP USER = a supprime un compte, GRANT = a accorde des droits, REVOKE = a retire des droits\n"
    "- Traduis les noms techniques : PAYROLL = donnees de paie, EMPLOYEES = informations du personnel\n"
    "- Structure ta reponse autour de : qui a fait quoi, quand\n"
    "- Si activite anormale (heure tardive, suppression, acces sensible) : signale-le en debut de reponse\n"
    "- Si aucun resultat : dis qu'aucune activite n'a ete detectee sur cette periode\n"
    "- Ne repete jamais la question, ne montre jamais le code SQL\n"
    "- Reponds uniquement en francais naturel, sans jargon informatique\n"
)

ORA_ERRORS = {
    "ORA-00904": "nom de colonne invalide",
    "ORA-00907": "parenthèse manquante",
    "ORA-00911": "caractère invalide",
    "ORA-00933": "commande SQL mal terminée",
    "ORA-00942": "table ou vue inexistante ou accès non autorisé",
    "ORA-01756": "chaîne entre guillemets non terminée",
    "ORA-01950": "quota tablespace insuffisant",
    "ORA-12154": "TNS — identifiant de connexion non résolu",
}

# ══════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════
def unzip_if_needed(zip_path: str, target_dir: str):
    if not os.path.exists(target_dir) and os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(".")

@st.cache_data
def load_data():
    audit = pd.DataFrame()
    dataset = pd.DataFrame()
    if os.path.exists("oracle_audit_trail.csv"):
        audit = pd.read_csv("oracle_audit_trail.csv")
    elif os.path.exists("oracle_audit_trail.xlsx"):
        audit = pd.read_excel("oracle_audit_trail.xlsx")
    if os.path.exists("oracle_nlp_dataset.csv"):
        dataset = pd.read_csv("oracle_nlp_dataset.csv")
    return audit, dataset

def df_to_html_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return '<div style="color:#888;font-size:13px;padding:8px">Aucun résultat.</div>'
    headers = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = ""
    for _, row in df.head(50).iterrows():
        cells = "".join(f"<td>{v}</td>" for v in row.values)
        rows += f"<tr>{cells}</tr>"
    return f"""<div style="overflow-x:auto;margin-top:8px">
<table class="result-table"><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>"""

# ══════════════════════════════════════════════════════════════
# POST-PROCESSING SQL
# ══════════════════════════════════════════════════════════════
def post_process_sql(sql: str, question: str) -> str:
    # Fix ≥/≤ Unicode → ASCII
    sql = sql.replace("≥", ">=").replace("≤", "<=")

    su = sql.upper()

    # Corrections colonnes résiduelles
    sql = re.sub(r"\bDB_USER\b",   "DBUSERNAME",     sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bOBJ_NAME\b",  "OBJECT_NAME",    sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bAUDIT_ID\b",  "ID",             sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bOS_HOST\b",   "USERHOST",       sql, flags=re.IGNORECASE)

    # Fix SUBSTR(TIMESTAMP → TRUNC(EVENT_TIMESTAMP)
    sql = re.sub(
        r"SUBSTR\s*\(\s*TIMESTAMP\s*,\s*1\s*,\s*10\s*\)\s*(>=|<=|=|>|<)\s*TO_CHAR\s*\(\s*SYSDATE\s*-\s*(\d+)\s*,\s*'YYYY-MM-DD'\s*\)",
        lambda m: f"TRUNC(EVENT_TIMESTAMP) {m.group(1)} TRUNC(SYSDATE-{m.group(2)})",
        sql, flags=re.IGNORECASE
    )
    sql = re.sub(
        r"SUBSTR\s*\(\s*EVENT_TIMESTAMP\s*,\s*1\s*,\s*10\s*\)\s*(>=|<=|=|>|<)\s*TO_CHAR\s*\(\s*SYSDATE\s*-\s*(\d+)\s*,\s*'YYYY-MM-DD'\s*\)",
        lambda m: f"TRUNC(EVENT_TIMESTAMP) {m.group(1)} TRUNC(SYSDATE-{m.group(2)})",
        sql, flags=re.IGNORECASE
    )

    # Fix DBUSERNAME manquant dans SELECT tracabilité
    if "DBUSERNAME" not in su and "USERNAME" not in su:
        sql = re.sub(
            r"SELECT\s+MAX\(EVENT_TIMESTAMP\)",
            "SELECT DBUSERNAME, ACTION_NAME, MAX(EVENT_TIMESTAMP) AS DERNIERE_ACTION",
            sql, flags=re.IGNORECASE
        )

    # Fix OBJECT_NAME='1' ou OBJECT_NAME numérique
    if re.search(r"OBJECT_NAME\s*=\s*'1'", sql, re.IGNORECASE) or \
       re.search(r"OBJECT_NAME\s*=\s*'\d+'", sql, re.IGNORECASE):
        q_lower = question.lower()
        known_objects = [
            "EMPLOYEES","VROMUALD","CLIENTS","TRANSACTIONS","ORDERS",
            "ACCOUNTS","PAYROLL","JOURNAL","CONTRACTS","BUDGET",
            "PRODUCTS","SUPPLIERS","INVOICES","USERS","PAYMENTS",
            "AUDIT_LOG","SESSIONS","ALERTS","DBA_USERS","V$SESSION",
            "ALL_TABLES","CUSTOMERS","EMP","DEPT","SALGRADE"
        ]
        found_obj = None
        for obj in known_objects:
            if obj.lower() in q_lower:
                found_obj = obj
                break
        if found_obj:
            sql = re.sub(r"OBJECT_NAME\s*=\s*'\d+'", f"OBJECT_NAME='{found_obj}'", sql, flags=re.IGNORECASE)
        else:
            sql = re.sub(r"OBJECT_NAME\s*=\s*'\d+'", "OBJECT_NAME='EMPLOYEES'", sql, flags=re.IGNORECASE)

    return sql


def clean_sql(raw: str, question: str = "") -> str:
    sql = raw.strip()
    # Retirer balises et préfixes
    sql = re.sub(r"```sql", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```",    "", sql)
    sql = re.sub(r"^(SQL\s*:|Requête\s*:|Réponse\s*:)\s*", "", sql, flags=re.IGNORECASE)
    # Garder uniquement le premier statement SQL
    for kw in ["SELECT","INSERT","UPDATE","DELETE","WITH","CREATE","DROP","ALTER","GRANT","REVOKE"]:
        idx = sql.upper().find(kw)
        if idx != -1:
            sql = sql[idx:]
            break
    # Tronquer au premier ; ou à la fin
    if ";" in sql:
        sql = sql[:sql.index(";")+1]
    sql = sql.strip()
    return post_process_sql(sql, question)

# ══════════════════════════════════════════════════════════════
# EXÉCUTION LOCALE (pandasql)
# ══════════════════════════════════════════════════════════════
def executer_sur_audit(sql: str, df: pd.DataFrame):
    try:
        import pandasql as psql
        oracle_audit_trail = df  # noqa
        dba_users = pd.DataFrame({
            "USERNAME": sorted(df["DBUSERNAME"].unique()) if "DBUSERNAME" in df.columns else [],
            "ACCOUNT_STATUS": ["OPEN"] * (df["DBUSERNAME"].nunique() if "DBUSERNAME" in df.columns else 0),
            "CREATED": ["2024-01-01"] * (df["DBUSERNAME"].nunique() if "DBUSERNAME" in df.columns else 0),
        })  # noqa

        sql_a = re.sub(r"FETCH FIRST (\d+) ROWS ONLY", r"LIMIT \1", sql, flags=re.IGNORECASE)
        # Adaptateurs Oracle → SQLite
        sql_a = re.sub(r"TRUNC\(EVENT_TIMESTAMP\s*,\s*'MM'\)", "strftime('%Y-%m-01', EVENT_TIMESTAMP)", sql_a, flags=re.IGNORECASE)
        sql_a = re.sub(r"TRUNC\(SYSDATE\s*,\s*'MM'\)",         "strftime('%Y-%m-01', 'now')",           sql_a, flags=re.IGNORECASE)
        sql_a = re.sub(r"TRUNC\(ADD_MONTHS\(SYSDATE,-1\)\s*,\s*'MM'\)", "strftime('%Y-%m-01', 'now', '-1 month')", sql_a, flags=re.IGNORECASE)
        sql_a = re.sub(r"TRUNC\(EVENT_TIMESTAMP\)", "date(EVENT_TIMESTAMP)", sql_a, flags=re.IGNORECASE)
        sql_a = re.sub(r"TRUNC\(SYSDATE-(\d+)\)", lambda m: f"date('now', '-{m.group(1)} days')", sql_a, flags=re.IGNORECASE)
        sql_a = re.sub(r"TRUNC\(SYSDATE\)", "date('now')", sql_a, flags=re.IGNORECASE)
        sql_a = re.sub(r"TO_NUMBER\(TO_CHAR\(EVENT_TIMESTAMP,'HH24'\)\)", "CAST(strftime('%H', EVENT_TIMESTAMP) AS INTEGER)", sql_a, flags=re.IGNORECASE)
        sql_a = re.sub(r"ADD_MONTHS\(SYSDATE,-1\)", "date('now', '-1 month')", sql_a, flags=re.IGNORECASE)
        sql_a = re.sub(r"\bSYSDATE\b", "date('now')", sql_a, flags=re.IGNORECASE)
        return psql.sqldf(sql_a, locals())
    except Exception as e:
        return str(e)

# ══════════════════════════════════════════════════════════════
# CHARGEMENT MODÈLES
# ══════════════════════════════════════════════════════════════
LORA_DIR  = "tinyllama_oracle_lora"
MODEL_DIR = "TinyLlama-1.1B-Chat-v1.0"

@st.cache_resource
def load_tinyllama():
    unzip_if_needed("TinyLlama-1.1B-Chat-v1.0.zip", MODEL_DIR)
    unzip_if_needed("tinyllama_oracle_lora.zip", LORA_DIR)
    if not os.path.exists(MODEL_DIR) or not os.path.exists(LORA_DIR):
        return None, None, None
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(MODEL_DIR, torch_dtype=torch.float32)
    mdl  = PeftModel.from_pretrained(base, LORA_DIR)
    mdl.eval()
    dev  = torch.device("cpu")
    mdl.to(dev)
    return tok, mdl, dev

@st.cache_resource
def load_phi3():
    unzip_if_needed("phi3-mini-gguf.zip", "phi3-mini-gguf")
    model_path = os.path.join("phi3-mini-gguf", "Phi-3-mini-4k-instruct-q4.gguf")
    if not os.path.exists(model_path):
        return None
    return Llama(model_path=model_path, n_ctx=2048, n_gpu_layers=0, verbose=False)

# ══════════════════════════════════════════════════════════════
# GÉNÉRATION SQL + TRADUCTION FR
# ══════════════════════════════════════════════════════════════
def generer_sql(question, tokenizer, model, device):
    prompt = f"<|system|>{SYSTEM_PROMPT}<|end|><|user|>{question}<|end|><|assistant|>"
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=150, do_sample=False,
                             pad_token_id=tokenizer.eos_token_id)
    raw = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return clean_sql(raw, question)

def traduire_resultat(sql: str, resultat_brut: str, phi3) -> str:
    if phi3 is None:
        return "Phi-3 mini non disponible — placez phi3-mini-gguf.zip dans le répertoire."
    newline = "\n"
    prompt = (
        f"<|system|>{SYSTEM_PROMPT_FR}<|end|>"
        "<|user|>SQL : " + sql + newline + "Résultat : " + resultat_brut[:800] + "<|end|>"
        "<|assistant|>"
    )
    response = phi3(
        prompt,
        max_tokens      = 200,
        temperature     = 0.2,
        repeat_penalty  = 1.1,
        stop            = ["<|end|>", "<|user|>"],
    )
    return response["choices"][0]["text"].strip()

# ══════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════
for k, v in {"historique": [], "prefill": "", "nb_requetes": 0,
             "current_user": "admin", "active_page": "home"}.items():
    if k not in st.session_state:
        st.session_state[k] = v

audit_df, dataset_df = load_data()

# Données réelles pour les sidebars (depuis captures)
USERS_REELS = [
    {"name": "SYSTEM",       "actions": 0},
    {"name": "VROMUALD",     "actions": 0},
    {"name": "SYS",          "actions": 0},
    {"name": "HR",           "actions": 0},
    {"name": "APP_USER",     "actions": 0},
    {"name": "REPORT_USR",   "actions": 0},
    {"name": "AUDIT_USR",    "actions": 0},
    {"name": "DBA_OPS",      "actions": 0},
    {"name": "BACKUP_USR",   "actions": 0},
    {"name": "MONITOR",      "actions": 0},
    {"name": "SCOTT",        "actions": 0},
    {"name": "ETL_USER",     "actions": 0},
]
TABLES_REELLES = [
    {"name": "EMPLOYEES",    "actions": 0},
    {"name": "VROMUALD",     "actions": 0},
    {"name": "CLIENTS",      "actions": 0},
    {"name": "TRANSACTIONS", "actions": 0},
    {"name": "ORDERS",       "actions": 0},
    {"name": "ACCOUNTS",     "actions": 0},
    {"name": "PAYROLL",      "actions": 0},
    {"name": "JOURNAL",      "actions": 0},
    {"name": "CONTRACTS",    "actions": 0},
    {"name": "BUDGET",       "actions": 0},
    {"name": "PRODUCTS",     "actions": 0},
    {"name": "SUPPLIERS",    "actions": 0},
    {"name": "INVOICES",     "actions": 0},
    {"name": "USERS",        "actions": 0},
    {"name": "PAYMENTS",     "actions": 0},
    {"name": "AUDIT_LOG",    "actions": 0},
    {"name": "SESSIONS",     "actions": 0},
    {"name": "ALERTS",       "actions": 0},
    {"name": "DBA_USERS",    "actions": 0},
    {"name": "V$SESSION",    "actions": 0},
]

# Enrichir avec les vraies données si audit_df chargé
if not audit_df.empty:
    if "DBUSERNAME" in audit_df.columns:
        usr_counts = audit_df["DBUSERNAME"].value_counts().to_dict()
        for u in USERS_REELS:
            u["actions"] = int(usr_counts.get(u["name"], 0))
    if "OBJECT_NAME" in audit_df.columns:
        obj_counts = audit_df["OBJECT_NAME"].value_counts().to_dict()
        for t in TABLES_REELLES:
            t["actions"] = int(obj_counts.get(t["name"], 0))

QUESTIONS_RAPIDES = [
    "Combien d'utilisateurs existent dans la base Oracle ?",
    "Quel utilisateur a le plus d'actions ?",
    "Qui a fait le plus de connexions ?",
    "Qu'est-ce qui s'est passé hier dans la base ?",
    "Qui a touche EMPLOYEES en dernier ?",
    "Y a-t-il eu des activites la nuit cette semaine ?",
]

# ══════════════════════════════════════════════════════════════
# GESTION QUESTION (depuis interface HTML via query_params)
# ══════════════════════════════════════════════════════════════
tok, mdl, dev = load_tinyllama()

# Traiter la question si soumise
result_html    = ""
result_sql     = ""
result_synthese = ""
question_traitee = ""

qp = st.query_params
if "q" in qp:
    question_traitee = qp["q"]
    st.query_params.clear()

    now = datetime.now().strftime("%H:%M:%S")
    st.session_state.historique.append({"role":"user","content":question_traitee,"time":now})
    st.session_state.nb_requetes += 1

    if tok is not None:
        with st.spinner("Génération SQL…"):
            sql_gen = generer_sql(question_traitee, tok, mdl, dev)
    else:
        sql_gen = "-- Modèle TinyLlama non disponible. Placez tinyllama_oracle_lora.zip et TinyLlama-1.1B-Chat-v1.0.zip."

    result_sql = sql_gen
    st.session_state.historique.append({"role":"sql","content":sql_gen,"time":now})

    if not audit_df.empty and not sql_gen.startswith("--"):
        result_df = executer_sur_audit(sql_gen, audit_df)
        if isinstance(result_df, pd.DataFrame):
            result_html = df_to_html_table(result_df)
            res_txt = result_df.to_string(index=False) if not result_df.empty else "Aucun résultat."
            st.session_state.historique.append({"role":"table","content":result_html,"time":now})
        else:
            res_txt = str(result_df)
            result_html = f'<div style="color:#c0392b;font-size:12px;padding:8px">{res_txt}</div>'
            st.session_state.historique.append({"role":"table","content":result_html,"time":now})

        phi3_model = load_phi3()
        result_synthese = traduire_resultat(sql_gen, res_txt, phi3_model)
        st.session_state.historique.append({"role":"bot","content":result_synthese,"time":now})
    elif audit_df.empty:
        result_synthese = "Aucune table d'audit chargée. Placez oracle_audit_trail.csv dans le répertoire."
        st.session_state.historique.append({"role":"bot","content":result_synthese,"time":now})

# ══════════════════════════════════════════════════════════════
# PRÉPARATION DES DONNÉES POUR L'INTERFACE HTML
# ══════════════════════════════════════════════════════════════
users_json   = json.dumps(USERS_REELS)
tables_json  = json.dumps(TABLES_REELLES)
history_json = json.dumps([
    {
        "datetime": m["time"],
        "user":     st.session_state.current_user,
        "question": m["content"],
        "sql":      "",
        "answer":   "",
        "raw":      ""
    }
    for m in st.session_state.historique if m["role"] == "user"
])

# Construire le bloc résultat HTML
if result_sql:
    result_block = f"""
    <h3>Requête SQL générée</h3>
    <div class="sql-box">{result_sql}</div>
    {"<h3>Réponse synthétique</h3><p>" + result_synthese + "</p>" if result_synthese else ""}
    {"<h3>Résultat détaillé</h3>" + result_html if result_html else ""}
    """
else:
    result_block = ""

# ══════════════════════════════════════════════════════════════
# INTERFACE HTML PRINCIPALE

# ══════════════════════════════════════════════════════════════
# INTERFACE HTML PRINCIPALE
# Stratégie : template HTML + .replace() pour éviter SyntaxError
# backslash dans f-string (PEP 701, résolu en Python 3.12+ seulement)
# ══════════════════════════════════════════════════════════════

# ── Template HTML (chargé une seule fois) ──────────────────────
HTML_TEMPLATE = open(
    os.path.join(os.path.dirname(__file__), "queryflow_template.html"),
    encoding="utf-8"
).read()

# ── Construire le HTML des utilisateurs ───────────────────────
users_html = "".join(
    "<li><span>" + u["name"] + "</span>"
    + "<span class=\"count-pill\">" + str(u["actions"]) + " actions</span></li>"
    for u in USERS_REELS
)

# ── HTML des tables ────────────────────────────────────────────
tables_html = "".join(
    "<li><span>" + t["name"] + "</span></li>"
    for t in TABLES_REELLES
)

# ── HTML des chips questions rapides ──────────────────────────
chips_html = "".join(
    "<button class=\"chip\" data-example=\"" + q.replace('"', '&quot;') + "\">"
    + q + "</button>"
    for q in QUESTIONS_RAPIDES
)

# ── HTML de l'historique ──────────────────────────────────────
history_msgs = [m for m in st.session_state.historique if m["role"] == "user"]
history_rows = "".join(
    "<tr><td>" + m["time"] + "</td>"
    + "<td>" + st.session_state.current_user + "</td>"
    + "<td>" + (m["content"][:60] + "..." if len(m["content"]) > 60 else m["content"]) + "</td></tr>"
    for m in reversed(history_msgs)
) or "<tr><td colspan=\"3\" style=\"color:#888;padding:12px\">Aucune requête exécutée.</td></tr>"

# ── HTML du bloc résultat ──────────────────────────────────────
if result_sql:
    synthese_block = (
        "<div class=\"synthese-box\">&#x2705; " + result_synthese + "</div>"
        if result_synthese else ""
    )
    result_html_block = (
        "<h3>Résultat détaillé</h3>" + result_html
        if result_html else ""
    )
    result_block_html = (
        "<h3>Requête SQL générée</h3>"
        + "<div class=\"sql-box\">" + result_sql + "</div>"
        + synthese_block
        + result_html_block
    )
    result_class = "result"
else:
    result_block_html = (
        "<div>"
        + "<div class=\"empty-icon\">&#x1F50D;</div>"
        + "<div style=\"font-size:14px;font-weight:600;color:#4a6a90;margin-bottom:4px\">Aucune requête exécutée</div>"
        + "<div style=\"font-size:12px\">Posez une question pour interroger ORACLE_AUDIT_TRAIL</div>"
        + "</div>"
    )
    result_class = "result empty"

# ── Récentes actions ───────────────────────────────────────────
RECENT_ACTIONS = [
    {"user": "VROMUALD", "object": "EMPLOYEES",  "date": "24/02 14:32"},
    {"user": "SYSTEM",   "object": "VROMUALD",   "date": "24/02 11:53"},
    {"user": "SYSTEM",   "object": "EMPLOYEES",  "date": "24/02 11:53"},
    {"user": "VROMUALD", "object": "VROMUALD",   "date": "24/02 11:53"},
    {"user": "SYSTEM",   "object": "VROMUALD",   "date": "24/02 11:53"},
    {"user": "SYSTEM",   "object": "",           "date": "24/02 11:53"},
    {"user": "VROMUALD", "object": "VROMUALD",   "date": "24/02 11:53"},
    {"user": "SYSTEM",   "object": "",           "date": "24/02 11:53"},
    {"user": "SYSTEM",   "object": "",           "date": "24/02 11:53"},
    {"user": "SYSTEM",   "object": "",           "date": "24/02 11:53"},
]
recent_html = "".join(
    "<li style=\"flex-direction:column;align-items:flex-start;gap:1px;padding:8px 10px\">"
    + "<span style=\"font-size:12px;font-weight:700;color:#2c3d57\">" + a["user"] + "</span>"
    + ("<span style=\"font-size:11px;color:#5f6f87\">&rarr; " + a["object"] + "</span>" if a["object"] else "")
    + "<span style=\"font-size:10px;color:#a0b0cc\">" + a["date"] + "</span>"
    + "</li>"
    for a in RECENT_ACTIONS
)

# ── Injecter dans le template ──────────────────────────────────
html_content = (HTML_TEMPLATE
    .replace("%%CURRENT_USER%%",       st.session_state.current_user)
    .replace("%%USERS_LIST_HTML%%",    users_html)
    .replace("%%TABLES_LIST_HTML%%",   tables_html)
    .replace("%%CHIPS_HTML%%",         chips_html)
    .replace("%%HISTORY_ROWS%%",       history_rows)
    .replace("%%RESULT_CLASS%%",       result_class)
    .replace("%%RESULT_BLOCK%%",       result_block_html)
    .replace("%%RECENT_ACTIONS_HTML%%", recent_html)
)

# Masquer les éléments Streamlit natifs
st.markdown("""
<style>
#MainMenu, footer, header, .stDeployButton, .stDecoration { display:none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown(html_content, unsafe_allow_html=True)
