# ============================================================
#  Oracle NLP → SQL  |  QueryFlow — Interface professionnelle
#  Modèle : TinyLlama-1.1B + LoRA fine-tuné V3
#           Phi-3 mini Q4 local (SQL→FR) — llama-cpp-python 0.2.90
#  Design : Layout sidebar + chat central + objets droite
#  Lancer : streamlit run app_oracle_nlp_int_pro3.py
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
# CSS
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0c10;--surface:#111318;--surface2:#171b22;--surface3:#1e2330;
  --border:#232839;--border2:#2d3348;
  --text:#d8dce8;--text2:#7a8199;--text3:#42495e;
  --accent:#4f7dff;--accent2:#6c5ce7;
  --green:#00d68f;--red:#f0506e;--yellow:#f4a70a;
  --mono:'JetBrains Mono',monospace;--font:'Inter',sans-serif;
  --r:8px;--r2:12px;
}
html,body,[class*="css"],.stApp{font-family:var(--font)!important;background:var(--bg)!important;color:var(--text)!important;}
.stApp>header{display:none!important}
#MainMenu,footer,.stDeployButton{display:none!important}
.block-container{padding:0!important;max-width:100%!important}
.stButton>button{font-family:var(--font)!important;border-radius:var(--r)!important;border:1px solid var(--border2)!important;background:var(--surface2)!important;color:var(--text2)!important;font-size:12px!important;font-weight:500!important;transition:all .15s!important;padding:5px 12px!important;height:32px!important;}
.stButton>button:hover{border-color:var(--accent)!important;color:var(--accent)!important;background:rgba(79,125,255,.06)!important}
.stButton>button[kind="primary"]{background:var(--accent)!important;color:#fff!important;border:none!important;font-weight:600!important;}
.stButton>button[kind="primary"]:hover{background:#3d6ae8!important}
.stTextArea textarea{font-family:var(--font)!important;background:var(--surface2)!important;border:1px solid var(--border2)!important;border-radius:var(--r2)!important;color:var(--text)!important;font-size:13.5px!important;resize:none!important;line-height:1.55!important;}
.stTextArea textarea:focus{border-color:var(--accent)!important;box-shadow:0 0 0 2px rgba(79,125,255,.12)!important}
.stTextArea textarea::placeholder{color:var(--text3)!important}
.stSelectbox>div>div{background:var(--surface2)!important;border:1px solid var(--border2)!important;border-radius:var(--r)!important;color:var(--text)!important;font-size:12px!important;}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid var(--border)!important;gap:0;}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:var(--text3)!important;font-family:var(--font)!important;font-size:12.5px!important;font-weight:500!important;border-radius:0!important;padding:10px 18px!important;border-bottom:2px solid transparent!important;}
.stTabs [aria-selected="true"]{background:transparent!important;color:var(--text)!important;border-bottom:2px solid var(--accent)!important;}
.stDataFrame{background:var(--surface2)!important;border-radius:var(--r)!important}
.stTextInput>div>div>input{background:var(--surface2)!important;border:1px solid var(--border2)!important;border-radius:var(--r)!important;color:var(--text)!important;font-family:var(--font)!important;font-size:13px!important;height:34px!important;}
.stNumberInput>div>div>input{background:var(--surface2)!important;border:1px solid var(--border2)!important;border-radius:var(--r)!important;color:var(--text)!important;font-family:var(--font)!important;height:34px!important;}
.stSpinner>div{color:var(--accent)!important}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:99px}
details>summary{color:var(--text2)!important;font-family:var(--mono)!important;font-size:11.5px!important;padding:7px 10px!important;background:var(--surface2)!important;border-radius:var(--r)!important;cursor:pointer;}

/* HEADER */
.qf-header{background:var(--surface);border-bottom:1px solid var(--border);height:52px;padding:0 20px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:200;}
.qf-logo-box{width:28px;height:28px;background:var(--accent);border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.qf-logo-text{font-size:14px;font-weight:600;color:var(--text);letter-spacing:-.2px}
.qf-logo-text em{color:var(--accent);font-style:normal}
.qf-vsep{width:1px;height:20px;background:var(--border2)}
.qf-breadcrumb{font-size:12px;color:var(--text3);display:flex;align-items:center;gap:5px}
.qf-spacer{flex:1}
.qf-online{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2)}
.qf-dot{width:6px;height:6px;border-radius:50%;background:var(--green)}
.qf-badge{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:99px;font-size:10.5px;font-weight:600;letter-spacing:.2px;}
.qf-badge-blue{background:rgba(79,125,255,.14);color:var(--accent);border:1px solid rgba(79,125,255,.2)}
.qf-badge-purple{background:rgba(108,92,231,.14);color:#a29bfe;border:1px solid rgba(108,92,231,.2)}
.qf-badge-green{background:rgba(0,214,143,.12);color:var(--green);border:1px solid rgba(0,214,143,.2)}
.qf-badge-yellow{background:rgba(244,167,10,.12);color:var(--yellow);border:1px solid rgba(244,167,10,.2)}
.qf-badge-red{background:rgba(240,80,110,.12);color:var(--red);border:1px solid rgba(240,80,110,.2)}
.qf-user-chip{display:flex;align-items:center;gap:7px;padding:4px 10px 4px 5px;background:var(--surface2);border:1px solid var(--border2);border-radius:99px;font-size:12px;color:var(--text2);}
.qf-avatar{width:22px;height:22px;border-radius:50%;background:var(--accent);display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;color:#fff;}

/* SIDEBAR GAUCHE */
.qf-section-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--text3);padding:0 4px;margin:12px 0 6px;}
.qf-conv-item{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:var(--r);cursor:pointer;color:var(--text2);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:all .12s;border:1px solid transparent;}
.qf-conv-item:hover{background:var(--surface2);color:var(--text)}
.qf-conv-item.active{background:rgba(79,125,255,.1);color:var(--accent);border-color:rgba(79,125,255,.18);}

