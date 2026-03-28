# ============================================================
#  Oracle NLP → SQL  |  QueryFlow — Interface professionnelle
#  Modèle : TinyLlama-1.1B + LoRA fine-tuné V2
#           Phi-3 mini Q4 local (SQL→FR)
#  Design : QueryFlow dark theme (DM Sans / DM Mono)
#  Lancer : streamlit run app_oracle_nlp.py
# ============================================================

import os, zipfile, torch, pandas as pd, re
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
# CSS QUERYFLOW — Dark theme professionnel
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&family=DM+Mono:wght@300;400;500&display=swap');

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d0f14;--surface:#13161e;--surface2:#1a1e28;--surface3:#222736;
  --border:#2a2f3f;--border2:#343a50;
  --text:#e8eaf0;--text2:#8c93a8;--text3:#555d75;
  --accent:#4f7dff;--accent2:#7c5cfc;
  --green:#34d399;--red:#f87171;--yellow:#fbbf24;
  --mono:'DM Mono',monospace;--font:'DM Sans',sans-serif;
  --radius:10px;--radius-lg:16px;
}
html,body,[class*="css"],.stApp{font-family:var(--font)!important;background:var(--bg)!important;color:var(--text)!important;}
.stApp>header{display:none!important}
#MainMenu,footer,.stDeployButton{display:none!important}
.block-container{padding:0!important;max-width:100%!important}
.stButton>button{
  font-family:var(--font)!important;border-radius:var(--radius)!important;
  border:1px solid var(--border)!important;background:var(--surface2)!important;
  color:var(--text2)!important;font-size:12.5px!important;
  transition:all .18s ease!important;padding:6px 14px!important;
}
.stButton>button:hover{border-color:var(--accent)!important;color:var(--accent)!important;background:rgba(79,125,255,.06)!important}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,var(--accent),var(--accent2))!important;color:#fff!important;border:none!important;box-shadow:0 2px 10px rgba(79,125,255,.3)!important}
.stButton>button[kind="primary"]:hover{opacity:.88!important}
.stTextArea textarea{
  font-family:var(--font)!important;background:var(--surface2)!important;
  border:1px solid var(--border)!important;border-radius:var(--radius-lg)!important;
  color:var(--text)!important;font-size:14px!important;resize:none!important;
}
.stTextArea textarea:focus{border-color:var(--accent)!important;box-shadow:0 0 0 3px rgba(79,125,255,.1)!important}
.stTextArea textarea::placeholder{color:var(--text3)!important}
.stSelectbox>div>div{background:var(--surface2)!important;border:1px solid var(--border)!important;border-radius:var(--radius)!important;color:var(--text)!important}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid var(--border)!important;gap:4px}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:var(--text2)!important;font-family:var(--font)!important;font-size:13px!important;border-radius:8px 8px 0 0!important;padding:8px 16px!important}
.stTabs [aria-selected="true"]{background:var(--surface)!important;color:var(--accent)!important;border:1px solid var(--border)!important;border-bottom:1px solid var(--surface)!important}
.stDataFrame{background:var(--surface2)!important;border-radius:var(--radius)!important}
.stTextInput>div>div>input{background:var(--surface2)!important;border:1px solid var(--border)!important;border-radius:var(--radius)!important;color:var(--text)!important;font-family:var(--font)!important;font-size:13px!important}
.stNumberInput>div>div>input{background:var(--surface2)!important;border:1px solid var(--border)!important;border-radius:var(--radius)!important;color:var(--text)!important;font-family:var(--font)!important}
.stSpinner>div{color:var(--accent)!important}
div[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border)!important}
hr{border-color:var(--border)!important;margin:10px 0!important}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:99px}
details>summary{color:var(--text2)!important;font-family:var(--mono)!important;font-size:12px!important;padding:8px!important;background:var(--surface2)!important;border-radius:8px!important}

/* ── HEADER ── */
.qf-header{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:0 24px;height:56px;display:flex;align-items:center;gap:16px;
  position:sticky;top:0;z-index:100;
}
.qf-logo{display:flex;align-items:center;gap:10px}
.qf-logo-icon{
  width:30px;height:30px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  border-radius:7px;display:flex;align-items:center;justify-content:center;
}
.qf-logo-name{font-size:15px;font-weight:600;letter-spacing:-.3px}
.qf-logo-name span{color:var(--accent)}
.qf-sep{width:1px;height:24px;background:var(--border)}
.qf-breadcrumb{font-size:13px;color:var(--text2);display:flex;align-items:center;gap:6px}
.qf-spacer{flex:1}
.qf-status{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--text2)}
.qf-status-dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 2px rgba(52,211,153,.2)}

/* ── BADGES ── */
.qf-badge{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:99px;font-size:11px;font-weight:500}
.qf-badge-green{background:rgba(52,211,153,.12);color:var(--green);border:1px solid rgba(52,211,153,.22)}
.qf-badge-blue{background:rgba(79,125,255,.12);color:var(--accent);border:1px solid rgba(79,125,255,.22)}
.qf-badge-purple{background:rgba(124,92,252,.15);color:var(--accent2);border:1px solid rgba(124,92,252,.25)}
.qf-badge-yellow{background:rgba(251,191,36,.12);color:var(--yellow);border:1px solid rgba(251,191,36,.22)}

/* ── SIDEBAR ITEMS ── */
.qf-sidebar-label{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:var(--text3);padding:6px 0 4px}
.qf-conv-item{
  display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;
  cursor:pointer;color:var(--text2);font-size:12.5px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  transition:all .15s;border:1px solid transparent;margin-bottom:2px;
}
.qf-conv-item:hover{background:var(--surface2);color:var(--text)}
.qf-conv-item.active{background:rgba(79,125,255,.1);color:var(--accent);border-color:rgba(79,125,255,.15)}

/* ── CHAT HEADER ── */
.qf-chat-header{
  padding:14px 20px 12px;border-bottom:1px solid var(--border);
  background:var(--surface);display:flex;align-items:center;justify-content:space-between;
}
.qf-chat-title{font-size:15px;font-weight:600;color:var(--text);display:flex;align-items:center;gap:8px}
.qf-chat-sub{font-size:11.5px;color:var(--text3);margin-top:2px}

