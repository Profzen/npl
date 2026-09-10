# Rapport de benchmark — Failles du modèle TinyLlama LoRA Oracle NLP
**Date :** 24 mars 2026  
**Modèle évalué :** TinyLlama-1.1B-Chat + LoRA fine-tuné Oracle audit  
**Script :** `benchmark_15_varied_questions.py`  
**Rapport JSON brut :** `benchmark_15_varied_report.json`

---

## Résultat global

| Métrique | Valeur |
|---|---|
| Questions testées | 15 |
| Réussites | 8 |
| Échecs | 7 |
| Taux de réussite | **53,33 %** |

> **Conclusion : le modèle est insuffisant pour la production.** Un taux de réussite en dessous de 85 % signifie que quasiment 1 question sur 2 posée par un utilisateur non-technique génère une réponse incorrecte, voire une erreur Oracle bloquante.

---

## Questions réussies

| # | Question | SQL généré | Résultat |
|---|---|---|---|
| 2 | Qui s'est connecté aujourd'hui ? | `WHERE ACTION_NAME='LOGON' AND TRUNC(...)=TRUNC(SYSDATE)` | ✅ Correct |
| 3 | Qui s'est déconnecté aujourd'hui ? | `WHERE ACTION_NAME='LOGOFF' AND TRUNC(...)=TRUNC(SYSDATE)` | ✅ Correct |
| 4 | Montre-moi les 5 personnes qui ont fait le plus d'actions sur les 7 derniers jours | `GROUP BY DBUSERNAME … FETCH FIRST 5 ROWS ONLY` | ✅ Correct |
| 7 | Y a-t-il eu des suppressions de comptes sur les 30 derniers jours ? | `ACTION_NAME IN ('DROP USER','ALTER USER',...)` | ✅ Correct |
| 8 | Qui a modifié des droits récemment ? | `ACTION_NAME='GRANT' ORDER BY … FETCH FIRST 1` | ✅ Correct |
| 10 | Donne les 10 dernières actions enregistrées | `ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST 10` | ✅ Correct |
| 12 | Pour l'utilisateur SYS, montre les 5 dernières actions | `WHERE DBUSERNAME='SYS' … FETCH FIRST 5` | ✅ Correct |
| 14 | Combien d'actions au total ont été enregistrées hier ? | `COUNT(*) WHERE TRUNC(...)=TRUNC(SYSDATE-1)` | ✅ Correct |

---

## Questions échouées — Analyse détaillée

---

### ❌ Q1 — "combien d'utilisateur a t'on dans la base"

**SQL généré :**
```sql
SELECT COUNT(*) AS NB_UTILISATEURS FROM DISTINCT DBUSERNAME;
```

**SQL attendu :**
```sql
SELECT COUNT(DISTINCT DBUSERNAME) AS NB_UTILISATEURS
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE DBUSERNAME IS NOT NULL;
```

**Erreur Oracle :** `ORA-00903: invalid table name`

**Problèmes identifiés :**
- **Syntaxe SQL invalide** : `FROM DISTINCT DBUSERNAME` n'est pas du SQL Oracle valide. Le modèle a mal positionné le mot-clé `DISTINCT` — il devait être dans le `COUNT()`.
- **Table absente** : aucune référence à `SMART2DSECU.UNIFIED_AUDIT_DATA`. Le modèle a généré une requête hors de la table cible.
- **COUNT incorrect** : `COUNT(*)` compte toutes les lignes, pas les utilisateurs distincts.

**Cause racine :**  
Le modèle n'a pas appris à associer la formulation informelle _"combien d'utilisateurs"_ sans contexte technique à un `COUNT(DISTINCT DBUSERNAME)` sur la table d'audit. Quand la question ne contient pas de mots-clés comme "audit", "trace", "derniers jours", il perd le contexte de la table cible.

**Impact :** Crash total — l'utilisateur voit une erreur Oracle, aucun résultat.

---

### ❌ Q5 — "Quelles sont les 5 tables les plus utilisées cette semaine ?"

**SQL généré :**
```sql
SELECT DBUSERNAME, COUNT(*) AS NB
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE TRUNC(EVENT_TIMESTAMP)>=TRUNC(SYSDATE-7)
GROUP BY DBUSERNAME
ORDER BY NB DESC FETCH FIRST 5 ROWS ONLY;
```