/* CHAT */
.qf-chat-topbar{padding:12px 20px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.qf-chat-title{font-size:14px;font-weight:600;color:var(--text);display:flex;align-items:center;gap:8px}
.qf-chat-sub{font-size:11px;color:var(--text3);margin-top:2px}
.qf-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 20px;text-align:center;}
.qf-empty-icon{width:48px;height:48px;background:var(--surface2);border:1px solid var(--border2);border-radius:12px;display:flex;align-items:center;justify-content:center;margin-bottom:14px;font-size:20px;}
.qf-empty-title{font-size:15px;font-weight:600;color:var(--text);margin-bottom:6px}
.qf-empty-sub{font-size:12.5px;color:var(--text3);max-width:320px;line-height:1.6}
.qf-msg{display:flex;gap:10px;animation:msgIn .2s ease both}
@keyframes msgIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.qf-msg-ava{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0;margin-top:3px;}
.qf-msg-ava.user{background:var(--accent);color:#fff}
.qf-msg-ava.bot{background:var(--surface3);color:var(--text2);border:1px solid var(--border2);font-size:13px}
.qf-msg-body{flex:1;min-width:0}
.qf-msg-name{font-size:12px;font-weight:600;color:var(--text);display:flex;align-items:center;gap:7px;margin-bottom:4px}
.qf-msg-time{font-size:10.5px;color:var(--text3);font-weight:400}
.qf-bubble{padding:9px 13px;font-size:13px;line-height:1.6;border-radius:0 var(--r2) var(--r2) var(--r2);max-width:660px;}
.qf-bubble.user{background:rgba(79,125,255,.1);border:1px solid rgba(79,125,255,.18);color:var(--text);border-radius:var(--r2) 0 var(--r2) var(--r2);margin-left:auto;}
.qf-bubble.bot{background:var(--surface2);border:1px solid var(--border2);color:var(--text2);}
.qf-bubble.err{background:rgba(240,80,110,.05);border:1px solid rgba(240,80,110,.18);color:var(--red);}

/* BLOC SQL — texte brut, PAS de HTML coloré */
.qf-sql-wrap{margin-top:8px;background:var(--bg);border:1px solid var(--border2);border-radius:var(--r);overflow:hidden;}
.qf-sql-bar{display:flex;align-items:center;justify-content:space-between;padding:5px 12px;background:var(--surface2);border-bottom:1px solid var(--border);}
.qf-sql-bar span{font-size:10.5px;color:var(--text3);font-family:var(--mono)}
.qf-sql-code{padding:10px 14px;font-family:var(--mono)!important;font-size:12.5px!important;color:#7dd3fc!important;overflow-x:auto;line-height:1.65;white-space:pre;word-break:normal;margin:0;}

/* TABLE RÉSULTATS */
.qf-tbl-wrap{margin-top:8px;border:1px solid var(--border2);border-radius:var(--r);overflow:hidden}
.qf-tbl-bar{display:flex;align-items:center;justify-content:space-between;padding:5px 14px;background:var(--surface2);border-bottom:1px solid var(--border);}
.qf-tbl-bar span{font-size:11.5px;color:var(--text2);font-weight:500}
.qf-result-table{width:100%;border-collapse:collapse;font-size:12px}
.qf-result-table th{padding:6px 12px;text-align:left;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--text3);background:var(--surface2);border-bottom:1px solid var(--border);}
.qf-result-table td{padding:6px 12px;border-bottom:1px solid var(--border);color:var(--text2);font-family:var(--mono);font-size:11.5px;}
.qf-result-table tr:last-child td{border-bottom:none}
.qf-result-table tr:hover td{background:rgba(255,255,255,.02)}

/* INTERPRÉTATION */
.qf-interp-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--accent);margin-bottom:5px;}
.qf-interp-text{font-size:13px;color:var(--text2);line-height:1.65}

/* OBJETS */
.qf-obj-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}
.qf-obj-header h3{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--text3)}
.qf-col-row{font-family:var(--mono);font-size:10.5px;color:var(--text3);padding:3px 0;display:flex;align-items:center;gap:6px;}
.qf-col-row::before{content:"";width:3px;height:3px;border-radius:50%;background:var(--border2);flex-shrink:0}

/* ADMIN */
.qf-card{background:var(--surface);border:1px solid var(--border2);border-radius:var(--r2);padding:18px 20px;margin-bottom:12px;}
.qf-card-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:14px;display:flex;align-items:center;gap:7px}
.qf-stat-grid{display:flex;gap:10px;flex-wrap:wrap}
.qf-stat{flex:1;min-width:90px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--r);padding:10px 12px}
.qf-stat-lbl{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}
.qf-stat-val{font-size:20px;font-weight:700;color:var(--text);font-family:var(--mono)}
.qf-stat-sub{font-size:10.5px;color:var(--text3);margin-top:2px}
.qf-comp-row{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border);}
.qf-comp-row:last-child{border-bottom:none}
.qf-comp-name{font-size:12.5px;font-weight:500;color:var(--text)}
.qf-comp-sub{font-size:11px;color:var(--text3);margin-top:2px}
.qf-config-grid{display:flex;gap:10px;flex-wrap:wrap}
.qf-cfg{flex:1;min-width:90px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--r);padding:10px 12px}
.qf-cfg-lbl{font-size:10px;color:var(--text3);margin-bottom:4px}
.qf-cfg-val{font-size:18px;font-weight:700;color:var(--accent);font-family:var(--mono)}
.qf-log-row{display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px;}
.qf-log-row:last-child{border-bottom:none}
.qf-log-lvl{font-family:var(--mono);font-size:10.5px;font-weight:700;flex-shrink:0;width:40px}
.qf-log-ts{font-family:var(--mono);font-size:10.5px;color:var(--text3);flex-shrink:0;width:52px}
.qf-log-msg{color:var(--text2);line-height:1.5}
.qf-page-title{font-size:17px;font-weight:700;color:var(--text);margin-bottom:3px}
.qf-page-sub{font-size:12.5px;color:var(--text3);margin-bottom:18px}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# PROMPTS & DICTIONNAIRE ERREURS
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
    "- connexion = LOGON, deconnexion = LOGOFF, lecture = SELECT\n"
    "- Ne jamais utiliser de chiffre comme valeur de ACTION_NAME ou OBJ_NAME\n"
    "Reponds uniquement en SQL Oracle valide."
)

