# ============================================================
#  QueryFlow — Oracle Audit Intelligence  (VERSION PROD)
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
    page_title="QueryFlow — Oracle Audit Intelligence",
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
ORACLE_TABLE    = "ORACLE_AUDIT_TRAIL"

# ══════════════════════════════════════════════════════════════
# PROMPTS
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
    "- PAYROLL=donnees de paie, EMPLOYEES=informations du personnel\n"
    "- Structure : qui a fait quoi, quand\n"
    "- Si activite anormale : signale-le en debut de reponse\n"
    "- Si aucun resultat : dis qu'aucune activite n'a ete detectee\n"
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
        cols = [d[0].upper() for d in cur.description]
        df   = pd.DataFrame(cur.fetchall(), columns=cols)
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
    print("[DATA] Chargement ORACLE_AUDIT_TRAIL...", flush=True)
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
                "SELECT * FROM ORACLE_AUDIT_TRAIL "
                "ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST 5000 ROWS ONLY"
            )
            print(f"[DATA] Execution : {query[:80]}...", flush=True)
            cur.execute(query.rstrip().rstrip(";").rstrip())
            cols = [d[0].upper() for d in cur.description]
            df   = pd.DataFrame(cur.fetchall(), columns=cols)
            cur.close(); conn.close()
            print(f"[DATA] Succes Oracle : {len(df)} lignes chargees", flush=True)
            return df, "oracle"
        except Exception as e:
            print(f"[DATA] ECHEC chargement Oracle : {e}", flush=True)
            try: conn.close()
            except: pass
    else:
        print(f"[DATA] Connexion Oracle impossible : {err}", flush=True)
    # Production pure — pas de CSV fallback
    print("[DATA] Aucune donnee disponible (mode production, pas de CSV)", flush=True)
    return pd.DataFrame(), "none"