**SQL attendu :**
```sql
SELECT OBJECT_NAME, COUNT(*) AS NB
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE TRUNC(EVENT_TIMESTAMP) >= TRUNC(SYSDATE-7)
  AND OBJECT_NAME IS NOT NULL
GROUP BY OBJECT_NAME
ORDER BY NB DESC
FETCH FIRST 5 ROWS ONLY;
```

**Problèmes identifiés :**
- **Mauvaise colonne de regroupement** : `GROUP BY DBUSERNAME` au lieu de `GROUP BY OBJECT_NAME`. Le modèle renvoie les 5 **utilisateurs** les plus actifs, alors qu'on demandait les 5 **tables**.
- **Sélection incohérente** : `SELECT DBUSERNAME` au lieu de `SELECT OBJECT_NAME`.

**Cause racine :**  
Le modèle sur-associe quasiment toutes les questions sur l'activité à `DBUSERNAME`. Il manque d'exemples d'entraînement associant les mots "table", "objet", "ressource", "utilisée" au `GROUP BY OBJECT_NAME`.

**Impact :** Résultat silencieusement faux — les données Oracle sont retournées, mais elles concernent les utilisateurs, pas les objets. L'utilisateur non-technique ne verra pas l'erreur.

---

### ❌ Q6 — "Y a-t-il eu des créations de comptes sur les 30 derniers jours ?"

**SQL généré :**
```sql
SELECT DBUSERNAME, ACTION_NAME, EVENT_TIMESTAMP, OBJECT_NAME
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE ACTION_NAME IN ('CREATE USER','ALTER USER','DELETE USER')
  AND TRUNC(EVENT_TIMESTAMP)>=TRUNC(SYSDATE-30)
ORDER BY EVENT_TIMESTAMP DESC;
```

**SQL attendu :**
```sql
SELECT DBUSERNAME, ACTION_NAME, OBJECT_NAME, EVENT_TIMESTAMP
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE ACTION_NAME IN ('CREATE USER')
  AND TRUNC(EVENT_TIMESTAMP) >= TRUNC(SYSDATE-30)
ORDER BY EVENT_TIMESTAMP DESC
FETCH FIRST 50 ROWS ONLY;
```

**Problèmes identifiés :**
- **Action invalide** : `'DELETE USER'` n'existe pas dans Oracle Audit. L'action correcte est `'DROP USER'`. Si cette valeur est présente dans un filtre `IN`, elle ne cause pas d'erreur Oracle mais fausse les résultats.
- **Actions hors sujet ajoutées** : `'ALTER USER'` est une modification de compte, pas une création. Inclure `ALTER USER` gonfle artificiellement les résultats.
- **Pas de FETCH FIRST** : sur 30 jours de données, le résultat peut être très volumineux sans limite.

**Cause racine :**  
Le modèle a appris un mapping _"compte"_ → liste de toutes les actions liées aux comptes (`CREATE USER`, `ALTER USER`, `DROP USER`), sans distinguer la sémantique _création_ vs _modification_ vs _suppression_. Il confond aussi `DELETE USER` (MySQL) avec `DROP USER` (Oracle).

**Impact :** Résultats faussés — des modifications de compte apparaissent dans une liste censée ne montrer que les créations. Confusion certaine pour un utilisateur non-technique.

---

### ❌ Q9 — "Quel poste a été le plus actif ce mois-ci ?"

**SQL généré :**
```sql
SELECT DBUSERNAME, COUNT(*) AS NB
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE TRUNC(EVENT_TIMESTAMP,'MM')=TRUNC(SYSDATE,'MM')
GROUP BY DBUSERNAME
ORDER BY NB DESC FETCH FIRST 1 ROWS ONLY;
```

**SQL attendu :**
```sql
SELECT USERHOST, COUNT(*) AS NB
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE TRUNC(EVENT_TIMESTAMP,'MM') = TRUNC(SYSDATE,'MM')
  AND USERHOST IS NOT NULL
GROUP BY USERHOST
ORDER BY NB DESC
FETCH FIRST 1 ROWS ONLY;
```

**Problèmes identifiés :**
- **Mauvaise colonne** : "poste" = colonne `USERHOST` (nom de machine / poste réseau). Le modèle renvoie l'**utilisateur** le plus actif, pas le **poste** le plus actif.
- Le filtre mensuel `TRUNC(EVENT_TIMESTAMP,'MM')` est correct.