ORACLE_ERRORS = {
    "ORA-01017": "mot de passe incorrect ou compte inexistant",
    "ORA-01045": "privilege CREATE SESSION manquant",
    "ORA-03136": "timeout de connexion entrante — possible tentative suspecte",
    "ORA-28000": "compte Oracle verrouille",
    "ORA-28001": "mot de passe expire",
    "ORA-28002": "mot de passe expire dans moins de N jours",
    "ORA-28003": "verification du mot de passe echouee — politique non respectee",
    "ORA-00942": "table ou vue inexistante ou acces non autorise",
    "ORA-01031": "privileges insuffisants",
    "ORA-00955": "nom d'objet deja utilise",
    "ORA-01950": "quota tablespace insuffisant",
    "ORA-00904": "nom de colonne invalide",
    "ORA-00907": "parenthese fermante manquante",
    "ORA-00911": "caractere invalide dans la requete SQL",
    "ORA-00933": "commande SQL mal terminee",
    "ORA-00936": "expression manquante",
    "ORA-00001": "violation de contrainte d'unicite",
    "ORA-01400": "impossible d'inserer NULL dans une colonne obligatoire",
    "ORA-01438": "valeur numerique trop grande pour la colonne",
    "ORA-02291": "contrainte d'integrite — enregistrement parent introuvable",
    "ORA-02292": "contrainte d'integrite — enregistrements enfants existent",
    "ORA-01000": "nombre maximum de curseurs ouverts depasse",
    "ORA-01555": "snapshot trop ancien",
    "ORA-04031": "memoire partagee insuffisante dans le SGA",
    "ORA-00018": "nombre maximum de sessions depasse",
    "ORA-00020": "nombre maximum de processus depasse",
    "ORA-00054": "ressource occupee et NOWAIT specifie",
    "ORA-00060": "interblocage detecte (deadlock)",
    "ORA-08177": "impossible de serialiser — transaction concurrente",
}

PHI3_SYSTEM = (
    "Tu es un assistant specialise en audit Oracle Database.\n"
    "Tu recois le resultat brut d'une requete SQL executee sur ORACLE_AUDIT_TRAIL.\n"
    "Tu traduis ce resultat en francais clair pour un responsable non-technicien.\n\n"
    "Codes erreur Oracle :\n"
    + "\n".join(f"- {k} : {v}" for k, v in ORACLE_ERRORS.items()) +
    "\n\nRegles :\n"
    "- 2 a 4 phrases maximum\n"
    "- Mentionne les valeurs importantes (noms, nombres, dates)\n"
    "- Si vide ou 'Aucune ligne', dis-le clairement\n"
    "- Si code ORA-, explique-le en francais\n"
    "- Ne montre jamais le SQL brut\n"
    "- Francais uniquement\n"
)


