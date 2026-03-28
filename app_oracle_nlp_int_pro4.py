# ============================================================
#  Oracle NLP → SQL  |  QueryFlow — Interface HTML intégrée
#  Modèle : TinyLlama-1.1B + LoRA fine-tuné V4
#           Phi-3 mini Q4 local (SQL→FR) — llama-cpp-python 0.2.90
#  Interface : HTML/CSS soumise par l'utilisateur, branchée via
#              st.components.v1.html + communication Streamlit
#  Lancer : streamlit run app_oracle_nlp_int_pro4.py
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
    "Tu es un assistant specialise en audit Oracle Database.\n"
    "Tu recois une question en francais, la requete SQL generee, et le resultat brut.\n"
    "Reponds en une ou deux phrases claires, en francais, destinees a un utilisateur non-technicien.\n"
    "Ne repete pas le SQL. Reformule le resultat de facon naturelle et comprehensible.\n"
    "Si le resultat est vide, dis-le clairement."
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
    prompt = (
        f"<|system|>{SYSTEM_PROMPT_FR}<|end|>"
        f"<|user|>SQL : {sql}\nRésultat : {resultat_brut[:800]}<|end|>"
        f"<|assistant|>"
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
st.markdown(f"""
<style>
/* ─── Reset & variables ─── */
:root {{
  --bg: #eaf1ff;
  --surface: #ffffff;
  --surface-soft: #f1f6ff;
  --line: #cfdbf1;
  --text: #1f2b3d;
  --muted: #5f6f87;
  --accent: #2e67dc;
  --accent-strong: #2253b8;
  --success: #1f8f5f;
  --warning: #b7791f;
  --danger: #b23a3a;
  --radius: 12px;
  --shadow: 0 8px 22px rgba(22,42,79,0.08);
}}
* {{ box-sizing: border-box; }}
body, .main, .block-container {{
  background:
    radial-gradient(1200px 500px at 20% -10%, #dce9ff 0%, transparent 65%),
    radial-gradient(1000px 420px at 90% 0%, #e5efff 0%, transparent 60%),
    var(--bg) !important;
  font-family: "Segoe UI","Helvetica Neue",Arial,sans-serif !important;
  color: var(--text) !important;
  padding: 0 !important;
}}
/* Masquer éléments Streamlit natifs */
#MainMenu, footer, header, .stDeployButton {{ display:none !important; }}
.block-container {{ padding: 0 !important; max-width: 100% !important; }}

/* ─── Topbar ─── */
.topbar {{
  height:66px; border-bottom:1px solid var(--line);
  background:linear-gradient(180deg,#fff 0%,#f5f9ff 100%);
  display:flex; align-items:center; justify-content:space-between;
  padding:0 18px; gap:12px;
}}
.brand {{
  display:flex; align-items:center; gap:8px;
  font-weight:700; color:var(--accent-strong);
  font-size:22px; letter-spacing:-0.02em; white-space:nowrap;
}}
.nav {{ display:flex; align-items:center; gap:8px; flex:1; justify-content:center; }}
.nav-btn {{
  background:transparent; border:1px solid transparent;
  color:#4f5f78; height:40px; border-radius:10px;
  padding:0 14px; font-weight:600; cursor:pointer;
  display:inline-flex; align-items:center; gap:8px; font-size:14px;
}}
.nav-btn.active {{
  background:linear-gradient(180deg,#e6efff 0%,#dce8ff 100%);
  color:var(--accent-strong); border-color:#c5d8ff;
}}
.topbar-right {{ display:flex; align-items:center; gap:12px; white-space:nowrap; }}
.user-badge {{ color:var(--muted); font-size:13px; font-weight:600;
  display:inline-flex; align-items:center; gap:6px; }}
.btn-logout {{
  height:40px; border-radius:10px; border:1px solid var(--line);
  background:#fff; color:var(--muted); font-weight:600; font-size:14px;
  padding:0 14px; cursor:pointer; display:inline-flex; align-items:center; gap:8px;
}}
.btn-logout:hover {{ color:var(--text); border-color:#c8d2e3; }}

/* ─── Layout ─── */
.page-wrap {{ width:min(96vw,1600px); margin:16px auto; }}
.home-layout {{
  display:grid; grid-template-columns:3fr 1fr 1fr;
  gap:14px; align-items:start;
}}
.card {{
  background:var(--surface); border:1px solid var(--line);
  border-radius:var(--radius); box-shadow:var(--shadow);
}}
.main-card {{
  padding:18px; min-height:680px;
  display:flex; flex-direction:column;
  background:linear-gradient(180deg,#fff 0%,#f7faff 100%);
}}
.main-title {{
  margin:0 0 14px; font-size:28px; letter-spacing:-0.02em;
  display:inline-flex; align-items:center; gap:8px;
}}
.ask-row {{ display:flex; gap:10px; margin-bottom:10px; }}
.ask-row input {{
  flex:1; height:42px; border:1px solid var(--line);
  border-radius:10px; padding:0 12px; font-size:14px;
  color:var(--text); background:#fff; outline:none;
}}
.ask-row input:focus {{ border-color:var(--accent); }}
.btn-ask {{
  height:42px; border-radius:10px; border:1px solid transparent;
  background:var(--accent); color:#fff; font-weight:600;
  font-size:14px; padding:0 18px; cursor:pointer;
  display:inline-flex; align-items:center; gap:8px;
}}
.btn-ask:hover {{ background:var(--accent-strong); }}
.examples {{
  display:flex; flex-wrap:wrap; gap:7px; margin-bottom:14px;
  color:var(--muted); font-size:12px; align-items:center;
}}
.chip {{
  border:1px solid #d8e4fa; background:#eef4ff; border-radius:999px;
  padding:6px 10px; font-size:12px; color:#506077; cursor:pointer;
}}
.chip:hover {{ background:#dceeff; }}
.result {{
  margin-top:6px; border:1px solid var(--line); border-radius:10px;
  background:linear-gradient(180deg,#f4f8ff 0%,#eef4ff 100%);
  padding:14px; min-height:140px; flex:1;
}}
.result.empty {{
  color:var(--muted); display:grid; place-items:center;
  text-align:center; padding:26px; min-height:220px;
  border-style:dashed;
}}
.result h3 {{ margin:0 0 8px; font-size:16px; color:#233451; }}
.sql-box {{
  border:1px solid var(--line); border-radius:8px; background:#fff;
  padding:10px; font-family:"Consolas","Courier New",monospace;
  font-size:12px; color:#2c3b56; overflow-x:auto; margin-top:8px;
  white-space:pre-wrap;
}}
.result-table {{
  width:100%; border-collapse:collapse; margin-top:10px;
  font-size:12px; background:#fff; border:1px solid var(--line);
  border-radius:8px; overflow:hidden;
}}
.result-table th, .result-table td {{
  border-bottom:1px solid #edf2f8; padding:8px; text-align:left; white-space:nowrap;
}}
.result-table th {{ background:#eaf2ff; color:#36527f; font-weight:700; }}

/* ─── Sidebar cards ─── */
.side-card {{ min-height:680px; display:flex; flex-direction:column; }}
.side-head {{
  padding:12px; border-bottom:1px solid #c6d8fb; font-weight:700;
  color:#fff; display:inline-flex; align-items:center; gap:8px;
  background:linear-gradient(180deg,#3b77e8 0%,#2a60cc 100%);
  border-radius:12px 12px 0 0;
}}
.side-body {{ padding:10px; display:flex; flex-direction:column; flex:1; }}
.search-input {{
  height:38px; border:1px solid var(--line); border-radius:8px;
  padding:0 10px; font-size:13px; margin-bottom:8px; width:100%; outline:none;
}}
.simple-list {{
  list-style:none; margin:0; padding:0; overflow:auto; flex:1;
  border:1px solid var(--line); border-radius:8px; background:#fbfdff;
}}
.simple-list li {{
  display:flex; align-items:center; justify-content:space-between;
  gap:8px; padding:9px 10px; border-bottom:1px solid #eef3f8;
  font-size:13px; font-weight:600; color:#2c3d57;
}}
.simple-list li:last-child {{ border-bottom:none; }}
.count-pill {{
  font-size:11px; color:#325ca6; background:#e0ebff;
  border-radius:999px; padding:4px 8px; flex-shrink:0;
}}

/* ─── Historique ─── */
.history-layout {{ display:grid; grid-template-columns:1.4fr 1fr; gap:14px; }}
.history-table-wrap, .history-detail {{ padding:14px; }}
.section-title {{
  margin:0 0 12px; font-size:20px;
  display:inline-flex; align-items:center; gap:8px;
}}
.history-table {{
  width:100%; border-collapse:collapse; font-size:12px;
  border:1px solid var(--line); border-radius:8px; overflow:hidden;
}}
.history-table th, .history-table td {{
  border-bottom:1px solid #edf2f8; padding:8px; text-align:left; vertical-align:top;
}}
.history-table th {{ background:#eaf2ff; color:#36527f; font-weight:700; }}
.history-table tr:hover td {{ background:#eef4ff; cursor:pointer; }}
.detail-box {{
  border:1px solid var(--line); border-radius:8px;
  background:#f3f8ff; padding:10px; margin-bottom:10px; font-size:13px;
}}
.detail-box h4 {{ margin:0 0 6px; font-size:13px; color:#2c3d57; }}
.detail-pre {{
  margin:0; font-family:"Consolas","Courier New",monospace;
  font-size:12px; white-space:pre-wrap; color:#2b3a56;
}}

/* ─── Paramètres ─── */
.settings-card {{ padding:14px; }}
.settings-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.setting-group {{
  border:1px solid var(--line); border-radius:10px;
  padding:12px; background:#f8fbff;
}}
.setting-group h4 {{ margin:0 0 10px; font-size:14px; color:#2d3f5b; }}
.inline-field {{ margin-bottom:9px; }}
.inline-field label {{
  display:block; font-size:12px; color:var(--muted);
  margin-bottom:4px; font-weight:600;
}}
.inline-field input {{
  width:100%; height:36px; border:1px solid var(--line);
  border-radius:8px; padding:0 10px; font-size:13px;
  background:#fff; color:var(--text);
}}
.settings-actions {{ margin-top:12px; display:flex; gap:8px; justify-content:flex-end; }}
.btn-save {{
  height:40px; border-radius:10px; border:none;
  background:var(--accent); color:#fff; font-weight:600;
  font-size:14px; padding:0 14px; cursor:pointer;
}}
.btn-reset {{
  height:40px; border-radius:10px; border:1px solid var(--line);
  background:#fff; color:var(--muted); font-weight:600;
  font-size:14px; padding:0 14px; cursor:pointer;
}}

/* ─── Page masquée ─── */
.page {{ display:none; }}
.page.active {{ display:block; }}

/* ─── Responsive ─── */
@media(max-width:1300px) {{
  .home-layout {{ grid-template-columns:1fr 1fr; }}
  .main-card {{ grid-column:1/span 2; min-height:500px; }}
  .side-card {{ min-height:300px; }}
  .history-layout {{ grid-template-columns:1fr; }}
}}
@media(max-width:900px) {{
  .topbar {{ flex-wrap:wrap; height:auto; padding:12px; }}
  .nav {{ order:3; justify-content:flex-start; width:100%; }}
  .home-layout {{ grid-template-columns:1fr; }}
  .main-card {{ grid-column:auto; }}
  .settings-grid {{ grid-template-columns:1fr; }}
}}
</style>

<!-- ═══════════════ TOPBAR ═══════════════ -->
<div class="topbar">
  <div class="brand">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <ellipse cx="12" cy="5" rx="8" ry="3"></ellipse>
      <path d="M4 5v10c0 1.7 3.6 3 8 3s8-1.3 8-3V5"></path>
      <path d="M4 10c0 1.7 3.6 3 8 3s8-1.3 8-3"></path>
    </svg>
    Queryflow
  </div>

  <nav class="nav">
    <button class="nav-btn active" onclick="showPage('home',this)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>
      </svg>
      Accueil
    </button>
    <button class="nav-btn" onclick="showPage('history',this)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="1 4 1 10 7 10"/><path d="M3.5 15a9 9 0 1 0 .5-4"/>
      </svg>
      Historique
    </button>
    <button class="nav-btn" onclick="showPage('settings',this)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.54V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.54 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.54-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.54-1A1.7 1.7 0 0 0 4.3 7.13l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6h.09a1.7 1.7 0 0 0 1-1.54V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.54 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.26.62.87 1.02 1.54 1.02H21a2 2 0 1 1 0 4h-.09c-.67 0-1.28.4-1.51.98z"/>
      </svg>
      Paramètres
    </button>
  </nav>

  <div class="topbar-right">
    <span class="user-badge">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 21a8 8 0 1 0-16 0"/><circle cx="12" cy="8" r="4"/>
      </svg>
      {st.session_state.current_user}
    </span>
    <button class="btn-logout">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
        <polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
      </svg>
      Déconnexion
    </button>
  </div>
</div>

<div class="page-wrap">

<!-- ═══════════════ PAGE ACCUEIL ═══════════════ -->
<section id="page-home" class="page active">
  <div class="home-layout">

    <!-- ZONE PRINCIPALE -->
    <article class="card main-card">
      <h2 class="main-title">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2e67dc" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        Posez votre question ci-dessous
      </h2>

      <div class="ask-row">
        <input id="question-input" type="text"
          placeholder="Posez votre question en français..."
          onkeydown="if(event.key==='Enter') submitQuestion()" />
        <button class="btn-ask" onclick="submitQuestion()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          Interroger
        </button>
      </div>

      <div class="examples">
        <strong>Exemples :</strong>
        {"".join(f'<button class="chip" onclick="setQuestion(this.textContent)">{q}</button>' for q in QUESTIONS_RAPIDES)}
      </div>

      <section id="result-box" class="result {"" if result_block else "empty"}">
        {"" if result_block else "Posez une question pour obtenir une réponse."}
        {result_block}
      </section>
    </article>

    <!-- SIDEBAR UTILISATEURS -->
    <aside class="card side-card">
      <header class="side-head">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2">
          <path d="M20 21a8 8 0 1 0-16 0"/><circle cx="12" cy="8" r="4"/>
        </svg>
        Utilisateurs
      </header>
      <div class="side-body">
        <input class="search-input" type="search" placeholder="Rechercher..."
          oninput="filterList('users-list',this.value)" />
        <ul id="users-list" class="simple-list">
          {"".join(f'<li><span>{u["name"]}</span><span class="count-pill">{u["actions"]} actions</span></li>' for u in USERS_REELS)}
        </ul>
      </div>
    </aside>

    <!-- SIDEBAR TABLES -->
    <aside class="card side-card">
      <header class="side-head">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/>
          <line x1="9" y1="3" x2="9" y2="21"/>
        </svg>
        Tables / Objets
      </header>
      <div class="side-body">
        <input class="search-input" type="search" placeholder="Rechercher..."
          oninput="filterList('tables-list',this.value)" />
        <ul id="tables-list" class="simple-list">
          {"".join(f'<li><span>{t["name"]}</span><span class="count-pill">{t["actions"]} actions</span></li>' for t in TABLES_REELLES)}
        </ul>
      </div>
    </aside>
  </div>
</section>

<!-- ═══════════════ PAGE HISTORIQUE ═══════════════ -->
<section id="page-history" class="page">
  <div class="history-layout">
    <article class="card history-table-wrap">
      <h3 class="section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="1 4 1 10 7 10"/><path d="M3.5 15a9 9 0 1 0 .5-4"/>
        </svg>
        Historique des requêtes
      </h3>
      <table class="history-table">
        <thead><tr><th>Heure</th><th>Utilisateur</th><th>Question</th></tr></thead>
        <tbody id="history-tbody">
          {"".join(
              f'<tr onclick="showDetail(this)" data-q="{m[\"content\"]}" data-t="{m[\"time\"]}">'
              f'<td>{m["time"]}</td><td>{st.session_state.current_user}</td>'
              f'<td>{m["content"][:60]}{"..." if len(m["content"])>60 else ""}</td></tr>'
              for m in reversed(st.session_state.historique) if m["role"]=="user"
          ) or "<tr><td colspan='3' style='color:#888;padding:12px'>Aucune requête exécutée.</td></tr>"}
        </tbody>
      </table>
    </article>

    <article class="card history-detail" style="padding:14px">
      <h3 class="section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        Détail sélectionné
      </h3>
      <div id="history-detail-content">
        <div class="detail-box">Sélectionnez une ligne pour afficher les détails.</div>
      </div>
    </article>
  </div>
</section>

<!-- ═══════════════ PAGE PARAMÈTRES ═══════════════ -->
<section id="page-settings" class="page">
  <article class="card settings-card">
    <h3 class="section-title">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"/>
      </svg>
      Paramètres
    </h3>
    <div class="settings-grid">
      <section class="setting-group">
        <h4>Informations générales</h4>
        <div class="inline-field"><label>Nom de l'utilisateur</label>
          <input value="{st.session_state.current_user}" /></div>
        <div class="inline-field"><label>Nom de l'entreprise</label>
          <input value="Smart2d" /></div>
        <div class="inline-field"><label>Hôte</label>
          <input value="oracle-prod.local" /></div>
      </section>
      <section class="setting-group">
        <h4>Connexion base de données</h4>
        <div class="inline-field"><label>Port</label><input value="1521" /></div>
        <div class="inline-field"><label>Session active (minutes)</label><input value="30" /></div>
        <div class="inline-field"><label>Conservation des logs (jours)</label><input value="90" /></div>
      </section>
    </div>
    <div class="settings-actions">
      <button class="btn-reset">Réinitialiser</button>
      <button class="btn-save">Sauvegarder</button>
    </div>
  </article>
</section>

</div><!-- /page-wrap -->

<script>
// ── Navigation entre pages ──
function showPage(name, btn) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}}

// ── Filtrage des listes ──
function filterList(listId, term) {{
  const ul = document.getElementById(listId);
  if (!ul) return;
  ul.querySelectorAll('li').forEach(li => {{
    li.style.display = li.textContent.toLowerCase().includes(term.toLowerCase()) ? '' : 'none';
  }});
}}

// ── Remplir le champ question depuis un chip ──
function setQuestion(text) {{
  document.getElementById('question-input').value = text;
  document.getElementById('question-input').focus();
}}

// ── Soumettre la question via query_params Streamlit ──
function submitQuestion() {{
  const q = document.getElementById('question-input').value.trim();
  if (!q) return;
  const url = new URL(window.location.href);
  url.searchParams.set('q', q);
  window.location.href = url.toString();
}}

// ── Afficher le détail dans l'historique ──
function showDetail(row) {{
  const q = row.dataset.q;
  const t = row.dataset.t;
  document.getElementById('history-detail-content').innerHTML =
    '<div class="detail-box"><h4>Question</h4>' + q + '</div>' +
    '<div class="detail-box"><h4>Heure</h4>' + t + '</div>';
}}
</script>
""", unsafe_allow_html=True)