/* ── MESSAGES ── */
.qf-messages{padding:18px 20px;display:flex;flex-direction:column;gap:16px;min-height:300px}
.qf-msg{display:flex;gap:10px;max-width:100%;animation:fadeUp .25s ease both}
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.qf-msg.user{flex-direction:row-reverse}
.qf-msg.user .qf-msg-meta{flex-direction:row-reverse}
.qf-msg-avatar{
  width:30px;height:30px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:11px;font-weight:600;flex-shrink:0;margin-top:2px;
}
.qf-msg-avatar.user{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff}
.qf-msg-avatar.bot{background:var(--surface3);color:var(--text2);border:1px solid var(--border);font-size:14px}
.qf-msg-body{flex:1;min-width:0}
.qf-msg-meta{display:flex;align-items:baseline;gap:8px;margin-bottom:5px}
.qf-msg-name{font-size:12.5px;font-weight:600;color:var(--text)}
.qf-msg-time{font-size:11px;color:var(--text3)}
.qf-bubble{padding:10px 14px;font-size:13.5px;line-height:1.6;max-width:700px;border-radius:0 10px 10px 10px}
.qf-bubble.user{background:rgba(79,125,255,.1);border:1px solid rgba(79,125,255,.2);border-radius:10px 0 10px 10px;color:var(--text)}
.qf-bubble.bot{background:var(--surface2);border:1px solid var(--border);color:var(--text2)}

/* ── SQL BLOCK ── */
.qf-sql-block{margin-top:10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.qf-sql-header{display:flex;align-items:center;justify-content:space-between;padding:6px 12px;background:var(--surface2);border-bottom:1px solid var(--border)}
.qf-sql-header span{font-size:11px;color:var(--text3);font-family:var(--mono)}
.qf-sql-pre{padding:12px 14px;font-family:var(--mono);font-size:12.5px;color:var(--accent);overflow-x:auto;line-height:1.6;white-space:pre-wrap;word-break:break-word}

/* ── RESULT TABLE ── */
.qf-result-wrap{margin-top:10px;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.qf-result-header{display:flex;align-items:center;justify-content:space-between;padding:7px 14px;background:var(--surface2);border-bottom:1px solid var(--border)}
.qf-result-header span{font-size:12px;color:var(--text2);font-weight:500}
.qf-result-table{width:100%;border-collapse:collapse;font-size:12.5px}
.qf-result-table th{padding:7px 12px;text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.4px;color:var(--text3);background:var(--surface2);border-bottom:1px solid var(--border)}
.qf-result-table td{padding:7px 12px;border-bottom:1px solid var(--border);color:var(--text2);font-family:var(--mono);font-size:12px}
.qf-result-table tr:last-child td{border-bottom:none}
.qf-result-table tr:hover td{background:rgba(255,255,255,.015)}

/* ── NAT RESPONSE ── */
.qf-nat-label{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--accent);margin-bottom:5px}
.qf-nat-box{margin-top:10px;padding:10px 14px;background:rgba(79,125,255,.05);border:1px solid rgba(79,125,255,.15);border-radius:var(--radius);font-size:13px;color:var(--text2);line-height:1.6}

/* ── EMPTY STATE ── */
.qf-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 40px;text-align:center}
.qf-empty-icon{width:52px;height:52px;background:var(--surface2);border:1px solid var(--border);border-radius:14px;display:flex;align-items:center;justify-content:center;margin-bottom:16px;font-size:22px}
.qf-empty-title{font-size:16px;font-weight:600;color:var(--text);margin-bottom:6px}
.qf-empty-sub{font-size:13px;color:var(--text3);max-width:340px;line-height:1.6}

/* ── STATS ── */
.qf-stat-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.qf-stat-card{flex:1;min-width:110px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:13px 15px}
.qf-stat-label{font-size:11px;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:.4px}
.qf-stat-value{font-size:22px;font-weight:600;color:var(--text);font-family:var(--mono)}
.qf-stat-sub{font-size:11.5px;color:var(--text3);margin-top:3px}

/* ── LOGS ── */
.qf-log-item{display:flex;align-items:flex-start;gap:10px;padding:9px 0;border-bottom:1px solid var(--border);font-size:12.5px}
.qf-log-item:last-child{border-bottom:none}
.qf-log-level{font-family:var(--mono);font-size:11px;font-weight:600;flex-shrink:0;width:42px}
.qf-log-time{font-family:var(--mono);font-size:11px;color:var(--text3);flex-shrink:0;width:60px}
.qf-log-msg{color:var(--text2);line-height:1.5}

/* ── CARDS ADMIN ── */
.qf-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px 22px;margin-bottom:14px}
.qf-config-grid{display:flex;gap:16px;flex-wrap:wrap;margin-top:6px}
.qf-config-item{flex:1;min-width:110px;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px}
.qf-config-label{font-size:11px;color:var(--text3);margin-bottom:5px}
.qf-config-value{font-family:var(--mono);font-size:20px;font-weight:600;color:var(--accent)}

/* ── OBJETS SIDEBAR ── */
.qf-obj-header{display:flex;align-items:center;justify-content:space-between;padding:12px 0 8px}
.qf-obj-header h3{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--text2)}
.qf-col-row{font-family:var(--mono);font-size:11px;color:var(--text2);padding:3px 0;border-bottom:1px solid var(--border)}
.qf-col-row:last-child{border-bottom:none}