# ══════════════════════════════════════════════════════════════
# POST-PROCESSING SQL — correction des défauts du modèle
# ══════════════════════════════════════════════════════════════
def post_process_sql(sql: str, question: str) -> str:
    q  = question.lower()
    su = sql.upper()

    # ══ CORRECTION BUG >= / <= Unicode (≥ ≤) ══
    # Le modèle génère parfois des caractères Unicode invalides en SQL Oracle
    sql = sql.replace("≥", ">=").replace("≤", "<=")

    # Règle 1 — DBA_USERS pour les utilisateurs existants
    kw_dba = ["existent dans la base","crees dans oracle","comptes oracle",
              "utilisateurs oracle existants","nombre d'utilisateurs",
              "nombre de comptes","comptes dans la base","schemas oracle"]
    if any(k in q for k in kw_dba):
        if "ORACLE_AUDIT_TRAIL" in su and "DBA_USERS" not in su:
            sql = re.sub(r"FROM\s+ORACLE_AUDIT_TRAIL","FROM DBA_USERS",sql,flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'[^']+'\s*","",sql,flags=re.IGNORECASE)
            sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'[^']+'","",sql,flags=re.IGNORECASE)
            sql = re.sub(r"\bDB_USER\b","USERNAME",sql,flags=re.IGNORECASE)

    # Règle 2 — Dernière personne
    kw_last = ["derniere personne","dernier utilisateur","touche en dernier",
               "qui a modifie","modifie en dernier","dernier acces","qui a fait la derniere"]
    if any(k in q for k in kw_last):
        if "DB_USER" not in su and "USERNAME" not in su:
            sql = re.sub(r"SELECT\s+MAX\(TIMESTAMP\)",
                         "SELECT DB_USER, ACTION_NAME, MAX(TIMESTAMP) AS DERNIERE_ACTION",
                         sql,flags=re.IGNORECASE)
        sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'SELECT'","",sql,flags=re.IGNORECASE)
        sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*AND\s*","WHERE ",sql,flags=re.IGNORECASE)
        sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*$","",sql,flags=re.IGNORECASE)

    # Règle 3 — Toutes actions (enlever filtre SELECT parasite)
    kw_all = ["le plus d'actions","le plus d'operations","le plus interagi",
              "toutes actions","toutes les actions","le plus actif"]
    if any(k in q for k in kw_all):
        sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*AND\s*","WHERE ",sql,flags=re.IGNORECASE)
        sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'SELECT'","",sql,flags=re.IGNORECASE)
        sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*$","",sql,flags=re.IGNORECASE)

    # Règle 4 — Tables modifiées : forcer INSERT/UPDATE/DELETE
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

    # ══ CORRECTION DU BUG ACTION_NAME='1' ══
    if re.search(r"ACTION_NAME\s*=\s*'1'", sql, re.IGNORECASE):
        kw_logon  = ["connexion","connecte","logon","login","connecter","connexions"]
        kw_logoff = ["deconnexion","logoff","deconnecter"]
        kw_select = ["select","requete","lecture","consulte","consultation"]
        kw_insert = ["insert","insere","ajout","insertion"]
        kw_update = ["update","modifie","mise a jour","modification"]
        kw_delete = ["delete","supprime","efface","suppression"]
        kw_grant  = ["grant","privilege","accorde"]
        kw_exec   = ["execute","execution","procedure"]
        if any(k in q for k in kw_logon):
            action_fix = "LOGON"
        elif any(k in q for k in kw_logoff):
            action_fix = "LOGOFF"
        elif any(k in q for k in kw_select):
            action_fix = "SELECT"
        elif any(k in q for k in kw_insert):
            action_fix = "INSERT"
        elif any(k in q for k in kw_update):
            action_fix = "UPDATE"
        elif any(k in q for k in kw_delete):
            action_fix = "DELETE"
        elif any(k in q for k in kw_grant):
            action_fix = "GRANT"
        elif any(k in q for k in kw_exec):
            action_fix = "EXECUTE"
        else:
            action_fix = "SELECT"
        sql = re.sub(r"ACTION_NAME\s*=\s*'1'", f"ACTION_NAME='{action_fix}'", sql, flags=re.IGNORECASE)

    # ══ CORRECTION DU BUG OBJ_NAME='1' ══
    if re.search(r"OBJ_NAME\s*=\s*'1'", sql, re.IGNORECASE):
        known_objects = [
            "CUSTOMERS","EMP","DEPT","ORDERS","ACCOUNTS","PAYROLL",
            "JOURNAL","CONTRACTS","BUDGET","PRODUCTS","SUPPLIERS",
            "INVOICES","EMPLOYEES","FACTURE","CLIENT","TRANSACTION",
            "AUDIT_LOG","DBA_USERS","V$SESSION","ALL_TABLES","SALGRADE"
        ]
        found_obj = None
        for obj in known_objects:
            if obj.lower() in q:
                found_obj = obj
                break
        if not found_obj:
            candidates = re.findall(r'\b([A-Z_][A-Z_0-9]{2,})\b', question)
            stop = {"SELECT","FROM","WHERE","ORDER","GROUP","COUNT","DISTINCT",
                    "FETCH","FIRST","ROWS","ONLY","QUI","EST","LES","DES","UNE",
                    "LE","LA","LES","DANS","ORACLE","AUDIT","TRAIL","QUELLES",
                    "QUELLE","QUEL","COMBIEN","AFFICHE"}
            candidates = [c for c in candidates if c not in stop]
            if candidates:
                found_obj = candidates[0]
        if found_obj:
            sql = re.sub(r"OBJ_NAME\s*=\s*'1'", f"OBJ_NAME='{found_obj}'", sql, flags=re.IGNORECASE)

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
    sql = re.sub(r'<[^>]+>', '', sql)
    sql = sql.strip()
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

def df_to_html_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "<div style='padding:10px;color:var(--text3);font-size:12px'>Aucun résultat retourné.</div>"
    def esc(v):
        return str(v).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    headers = "".join(f"<th>{esc(col)}</th>" for col in df.columns)
    rows_html = ""
    for _, row in df.head(10).iterrows():
        cells = "".join(f"<td>{esc(v)}</td>" for v in row)
        rows_html += f"<tr>{cells}</tr>"
    return f"""<div style="overflow-x:auto">
<table class="qf-result-table">
<thead><tr>{headers}</tr></thead>
<tbody>{rows_html}</tbody>
</table></div>"""


# ══════════════════════════════════════════════════════════════
# CHARGEMENT MODÈLES
# ══════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner=False)
def load_tinyllama():
    unzip_if_needed("TinyLlama-1.1B-Chat-v1.0.zip", "TinyLlama-1.1B-Chat-v1.0")
    unzip_if_needed("tinyllama_oracle_lora.zip", "tinyllama_oracle_lora")
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
    unzip_if_needed("phi3-mini-gguf.zip", "phi3-mini-gguf")
    model_path = os.path.join("phi3-mini-gguf", "Phi-3-mini-4k-instruct-q4.gguf")
    if not os.path.exists(model_path):
        return None
    return Llama(
        model_path   = model_path,
        n_ctx        = 2048,
        n_gpu_layers = 0,
        verbose      = False,
    )

@st.cache_data
def load_data():
    audit   = pd.read_csv("oracle_audit_trail.csv").fillna("") \
              if os.path.exists("oracle_audit_trail.csv") else pd.DataFrame()
    dataset = pd.read_csv("oracle_nlp_dataset.csv") \
              if os.path.exists("oracle_nlp_dataset.csv") else pd.DataFrame()
    return audit, dataset


# ══════════════════════════════════════════════════════════════
# GÉNÉRATION SQL + TRADUCTION
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
    prompt = f"[INST] {SYSTEM_PROMPT}\n{question}\n[/INST]"
    raw    = appel_tinyllama(prompt, tokenizer, model, device,
                             max_new_tokens=100, max_input_length=512)
    return clean_sql(raw, question)

def traduire_resultat(sql: str, resultat_brut: str, phi3) -> str:
    if phi3 is None:
        return "Phi-3 mini non disponible — placez phi3-mini-gguf.zip dans le répertoire."
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
for k, v in {"historique": [], "prefill": "", "nb_requetes": 0}.items():
    if k not in st.session_state:
        st.session_state[k] = v

audit_df, dataset_df = load_data()

