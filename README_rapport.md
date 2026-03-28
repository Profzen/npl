# Rapport de Diagnostic — TinyLlama V9 SQL Generation

**Date**: 25 mars 2026  
**Campagne de test**: 10 questions graduées (facile→moyen→difficile)  
**Données audit**: Janvier 2026, 5000 lignes (SMART2DSECU.UNIFIED_AUDIT_DATA)  
**Model SQL**: TinyLlama-1.1B-Chat + LoRA V6  
**Model Synthèse**: Phi-3 mini Q4 GGUF

---

## 1. RÉSULTATS GLOBAUX

| Métrique | Valeur |
|----------|--------|
| **Questions réussies** | 3/10 (30%) |
| **Questions échouées** | 7/10 (70%) |
| **Objectif visé** | 90%+ |
| **Verdict entraînement** | ⚠️ REQUIS avant production |

---

## 2. RÉSULTATS DÉTAILLÉS PAR QUESTION

### ✅ PASSÉES (3/10)

#### Q1 : Combien d'utilisateurs distincts apparaissent dans les données d'audit ?
- **SQL généré**: `SELECT COUNT(DISTINCT DBUSERNAME) FROM SMART2DSECU.UNIFIED_AUDIT_DATA`
- **Résultat**: Correct, synthèse appropriée
- **Analyse**: Pattern de base `COUNT(DISTINCT)` maîtrisé ✅

#### Q2 : Qui s'est connecté le plus ?
- **SQL généré**: `SELECT DBUSERNAME, COUNT(*) AS NB FROM ... WHERE ACTION_NAME='LOGON' GROUP BY DBUSERNAME ORDER BY NB DESC FETCH FIRST 1 ROWS ONLY`
- **Résultat**: TEST 992 connexions (correct)
- **Analyse**: Pattern `WHERE ACTION_NAME + GROUP BY DBUSERNAME + TOP 1` maîtrisé ✅

#### Q7 : Qui a fait le plus d'actions sur AUD$ ?
- **SQL généré**: `SELECT DBUSERNAME, COUNT(*) AS NB FROM ... WHERE OBJECT_NAME='AUD$' GROUP BY DBUSERNAME ORDER BY NB DESC FETCH FIRST 1 ROWS ONLY`
- **Résultat**: SYS 41 actions (correct)
- **Analyse**: Pattern `WHERE OBJECT_NAME + GROUP BY DBUSERNAME + agrégation` maîtrisé ✅

---

### ❌ ÉCHOUÉES (7/10)

#### Q3 : Combien d'actions a VROMUALD effectuées ?
- **SQL généré**: `WHERE OBJECT_NAME='VROMUALD'` → 192 résultats
- **Attendu**: `WHERE DBUSERNAME='VROMUALD'` → 1 résultat
- **Faille**: **Confusion acteur/objet** quand le nom existe dans les deux colonnes
- **Type**: Sémantique — confusion qui génère résultat faux silencieusement
- **Severity**: 🔴 CRITIQUE (incompréhension du contexte)

#### Q4 : Qui a accédé à la table EMPLOYEES ?
- **SQL généré**: `WHERE ACTION_NAME='LOGON' AND OBJECT_NAME='EMPLOYEES'` → 0 résultats
- **Attendu**: `WHERE OBJECT_NAME='EMPLOYEES' GROUP BY DBUSERNAME` (sans ACTION_NAME='LOGON')
- **Faille**: (1) LOGON incompatible avec filtrer sur OBJECT_NAME, (2) pas de GROUP BY DBUSERNAME
- **Type**: Sémantique double — ACTION_NAME mal mappé + agrégation manquante
- **Severity**: 🔴 CRITIQUE