**Cause racine :**  
Le modèle ne connaît pas l'association sémantique _"poste"_ → `USERHOST`. Cette association n'est probablement pas présente (ou très peu représentée) dans le dataset d'entraînement. Il retombe par défaut sur `DBUSERNAME`, sa colonne "par défaut" pour tout ce qui touche à l'activité.

**Impact :** Réponse silencieusement fausse — le nom retourné est un nom d'utilisateur, pas un nom de machine. L'utilisateur qui demande quel poste est actif reçoit un nom d'utilisateur.

---

### ❌ Q11 — "Sur les 48 dernières heures, quels objets ont le plus changé ?"

**SQL généré :**
```sql
SELECT DBUSERNAME, COUNT(*) AS NB
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE TRUNC(EVENT_TIMESTAMP)>=TRUNC(SYSDATE-7)
GROUP BY DBUSERNAME
ORDER BY NB DESC FETCH FIRST 1 ROWS ONLY;
```

**SQL attendu :**
```sql
SELECT OBJECT_NAME, COUNT(*) AS NB
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE EVENT_TIMESTAMP >= SYSDATE - 2
  AND OBJECT_NAME IS NOT NULL
GROUP BY OBJECT_NAME
ORDER BY NB DESC
FETCH FIRST 10 ROWS ONLY;
```

**Problèmes identifiés :**
- **Double erreur de colonne** : `DBUSERNAME` au lieu de `OBJECT_NAME` (question sur des objets, pas des personnes).
- **Fenêtre temporelle fausse** : 48 heures = 2 jours → doit utiliser `SYSDATE-2` ou `EVENT_TIMESTAMP >= SYSDATE - 2`. Le modèle a généré `SYSDATE-7` (7 jours).
- **Limite trop restrictive** : `FETCH FIRST 1 ROWS ONLY` alors qu'on demande les objets (pluriel) qui ont le plus changé.

**Cause racine :**  
- Le modèle ne sait pas convertir _"48 heures"_ en `SYSDATE-2`. Il a tendance à utiliser `-7` comme fenêtre par défaut pour tout ce qui ressemble à "récemment" ou "dernières heures".
- Même problème que Q5 : sur-association de toute activité à `DBUSERNAME`.

**Impact :** Résultat doublement faux : mauvaise fenêtre temporelle ET mauvaise colonne.

---

### ❌ Q13 — "Qui a fait la toute dernière action dans les traces ?"

**SQL généré :**
```sql
SELECT DBUSERNAME, ACTION_NAME, EVENT_TIMESTAMP
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE TRUNC(EVENT_TIMESTAMP)=TRUNC(SYSDATE-1)
ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST 1 ROWS ONLY;
```

**SQL attendu :**
```sql
SELECT DBUSERNAME, ACTION_NAME, EVENT_TIMESTAMP
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
ORDER BY EVENT_TIMESTAMP DESC
FETCH FIRST 1 ROWS ONLY;
```

**Problèmes identifiés :**
- **Filtre temporel non sollicité** : la question ne demande aucune période. _"La toute dernière action"_ = le dernier enregistrement de toute la table. Le modèle a ajouté `TRUNC(SYSDATE-1)` (= hier), ce qui peut retourner 0 résultat si la dernière action est plus ancienne ou est d'aujourd'hui.
- Si `SYSDATE-1` ne contient aucune trace, la réponse sera "aucune activité", ce qui est faux.

**Cause racine :**  
Le modèle a appris à systématiquement ajouter une condition temporelle dès que la question contient le mot "dernier" ou "dernière", même quand l'intention est de récupérer l'enregistrement le plus récent de toute la table sans filtre.

**Impact :** Faux négatif — le système peut répondre "aucune activité" alors qu'il y en a une.

---

### ❌ Q15 — "Quels sont les 3 objets les plus modifiés ?"

**SQL généré :**
```sql
SELECT DBUSERNAME, COUNT(*) AS NB
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
GROUP BY DBUSERNAME
ORDER BY NB DESC FETCH FIRST 3 ROWS ONLY;
```

**SQL attendu :**
```sql
SELECT OBJECT_NAME, COUNT(*) AS NB
FROM SMART2DSECU.UNIFIED_AUDIT_DATA
WHERE OBJECT_NAME IS NOT NULL
GROUP BY OBJECT_NAME
ORDER BY NB DESC
FETCH FIRST 3 ROWS ONLY;
```