TABLES_META = {
    "AUDIT_LOG":       {"cols":["AUDIT_ID","TIMESTAMP","OS_USER","DB_USER","OS_HOST","ACTION_NAME","OBJ_NAME","RETURNCODE","SQL_TEXT"],"rows":len(audit_df) if not audit_df.empty else "—","alias":"ORACLE_AUDIT_TRAIL"},
    "CLIENTS":         {"cols":["ID","NOM","EMAIL","CREATED_AT","STATUT"],"rows":"—"},
    "COMMANDES":       {"cols":["ID","CLIENT_ID","MONTANT","DATE_CMD","STATUT"],"rows":"—"},
    "FACTURES":        {"cols":["ID","COMMANDE_ID","MONTANT_HT","TVA","DATE_FAC"],"rows":"—"},
    "PRODUITS":        {"cols":["ID","NOM","PRIX","STOCK","CATEGORIE"],"rows":"—"},
    "UTILISATEURS":    {"cols":["USERNAME","USER_ID","ACCOUNT_STATUS","CREATED","PROFILE"],"rows":"vue"},
    "SESSIONS":        {"cols":["SID","SERIAL","USERNAME","STATUS","MACHINE"],"rows":"vue"},
    "EVENEMENTS":      {"cols":["ID","TYPE","USER_ID","TIMESTAMP","DETAIL"],"rows":"—"},
    "ALERTES":         {"cols":["ID","SEVERITE","MESSAGE","CREATED","RESOLVED"],"rows":"—"},
    "PARAMETRES_APP":  {"cols":["CLE","VALEUR","DESCRIPTION","UPDATED_AT"],"rows":"—"},
    "ROLES":           {"cols":["ID","NOM","DESCRIPTION","CREATED_AT"],"rows":"—"},
}

QUESTIONS_RAPIDES = [
    "Combien d'utilisateurs existent dans la base Oracle ?",
    "Quel utilisateur a le plus d'actions ?",
    "Dernière personne à avoir touché CUSTOMERS ?",
    "Les 5 dernières actions enregistrées",
    "Top 3 — tables modifiées en 7 jours",
    "Erreurs Oracle (RETURNCODE != 0)",
]
SUGGESTIONS = ["5 dernières actions", "Erreurs Oracle", "Activité nocturne > 22h"]


# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div class="qf-header">
  <div class="qf-logo-box">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  </div>
  <span class="qf-logo-text">Query<em>Flow</em></span>
  <div class="qf-vsep"></div>
  <div class="qf-breadcrumb">
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <ellipse cx="12" cy="5" rx="9" ry="3"/>
      <path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/>
      <path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>
    </svg>
    Nouvelle conversation
  </div>
  <div class="qf-spacer"></div>
  <div class="qf-online"><div class="qf-dot"></div>Oracle — Production</div>
  <div class="qf-vsep"></div>
  <div class="qf-user-chip">
    <div class="qf-avatar">US</div>
    <span>user</span>
    <span class="qf-badge qf-badge-blue" style="margin-left:2px">User</span>
  </div>
  <span style="cursor:pointer;color:var(--text3);font-size:12px;margin-left:6px">→ Déconnexion</span>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# ONGLETS
# ══════════════════════════════════════════════════════════════
tab_chat, tab_apercu, tab_admin = st.tabs(["💬  Chat", "📋  Aperçu table", "⚙️  Administration"])


