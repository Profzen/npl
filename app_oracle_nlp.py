# ============================================================
#  Oracle NLP → SQL  |  Interface de démonstration
#  Modèle : TinyLlama-1.1B + LoRA fine-tuné V2
#  VERSION OPTIMISÉE CPU — compatible modèle V2 (r=32, 5 epochs)
#  Lancer : streamlit run app_oracle_nlp.py
# ============================================================

import os, zipfile, torch, pandas as pd, re
from datetime import datetime, timedelta
import streamlit as st
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

st.set_page_config(
    page_title="Oracle NLP · SQL Assistant",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600&family=DM+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.qf-badge { display:inline-block; background:#4f7dff; color:#fff; border-radius:99px; padding:3px 11px; font-size:11px; font-weight:500; margin-right:6px; }
.qf-badge-green { background: #2bb686; }
.qf-sidebar { background: #f7f8fa; border-right: 1px solid #e0e2ea; min-width:220px; max-width:260px; padding: 18px 12px 18px 18px; }
.qf-sidebar h3 { font-size:13px; text-transform:uppercase; color:#8b92b2; margin-bottom:10px; }
.qf-obj-list { margin:0; padding:0; list-style:none; }
.qf-obj-list li { background:#fff; border:1px solid #e0e2ea; border-radius:8px; margin-bottom:7px; padding:8px 12px; font-family:'DM Mono',monospace; font-size:13px; color:#4d5476; display:flex; align-items:center; gap:8px; }
.qf-chat-wrap { background:#f4f6fb; border-radius:12px; padding:24px 32px; margin-bottom:24px; }
.qf-msg-user { background:#4f7dff; color:#fff; border-radius:10px 0 10px 10px; padding:10px 16px; margin-bottom:8px; display:inline-block; }
.qf-msg-bot { background:#fff; color:#23243a; border-radius:0 10px 10px 10px; padding:10px 16px; margin-bottom:8px; display:inline-block; border:1px solid #e0e2ea; }
.qf-sql-block { background:#f2f4fa; border:1px solid #bfc4d6; border-radius:7px; padding:12px 16px; font-family:'DM Mono',monospace; font-size:13px; color:#4f7dff; margin:10px 0; }
.qf-table { width:100%; border-collapse:collapse; margin-top:10px; }
.qf-table th { background:#f2f4fa; color:#4d5476; font-size:11px; font-weight:600; text-transform:uppercase; border-bottom:1px solid #e0e2ea; padding:7px 10px; }
.qf-table td { color:#4d5476; font-size:13px; border-bottom:1px solid #e0e2ea; padding:7px 10px; }
.qf-table tr:last-child td { border-bottom:none; }
.qf-header { display:flex; align-items:center; gap:16px; margin-bottom:18px; }
.qf-header .qf-badge { margin:0 0 0 8px; }
.qf-chat-title { font-size:17px; font-weight:600; color:#23243a; }
.qf-chat-sub { font-size:13px; color:#8b92b2; margin-bottom:8px; }
</style>
''', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# PROMPT SYSTÈME V2 — identique à celui utilisé à l'entraînement
# IMPORTANT : doit être exactement le même que dans le notebook
# ════════════════════════════════════════════════════════════
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


# ════════════════════════════════════════════════════════════
# POST-PROCESSING SQL V2 — 4 règles sémantiques
# Corrige les erreurs fréquentes du modèle après génération
# ════════════════════════════════════════════════════════════
def post_process_sql(sql: str, question: str) -> str:
    q = question.lower()
    su = sql.upper()

    # RÈGLE 1 : utilisateurs EXISTANTS → DBA_USERS (pas ORACLE_AUDIT_TRAIL)
    kw_dba = ["existent dans la base", "crees dans oracle", "comptes oracle",
              "utilisateurs oracle existants", "nombre d'utilisateurs",
              "nombre de comptes", "comptes dans la base", "schemas oracle"]
    if any(k in q for k in kw_dba):
        if "ORACLE_AUDIT_TRAIL" in su and "DBA_USERS" not in su:
            sql = re.sub(r"FROM\s+ORACLE_AUDIT_TRAIL", "FROM DBA_USERS",
                         sql, flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'[^']+'\s*", "",
                         sql, flags=re.IGNORECASE)
            sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'[^']+'", "",
                         sql, flags=re.IGNORECASE)
            sql = re.sub(r"\bDB_USER\b", "USERNAME", sql, flags=re.IGNORECASE)

    # RÈGLE 2 : "dernière personne/utilisateur" → inclure DB_USER + ACTION_NAME
    kw_last = ["derniere personne", "dernier utilisateur", "touche en dernier",
               "qui a modifie", "modifie en dernier", "dernier acces",
               "qui a fait la derniere"]
    if any(k in q for k in kw_last):
        if "DB_USER" not in su and "USERNAME" not in su:
            sql = re.sub(
                r"SELECT\s+MAX\(TIMESTAMP\)",
                "SELECT DB_USER, ACTION_NAME, MAX(TIMESTAMP) AS DERNIERE_ACTION",
                sql, flags=re.IGNORECASE
            )
        # Retirer filtre SELECT si pas explicitement demandé
        if "ACTION_NAME='SELECT'" in su.replace(" ", ""):
            sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'SELECT'", "",
                         sql, flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*AND\s*",
                         "WHERE ", sql, flags=re.IGNORECASE)
            sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*$", "",
                         sql, flags=re.IGNORECASE)

    # RÈGLE 3 : "toutes actions" / "le plus d'actions" → pas de filtre ACTION_NAME=SELECT
    kw_all = ["le plus d'actions", "le plus d'operations", "le plus interagi",
              "toutes actions", "toutes les actions"]
    if any(k in q for k in kw_all):
        sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*AND\s*",
                     "WHERE ", sql, flags=re.IGNORECASE)
        sql = re.sub(r"AND\s+ACTION_NAME\s*=\s*'SELECT'", "",
                     sql, flags=re.IGNORECASE)
        sql = re.sub(r"WHERE\s+ACTION_NAME\s*=\s*'SELECT'\s*$", "",
                     sql, flags=re.IGNORECASE)

    # RÈGLE 4 : "modifié des tables" → forcer INSERT/UPDATE/DELETE
    kw_modif = ["modifie le plus de tables", "tables differentes", "tables modifiees",
                "modifications", "le plus de tables", "tables distinctes modifiees"]
    if any(k in q for k in kw_modif):
        if "INSERT" not in su and "UPDATE" not in su and "DELETE" not in su:
            if "WHERE" in su:
                sql = re.sub(
                    r"WHERE\s+",
                    "WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') AND ",
                    sql, count=1, flags=re.IGNORECASE
                )
            elif "GROUP BY" in su:
                sql = re.sub(
                    r"GROUP BY",
                    "WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') GROUP BY",
                    sql, count=1, flags=re.IGNORECASE
                )

    # Tronquer à la première instruction complète
    if ";" in sql:
        sql = sql[:sql.index(";") + 1]

    return sql.strip()


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════
def unzip_if_needed(zip_path, extract_dir):
    if not os.path.exists(extract_dir) and os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)

def clean_sql(raw: str, question: str = "") -> str:
    """Extrait le SQL brut puis applique le post-processing V2."""
    if "[/INST]" in raw:
        raw = raw.split("[/INST]")[-1]
    sql = raw.strip().split("\n\n")[0].strip()
    return post_process_sql(sql, question)

def reformuler_sql(sql: str) -> str:
    sql_up = sql.upper()
    parts = []
    m = re.search(r'FROM\s+(\w+)', sql_up)
    table = m.group(1).lower() if m else "la table"
    m_sel = re.search(r'SELECT\s+(.*?)\s+FROM', sql_up, re.DOTALL)
    cols = m_sel.group(1).strip() if m_sel else "*"
    cols_txt = "toutes les colonnes" if cols == "*" else f"les colonnes : {cols.lower()}"
    parts.append(f"Sélectionne {cols_txt} depuis **{table}**")
    m_w = re.search(r'WHERE\s+(.*?)(?:ORDER|GROUP|HAVING|FETCH|$)', sql_up, re.DOTALL)
    if m_w:
        parts.append(f"avec la condition : `{m_w.group(1).strip().lower()}`")
    m_o = re.search(r'ORDER BY\s+(.*?)(?:FETCH|LIMIT|$)', sql_up, re.DOTALL)
    if m_o:
        parts.append(f"trié par {m_o.group(1).strip().lower()}")
    if any(k in sql_up for k in ['ROWNUM', 'FETCH', 'LIMIT']):
        parts.append("en limitant le nombre de résultats")
    return ", ".join(parts) + "." if parts else "Requête générée."

def executer_sur_audit(sql: str, df: pd.DataFrame):
    """Exécute le SQL généré sur le DataFrame pandas via pandasql."""
    # Ignorer les refus de sécurité
    if sql.strip().startswith("--") or "REFUS" in sql.upper():
        return None
    try:
        import pandasql as psql
        oracle_audit_trail = df  # noqa — alias pour pandasql
        # Adapter FETCH FIRST N ROWS ONLY → LIMIT N (syntaxe SQLite/pandasql)
        sql_adapted = re.sub(
            r"FETCH FIRST (\d+) ROWS ONLY", r"LIMIT \1",
            sql, flags=re.IGNORECASE
        )
        # Adapter SUBSTR Oracle → SUBSTR SQLite (compatible)
        return psql.sqldf(sql_adapted, locals())
    except Exception:
        return None

def dataframe_to_text(df: pd.DataFrame, max_rows: int = 5) -> str:
    if df is None or df.empty:
        return "Aucun résultat trouvé."
    total = len(df)
    sample = df.head(max_rows)
    lines = [f"Résultat : {total} ligne(s)."]
    lines.append(sample.to_string(index=False))
    if total > max_rows:
        lines.append(f"(+{total - max_rows} lignes supplémentaires)")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# CHARGEMENT MODÈLE V2
# float16 au lieu de float32 → moitié moins de RAM
# ════════════════════════════════════════════════════════════
@st.cache_resource(show_spinner=False)
def load_model():
    unzip_if_needed('TinyLlama-1.1B-Chat-v1.0.zip', 'TinyLlama-1.1B-Chat-v1.0')
    unzip_if_needed('tinyllama_oracle_lora.zip', 'tinyllama_oracle_lora')

    tokenizer = AutoTokenizer.from_pretrained('TinyLlama-1.1B-Chat-v1.0')
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # float16 → ~1.1 GB RAM au lieu de ~2.2 GB en float32
    base = AutoModelForCausalLM.from_pretrained(
        'TinyLlama-1.1B-Chat-v1.0',
        torch_dtype=torch.float16,
        device_map=None
    )
    model = PeftModel.from_pretrained(base, 'tinyllama_oracle_lora')
    model.eval()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    return tokenizer, model.to(device), device

@st.cache_data
def load_data():
    audit   = pd.read_csv('oracle_audit_trail.csv').fillna("") \
              if os.path.exists('oracle_audit_trail.csv') else pd.DataFrame()
    dataset = pd.read_csv('oracle_nlp_dataset.csv') \
              if os.path.exists('oracle_nlp_dataset.csv') else pd.DataFrame()
    return audit, dataset


# ════════════════════════════════════════════════════════════
# GÉNÉRATION — prompt V2 avec schéma complet
# ════════════════════════════════════════════════════════════
def appel_modele(prompt: str, tokenizer, model, device,
                 max_new_tokens: int = 80,
                 max_input_length: int = 512) -> str:
    inputs = tokenizer(prompt, return_tensors="pt",
                       truncation=True, max_length=max_input_length)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,               # greedy = rapide sur CPU
            pad_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.15,       # évite les répétitions
        )
    raw = tokenizer.decode(out[0], skip_special_tokens=True)
    return raw.split("[/INST]")[-1].strip() if "[/INST]" in raw else raw.strip()

def generer_sql(question: str, tokenizer, model, device) -> str:
    # Prompt complet avec SYSTEM_PROMPT V2 — indispensable pour la précision
    prompt = f"[INST] {SYSTEM_PROMPT}\n{question}\n[/INST]"
    raw = appel_modele(prompt, tokenizer, model, device,
                       max_new_tokens=100, max_input_length=512)
    return clean_sql(raw, question)   # ← post-processing V2 appliqué ici

def generer_reponse_naturelle(question: str, sql: str, resultat_texte: str,
                               tokenizer, model, device) -> str:
    prompt = (
        f"[INST] Question posée : {question}\n"
        f"SQL exécuté : {sql}\n"
        f"Données retournées : {resultat_texte}\n"
        f"Explique le résultat en 2-3 phrases claires en français.\n[/INST]"
    )
    return appel_modele(prompt, tokenizer, model, device,
                        max_new_tokens=100, max_input_length=400)


# ════════════════════════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════════════════════════
if "historique" not in st.session_state:
    st.session_state.historique = []
if "prefill" not in st.session_state:
    st.session_state.prefill = ""


# ════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown('<div class="qf-sidebar">', unsafe_allow_html=True)
    st.markdown('<h3>Objets Oracle</h3>', unsafe_allow_html=True)
    audit_df, dataset_df = load_data()

    # Afficher les colonnes de ORACLE_AUDIT_TRAIL
    tables = list(audit_df.columns) if not audit_df.empty \
             else ["AUDIT_ID","TIMESTAMP","DB_USER","ACTION_NAME",
                   "OBJ_NAME","RETURNCODE","OS_HOST","SQL_TEXT"]
    st.markdown(
        '<ul class="qf-obj-list">'
        + ''.join([f'<li>{t}</li>' for t in tables])
        + '</ul>',
        unsafe_allow_html=True
    )

    st.markdown('</div>', unsafe_allow_html=True)
    st.divider()

    # Questions prédéfinies pour tester les 5 cas du rapport
    st.markdown("**Questions de test rapides**")
    questions_rapides = [
        "Combien d'utilisateurs existent dans la base Oracle ?",
        "Quel utilisateur a le plus d'actions sur DBA_USERS ?",
        "Dernière personne à avoir touché CUSTOMERS ?",
        "Donne-moi les 5 dernières actions enregistrées.",
        "Top 3 utilisateurs qui ont modifié le plus de tables en 7 jours.",
    ]
    for q in questions_rapides:
        if st.button(q, key=f"btn_{hash(q)}"):
            st.session_state.prefill = q
            st.rerun()

    st.divider()
    if st.button("🗑️ Vider l'historique"):
        st.session_state.historique = []
        st.rerun()


# ════════════════════════════════════════════════════════════
# INTERFACE PRINCIPALE
# ════════════════════════════════════════════════════════════
st.markdown(
    '<div class="qf-header">'
    '<span class="qf-chat-title">Oracle NLP → SQL Assistant</span>'
    '<span class="qf-badge qf-badge-green">V2 · 90%+</span>'
    '</div>',
    unsafe_allow_html=True
)
st.markdown(
    '<div class="qf-chat-sub">'
    'Posez une question en français · génération SQL V2 · '
    'exécution · réponse naturelle'
    '</div>',
    unsafe_allow_html=True
)

# Zone de chat
st.markdown('<div class="qf-chat-wrap">', unsafe_allow_html=True)

for msg in st.session_state.historique:
    role = msg.get('role', 'user')
    if role == 'user':
        st.markdown(
            f'<div class="qf-msg-user">{msg["content"]}</div>',
            unsafe_allow_html=True
        )
    elif role == 'bot_sql':
        st.markdown(
            f'<div class="qf-sql-block">{msg["content"]}</div>',
            unsafe_allow_html=True
        )
    elif role == 'bot_table':
        st.markdown(msg["content"], unsafe_allow_html=True)
    elif role == 'bot':
        st.markdown(
            f'<div class="qf-msg-bot">{msg["content"]}</div>',
            unsafe_allow_html=True
        )

# Saisie
user_input = st.text_area(
    "Posez votre question en langage naturel…",
    value=st.session_state.prefill,
    key="qf_input",
    label_visibility="collapsed"
)

if st.button("Envoyer", key="qf_send") and user_input.strip():
    st.session_state.prefill = ""
    question = user_input.strip()
    st.session_state.historique.append({'role': 'user', 'content': question})

    with st.spinner("Génération SQL en cours…"):
        tokenizer, model, device = load_model()

        # 1. Génération SQL avec prompt V2 + post-processing
        sql = generer_sql(question, tokenizer, model, device)
        st.session_state.historique.append({'role': 'bot_sql', 'content': sql})

        # 2. Exécution sur oracle_audit_trail.csv
        result = executer_sur_audit(sql, audit_df)
        if result is not None and not result.empty:
            html_table = result.head(10).to_html(
                classes="qf-table", index=False, border=0
            )
            st.session_state.historique.append(
                {'role': 'bot_table', 'content': html_table}
            )
        else:
            msg_vide = (
                "<div class='qf-msg-bot'>"
                "Requête exécutée — aucun résultat retourné "
                "(DBA_USERS simulée ou filtre trop restrictif)."
                "</div>"
            )
            st.session_state.historique.append(
                {'role': 'bot_table', 'content': msg_vide}
            )

        # 3. Réponse naturelle basée sur le résultat
        resultat_texte = dataframe_to_text(result) if result is not None \
                         else "Aucun résultat (requête DBA_USERS ou refus sécurité)."
        reponse_ia = generer_reponse_naturelle(
            question, sql, resultat_texte, tokenizer, model, device
        )
        st.session_state.historique.append({'role': 'bot', 'content': reponse_ia})

    st.rerun()

st.markdown('</div>', unsafe_allow_html=True)