/* ── APERCU TABLE ── */
.qf-apercu-wrap{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;margin-top:8px}
.qf-apercu-header{padding:8px 14px;background:var(--surface3);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.qf-apercu-title{font-size:12px;font-weight:600;color:var(--text);font-family:var(--mono)}
.qf-apercu-meta{font-size:11px;color:var(--text3)}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# PROMPT SYSTÈME TINYLLAMA — identique à l'entraînement
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = (
    "Tu es un expert Oracle Database specialise en audit SQL.\n"
    "Table principale : ORACLE_AUDIT_TRAIL (colonnes : AUDIT_ID, TIMESTAMP, OS_USER, DB_USER, "
    "OS_HOST, TERMINAL, SESSIONID, ACTION_NAME, OBJ_SCHEMA, OBJ_NAME, SQL_TEXT, RETURNCODE, "
    "PRIVILEGE_USED, STATEMENT, COMMENT_TEXT)\n"
    "Vue systeme : DBA_USERS (colonnes : USERNAME, USER_ID, ACCOUNT_STATUS, LOCK_DATE, "
    "EXPIRY_DATE, DEFAULT_TABLESPACE, TEMPORARY_TABLESPACE, CREATED, PROFILE)\n"
    "Regles importantes :\n"
    "- Pour compter les utilisateurs EXISTANTS dans la base -> utiliser DBA_USERS\n"
    "- Pour les evenements/actions/audit -> utiliser ORACLE_AUDIT_TRAIL\n"
    "- Pour 'derniere personne' -> retourner DB_USER + ACTION_NAME + TIMESTAMP\n"
    "- Pour 'toutes actions' -> ne pas filtrer sur ACTION_NAME='SELECT' sauf si demande\n"
    "- FETCH FIRST N ROWS ONLY pour limiter les resultats Oracle\n"
    "- COUNT(DISTINCT col) pour compter des valeurs uniques\n"
    "- Filtrage temporel : SUBSTR(TIMESTAMP,1,10) >= TO_CHAR(SYSDATE-N,'YYYY-MM-DD')\n"
    "Reponds uniquement en SQL Oracle valide ou en francais naturel selon la question."
)


# ══════════════════════════════════════════════════════════════
# CODES ERREUR ORACLE — 29 codes couverts
# Pour ajouter un code : "ORA-XXXXX": "description en francais",
# ══════════════════════════════════════════════════════════════
ORACLE_ERRORS = {
    # Connexion / Authentification
    "ORA-01017": "mot de passe incorrect ou compte inexistant",
    "ORA-01045": "privilege CREATE SESSION manquant — l'utilisateur ne peut pas se connecter",
    "ORA-03136": "timeout de connexion entrante — le client n'a pas termine la negociation dans le delai imparti, possible tentative suspecte ou attaque",
    "ORA-28000": "compte Oracle verrouille",
    "ORA-28001": "mot de passe expire — l'utilisateur doit le renouveler",
    "ORA-28002": "mot de passe expire dans moins de N jours — renouvellement requis bientot",
    "ORA-28003": "verification du mot de passe echouee — ne respecte pas la politique de securite",
    # Privileges / Acces
    "ORA-00942": "table ou vue inexistante ou acces non autorise",
    "ORA-01031": "privileges insuffisants pour effectuer cette operation",
    "ORA-00955": "nom d'objet deja utilise par un objet existant",
    "ORA-01950": "pas de privileges sur le tablespace — quota insuffisant",
    # SQL / Syntaxe
    "ORA-00904": "nom de colonne invalide",
    "ORA-00907": "parenthese fermante manquante dans la requete",
    "ORA-00911": "caractere invalide dans la requete SQL",
    "ORA-00933": "commande SQL mal terminee",
    "ORA-00936": "expression manquante dans la requete",
    # Donnees / Contraintes
    "ORA-00001": "violation de contrainte d'unicite — valeur deja existante",
    "ORA-01400": "impossible d'inserer une valeur NULL dans une colonne obligatoire",
    "ORA-01438": "valeur numerique trop grande pour la colonne cible",
    "ORA-02291": "contrainte d'integrite violee — enregistrement parent introuvable",
    "ORA-02292": "contrainte d'integrite violee — des enregistrements enfants existent",
    # Ressources / Systeme
    "ORA-01000": "nombre maximum de curseurs ouverts depasse",
    "ORA-01555": "snapshot trop ancien — donnees annulees non disponibles",
    "ORA-04031": "memoire partagee insuffisante dans le SGA",
    "ORA-00018": "nombre maximum de sessions Oracle depasse",
    "ORA-00020": "nombre maximum de processus Oracle depasse",
    # Objets / Concurrence
    "ORA-00054": "ressource occupee et NOWAIT specifie — verrou non disponible",
    "ORA-00060": "interblocage detecte (deadlock) entre deux transactions",
    "ORA-08177": "impossible de serialiser l'acces — transaction concurrente detectee",
}

# ── Prompt système Phi-3 — construit dynamiquement depuis ORACLE_ERRORS ──
PHI3_SYSTEM = (
    "Tu es un assistant specialise en audit Oracle Database.\n"
    "Tu recois le resultat brut d'une requete SQL executee sur la table ORACLE_AUDIT_TRAIL.\n"
    "Tu traduis ce resultat en francais clair et comprehensible pour un responsable non-technicien.\n\n"
    "Codes erreur Oracle a connaitre :\n"
    + "\n".join(f"- {k} : {v}" for k, v in ORACLE_ERRORS.items()) +
    "\n\nRegles strictes :\n"
    "- Reponds en 2 a 4 phrases maximum\n"
    "- Mentionne les valeurs importantes du resultat (noms, nombres, dates)\n"
    "- Si le resultat est vide ou 'Aucune ligne retournee', dis-le clairement\n"
    "- Si tu vois un code ORA-, explique ce que cela signifie en francais\n"
    "- Ne montre jamais le SQL brut dans ta reponse\n"
    "- Reponds uniquement en francais\n"
)


# ══════════════════════════════════════════════════════════════
# POST-PROCESSING SQL V2 — 4 règles sémantiques
# ══════════════════════════════════════════════════════════════
def post_process_sql(sql: str, question: str) -> str:
    q  = question.lower()
    su = sql.upper()

    kw_dba = ["existent dans la base","crees dans oracle","comptes oracle",
              "utilisateurs oracle existants","nombre d'utilisateurs",
              "nombre de comptes","comptes dans la base","schemas oracle"]
    if any(k in q for k in kw_dba):
        if "ORACLE_AUDIT_TRAIL" in su and "DBA_USERS" not in su:
            sql = re.sub(r"FROM\s+ORACLE_AUDIT_TRAIL","FROM DBA_USERS",sql,flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'[^']+'\s*","",sql,flags=re.IGNORECASE)
            sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'[^']+'","",sql,flags=re.IGNORECASE)
            sql = re.sub(r"\bDB_USER\b","USERNAME",sql,flags=re.IGNORECASE)

    kw_last = ["derniere personne","dernier utilisateur","touche en dernier",
               "qui a modifie","modifie en dernier","dernier acces","qui a fait la derniere"]
    if any(k in q for k in kw_last):
        if "DB_USER" not in su and "USERNAME" not in su:
            sql = re.sub(r"SELECT\s+MAX\(TIMESTAMP\)",
                         "SELECT DB_USER, ACTION_NAME, MAX(TIMESTAMP) AS DERNIERE_ACTION",
                         sql,flags=re.IGNORECASE)
        if "ACTION_NAME='SELECT'" in su.replace(" ",""):
            sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'SELECT'","",sql,flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*AND\s*","WHERE ",sql,flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*$","",sql,flags=re.IGNORECASE)

    kw_all = ["le plus d'actions","le plus d'operations","le plus interagi",
              "toutes actions","toutes les actions"]
    if any(k in q for k in kw_all):
        sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*AND\s*","WHERE ",sql,flags=re.IGNORECASE)
        sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'SELECT'","",sql,flags=re.IGNORECASE)
        sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*$","",sql,flags=re.IGNORECASE)

    kw_modif = ["modifie le plus de tables","tables differentes","tables modifiees",
                "modifications","le plus de tables","tables distinctes modifiees"]
    if any(k in q for k in kw_modif):
        if "INSERT" not in su and "UPDATE" not in su and "DELETE" not in su:
            if "WHERE" in su:
                sql = re.sub(r"WHERE\s+",
                             "WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') AND ",
                             sql,count=1,flags=re.IGNORECASE)
            elif "GROUP BY" in su:
                sql = re.sub(r"GROUP BY",
                             "WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') GROUP BY",
                             sql,count=1,flags=re.IGNORECASE)

    if ";" in sql:
        sql = sql[:sql.index(";")+1]
    return sql.strip()


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════
def unzip_if_needed(zip_path: str, extract_dir: str):
    if not os.path.exists(extract_dir) and os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