# ══════════════════════════════════════════════════════════════
# POST-PROCESSING SQL
# ══════════════════════════════════════════════════════════════
def post_process_sql(sql: str, question: str) -> str:
    sql = sql.replace("≥", ">=").replace("≤", "<=")
    sql = re.sub(r"\bDB_USER\b",  "DBUSERNAME",  sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bOBJ_NAME\b", "OBJECT_NAME", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bAUDIT_ID\b", "ID",           sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bOS_HOST\b",  "USERHOST",     sql, flags=re.IGNORECASE)
    sql = re.sub(
        r"SUBSTR\s*\(\s*TIMESTAMP\s*,\s*1\s*,\s*10\s*\)\s*(>=|<=|=|>|<)\s*"
        r"TO_CHAR\s*\(\s*SYSDATE\s*-\s*(\d+)\s*,\s*'YYYY-MM-DD'\s*\)",
        lambda m: f"TRUNC(EVENT_TIMESTAMP) {m.group(1)} TRUNC(SYSDATE-{m.group(2)})",
        sql, flags=re.IGNORECASE
    )
    su = sql.upper()
    if "DBUSERNAME" not in su and "USERNAME" not in su:
        sql = re.sub(
            r"SELECT\s+MAX\(EVENT_TIMESTAMP\)",
            "SELECT DBUSERNAME, ACTION_NAME, MAX(EVENT_TIMESTAMP) AS DERNIERE_ACTION",
            sql, flags=re.IGNORECASE
        )
    if re.search(r"OBJECT_NAME\s*=\s*'\d+'", sql, re.IGNORECASE):
        known = ["EMPLOYEES","VROMUALD","CLIENTS","TRANSACTIONS","ORDERS","ACCOUNTS",
                 "PAYROLL","JOURNAL","CONTRACTS","BUDGET","PRODUCTS","SUPPLIERS",
                 "INVOICES","USERS","PAYMENTS","AUDIT_LOG","DBA_USERS","V$SESSION"]
        found = next((o for o in known if o.lower() in question.lower()), "EMPLOYEES")
        sql = re.sub(r"OBJECT_NAME\s*=\s*'\d+'",
                     "OBJECT_NAME='" + found + "'", sql, flags=re.IGNORECASE)
    if ";" in sql:
        sql = sql[:sql.index(";")+1]
    return sql.strip()

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
    return post_process_sql(sql.strip(), question)

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

def traduire_resultat(question: str, resultat_brut: str, phi3) -> str:
    if phi3 is None:
        return ""
    nl = "\n"
    prompt = (
        f"<|system|>{SYSTEM_PROMPT_FR}<|end|>"
        "<|user|>Question : " + question + nl
        + "Resultat : " + resultat_brut[:800] + "<|end|>"
        "<|assistant|>"
    )
    resp = phi3(prompt, max_tokens=200, temperature=0.2,
                repeat_penalty=1.1, stop=["<|end|>", "<|user|>"])
    return resp["choices"][0]["text"].strip()

def df_to_html_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return '<p style="color:#888;font-size:13px;padding:8px">Aucun résultat.</p>'
    headers = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{v}</td>" for v in row.values) + "</tr>"
        for _, row in df.head(100).iterrows()
    )
    return (
        '<div style="overflow-x:auto;margin-top:10px">'
        f'<table class="result-table"><thead><tr>{headers}</tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
    )

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
      radial-gradient(1400px 600px at 15% -5%,#d4e4ff 0%,transparent 60%),
      radial-gradient(900px 500px at 90% 10%,#dce8ff 0%,transparent 55%),
      #eaf1ff!important}
    div[data-testid="stTextInput"] input{
      border-radius:10px!important;border:1.5px solid #cfdbf1!important;
      background:#f8fbff!important;font-size:14px!important;height:42px!important}
    div[data-testid="stTextInput"] input:focus{
      border-color:#2e67dc!important;
      box-shadow:0 0 0 3px rgba(46,103,220,.12)!important}
    div[data-testid="stTextInput"] label{
      font-size:12px!important;font-weight:700!important;
      color:#5f6f87!important;text-transform:uppercase!important;
      letter-spacing:.04em!important}
    .stButton>button{
      background:linear-gradient(135deg,#2e67dc,#4a7be8)!important;
      color:#fff!important;border:none!important;border-radius:10px!important;
      font-weight:700!important;font-size:14px!important;height:44px!important;
      box-shadow:0 2px 10px rgba(46,103,220,.3)!important}
    .stButton>button:hover{
      background:linear-gradient(135deg,#2253b8,#2e67dc)!important;
      box-shadow:0 4px 16px rgba(46,103,220,.4)!important}
    </style>
    """, unsafe_allow_html=True)

    # Centrer le formulaire
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("""
        <div style="margin-top:60px"></div>
        <div style="background:#fff;border:1px solid #cfdbf1;border-radius:18px;
          padding:32px 32px 24px;box-shadow:0 8px 32px rgba(22,42,79,.13)">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:28px">
            <div style="width:40px;height:40px;
              background:linear-gradient(135deg,#2e67dc,#5b8fee);
              border-radius:10px;display:flex;align-items:center;justify-content:center">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff"
                stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <ellipse cx="12" cy="5" rx="8" ry="3"/>
                <path d="M4 5v10c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>
                <path d="M4 10c0 1.7 3.6 3 8 3s8-1.3 8-3"/>
              </svg>
            </div>
            <div>
              <div style="font-size:22px;font-weight:800;color:#2253b8;
                letter-spacing:-.02em;line-height:1">Queryflow</div>
              <div style="font-size:11px;color:#5f6f87;margin-top:2px">
                Oracle Audit Intelligence &middot; Smart2d</div>
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
        with st.spinner("Génération SQL en cours..."):
            result_sql = generer_sql(question, tok, mdl, dev)
        print(f"[NLP] SQL genere : {result_sql}", flush=True)
    else:
        result_sql = "-- Modèle TinyLlama non disponible."
        print("[NLP] ERREUR : TinyLlama non charge", flush=True)

    # ── Étape 2 : Exécution Oracle ──
    res_txt = ""
    if not result_sql.startswith("--"):
        df_res, err_oracle = executer_sql_oracle(result_sql)
        if df_res is not None:
            result_html_out = df_to_html_table(df_res)
            res_txt = (df_res.to_string(index=False)
                       if not df_res.empty else "Aucun résultat.")
        else:
            result_erreur   = err_oracle or "Erreur inconnue"
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
        phi3_model = load_phi3()
        result_synthese = traduire_resultat(question, res_txt, phi3_model)

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
        f'Oracle connect&eacute; &middot; {len(audit_df)} lignes</span>'
    )
elif data_src == "csv":
    # Ne devrait plus arriver en mode production
    statut_db = (
        '<span style="font-size:11px;font-weight:600;color:#991b1b;background:#fee2e2;'
        'border:1px solid #fca5a5;border-radius:20px;padding:4px 10px">'
        '&#10060; Oracle non connect&eacute;</span>'
    )
else:
    statut_db = (
        '<span style="font-size:11px;font-weight:600;color:#991b1b;background:#fee2e2;'
        'border:1px solid #fca5a5;border-radius:20px;padding:4px 10px">'
        '&#10060; Aucune source</span>'
    )

# Utilisateurs
USERS_REELS = [
    {"name": n, "actions": 0} for n in
    ["SYSTEM","VROMUALD","SYS","HR","APP_USER","REPORT_USR",
     "AUDIT_USR","DBA_OPS","BACKUP_USR","MONITOR","SCOTT","ETL_USER"]
]
if not audit_df.empty and "DBUSERNAME" in audit_df.columns:
    uc = audit_df["DBUSERNAME"].value_counts().to_dict()
    for u in USERS_REELS:
        u["actions"] = int(uc.get(u["name"], 0))

TABLES_REELLES = [
    "EMPLOYEES","VROMUALD","CLIENTS","TRANSACTIONS","ORDERS","ACCOUNTS",
    "PAYROLL","JOURNAL","CONTRACTS","BUDGET","PRODUCTS","SUPPLIERS",
    "INVOICES","USERS","PAYMENTS","AUDIT_LOG","SESSIONS","ALERTS",
    "DBA_USERS","V$SESSION"
]

# Dernières actions
RECENT_ACTIONS = []
if not audit_df.empty and "DBUSERNAME" in audit_df.columns:
    for _, row in audit_df.head(10).iterrows():
        RECENT_ACTIONS.append({
            "user":   str(row.get("DBUSERNAME", "")),
            "object": str(row.get("OBJECT_NAME", "")),
            "date":   str(row.get("EVENT_TIMESTAMP", ""))[:16],
        })
else:
    print("[DATA] Aucune donnee reelle disponible pour les actions recentes", flush=True)
    RECENT_ACTIONS = []

users_html = "".join(
    "<li><span>" + u["name"] + "</span>"
    + "<span class='count-pill'>" + str(u["actions"]) + " actions</span></li>"
    for u in USERS_REELS
)
tables_html = "".join(
    "<li><span>" + t + "</span></li>" for t in TABLES_REELLES
)
recent_html = "".join(
    "<li style='flex-direction:column;align-items:flex-start;gap:1px;padding:8px 10px'>"
    + "<span style='font-size:12px;font-weight:700;color:#2c3d57'>" + a["user"] + "</span>"
    + ("<span style='font-size:11px;color:#5f6f87'>&rarr; " + a["object"] + "</span>"
       if a.get("object") else "")
    + "<span style='font-size:10px;color:#a0b0cc'>" + a["date"] + "</span>"
    + "</li>"
    for a in RECENT_ACTIONS
)

# Bloc résultat
# Bandeau question posée
def question_bandeau(q):
    if not q:
        return ""
    return (
        "<div style='background:#eef4ff;border:1px solid #c5d8f5;border-radius:8px;"
        "padding:10px 14px;margin-bottom:12px;font-size:13px;color:#2c3d57'>"
        "<strong style='color:#2253b8;font-size:11px;text-transform:uppercase;"
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
        "<div style='font-size:14px;font-weight:600;color:#4a6a90;margin-bottom:6px'>"
        "Aucune question pos&eacute;e</div>"
        "<div style='font-size:12px;color:#7a90b0'>"
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
:root{--bg:#eaf1ff;--surface:#ffffff;--line:#cfdbf1;--text:#1f2b3d;
  --muted:#5f6f87;--accent:#2e67dc;--accent-strong:#2253b8;
  --accent-light:#e8f0fe;--radius:12px;
  --shadow:0 4px 18px rgba(22,42,79,.09);
  --shadow-lg:0 8px 32px rgba(22,42,79,.13)}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif;
  background:radial-gradient(1400px 600px at 15% -5%,#d4e4ff 0%,transparent 60%),
  radial-gradient(900px 500px at 90% 10%,#dce8ff 0%,transparent 55%),#eaf1ff;
  color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-thumb{background:#c5d5ef;border-radius:3px}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.85)}}
.icon{width:15px;height:15px;display:inline-block;vertical-align:middle;
  stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;
  stroke-linejoin:round;flex-shrink:0}
.page{display:none}.page.active{display:block}
.app-shell{min-height:100vh;display:flex;flex-direction:column}
.topbar{height:62px;background:rgba(255,255,255,.92);backdrop-filter:blur(14px);
  border-bottom:1px solid rgba(207,219,241,.7);display:flex;align-items:center;
  padding:0 18px;gap:14px;position:sticky;top:0;z-index:50;
  box-shadow:0 1px 8px rgba(22,42,79,.06)}
.brand{display:flex;align-items:center;gap:9px;font-weight:800;
  color:var(--accent-strong);font-size:20px;letter-spacing:-.025em;white-space:nowrap}
.brand-icon{width:32px;height:32px;
  background:linear-gradient(135deg,var(--accent),#5b8fee);
  border-radius:8px;display:flex;align-items:center;justify-content:center}
.nav{display:flex;align-items:center;gap:4px;flex:1;justify-content:center}
.nav-btn{background:transparent;border:1.5px solid transparent;color:#4f5f78;
  height:36px;border-radius:9px;padding:0 13px;font-weight:600;font-size:13px;
  cursor:pointer;display:inline-flex;align-items:center;gap:7px;transition:all .15s}
.nav-btn:hover{background:var(--accent-light);color:var(--accent)}
.nav-btn.active{background:linear-gradient(135deg,var(--accent-light),#dce8ff);
  color:var(--accent-strong);border-color:#b8d0f8;
  box-shadow:0 1px 6px rgba(46,103,220,.12)}
.topbar-right{display:flex;align-items:center;gap:10px;white-space:nowrap;margin-left:auto}
.user-badge{color:var(--muted);font-size:13px;font-weight:600;
  display:inline-flex;align-items:center;gap:6px;background:#f0f5ff;
  border:1px solid var(--line);border-radius:8px;padding:5px 10px}
.btn-logout{height:36px;border-radius:9px;border:1.5px solid var(--line);
  background:#fff;color:var(--muted);font-weight:600;font-size:13px;
  padding:0 13px;cursor:pointer;display:inline-flex;align-items:center;
  gap:7px;transition:all .15s}
.btn-logout:hover{color:var(--text);border-color:#b0c4e8;background:#f5f8ff}
.page-wrap{width:min(98vw,1800px);margin:14px auto;flex:1;padding:0 4px}
.home-layout{display:grid;grid-template-columns:2.2fr .9fr .9fr .9fr;
  gap:12px;align-items:start}
.card{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);box-shadow:var(--shadow);transition:box-shadow .2s}
.card:hover{box-shadow:var(--shadow-lg)}
.main-card{padding:16px;min-height:680px;display:flex;flex-direction:column;
  background:linear-gradient(160deg,#fff 0%,#f6f9ff 100%)}
.main-title{margin:0 0 14px;font-size:20px;font-weight:700;letter-spacing:-.02em;
  display:inline-flex;align-items:center;gap:8px;color:var(--accent-strong)}
.ask-row{display:flex;gap:8px;margin-bottom:14px}
.ask-input{flex:1;height:44px;border:1.5px solid var(--line);border-radius:10px;
  padding:0 14px;font-size:14px;color:var(--text);background:#f8fbff;
  font-family:inherit;outline:none;transition:border-color .15s,box-shadow .15s}
.ask-input:focus{border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(46,103,220,.12);background:#fff}
.ask-input::placeholder{color:var(--muted)}
.btn-ask{height:44px;border-radius:10px;border:none;
  background:linear-gradient(135deg,var(--accent),#4a7be8);color:#fff;
  font-weight:700;font-size:14px;padding:0 20px;cursor:pointer;
  display:inline-flex;align-items:center;gap:8px;white-space:nowrap;
  transition:all .15s;box-shadow:0 2px 10px rgba(46,103,220,.3)}
.btn-ask:hover{background:linear-gradient(135deg,var(--accent-strong),var(--accent));
  transform:translateY(-1px)}
.btn-ask:active{transform:translateY(0)}
.result{margin-top:4px;border:1.5px solid var(--line);border-radius:10px;
  background:linear-gradient(160deg,#f5f9ff,#edf3ff);padding:16px;
  min-height:140px;flex:1}
.result.empty{color:var(--muted);display:grid;place-items:center;text-align:center;
  padding:30px;min-height:200px;border-style:dashed;border-color:#c5d8f5}
.empty-icon{font-size:32px;margin-bottom:8px;opacity:.5}
.result h3{margin:0 0 10px;font-size:13px;font-weight:700;color:var(--accent-strong);
  text-transform:uppercase;letter-spacing:.05em}
.synthese-box{background:#edf6f0;border:1px solid #b8e0c8;border-radius:8px;
  padding:12px 14px;font-size:14px;color:#1a4a30;margin-bottom:12px;line-height:1.6}
.sql-box{border:1px solid #c8d8f0;border-radius:8px;background:#f0f5ff;
  padding:10px 14px;font-family:"Consolas","Courier New",monospace;font-size:12px;
  color:#1e3a6e;overflow-x:auto;margin-bottom:12px;white-space:pre-wrap}
.result-table{width:100%;border-collapse:collapse;font-size:12px;background:#fff;
  border:1px solid var(--line);border-radius:8px;overflow:hidden}
.result-table th{background:linear-gradient(135deg,#eaf2ff,#dce8ff);color:#2a4a80;
  font-weight:700;padding:8px 10px;text-align:left;font-size:11px;
  text-transform:uppercase;letter-spacing:.04em}
.result-table td{border-bottom:1px solid #edf2f8;padding:7px 10px;
  white-space:nowrap;color:#2c3d57}
.result-table tbody tr:hover td{background:#f2f7ff}
.side-card{min-height:680px;display:flex;flex-direction:column}
.side-head{padding:11px 12px;font-weight:700;font-size:13px;color:#fff;
  display:inline-flex;align-items:center;gap:8px;
  background:linear-gradient(135deg,#3b77e8,#2a60cc);border-radius:11px 11px 0 0}
.side-body{padding:9px;display:flex;flex-direction:column;flex:1;min-height:0}
.search{height:34px;border:1.5px solid var(--line);border-radius:8px;
  padding:0 10px;font-size:12px;margin-bottom:8px;width:100%;
  background:#f8fbff;outline:none;transition:border-color .15s}
.search:focus{border-color:var(--accent)}
.simple-list{list-style:none;overflow:auto;flex:1;
  border:1px solid var(--line);border-radius:8px;background:#fbfdff}
.simple-list li{display:flex;align-items:center;justify-content:space-between;
  gap:6px;padding:8px 10px;border-bottom:1px solid #eef3f8;font-size:12px;
  font-weight:600;color:#2c3d57;transition:background .12s}
.simple-list li:last-child{border-bottom:none}
.simple-list li:hover{background:#f2f7ff}
.count-pill{font-size:10px;color:#325ca6;
  background:linear-gradient(135deg,#e0ebff,#d5e4ff);
  border:1px solid #c0d4f5;border-radius:999px;padding:3px 7px;flex-shrink:0}
.history-layout{display:grid;grid-template-columns:1.5fr 1fr;gap:12px;align-items:start}
.history-table-wrap,.history-detail,.settings-card{padding:14px}
.section-title{margin:0 0 12px;font-size:18px;font-weight:700;
  display:inline-flex;align-items:center;gap:8px;color:var(--accent-strong)}
.history-table{width:100%;border-collapse:collapse;font-size:12px;
  border:1px solid var(--line);border-radius:8px;overflow:hidden}
.history-table th{background:linear-gradient(135deg,#eaf2ff,#dce8ff);color:#2a4a80;
  font-weight:700;padding:8px 10px;text-align:left;font-size:11px;
  text-transform:uppercase;letter-spacing:.04em}
.history-table td{border-bottom:1px solid #edf2f8;padding:8px 10px;
  vertical-align:top;font-size:12px}
.history-table tr:hover td{background:#f2f7ff;cursor:pointer}
.detail-box{border:1px solid #d0e0f8;border-radius:8px;
  background:linear-gradient(135deg,#f5f9ff,#edf3ff);
  padding:10px;margin-bottom:10px;font-size:13px}
.detail-box h4{margin:0 0 6px;font-size:11px;font-weight:700;color:var(--accent);
  text-transform:uppercase;letter-spacing:.05em}
.detail-pre{margin:0;font-family:"Consolas","Courier New",monospace;
  font-size:12px;white-space:pre-wrap;color:#1e3a6e}
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.setting-group{border:1px solid var(--line);border-radius:10px;padding:12px;
  background:linear-gradient(135deg,#f8fbff,#f2f7ff)}
.setting-group h4{margin:0 0 10px;font-size:13px;font-weight:700;
  color:var(--accent-strong)}
.inline-field{margin-bottom:9px}
.inline-field label{display:block;font-size:11px;color:var(--muted);margin-bottom:4px;
  font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.inline-field input{width:100%;height:36px;border:1.5px solid var(--line);
  border-radius:8px;padding:0 10px;font-size:13px;background:#f8fbff;
  color:var(--text);outline:none;transition:border-color .15s}
.inline-field input:focus{border-color:var(--accent)}
.settings-actions{margin-top:12px;display:flex;gap:8px;justify-content:flex-end}
.btn-save{height:38px;border-radius:9px;border:none;
  background:linear-gradient(135deg,var(--accent),#4a7be8);color:#fff;
  font-weight:700;font-size:13px;padding:0 16px;cursor:pointer}
.btn-reset{height:38px;border-radius:9px;border:1.5px solid var(--line);
  background:#fff;color:var(--muted);font-weight:600;font-size:13px;
  padding:0 16px;cursor:pointer}
@media(max-width:1400px){.home-layout{grid-template-columns:2fr 1fr 1fr 1fr}}
@media(max-width:1100px){.home-layout{grid-template-columns:1fr 1fr}
  .main-card{grid-column:1/span 2}}
@media(max-width:900px){.topbar{flex-wrap:wrap;height:auto;padding:12px}
  .nav{order:3;justify-content:flex-start;width:100%}
  .home-layout{grid-template-columns:1fr}.main-card{grid-column:auto}
  .settings-grid{grid-template-columns:1fr}
  .history-layout{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app-shell">
  <header class="topbar">
    <div class="brand">
      <div class="brand-icon">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff"
          stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="5" rx="8" ry="3"/>
          <path d="M4 5v10c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>
          <path d="M4 10c0 1.7 3.6 3 8 3s8-1.3 8-3"/>
        </svg>
      </div>Queryflow
    </div>
    %%STATUT_DB%%
    <nav class="nav">
      <button class="nav-btn %%AH%%" onclick="showPage('home',this)">
        <svg class="icon" viewBox="0 0 24 24">
          <path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>
        Accueil</button>
      <button class="nav-btn %%AHH%%" onclick="showPage('history',this)">
        <svg class="icon" viewBox="0 0 24 24">
          <polyline points="1 4 1 10 7 10"/>
          <path d="M3.5 15a9 9 0 1 0 .5-4"/></svg>
        Historique</button>
      <button class="nav-btn %%AS%%" onclick="showPage('settings',this)">
        <svg class="icon" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06
            a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09
            A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83
            l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09
            A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83
            l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09
            a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83
            l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09
            a1.65 1.65 0 0 0-1.51 1z"/></svg>
        Param&egrave;tres</button>
    </nav>
    <div class="topbar-right">
      <span class="user-badge">
        <svg class="icon" viewBox="0 0 24 24">
          <path d="M20 21a8 8 0 1 0-16 0"/>
          <circle cx="12" cy="8" r="4"/></svg>
        %%USER%%</span>
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
          <section class="%%RC%%">%%RB%%</section>
        </article>

        <aside class="card side-card">
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
          </div>
        </aside>

        <aside class="card side-card">
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
          </div>
        </aside>

        <aside class="card side-card">
          <header class="side-head"
            style="background:linear-gradient(135deg,#1e5cb3,#1a4d9a)">
            <svg class="icon" viewBox="0 0 24 24">
              <polyline points="1 4 1 10 7 10"/>
              <path d="M3.5 15a9 9 0 1 0 .5-4"/></svg>
            Derni&egrave;res actions</header>
          <div class="side-body" style="padding:6px">
            <ul class="simple-list" style="border:none;background:transparent">
              %%RECENT%%</ul>
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
            <div class="inline-field"><label>Utilisateur</label>
              <input value="%%USER%%" readonly/></div>
            <div class="inline-field"><label>Entreprise</label>
              <input value="Smart2d"/></div>
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
          <section class="setting-group" style="grid-column:1/-1">
            <h4>Mod&egrave;le NLP</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
              <div class="inline-field"><label>G&eacute;n&eacute;ration SQL</label>
                <input value="TinyLlama-1.1B + LoRA V6" readonly/></div>
              <div class="inline-field"><label>Traduction FR</label>
                <input value="Phi-3 mini Q4 (local)" readonly/></div>
              <div class="inline-field"><label>Statut</label>
                <input value="%%MODEL_STATUS%%" readonly/></div>
            </div>
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

<script>
// Navigation
function showPage(name, btn) {
  document.querySelectorAll('.page').forEach(p =>
    p.classList.toggle('active', p.id === 'page-' + name));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

// Filtrage
function filterList(id, term) {
  document.getElementById(id).querySelectorAll('li').forEach(li =>
    li.style.display =
      li.textContent.toLowerCase().includes(term.toLowerCase()) ? '' : 'none');
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
function submitQuestion() {
  const q = document.getElementById('ask-input').value.trim();
  if (!q) return;

  // Cibler le champ texte du formulaire caché dans le parent Streamlit
  const inputs = window.parent.document.querySelectorAll('input[type="text"]');
  let qfInput = null;
  for (const inp of inputs) {
    // Le champ est identifiable par son aria-label ou son data-testid
    const label = inp.getAttribute('aria-label') || '';
    const placeholder = inp.getAttribute('placeholder') || '';
    if (label === 'q' || placeholder === 'q') {
      qfInput = inp; break;
    }
  }
  // Fallback : prendre le premier input caché non visible
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
    // Simuler la saisie pour que React/Streamlit détecte le changement
    const nativeInputSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    nativeInputSetter.call(qfInput, q);
    qfInput.dispatchEvent(new Event('input', {bubbles: true}));
    qfInput.dispatchEvent(new Event('change', {bubbles: true}));

    // Cliquer le bouton "Envoyer" du formulaire
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
    .replace("%%AH%%",           ah)
    .replace("%%AHH%%",          aH)
    .replace("%%AS%%",           aS)
    .replace("%%RC%%",           result_class)
    .replace("%%RB%%",           result_block)
    .replace("%%USERS%%",        users_html)
    .replace("%%TABLES%%",       tables_html)
    .replace("%%RECENT%%",       recent_html)
    .replace("%%HISTORY%%",      history_rows)
    .replace("%%MODEL_STATUS%%", model_status)
)

# Masquer le formulaire Streamlit complètement
st.markdown("""
<style>
#MainMenu,footer,header,.stDeployButton,.stDecoration{display:none!important}
.block-container{padding:0!important;max-width:100%!important}
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

components.html(html_final, height=940, scrolling=True)