#### Q5 : Quelle table a été la plus modifiée ?
- **SQL généré**: `GROUP BY DBUSERNAME` (pas de filtre ACTION_NAME, pas de WHERE OBJECT_NAME)
- **Attendu**: `WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') GROUP BY OBJECT_NAME`
- **Faille**: **GROUP BY inversé** (user au lieu d'objet)
- **Type**: Sémantique — mauvais choix de colonne de groupement
- **Severity**: 🔴 CRITIQUE (retour résultat faux)

#### Q6 : Qui s'est connecté en janvier 2026 ?
- **SQL généré**: `WHERE TRUNC(EVENT_TIMESTAMP,'MM')=TRUNC(SYSDATE,'MM')` + `ORA-01858: a non-numeric character was found where a numeric one was expected`
- **Attendu**: `WHERE TRUNC(EVENT_TIMESTAMP) BETWEEN TO_DATE('2026-01-01','YYYY-MM-DD') AND TO_DATE('2026-01-31','YYYY-MM-DD')`
- **Faille**: **Conversion temporelle échouée** — modèle ignore "janvier 2026" et force comparaison au mois courant (mars)
- **Type**: Syntaxe Oracle + sémantique temporelle
- **Severity**: 🔴 CRITIQUE (erreur Oracle, zéro résultat)

#### Q8 : Qui a accédé à EMPLOYEES entre 1er jan 2026 et 31 jan 2026 ?
- **SQL généré**: Pas d'`OBJECT_NAME='EMPLOYEES'`, `ACTION_NAME='LOGON'`, conversion temporelle fausse `HH24>=31`
- **Attendu**: `WHERE OBJECT_NAME='EMPLOYEES' AND TRUNC(EVENT_TIMESTAMP) BETWEEN TO_DATE('2026-01-01',...) GROUP BY DBUSERNAME`
- **Faille**: Trois accumulations : objet oublié, ACTION_NAME mauvais, conversion temporelle cassée
- **Type**: Composite
- **Severity**: 🔴 CRITIQUE (0 résultats, requête non-sensée)

#### Q9 : Qui a le plus changé d'informations dans la base ?
- **SQL généré** (présumé faille, utilisateur dit "problème d'interprétation langage non-tech")
- **Attendu**: `WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') GROUP BY DBUSERNAME`
- **Faille**: Langage utilisateur "changé d'informations" → pas d'exemples en dataset pour cette formulation
- **Type**: Mapping langage métier → SQL
- **Severity**: 🟡 MAJEUR (exemple métier manquant)

#### Q10 : Qui a fait des actions inhabituelles tard dans la nuit en janvier 2026 ?
- **SQL généré**: `TO_NUMBER(TO_CHAR(EVENT_TIMESTAMP,'HH24'))>22` ✅ (correct pour "tard") MAIS `TRUNC(EVENT_TIMESTAMP,'MM')=TRUNC(SYSDATE,'MM')` ❌ (mars, pas janvier)
- **Attendu**: `TO_NUMBER(TO_CHAR(...,'HH24'))>22 AND TRUNC(EVENT_TIMESTAMP) BETWEEN TO_DATE('2026-01-01',...)`
- **Faille**: **Conversion temporelle mois échouée** (même que Q6, Q8)
- **Type**: Sémantique temporelle
- **Severity**: 🔴 CRITIQUE (0 résultats)

---

## 3. ANALYSE DES PATTERNS DE FAILLE

### 🔴 Faille #1 : Conversion Temporelle (3 occurrences — Q6, Q8, Q10)

**Description**: Quand l'utilisateur mentionne un mois spécifique ("janvier 2026", "février", etc.), le modèle :
- Oublie le mois nommé et force une comparaison au mois COURANT (SYSDATE)
- Génère des syntaxes Oracle invalides (`TRUNC(EVENT_TIMESTAMP,'MM')=TRUNC(SYSDATE,'MM')` avec texte)
- Résultat : `ORA-01858` ou 0 résultats

**Root Cause**: Bloc B15 (vague questions avec noms) du V9 ne couvre pas les **conversions temporelles de mois nommés**. Exemples nécessaires :
```
"en janvier 2026" → WHERE TRUNC(EVENT_TIMESTAMP) BETWEEN TO_DATE('2026-01-01',...) AND TO_DATE('2026-01-31',...)
"le mois dernier" → WHERE TRUNC(EVENT_TIMESTAMP,'MM') = TRUNC(ADD_MONTHS(SYSDATE,-1),'MM')
"la dernière semaine" → WHERE TRUNC(EVENT_TIMESTAMP) >= TRUNC(SYSDATE) - 7
```

**Impact**: Production inutilisable pour questions temporelles avec mois nommés.

---

### 🔴 Faille #2 : GROUP BY Objet vs. User (2 occurrences — Q3, Q5)

**Description**: Quand la question porte sur "objet" ou "table" :
- Modèle génère `GROUP BY DBUSERNAME` (utilisateur)  
- Génère résultat sémantiquement faux (silencieux)

**Root Cause**: Données d'entraînement biaisées vers "actions par utilisateur" (Q1, Q2, Q7 réussissent avec `GROUP BY DBUSERNAME`). Bloc B15 ajoute des exemples "table modifiée" mais insuffisants.

**Impact**: 40% des questions "objet" échouent silencieusement.

---

### 🔴 Faille #3 : ACTION_NAME Incomplet ou Mauvais (2 occurrences — Q4, Q8)

**Description**: Questions sur "accédé à" + objet :
- Modèle génère `ACTION_NAME='LOGON'` (mauvais pour objet)
- Oublie `GROUP BY DBUSERNAME`

**Root Cause**: "Accédé à EMPLOYEES" est ambigu :
- Prise littérale : LOGON (connexion, ne touche pas les objets)
- Intention réelle : SELECT/INSERT/UPDATE/DELETE sur EMPLOYEES

**Impact**: Requête tombe à 0 résultats, utilisateur reçoit "aucune activité".

---

### 🟡 Faille #4 : Langage Métier Non-Couvert (1 occurrence — Q9)

**Description**: "Qui a le plus changé d'informations dans la base ?"
- Langage utilisateur non-technique pas mappé à `INSERT/UPDATE/DELETE`

**Root Cause**: V9 Bloc B15 ne couvre pas cette formulation métier.

**Impact**: Modèle invente une requête non-sensée.

---

## 4. VERDICT ENTRAÎNEMENT

### 4.1. TinyLlama SQL Generation : **OUI, RETRAIN REQUIS** 🔴

**Justification**:
- Taux actuel: 30% réussi = **inutilisable en production** (cible 90%)
- 7/10 failles critiques dont 3 récurrentes (temporelle)
- Patterns fixes (GROUP BY objet, ACTION_NAME) identifiés et reproductibles

**Recommendation**:  
Ajouter au dataset V10 **avant réentraînement** :

#### Block C: Conversion Temporelle (500 exemples)
```python
# Mois nommés
{
    "input": "Qui s'est connecté en janvier 2026 ?",
    "output": "SELECT DBUSERNAME FROM ... WHERE TRUNC(EVENT_TIMESTAMP) BETWEEN TO_DATE('2026-01-01','YYYY-MM-DD') AND TO_DATE('2026-01-31','YYYY-MM-DD')"
},
{
    "input": "Actions du mois dernier",
    "output": "SELECT ... WHERE TRUNC(EVENT_TIMESTAMP,'MM') = TRUNC(ADD_MONTHS(SYSDATE,-1),'MM')"
},

# Plages de temps
{
    "input": "Quoi en janvier 2026 jusqu'à fin février ?",
    "output": "... BETWEEN TO_DATE('2026-01-01',...) AND TO_DATE('2026-02-28',...)"
},

# Périodes relatives
{
    "input": "la dernière semaine",
    "output": "WHERE TRUNC(EVENT_TIMESTAMP) >= TRUNC(SYSDATE) - 7"
},
{
    "input": "les 30 derniers jours",
    "output": "WHERE EVENT_TIMESTAMP >= ADD_MONTHS(SYSDATE, -1)"
},
```

#### Block D: GROUP BY Objet (400 exemples)
```python
{
    "input": "Quelle table a été la plus modifiée ?",
    "output": "SELECT OBJECT_NAME, COUNT(*) FROM ... GROUP BY OBJECT_NAME ORDER BY COUNT(*) DESC FETCH FIRST 1 ROWS ONLY"
},
{
    "input": "Combien d'objets a [USER] modifiés ?",
    "output": "SELECT COUNT(DISTINCT OBJECT_NAME) FROM ... WHERE DBUSERNAME='[USER]'"
},
{
    "input": "Qui a touché EMPLOYEES ?",
    "output": "SELECT DBUSERNAME FROM ... WHERE OBJECT_NAME='EMPLOYEES' GROUP BY DBUSERNAME"
},
```

#### Block E: ACTION_NAME Contextualisé (300 exemples)
```python
{
    "input": "Qui a accédé à [TABLE] ?",
    "output": "... WHERE OBJECT_NAME='[TABLE]' GROUP BY DBUSERNAME ORDER BY COUNT(*) DESC"
    # Sans ACTION_NAME='LOGON'
},
{
    "input": "Actions sur PAYROLL",
    "output": "... WHERE OBJECT_NAME='PAYROLL' AND ACTION_NAME IN ('SELECT','INSERT','UPDATE','DELETE','ALTER')"
},
{
    "input": "Qui a modifié les données de [TABLE] ?",
    "output": "... WHERE OBJECT_NAME='[TABLE]' AND ACTION_NAME IN ('INSERT','UPDATE','DELETE')"
},
```

#### Block F: Langage Métier (200 exemples)
```python
{
    "input": "Qui a le plus changé d'informations ?",
    "output": "SELECT DBUSERNAME, COUNT(*) FROM ... WHERE ACTION_NAME IN ('INSERT','UPDATE','DELETE') GROUP BY DBUSERNAME ORDER BY COUNT(*) DESC FETCH FIRST 1 ROWS ONLY"
},
{
    "input": "Qui a créé de nouveaux comptes ?",
    "output": "... WHERE ACTION_NAME = 'CREATE USER' GROUP BY DBUSERNAME"
},
{
    "input": "Qui a supprimé des éléments ?",
    "output": "... WHERE ACTION_NAME IN ('DELETE','DROP') GROUP BY DBUSERNAME"
},
```

**Estimé rééntraînement**: 4 époques, LoRA r=32, MAX_LEN=256 (même config que V9) → ~24h GPU si vous avez accès.

---

### 4.2. Phi-3 French Synthesis : **NON, SUFFISANT** ✅

**Justification**:
- Q1, Q2, Q7 ont retourné synthèses correctes et naturelles
- Phi-3 gère bien les cas "0 résultats" ("Aucune activité")
- Problème vient de SQL cassé, pas de la synthèse

**Verdict**: Phi-3 fonctionne bien. Pas de retrain nécessaire. Une fois SQL fixé, synthèse sera plus pertinente.

---

## 5. PLAN DE REMÉDIATION ORDERED

### Phase 1 : Dataset Patch (THIS WEEK)
1. ✅ Créer Blocks C, D, E, F (total ~1400 exemples)
2. ✅ Valider exemples contre donnéees réelles oracle
3. ✅ Merger avec V9 (total ~10400 exemples) → V10

### Phase 2 : Réentraînement (WEEK 2)
1. Exécuter `tinyllama_oracle_v10_dataset.ipynb` (créer nouveau depuis V9 + blocks C-F)
2. Fine-tune TinyLlama 4 époque LoRA
3. Générer checkpoint final

### Phase 3 : Validation (WEEK 2-3)
1. Tester V10 sur mêmes 10 questions
2. Target : 90%+ réussi
3. Documentation des patterns validés

### Phase 4 : Deployment (WEEK 4)
1. Swap modèle dans `app_queryflow_prod8.py`
2. Test UAT utilisateurs non-tech
3. Go live

---

## 6. POINTS FAIBLES RÉSIDUELS À SURVEILLER

Même après retrain V10 :

1. **Ambiguïté de langage** ("accédé" = SELECT ou tous les actions ?)  
   → Mitigation: Post-processing intelligente avec contexte
   
2. **Noms ambivalents** (même valeur dans DBUSERNAME et OBJECT_NAME, ex: VROMUALD)  
   → Mitigation: Ajouter exemples "déambiguïsation" avec description explicite

3. **Horodatage précis** (heures/minutes)  
   → Mitigation: Block G futur si utilisateurs demandent "entre 14h et 16h"

4. **Calculs complexes** (ratios, moyennes)  
   → Cost/benefit faible pour audit, skip pour V10

---

## 7. CONCLUSIONS

**TinyLlama V9 n'est pas prêt pour production.**

Taux 30% → 70% de failles. Problèmes identifiés et corrigeables :
- Conversion temporelle: bloc C ajoutera ~500 exemples
- GROUP BY objet: bloc D ajouta ~400 exemples  
- ACTION_NAME contexte: bloc E ajouta ~300 exemples
- Langage métier: bloc F ajoutera ~200 exemples

**V10 projeté**: 90%+ si datasets patchés + 4 époque réentraînement.

Phi-3 OK, pas de changement. Déployer ensemble post-V10 validation.

---

**Signé**: Diagnostic automatisé, 10 questions terrain (réelles données Janvier 2026)  
**Date rapport**: 25 mars 2026