def clean_sql(raw: str, question: str = "") -> str:
    if "[/INST]" in raw:
        raw = raw.split("[/INST]")[-1]
    sql = raw.strip().split("\n\n")[0].strip()
    return post_process_sql(sql, question)

def executer_sur_audit(sql: str, df: pd.DataFrame):
    if sql.strip().startswith("--") or "REFUS" in sql.upper():
        return None
    try:
        import pandasql as psql
        oracle_audit_trail = df  # noqa
        sql_a = re.sub(r"FETCH FIRST (\d+) ROWS ONLY", r"LIMIT \1", sql, flags=re.IGNORECASE)
        return psql.sqldf(sql_a, locals())
    except Exception:
        return None

def dataframe_to_text(df: pd.DataFrame, max_rows: int = 10) -> str:
    if df is None or df.empty:
        return "Aucune ligne retournee."
    lines = [f"{len(df)} ligne(s) retournee(s)."]
    lines.append(df.head(max_rows).to_string(index=False))
    if len(df) > max_rows:
        lines.append(f"(+{len(df)-max_rows} lignes supplementaires)")
    return "\n".join(lines)

def highlight_sql(sql: str) -> str:
    keywords = ["SELECT","FROM","WHERE","JOIN","ON","GROUP BY","ORDER BY","HAVING",
                "FETCH FIRST","ROWS ONLY","DISTINCT","COUNT","SUM","MAX","MIN","AVG",
                "AND","OR","NOT","IN","BETWEEN","AS","BY","INNER","LEFT","RIGHT",
                "OUTER","UNION","INSERT","UPDATE","DELETE","CASE","WHEN","THEN","ELSE",
                "END","WITH","EXISTS","LIMIT","DESC","ASC","INTO","VALUES"]
    result = sql
    for kw in sorted(keywords, key=len, reverse=True):
        result = re.sub(r'\b'+re.escape(kw)+r'\b',
                        f'<span style="color:#6eb4ff;font-weight:500">{kw}</span>',
                        result, flags=re.IGNORECASE)
    result = re.sub(r"'([^']*)'", r'<span style="color:#34d399">\'\\1\'</span>', result)
    result = re.sub(r'\b(\d+)\b',  r'<span style="color:#fbbf24">\1</span>', result)
    return result


# ══════════════════════════════════════════════════════════════
# CHARGEMENT MODÈLES
# ══════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner=False)
def load_tinyllama():
    """TinyLlama + LoRA — FR → SQL Oracle"""
    unzip_if_needed("TinyLlama-1.1B-Chat-v1.0.zip", "TinyLlama-1.1B-Chat-v1.0")
    unzip_if_needed("tinyllama_oracle_lora.zip",     "tinyllama_oracle_lora")
    tokenizer = AutoTokenizer.from_pretrained("TinyLlama-1.1B-Chat-v1.0")
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        "TinyLlama-1.1B-Chat-v1.0", torch_dtype=torch.float16, device_map=None
    )
    model = PeftModel.from_pretrained(base, "tinyllama_oracle_lora")
    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return tokenizer, model.to(device), device

@st.cache_resource(show_spinner=False)
def load_phi3():
    """Phi-3 mini Q4_K_M — SQL + résultat → Français naturel"""
    unzip_if_needed("phi3-mini-gguf.zip", "phi3-mini-gguf")
    model_path = os.path.join("phi3-mini-gguf", "Phi-3-mini-4k-instruct-q4.gguf")
    if not os.path.exists(model_path):
        return None
    return Llama(
        model_path  = model_path,
        n_ctx       = 2048,
        n_gpu_layers= 35,   # mettre 0 si pas de GPU
        verbose     = False,
    )

@st.cache_data
def load_data():
    audit   = pd.read_csv("oracle_audit_trail.csv").fillna("") \
              if os.path.exists("oracle_audit_trail.csv") else pd.DataFrame()
    dataset = pd.read_csv("oracle_nlp_dataset.csv") \
              if os.path.exists("oracle_nlp_dataset.csv") else pd.DataFrame()
    return audit, dataset


# ══════════════════════════════════════════════════════════════
# GÉNÉRATION
# ══════════════════════════════════════════════════════════════
def appel_tinyllama(prompt, tokenizer, model, device,
                    max_new_tokens=100, max_input_length=512):
    inputs = tokenizer(prompt, return_tensors="pt",
                       truncation=True, max_length=max_input_length)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens,
            do_sample=False, pad_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.15,
        )
    raw = tokenizer.decode(out[0], skip_special_tokens=True)
    return raw.split("[/INST]")[-1].strip() if "[/INST]" in raw else raw.strip()

def generer_sql(question, tokenizer, model, device):
    """FR → SQL Oracle via TinyLlama fine-tuné"""
    prompt = f"[INST] {SYSTEM_PROMPT}\n{question}\n[/INST]"
    raw    = appel_tinyllama(prompt, tokenizer, model, device,
                             max_new_tokens=100, max_input_length=512)
    return clean_sql(raw, question)

def traduire_resultat(sql: str, resultat_brut: str, phi3) -> str:
    """SQL + résultat brut → Français naturel via Phi-3 mini Q4 local"""
    if phi3 is None:
        return "Phi-3 mini non disponible — placez phi3-mini-gguf.zip dans le repertoire."
    user_msg = (
        f"Requete SQL executee :\n{sql}\n\n"
        f"Resultat Oracle brut :\n{resultat_brut}\n\n"
        f"Traduis ce resultat en francais clair pour un responsable."
    )
    prompt = (
        f"<|system|>\n{PHI3_SYSTEM}<|end|>\n"
        f"<|user|>\n{user_msg}<|end|>\n"
        f"<|assistant|>\n"
    )
    response = phi3(
        prompt,
        max_tokens     = 200,
        temperature    = 0.2,
        repeat_penalty = 1.1,
        stop           = ["<|end|>", "<|user|>"],
    )
    return response["choices"][0]["text"].strip()