**Problèmes identifiés :**
- **Mauvaise colonne** : `DBUSERNAME` au lieu de `OBJECT_NAME`. Même erreur que Q5 et Q11.
- **Pas de filtre NULL** : sans `OBJECT_NAME IS NOT NULL`, les lignes sans objet cible (ex. connexions) polluent le résultat.

**Cause racine :**  
Même cause que Q5 et Q11 : le modèle sur-associe les requêtes d'agrégation à `DBUSERNAME` par défaut. Il manque massivement d'exemples d'entraînement avec `GROUP BY OBJECT_NAME`.

**Impact :** Résultat faux et trompeur : retourne les 3 utilisateurs les plus actifs, pas les 3 objets les plus modifiés.

---

## Synthèse des failles — Tableau de fréquence

| Faille | Nombre de questions touchées | Gravité |
|---|---|---|
| GROUP BY DBUSERNAME au lieu de OBJECT_NAME (objet/table demandé) | 3 / 15 | 🔴 Critique |
| SQL syntaxiquement invalide / table absente (question COUNT utilisateurs) | 1 / 15 | 🔴 Critique |
| Fenêtre temporelle mal convertie (48h → 7j) | 1 / 15 | 🔴 Critique |
| Filtre temporel ajouté sans raison | 1 / 15 | 🟠 Majeur |
| Colonne USERHOST non utilisée pour "poste" | 1 / 15 | 🟠 Majeur |
| Action Oracle incorrecte (DELETE USER vs DROP USER) | 1 / 15 | 🟡 Mineur |

---

## Failles structurelles identifiées

### 1. Sur-association DBUSERNAME (faille la plus fréquente)

Le modèle a appris que toute question sur "qui fait quoi" → `GROUP BY DBUSERNAME`. Il généralise ce pattern à des questions qui demandent pourtant des objets (`OBJECT_NAME`) ou des postes (`USERHOST`).

**Mots déclencheurs mal appris :** "tables", "objets", "ressources", "modifié", "utilisé", "changé"  
**Résolution entraînement :** Ajouter 30 à 50 exemples avec `GROUP BY OBJECT_NAME` pour les variantes de _"quels objets / tables / ressources"_.

### 2. COUNT DISTINCT mal formé

Pour la question la plus basique d'un responsable non-technique (_"combien d'utilisateurs a-t-on ?"_), le modèle génère une syntaxe SQL invalide et oublie la table cible.

**Résolution entraînement :** Ajouter au minimum 20 formulations de la même intention :
- "combien d'utilisateurs", "combien de personnes", "combien d'identifiants", "quel est le nombre de comptes", "combien de noms distincts"  
Tous doivent pointer vers `SELECT COUNT(DISTINCT DBUSERNAME) … FROM SMART2DSECU.UNIFIED_AUDIT_DATA`.

### 3. Conversion des unités de temps non maîtrisée

- **"48 heures"** → le modèle génère `-7` (copie un pattern de 7 jours)
- **"toute dernière"** → le modèle ajoute `-1` (= hier) au lieu de supprimer le filtre temporel

**Résolution entraînement :** Ajouter des exemples explicites pour :
- `N heures` → `EVENT_TIMESTAMP >= SYSDATE - N/24` ou `SYSDATE - (N/24)`  
- `48 heures` → `SYSDATE - 2`  
- `"dernière action"` sans période → `ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST 1 ROWS ONLY` sans WHERE temporal

### 4. Confusion sémantique crédit/suppression de compte

Le modèle mélange `CREATE USER`, `ALTER USER` et invente `DELETE USER` pour les questions de gestion de comptes.

**Résolution entraînement :** Ajouter des paires question/SQL ciblées :
- "créer un compte" → uniquement `CREATE USER`
- "supprimer un compte" → uniquement `DROP USER`
- "modifier un compte" → `ALTER USER`
- Ne jamais mélanger les trois dans un `IN (...)` sauf si la question est explicitement une liste de toutes les opérations sur les comptes.

### 5. Colonne USERHOST inconnue du modèle

Le mot "poste" (comme dans "poste de travail", "poste réseau", "poste le plus actif") n'est pas associé à `USERHOST`. Le modèle ignore cette colonne et retombe sur `DBUSERNAME`.

**Résolution entraînement :** Ajouter des exemples avec les mots "poste", "machine", "hôte", "terminal", "ordinateur" → `USERHOST`.

---

## Recommandations pour le réentraînement