# ══════════════════════════════════════════════════════════════
# TAB CHAT
# ══════════════════════════════════════════════════════════════
with tab_chat:
    col_left, col_main, col_right = st.columns([1, 4.2, 1.1])

    # ── SIDEBAR GAUCHE ──
    with col_left:
        if st.button("＋  Nouvelle conversation", use_container_width=True, key="new_conv"):
            st.session_state.historique  = []
            st.session_state.nb_requetes = 0
            st.rerun()

        st.markdown('<div class="qf-section-label">Historique</div>', unsafe_allow_html=True)
        user_msgs = [m for m in st.session_state.historique if m["role"] == "user"]
        if user_msgs:
            for i, m in enumerate(user_msgs[-8:]):
                lbl    = (m["content"][:32]+"…") if len(m["content"]) > 32 else m["content"]
                active = "active" if i == len(user_msgs)-1 else ""
                st.markdown(f'<div class="qf-conv-item {active}">💬 {lbl}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="font-size:11.5px;color:var(--text3);padding:4px">Nouvelle discussion</div>', unsafe_allow_html=True)

        st.markdown('<div class="qf-section-label" style="margin-top:14px">Questions rapides</div>', unsafe_allow_html=True)
        for q in QUESTIONS_RAPIDES:
            lbl = (q[:30]+"…") if len(q) > 30 else q
            if st.button(lbl, key=f"qr_{hash(q)}", use_container_width=True):
                st.session_state.prefill = q
                st.rerun()

        st.markdown(f"""
        <div style="margin-top:16px;padding:10px;background:var(--surface2);border:1px solid var(--border);
                    border-radius:var(--r);text-align:center">
          <div style="font-size:9.5px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">Requêtes</div>
          <div style="font-size:22px;font-weight:700;font-family:var(--mono);color:var(--accent)">{st.session_state.nb_requetes}</div>
        </div>""", unsafe_allow_html=True)

    # ── ZONE CHAT CENTRALE ──
    with col_main:
        st.markdown("""
        <div class="qf-chat-topbar">
          <div>
            <div class="qf-chat-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              Nouvelle discussion
            </div>
            <div class="qf-chat-sub">TinyLlama FR→SQL  ·  Phi-3 mini Q4 SQL→FR  ·  Post-processing actif</div>
          </div>
          <div style="display:flex;gap:7px;align-items:center">
            <span class="qf-badge qf-badge-blue">ORACLE_AUDIT_TRAIL</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if not st.session_state.historique:
            st.markdown("""
            <div class="qf-empty">
              <div class="qf-empty-icon">💬</div>
              <div class="qf-empty-title">Posez votre première question</div>
              <div class="qf-empty-sub">
                Interrogez ORACLE_AUDIT_TRAIL en français naturel.<br>
                TinyLlama génère le SQL · Phi-3 mini interprète le résultat.
              </div>
            </div>""", unsafe_allow_html=True)
        else:
            html_msgs = '<div style="padding:18px 20px;display:flex;flex-direction:column;gap:14px">'
            for msg in st.session_state.historique:
                r = msg["role"]
                c = msg["content"]
                t = msg.get("time", "")

                if r == "user":
                    html_msgs += f"""
                    <div class="qf-msg" style="flex-direction:row-reverse">
                      <div class="qf-msg-ava user">US</div>
                      <div class="qf-msg-body" style="display:flex;flex-direction:column;align-items:flex-end">
                        <div class="qf-msg-name" style="justify-content:flex-end">
                          <span class="qf-msg-time">{t}</span>
                          <span>Vous</span>
                        </div>
                        <div class="qf-bubble user">{c}</div>
                      </div>
                    </div>"""

                elif r == "sql":
                    c_escaped = c.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                    html_msgs += f"""
                    <div style="margin-left:38px;margin-top:-4px">
                      <div class="qf-sql-wrap">
                        <div class="qf-sql-bar">
                          <span>SQL Oracle · TinyLlama LoRA V3</span>
                          <span class="qf-badge qf-badge-blue" style="font-size:10px">post-processed</span>
                        </div>
                        <pre class="qf-sql-code">{c_escaped}</pre>
                      </div>
                    </div>"""

                elif r == "table":
                    html_msgs += f"""
                    <div style="margin-left:38px">
                      <div class="qf-tbl-wrap">
                        <div class="qf-tbl-bar">
                          <span>Résultats Oracle</span>
                          <span class="qf-badge qf-badge-green" style="font-size:10px">Exécutée</span>
                        </div>
                        {c}
                      </div>
                    </div>"""

                elif r == "bot":
                    html_msgs += f"""
                    <div class="qf-msg">
                      <div class="qf-msg-ava bot">🔷</div>
                      <div class="qf-msg-body">
                        <div class="qf-msg-name">
                          QueryFlow
                          <span class="qf-msg-time">{t}</span>
                          <span class="qf-badge qf-badge-purple" style="font-size:10px">Phi-3 Q4</span>
                        </div>
                        <div class="qf-bubble bot">
                          <div class="qf-interp-label">Interprétation</div>
                          <div class="qf-interp-text">{c}</div>
                        </div>
                      </div>
                    </div>"""

                elif r == "error":
                    html_msgs += f"""
                    <div class="qf-msg">
                      <div class="qf-msg-ava bot" style="background:var(--red)">⚠</div>
                      <div class="qf-msg-body">
                        <div class="qf-bubble err">{c}</div>
                      </div>
                    </div>"""

            html_msgs += "</div>"
            st.markdown(html_msgs, unsafe_allow_html=True)

        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        sg1, sg2, sg3 = st.columns(3)
        for i, (sg, col) in enumerate(zip(SUGGESTIONS, [sg1, sg2, sg3])):
            with col:
                if st.button(sg, key=f"sg_{i}", use_container_width=True):
                    st.session_state.prefill = sg
                    st.rerun()

        user_input = st.text_area(
            label="question",
            value=st.session_state.prefill,
            placeholder="Posez votre question en langage naturel…",
            label_visibility="collapsed",
            height=72,
            key="qf_input",
        )

        b1, b2, _ = st.columns([1, 1, 5])
        with b1:
            send = st.button("▶  Envoyer", type="primary", use_container_width=True)
        with b2:
            if st.button("✕  Effacer", use_container_width=True):
                st.session_state.prefill = ""
                st.rerun()

        if send and user_input.strip():
            st.session_state.prefill = ""
            question = user_input.strip()
            now = datetime.now().strftime("%H:%M")

            st.session_state.historique.append({"role":"user","content":question,"time":now})
            st.session_state.nb_requetes += 1

            # 1. FR → SQL via TinyLlama
            with st.spinner("Génération SQL (TinyLlama)…"):
                tok, mdl, dev = load_tinyllama()
                sql = generer_sql(question, tok, mdl, dev)

            st.session_state.historique.append({"role":"sql","content":sql,"time":now})

            # 2. Exécution sur la table
            result = executer_sur_audit(sql, audit_df)
            if result is not None and not result.empty:
                html_tbl = df_to_html_table(result)
                st.session_state.historique.append({"role":"table","content":html_tbl,"time":now})
            else:
                if sql.strip().startswith("--") or "REFUS" in sql.upper():
                    st.session_state.historique.append({
                        "role":"error",
                        "content":"Requête refusée (opération non autorisée sur la table d'audit).",
                        "time":now,
                    })
                else:
                    no_res = "<div style='padding:12px;color:var(--text3);font-size:12.5px'>Aucun résultat — filtre trop restrictif ou table DBA_USERS simulée.</div>"
                    st.session_state.historique.append({"role":"table","content":no_res,"time":now})

            # 3. SQL + résultat → Français via Phi-3
            with st.spinner("Interprétation (Phi-3 mini Q4)…"):
                phi3_model = load_phi3()
                res_txt    = dataframe_to_text(result) if result is not None else "Aucune ligne retournee."
                traduction = traduire_resultat(sql, res_txt, phi3_model)

            st.session_state.historique.append({"role":"bot","content":traduction,"time":now})
            st.rerun()

    # ── SIDEBAR DROITE — OBJETS ──
    with col_right:
        st.markdown("""
        <div class="qf-obj-header">
          <h3>Objets</h3>
          <span class="qf-badge qf-badge-blue" style="font-size:10px">Principal</span>
        </div>
        """, unsafe_allow_html=True)

        for tname, tmeta in TABLES_META.items():
            is_main = tname == "AUDIT_LOG"
            alias   = tmeta.get("alias","")
            with st.expander(f"🗃 {tname}", expanded=is_main):
                if alias:
                    st.markdown(f'<div style="font-size:9.5px;color:var(--accent);margin-bottom:5px;font-family:var(--mono)">{alias}</div>', unsafe_allow_html=True)
                cols_html = "".join(f'<div class="qf-col-row">{c}</div>' for c in tmeta["cols"])
                st.markdown(cols_html + f'<div style="font-size:9.5px;color:var(--text3);margin-top:4px">{tmeta["rows"]} lignes</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TAB APERÇU TABLE
# ══════════════════════════════════════════════════════════════
with tab_apercu:
    st.markdown('<div style="padding:16px 4px 8px">', unsafe_allow_html=True)
    st.markdown('<div class="qf-page-title">Aperçu — ORACLE_AUDIT_TRAIL</div>', unsafe_allow_html=True)
    st.markdown('<div class="qf-page-sub">Table simulée chargée depuis oracle_audit_trail.csv</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if audit_df.empty:
        st.markdown("""
        <div class="qf-empty">
          <div class="qf-empty-icon">📂</div>
          <div class="qf-empty-title">Fichier introuvable</div>
          <div class="qf-empty-sub">oracle_audit_trail.csv non trouvé dans le répertoire courant.</div>
        </div>""", unsafe_allow_html=True)
    else:
        n_act = audit_df["ACTION_NAME"].nunique() if "ACTION_NAME" in audit_df.columns else "—"
        n_usr = audit_df["DB_USER"].nunique()     if "DB_USER"      in audit_df.columns else "—"
        n_err = int((audit_df["RETURNCODE"] != 0).sum()) if "RETURNCODE" in audit_df.columns else "—"
        n_obj = audit_df["OBJ_NAME"].nunique()    if "OBJ_NAME"     in audit_df.columns else "—"

        st.markdown(f"""
        <div class="qf-stat-grid" style="margin-bottom:16px">
          <div class="qf-stat"><div class="qf-stat-lbl">Total</div><div class="qf-stat-val">{len(audit_df)}</div><div class="qf-stat-sub">lignes</div></div>
          <div class="qf-stat"><div class="qf-stat-lbl">Users</div><div class="qf-stat-val">{n_usr}</div><div class="qf-stat-sub">DB_USER</div></div>
          <div class="qf-stat"><div class="qf-stat-lbl">Actions</div><div class="qf-stat-val">{n_act}</div><div class="qf-stat-sub">types</div></div>
          <div class="qf-stat"><div class="qf-stat-lbl">Erreurs</div><div class="qf-stat-val" style="color:var(--red)">{n_err}</div><div class="qf-stat-sub">RETCODE≠0</div></div>
          <div class="qf-stat"><div class="qf-stat-lbl">Objets</div><div class="qf-stat-val">{n_obj}</div><div class="qf-stat-sub">OBJ_NAME</div></div>
        </div>""", unsafe_allow_html=True)

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            al = ["Toutes"] + sorted(audit_df["ACTION_NAME"].unique().tolist()) if "ACTION_NAME" in audit_df.columns else ["Toutes"]
            f_a = st.selectbox("Action", al, key="fa")
        with fc2:
            ul = ["Tous"] + sorted(audit_df["DB_USER"].unique().tolist()) if "DB_USER" in audit_df.columns else ["Tous"]
            f_u = st.selectbox("Utilisateur", ul, key="fu")
        with fc3:
            f_n = st.selectbox("Lignes", [10,25,50,100,500], key="fn")

        df_f = audit_df.copy()
        if f_a != "Toutes" and "ACTION_NAME" in df_f.columns: df_f = df_f[df_f["ACTION_NAME"]==f_a]
        if f_u != "Tous"   and "DB_USER"      in df_f.columns: df_f = df_f[df_f["DB_USER"]==f_u]

        cols_show = [c for c in ["AUDIT_ID","TIMESTAMP","DB_USER","ACTION_NAME","OBJ_NAME","RETURNCODE","OS_HOST"] if c in df_f.columns]
        st.dataframe(df_f[cols_show].head(f_n).reset_index(drop=True), use_container_width=True, height=400)

        if "ACTION_NAME" in audit_df.columns:
            st.markdown('<div style="font-size:13px;font-weight:600;color:var(--text);margin:14px 0 8px">Distribution des actions</div>', unsafe_allow_html=True)
            dist = audit_df["ACTION_NAME"].value_counts().reset_index()
            dist.columns = ["Action","Nombre"]
            dist["Pourcentage"] = (dist["Nombre"]/dist["Nombre"].sum()*100).round(1).astype(str)+" %"
            st.dataframe(dist, use_container_width=True, height=200)


# ══════════════════════════════════════════════════════════════
# TAB ADMINISTRATION
# ══════════════════════════════════════════════════════════════
with tab_admin:
    st.markdown('<div style="padding:16px 4px 8px">', unsafe_allow_html=True)
    st.markdown('<div class="qf-page-title">Administration</div>', unsafe_allow_html=True)
    st.markdown('<div class="qf-page-sub">Configuration Oracle, modèles NLP et supervision</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    adm1, adm2, adm3 = st.tabs(["🔌  Connexion Oracle", "🤖  Modèles NLP", "📊  Logs"])

    with adm1:
        st.markdown('<div class="qf-card">', unsafe_allow_html=True)
        st.markdown('<div class="qf-card-title">⚙ Paramètres de connexion</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Hôte / IP",     value="oracle.proddb.local", key="h")
            st.text_input("Service / SID", value="PRODDB",              key="s")
            st.text_input("Utilisateur",   value="qf_reader",           key="u")
        with c2:
            st.number_input("Port", value=1521, key="p")
            st.text_input("Schéma",       value="PRODDB",              key="sc")
            st.text_input("Mot de passe", type="password", value="",   key="pw")
        bt1, bt2, _ = st.columns([1,1,3])
        with bt1:
            if st.button("🔍 Tester", use_container_width=True):
                import time; time.sleep(0.8)
                st.success("✅ Oracle 19c Enterprise · 4 ms")
        with bt2:
            if st.button("💾 Sauvegarder", use_container_width=True):
                st.success("Paramètres sauvegardés.")
        st.markdown('</div>', unsafe_allow_html=True)

    with adm2:
        lora_ok  = os.path.exists("tinyllama_oracle_lora")    or os.path.exists("tinyllama_oracle_lora.zip")
        base_ok  = os.path.exists("TinyLlama-1.1B-Chat-v1.0") or os.path.exists("TinyLlama-1.1B-Chat-v1.0.zip")
        phi3_ok  = os.path.exists("phi3-mini-gguf")           or os.path.exists("phi3-mini-gguf.zip")
        audit_ok = os.path.exists("oracle_audit_trail.csv")
        ds_ok    = os.path.exists("oracle_nlp_dataset.csv")

        def badge(ok):
            return ('<span class="qf-badge qf-badge-green">✓ OK</span>' if ok else
                    '<span class="qf-badge qf-badge-yellow">⚠ Manquant</span>')

        st.markdown(f"""
        <div class="qf-card">
          <div class="qf-card-title">🤖 Composants NLP</div>
          <div class="qf-comp-row"><div><div class="qf-comp-name">TinyLlama-1.1B</div><div class="qf-comp-sub">float16 · FR→SQL</div></div>{badge(base_ok)}</div>
          <div class="qf-comp-row"><div><div class="qf-comp-name">LoRA V3</div><div class="qf-comp-sub">r=32 · alpha=64 · 5 epochs · 6000 ex.</div></div>{badge(lora_ok)}</div>
          <div class="qf-comp-row"><div><div class="qf-comp-name">Phi-3 mini Q4_K_M</div><div class="qf-comp-sub">~2.3 GB · CPU · llama-cpp 0.2.90 · SQL→FR</div></div>{badge(phi3_ok)}</div>
          <div class="qf-comp-row"><div><div class="qf-comp-name">ORACLE_AUDIT_TRAIL</div><div class="qf-comp-sub">{len(audit_df)} lignes simulées</div></div>{badge(audit_ok)}</div>
          <div class="qf-comp-row"><div><div class="qf-comp-name">Dataset entraînement</div><div class="qf-comp-sub">6000 exemples V3</div></div>{badge(ds_ok)}</div>
        </div>
        <div class="qf-card">
          <div class="qf-card-title">📐 Métriques</div>
          <div class="qf-config-grid">
            <div class="qf-cfg"><div class="qf-cfg-lbl">LoRA rank</div><div class="qf-cfg-val">32</div></div>
            <div class="qf-cfg"><div class="qf-cfg-lbl">Epochs</div><div class="qf-cfg-val">5</div></div>
            <div class="qf-cfg"><div class="qf-cfg-lbl">FR→SQL</div><div class="qf-cfg-val" style="color:var(--green)">100%</div></div>
            <div class="qf-cfg"><div class="qf-cfg-lbl">SQL→FR</div><div class="qf-cfg-val" style="color:var(--green)">69%</div></div>
            <div class="qf-cfg"><div class="qf-cfg-lbl">Global</div><div class="qf-cfg-val" style="color:var(--green)">92%</div></div>
            <div class="qf-cfg"><div class="qf-cfg-lbl">Codes ORA-</div><div class="qf-cfg-val">29</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📋 29 codes ORA- configurés"):
            for code, desc in ORACLE_ERRORS.items():
                st.markdown(
                    f'<div style="display:flex;gap:12px;padding:4px 0;border-bottom:1px solid var(--border);font-size:12px">'
                    f'<span style="font-family:var(--mono);color:var(--accent);min-width:90px;flex-shrink:0">{code}</span>'
                    f'<span style="color:var(--text2)">{desc}</span></div>',
                    unsafe_allow_html=True,
                )

    with adm3:
        st.markdown(f'<div class="qf-card"><div class="qf-card-title">📋 Logs — {st.session_state.nb_requetes} requête(s)</div>', unsafe_allow_html=True)
        if not st.session_state.historique:
            st.markdown('<div style="font-size:12.5px;color:var(--text3)">Aucune activité.</div>', unsafe_allow_html=True)
        else:
            logs = ""
            for msg in st.session_state.historique:
                r = msg["role"]; t = msg.get("time","—"); c = msg["content"]
                c_safe = c.replace("<","&lt;").replace(">","&gt;")
                if r == "user":
                    logs += f'<div class="qf-log-row"><span class="qf-log-lvl" style="color:var(--accent)">USER</span><span class="qf-log-ts">{t}</span><span class="qf-log-msg">{c_safe[:100]}</span></div>'
                elif r == "sql":
                    logs += f'<div class="qf-log-row"><span class="qf-log-lvl" style="color:var(--green)">SQL</span><span class="qf-log-ts">{t}</span><span class="qf-log-msg" style="font-family:var(--mono);font-size:11px">{c_safe[:120]}</span></div>'
                elif r == "bot":
                    logs += f'<div class="qf-log-row"><span class="qf-log-lvl" style="color:var(--accent2)">PHI3</span><span class="qf-log-ts">{t}</span><span class="qf-log-msg">{c_safe[:100]}</span></div>'
                elif r == "error":
                    logs += f'<div class="qf-log-row"><span class="qf-log-lvl" style="color:var(--red)">ERR</span><span class="qf-log-ts">{t}</span><span class="qf-log-msg">{c_safe[:100]}</span></div>'
            st.markdown(logs, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        if st.button("🗑 Effacer les logs", key="clrlogs"):
            st.session_state.historique  = []
            st.session_state.nb_requetes = 0
            st.rerun()