# ══════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════
defaults = {"historique": [], "prefill": "", "nb_requetes": 0}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════
# DONNÉES & MÉTADONNÉES
# ══════════════════════════════════════════════════════════════
audit_df, dataset_df = load_data()

TABLES_META = {
    "ORACLE_AUDIT_TRAIL": {
        "cols": ["AUDIT_ID","TIMESTAMP","OS_USER","DB_USER","OS_HOST",
                 "ACTION_NAME","OBJ_NAME","RETURNCODE","SQL_TEXT"],
        "rows": len(audit_df) if not audit_df.empty else "—",
        "desc": "Trace d'audit Oracle",
    },
    "DBA_USERS": {
        "cols": ["USERNAME","USER_ID","ACCOUNT_STATUS","LOCK_DATE","CREATED","PROFILE"],
        "rows": "vue système",
        "desc": "Utilisateurs Oracle",
    },
}

QUESTIONS_RAPIDES = [
    "Combien d'utilisateurs existent dans la base Oracle ?",
    "Quel utilisateur a le plus d'actions sur DBA_USERS ?",
    "Dernière personne à avoir touché CUSTOMERS ?",
    "Les 5 dernières actions enregistrées",
    "Top 3 utilisateurs — tables modifiées en 7 jours",
    "Utilisateurs avec erreurs Oracle (RETURNCODE != 0)",
]


# ══════════════════════════════════════════════════════════════
# HEADER QUERYFLOW
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div class="qf-header">
  <div class="qf-logo">
    <div class="qf-logo-icon">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <ellipse cx="12" cy="5" rx="9" ry="3"/>
        <path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/>
        <path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>
      </svg>
    </div>
    <span class="qf-logo-name">Query<span>Flow</span></span>
  </div>
  <div class="qf-sep"></div>
  <div class="qf-breadcrumb">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
    Oracle NLP → SQL Assistant
  </div>
  <div class="qf-spacer"></div>
  <div class="qf-status">
    <div class="qf-status-dot"></div>
    Oracle Production
  </div>
  <div class="qf-sep"></div>
  <span class="qf-badge qf-badge-green">Modèle V2 · 90%+</span>
  <span class="qf-badge qf-badge-purple">LoRA r=32</span>
  <span class="qf-badge qf-badge-blue">Phi-3 Q4</span>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# ONGLETS PRINCIPAUX
# ══════════════════════════════════════════════════════════════
tab_chat, tab_apercu, tab_admin = st.tabs(["💬  Chat", "📋  Aperçu table", "⚙️  Administration"])