### Priorité 1 — Ajouter des exemples `GROUP BY OBJECT_NAME`
Minimum **40 exemples** couvrant les formulations :
- "quels objets / tables / ressources / fichiers ont été les plus..."
- "sur quoi a-t-on le plus travaillé"
- "les 3/5/10 tables les plus touchées / modifiées / consultées / utilisées"

### Priorité 2 — Solidifier COUNT DISTINCT utilisateurs
Minimum **20 formulations** de "combien d'utilisateurs" :
- Sans adjectif : "combien d'utilisateurs", "combien de personnes", "combien d'identifiants"
- Avec période : "combien d'utilisateurs cette semaine", "sur le mois", "aujourd'hui"
- Informel : "t'as combien d'utilisateurs", "on est combien à utiliser le système", "liste le nombre de comptes actifs"

### Priorité 3 — Couvrir les fenêtres temporelles en heures
Ajouter des exemples pour :
- "dernières 24 heures", "48 heures", "72 heures", "6 heures"
- `WHERE EVENT_TIMESTAMP >= SYSDATE - 1` (24h), `SYSDATE - 2` (48h), `SYSDATE - 3` (72h)

### Priorité 4 — Apprendre "dernière action" sans filtre temporel
Exemples où il ne faut **pas** de clause WHERE sur la date :
- "qui a fait la dernière chose", "dernière opération en base", "dernière trace enregistrée", "action la plus récente"
- SQL cible : `ORDER BY EVENT_TIMESTAMP DESC FETCH FIRST 1 ROWS ONLY` (sans condition de date)

### Priorité 5 — Enseigner USERHOST
Exemples :
- "quel poste", "depuis quel ordinateur", "depuis quelle machine", "hôte le plus actif"
- SQL cible : `SELECT USERHOST, COUNT(*) … GROUP BY USERHOST`

### Priorité 6 — Corriger les actions de gestion de compte
Séparer clairement dans le dataset :
- **Création** → `ACTION_NAME = 'CREATE USER'` uniquement
- **Suppression** → `ACTION_NAME = 'DROP USER'` uniquement
- **Modification** → `ACTION_NAME = 'ALTER USER'` uniquement
- Ne jamais utiliser `DELETE USER` (n'existe pas en Oracle)

---

## Format recommandé pour les nouveaux exemples d'entraînement

```json
{
  "instruction": "quelles tables ont été les plus modifiées cette semaine",
  "input": "",
  "output": "SELECT OBJECT_NAME, COUNT(*) AS NB FROM SMART2DSECU.UNIFIED_AUDIT_DATA WHERE TRUNC(EVENT_TIMESTAMP)>=TRUNC(SYSDATE-7) AND OBJECT_NAME IS NOT NULL GROUP BY OBJECT_NAME ORDER BY NB DESC FETCH FIRST 5 ROWS ONLY;"
}
```

> Utiliser un français naturel et non-technique dans le champ `instruction`. Varier les formulations : fautes d'orthographe légères, absence de majuscules, formulations orales ("t'as combien", "montre-moi", "dis-moi si") pour couvrir les cas réels d'usage.

---

## Score de maturité par catégorie fonctionnelle

| Catégorie | Score actuel | Commentaire |
|---|---|---|
| Connexions / déconnexions (LOGON, LOGOFF) | 🟢 100 % (2/2) | Solide |
| Top-N utilisateurs avec période | 🟢 100 % (1/1) | Solide |
| Comptage actions par jour (COUNT *) | 🟢 100 % (1/1) | Solide |
| Droits / privilèges (GRANT, REVOKE) | 🟢 100 % (1/1) | Solide |
| Filtres par utilisateur nommé | 🟢 100 % (1/1) | Solide |
| Gestion de comptes (CREATE/DROP/ALTER USER) | 🟡 50 % (1/2) | `DELETE USER` invalide |
| Top-N objets / tables | 🔴 0 % (0/3) | Faille systématique |
| Comptage utilisateurs distincts | 🔴 0 % (0/1) | SQL invalide |
| Fenêtres temporelles en heures | 🔴 0 % (0/1) | Conversion fausse |
| "Dernière action" sans filtre date | 🔴 0 % (0/1) | Ajoute filtre inutile |
| Requêtes par poste (USERHOST) | 🔴 0 % (0/1) | Colonne inconnue |

---

*Généré automatiquement par `benchmark_15_varied_questions.py` — QueryFlow Oracle Audit NLP*