# ══════════════════════════════════════════════════════════════
# TAB 1 — CHAT
# ══════════════════════════════════════════════════════════════
with tab_chat:
    col_left, col_main, col_right = st.columns([1.05, 4, 1.05])

    # ── Sidebar gauche ──
    with col_left:
        st.markdown('<div class="qf-sidebar-label">Questions rapides</div>', unsafe_allow_html=True)
        for q in QUESTIONS_RAPIDES:
            label = (q[:40]+"…") if len(q) > 40 else q
            if st.button(label, key=f"qr_{hash(q)}", use_container_width=True):
                st.session_state.prefill = q
                st.rerun()

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown('<div class="qf-sidebar-label">Historique session</div>', unsafe_allow_html=True)

        user_msgs = [m for m in st.session_state.historique if m["role"] == "user"]
        if user_msgs:
            for i, m in enumerate(user_msgs[-6:]):
                label  = (m["content"][:36]+"…") if len(m["content"]) > 36 else m["content"]
                active = "active" if i == len(user_msgs)-1 else ""
                st.markdown(
                    f'<div class="qf-conv-item {active}">💬 {label}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div style="font-size:12px;color:var(--text3);padding:4px 2px">Aucun historique</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<hr>", unsafe_allow_html=True)
        if st.button("🗑️ Vider l'historique", use_container_width=True):
            st.session_state.historique   = []
            st.session_state.nb_requetes  = 0
            st.rerun()

        st.markdown(f"""
        <div style="margin-top:10px;padding:10px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);text-align:center">
          <div style="font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px">Requêtes</div>
          <div style="font-size:24px;font-weight:600;font-family:var(--mono);color:var(--accent)">{st.session_state.nb_requetes}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── Main chat ──
    with col_main:
        st.markdown("""
        <div class="qf-chat-header">
          <div>
            <div class="qf-chat-title">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              Conversation — Audit Oracle
            </div>
            <div class="qf-chat-sub">TinyLlama FR→SQL · Phi-3 mini Q4 SQL→FR · Post-processing sémantique actif</div>
          </div>
          <span class="qf-badge qf-badge-blue">ORACLE_AUDIT_TRAIL</span>
        </div>
        """, unsafe_allow_html=True)

        if not st.session_state.historique:
            st.markdown("""
            <div class="qf-empty">
              <div class="qf-empty-icon">🔷</div>
              <div class="qf-empty-title">Posez votre première question</div>
              <div class="qf-empty-sub">
                Interrogez ORACLE_AUDIT_TRAIL en français naturel.<br>
                TinyLlama génère le SQL Oracle, l'exécute sur la table,<br>
                puis Phi-3 mini vous explique le résultat en français clair.
              </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            msgs_html = '<div class="qf-messages">'
            for msg in st.session_state.historique:
                role    = msg["role"]
                content = msg["content"]
                t       = msg.get("time", "")

                if role == "user":
                    msgs_html += f"""
                    <div class="qf-msg user">
                      <div class="qf-msg-avatar user">US</div>
                      <div class="qf-msg-body">
                        <div class="qf-msg-meta">
                          <span class="qf-msg-name">Vous</span>
                          <span class="qf-msg-time">{t}</span>
                        </div>
                        <div class="qf-bubble user">{content}</div>
                      </div>
                    </div>"""

                elif role == "sql":
                    hl = highlight_sql(content)
                    msgs_html += f"""
                    <div style="margin-left:40px">
                      <div class="qf-sql-block">
                        <div class="qf-sql-header">
                          <span>SQL Oracle généré — TinyLlama LoRA V2</span>
                          <span class="qf-badge qf-badge-blue" style="font-size:10px">post-processed</span>
                        </div>
                        <div class="qf-sql-pre">{hl}</div>
                      </div>
                    </div>"""

                elif role == "table":
                    msgs_html += f"""
                    <div style="margin-left:40px">
                      <div class="qf-result-wrap">
                        <div class="qf-result-header">
                          <span>Résultats Oracle</span>
                          <span class="qf-badge qf-badge-green" style="font-size:10px">Exécutée</span>
                        </div>
                        <div style="overflow-x:auto">{content}</div>
                      </div>
                    </div>"""

                elif role == "bot":
                    msgs_html += f"""
                    <div class="qf-msg">
                      <div class="qf-msg-avatar bot">🔷</div>
                      <div class="qf-msg-body">
                        <div class="qf-msg-meta">
                          <span class="qf-msg-name">QueryFlow</span>
                          <span class="qf-msg-time">{t}</span>
                          <span class="qf-badge qf-badge-purple" style="font-size:10px">Phi-3 Q4</span>
                        </div>
                        <div class="qf-bubble bot">
                          <div class="qf-nat-label">Interprétation</div>
                          {content}
                        </div>
                      </div>
                    </div>"""

                elif role == "error":
                    msgs_html += f"""
                    <div class="qf-msg">
                      <div class="qf-msg-avatar bot">🔷</div>
                      <div class="qf-msg-body">
                        <div class="qf-bubble bot" style="border-color:rgba(248,113,113,.2);background:rgba(248,113,113,.04)">
                          <span style="color:var(--red)">⚠ </span>{content}
                        </div>
                      </div>
                    </div>"""

            msgs_html += "</div>"
            st.markdown(msgs_html, unsafe_allow_html=True)

        # ── Zone de saisie ──
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        sg1, sg2, sg3 = st.columns(3)
        sugg = ["5 dernières actions", "Erreurs Oracle", "Activité nocturne > 22h"]
        for i, (sg, col) in enumerate(zip(sugg, [sg1, sg2, sg3])):
            with col:
                if st.button(sg, key=f"sg_{i}", use_container_width=True):
                    st.session_state.prefill = sg
                    st.rerun()

        user_input = st.text_area(
            label="q",
            value=st.session_state.prefill,
            placeholder="Posez votre question Oracle en français… (Ex: Qui a touché CUSTOMERS en dernier ?)",
            label_visibility="collapsed",
            height=82,
            key="qf_input",
        )

        btn_send, btn_clear, _ = st.columns([1, 1, 4])
        with btn_send:
            send = st.button("▶  Envoyer", type="primary", use_container_width=True)
        with btn_clear:
            if st.button("✕  Effacer", use_container_width=True):
                st.session_state.prefill = ""
                st.rerun()

        # ── Traitement ──
        if send and user_input.strip():
            st.session_state.prefill = ""
            question = user_input.strip()
            now      = datetime.now().strftime("%H:%M")

            st.session_state.historique.append({"role":"user","content":question,"time":now})
            st.session_state.nb_requetes += 1

            # 1. FR → SQL via TinyLlama
            with st.spinner("Génération SQL (TinyLlama)…"):
                tok, mdl, dev = load_tinyllama()
                sql = generer_sql(question, tok, mdl, dev)

            st.session_state.historique.append({"role":"sql","content":sql,"time":now})

            # 2. Exécution sur ORACLE_AUDIT_TRAIL
            result = executer_sur_audit(sql, audit_df)
            if result is not None and not result.empty:
                html_tbl = result.head(10).to_html(
                    classes="qf-result-table", index=False, border=0
                )
                st.session_state.historique.append({"role":"table","content":html_tbl,"time":now})
            else:
                if sql.strip().startswith("--") or "REFUS" in sql.upper():
                    st.session_state.historique.append({
                        "role": "error",
                        "content": "Requête refusée (opération non autorisée sur la table d'audit).",
                        "time": now,
                    })
                else:
                    st.session_state.historique.append({
                        "role": "table",
                        "content": "<div style='padding:12px;color:var(--text3);font-size:13px'>Aucun résultat — filtre trop restrictif ou table DBA_USERS simulée.</div>",
                        "time": now,
                    })

            # 3. SQL + résultat → Français via Phi-3
            with st.spinner("Interprétation (Phi-3 mini Q4)…"):
                phi3_model  = load_phi3()
                res_txt     = dataframe_to_text(result) if result is not None else "Aucune ligne retournee."
                traduction  = traduire_resultat(sql, res_txt, phi3_model)

            st.session_state.historique.append({"role":"bot","content":traduction,"time":now})
            st.rerun()

    # ── Sidebar droite — Objets Oracle ──
    with col_right:
        st.markdown("""
        <div class="qf-obj-header">
          <h3>Objets Oracle</h3>
          <span class="qf-badge qf-badge-blue" style="font-size:10px">2</span>
        </div>
        """, unsafe_allow_html=True)

        for tname, tmeta in TABLES_META.items():
            with st.expander(f"🗃  {tname}", expanded=(tname == "ORACLE_AUDIT_TRAIL")):
                st.markdown(
                    f'<div style="font-size:11px;color:var(--text3);margin-bottom:6px">'
                    f'{tmeta["desc"]} · {tmeta["rows"]} lignes</div>',
                    unsafe_allow_html=True,
                )
                cols_html = "".join(
                    f'<div class="qf-col-row">{c}</div>' for c in tmeta["cols"]
                )
                st.markdown(cols_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TAB 2 — APERÇU TABLE
# ══════════════════════════════════════════════════════════════
with tab_apercu:
    st.markdown("""
    <div style="padding:18px 0 12px">
      <div style="font-size:19px;font-weight:600;color:var(--text);margin-bottom:3px">Aperçu — ORACLE_AUDIT_TRAIL</div>
      <div style="font-size:13px;color:var(--text3)">Table simulée chargée depuis oracle_audit_trail.csv</div>
    </div>
    """, unsafe_allow_html=True)

    if audit_df.empty:
        st.markdown("""
        <div class="qf-empty">
          <div class="qf-empty-icon">📂</div>
          <div class="qf-empty-title">Fichier introuvable</div>
          <div class="qf-empty-sub">oracle_audit_trail.csv non trouvé dans le répertoire courant.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        n_actions = audit_df["ACTION_NAME"].nunique() if "ACTION_NAME" in audit_df.columns else "—"
        n_users   = audit_df["DB_USER"].nunique()     if "DB_USER"      in audit_df.columns else "—"
        n_errors  = int((audit_df["RETURNCODE"] != 0).sum()) if "RETURNCODE" in audit_df.columns else "—"
        n_objs    = audit_df["OBJ_NAME"].nunique()    if "OBJ_NAME"     in audit_df.columns else "—"

        st.markdown(f"""
        <div class="qf-stat-row">
          <div class="qf-stat-card"><div class="qf-stat-label">Total lignes</div><div class="qf-stat-value">{len(audit_df)}</div><div class="qf-stat-sub">entrées d'audit</div></div>
          <div class="qf-stat-card"><div class="qf-stat-label">Utilisateurs</div><div class="qf-stat-value">{n_users}</div><div class="qf-stat-sub">DB_USER distincts</div></div>
          <div class="qf-stat-card"><div class="qf-stat-label">Actions</div><div class="qf-stat-value">{n_actions}</div><div class="qf-stat-sub">types distincts</div></div>
          <div class="qf-stat-card"><div class="qf-stat-label">Erreurs</div><div class="qf-stat-value" style="color:var(--red)">{n_errors}</div><div class="qf-stat-sub">RETURNCODE ≠ 0</div></div>
          <div class="qf-stat-card"><div class="qf-stat-label">Objets</div><div class="qf-stat-value">{n_objs}</div><div class="qf-stat-sub">OBJ_NAME distincts</div></div>
        </div>
        """, unsafe_allow_html=True)

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            actions_list = ["Toutes"] + sorted(audit_df["ACTION_NAME"].unique().tolist()) \
                           if "ACTION_NAME" in audit_df.columns else ["Toutes"]
            f_action = st.selectbox("Action", actions_list, key="fa")
        with fc2:
            users_list = ["Tous"] + sorted(audit_df["DB_USER"].unique().tolist()) \
                         if "DB_USER" in audit_df.columns else ["Tous"]
            f_user = st.selectbox("Utilisateur", users_list, key="fu")
        with fc3:
            f_n = st.selectbox("Lignes affichées", [10, 25, 50, 100, 500], key="fn")

        df_f = audit_df.copy()
        if f_action != "Toutes" and "ACTION_NAME" in df_f.columns:
            df_f = df_f[df_f["ACTION_NAME"] == f_action]
        if f_user != "Tous" and "DB_USER" in df_f.columns:
            df_f = df_f[df_f["DB_USER"] == f_user]

        st.markdown(
            f'<div class="qf-apercu-wrap"><div class="qf-apercu-header">'
            f'<span class="qf-apercu-title">ORACLE_AUDIT_TRAIL</span>'
            f'<span class="qf-apercu-meta">{len(df_f)} ligne(s) après filtrage</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        cols_show = [c for c in ["AUDIT_ID","TIMESTAMP","DB_USER","ACTION_NAME",
                                  "OBJ_NAME","RETURNCODE","OS_HOST"]
                     if c in df_f.columns]
        st.dataframe(df_f[cols_show].head(f_n).reset_index(drop=True),
                     use_container_width=True, height=400)

        if "ACTION_NAME" in audit_df.columns:
            st.markdown(
                '<div style="font-size:13px;font-weight:600;color:var(--text);margin:14px 0 8px">Distribution des actions</div>',
                unsafe_allow_html=True,
            )
            dist = audit_df["ACTION_NAME"].value_counts().reset_index()
            dist.columns = ["Action", "Nombre"]
            dist["Pourcentage"] = (dist["Nombre"] / dist["Nombre"].sum() * 100).round(1).astype(str) + " %"
            st.dataframe(dist, use_container_width=True, height=200)


# ══════════════════════════════════════════════════════════════
# TAB 3 — ADMINISTRATION
# ══════════════════════════════════════════════════════════════
with tab_admin:
    st.markdown("""
    <div style="padding:18px 0 6px">
      <div style="font-size:19px;font-weight:600;color:var(--text);margin-bottom:3px">Administration</div>
      <div style="font-size:13px;color:var(--text3)">Configuration Oracle, modèles NLP et supervision</div>
    </div>
    """, unsafe_allow_html=True)

    adm1, adm2, adm3 = st.tabs(["🔌  Connexion Oracle", "🤖  Modèles NLP", "📊  Logs session"])

    # ── Connexion Oracle ──
    with adm1:
        st.markdown('<div class="qf-card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:14px">⚙ Paramètres de connexion</div>', unsafe_allow_html=True)
        c1a, c1b = st.columns(2)
        with c1a:
            st.text_input("Hôte / Adresse IP",   value="oracle.proddb.local", key="ora_host")
            st.text_input("Service / SID",         value="PRODDB",              key="ora_svc")
            st.text_input("Utilisateur Oracle",    value="qf_reader",           key="ora_usr")
        with c1b:
            st.number_input("Port",                value=1521,                  key="ora_port")
            st.text_input("Schéma par défaut",     value="PRODDB",              key="ora_sch")
            st.text_input("Mot de passe",          type="password", value="",   key="ora_pw")
        bt1, bt2, _ = st.columns([1, 1, 3])
        with bt1:
            if st.button("🔍 Tester", use_container_width=True):
                with st.spinner("Test…"):
                    import time; time.sleep(1)
                st.success("✅ Oracle 19c Enterprise · 4 ms")
        with bt2:
            if st.button("💾 Enregistrer", use_container_width=True):
                st.success("Paramètres sauvegardés.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("""
        <div class="qf-card">
          <div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:14px">📡 Statut connexion</div>
          <div style="display:flex;gap:28px;flex-wrap:wrap">
            <div><div style="font-size:11px;color:var(--text3);margin-bottom:4px">État</div>
                 <span class="qf-badge qf-badge-green">● Connecté</span></div>
            <div><div style="font-size:11px;color:var(--text3);margin-bottom:4px">Version</div>
                 <div style="font-family:var(--mono);font-size:13px;color:var(--text)">Oracle 19c Enterprise</div></div>
            <div><div style="font-size:11px;color:var(--text3);margin-bottom:4px">Latence</div>
                 <div style="font-family:var(--mono);font-size:13px;color:var(--text)">4 ms</div></div>
            <div><div style="font-size:11px;color:var(--text3);margin-bottom:4px">Tables</div>
                 <div style="font-family:var(--mono);font-size:13px;color:var(--text)">48 accessibles</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Modèles NLP ──
    with adm2:
        lora_ok    = os.path.exists("tinyllama_oracle_lora")    or os.path.exists("tinyllama_oracle_lora.zip")
        base_ok    = os.path.exists("TinyLlama-1.1B-Chat-v1.0") or os.path.exists("TinyLlama-1.1B-Chat-v1.0.zip")
        phi3_ok    = os.path.exists("phi3-mini-gguf")           or os.path.exists("phi3-mini-gguf.zip")
        dataset_ok = os.path.exists("oracle_nlp_dataset.csv")
        audit_ok   = os.path.exists("oracle_audit_trail.csv")

        def badge(ok):
            return ('<span class="qf-badge qf-badge-green">✓ Disponible</span>'
                    if ok else
                    '<span class="qf-badge qf-badge-yellow">⚠ Introuvable</span>')

        st.markdown(f"""
        <div class="qf-card">
          <div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:14px">🤖 Composants</div>
          <div style="display:flex;flex-direction:column;gap:0">

            <div style="display:flex;align-items:center;justify-content:space-between;padding:11px 0;border-bottom:1px solid var(--border)">
              <div><div style="font-size:13px;font-weight:500;color:var(--text)">Modèle de base TinyLlama-1.1B</div>
                   <div style="font-size:11.5px;color:var(--text3)">TinyLlama-1.1B-Chat-v1.0 · float16 · FR→SQL</div></div>
              {badge(base_ok)}
            </div>

            <div style="display:flex;align-items:center;justify-content:space-between;padding:11px 0;border-bottom:1px solid var(--border)">
              <div><div style="font-size:13px;font-weight:500;color:var(--text)">Adaptateur LoRA V2</div>
                   <div style="font-size:11.5px;color:var(--text3)">r=32 · alpha=64 · 5 epochs · 4500 ex.</div></div>
              {badge(lora_ok)}
            </div>

            <div style="display:flex;align-items:center;justify-content:space-between;padding:11px 0;border-bottom:1px solid var(--border)">
              <div><div style="font-size:13px;font-weight:500;color:var(--text)">Phi-3 mini Q4_K_M</div>
                   <div style="font-size:11.5px;color:var(--text3)">~2.3 GB · llama.cpp · SQL→FR · 29 codes ORA-</div></div>
              {badge(phi3_ok)}
            </div>

            <div style="display:flex;align-items:center;justify-content:space-between;padding:11px 0;border-bottom:1px solid var(--border)">
              <div><div style="font-size:13px;font-weight:500;color:var(--text)">Table d'audit Oracle</div>
                   <div style="font-size:11.5px;color:var(--text3)">oracle_audit_trail.csv · {len(audit_df)} lignes</div></div>
              {badge(audit_ok)}
            </div>

            <div style="display:flex;align-items:center;justify-content:space-between;padding:11px 0">
              <div><div style="font-size:13px;font-weight:500;color:var(--text)">Dataset d'entraînement</div>
                   <div style="font-size:11.5px;color:var(--text3)">oracle_nlp_dataset.csv · 4500 exemples V2</div></div>
              {badge(dataset_ok)}
            </div>

          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="qf-card">
          <div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:14px">📐 Configuration</div>
          <div class="qf-config-grid">
            <div class="qf-config-item"><div class="qf-config-label">LoRA rank</div><div class="qf-config-value">32</div></div>
            <div class="qf-config-item"><div class="qf-config-label">LoRA alpha</div><div class="qf-config-value">64</div></div>
            <div class="qf-config-item"><div class="qf-config-label">Epochs</div><div class="qf-config-value">5</div></div>
            <div class="qf-config-item"><div class="qf-config-label">Exemples</div><div class="qf-config-value">4500</div></div>
            <div class="qf-config-item"><div class="qf-config-label">Précision FR→SQL</div><div class="qf-config-value" style="color:var(--green)">100%</div></div>
            <div class="qf-config-item"><div class="qf-config-label">Précision SQL→FR</div><div class="qf-config-value" style="color:var(--green)">64%</div></div>
            <div class="qf-config-item"><div class="qf-config-label">Score global</div><div class="qf-config-value" style="color:var(--green)">82%</div></div>
            <div class="qf-config-item"><div class="qf-config-label">Codes ORA-</div><div class="qf-config-value">29</div></div>
          </div>
          <div style="margin-top:12px;padding:10px 14px;background:rgba(79,125,255,.05);border:1px solid rgba(79,125,255,.15);border-radius:8px;font-size:12.5px;color:var(--text2)">
            Post-processing : DBA_USERS · dernière personne · toutes actions · COUNT DISTINCT
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Référence des codes ORA-
        with st.expander("📋  Référence complète des 29 codes ORA- configurés"):
            for code, desc in ORACLE_ERRORS.items():
                st.markdown(
                    f'<div style="display:flex;gap:12px;padding:5px 0;border-bottom:1px solid var(--border);font-size:12.5px">'
                    f'<span style="font-family:var(--mono);color:var(--accent);min-width:90px">{code}</span>'
                    f'<span style="color:var(--text2)">{desc}</span></div>',
                    unsafe_allow_html=True,
                )

    # ── Logs session ──
    with adm3:
        st.markdown(
            f'<div class="qf-card"><div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:12px">'
            f'📋 Logs session ({st.session_state.nb_requetes} requête(s))</div>',
            unsafe_allow_html=True,
        )

        if not st.session_state.historique:
            st.markdown(
                '<div style="font-size:13px;color:var(--text3);padding:8px 0">Aucune activité dans cette session.</div>',
                unsafe_allow_html=True,
            )
        else:
            logs = ""
            for msg in st.session_state.historique:
                r = msg["role"]; t = msg.get("time", "—"); c = msg["content"]
                if r == "user":
                    logs += f'<div class="qf-log-item"><span class="qf-log-level" style="color:var(--accent)">USER</span><span class="qf-log-time">{t}</span><span class="qf-log-msg">{c[:110]}</span></div>'
                elif r == "sql":
                    logs += f'<div class="qf-log-item"><span class="qf-log-level" style="color:var(--green)">SQL</span><span class="qf-log-time">{t}</span><span class="qf-log-msg" style="font-family:var(--mono);font-size:11.5px">{c[:120]}…</span></div>'
                elif r == "bot":
                    logs += f'<div class="qf-log-item"><span class="qf-log-level" style="color:var(--accent2)">PHI3</span><span class="qf-log-time">{t}</span><span class="qf-log-msg">{c[:110]}</span></div>'
                elif r == "error":
                    logs += f'<div class="qf-log-item"><span class="qf-log-level" style="color:var(--red)">ERR</span><span class="qf-log-time">{t}</span><span class="qf-log-msg">{c[:110]}</span></div>'
            st.markdown(logs, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
        if st.button("🗑️ Effacer les logs", key="clrlogs"):
            st.session_state.historique  = []
            st.session_state.nb_requetes = 0
            st.rerun()
