from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.intent_policy import normalize_intent
from app.services.local_model_service import build_local_synthesis
from app.services.safe_sql_builder import ALLOWED_ACTIONS, UnsafeIntentError, build_safe_audit_query


USERS = ["CYRILLE", "SYSTEM", "REPORT_USER", "NICOLAS"]
OBJECTS = ["CLIENT", "EMPLOYEES", "PAIEMENTS"]


class IntentPolicyTests(unittest.TestCase):
    def test_audit_delete_question_is_read_only_intent(self) -> None:
        intent = normalize_intent(
            "ki a suprimer des données sur CLIENT hier ?",
            {"users": ["REPORT_USER"], "actions": ["DELETE"]},
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["status"], "query")
        self.assertEqual(intent["users"], [])
        self.assertEqual(intent["objects"], ["CLIENT"])
        self.assertEqual(intent["actions"], ["DELETE"])
        self.assertEqual(intent["period"], "yesterday")

    def test_overbroad_model_actions_are_collapsed_but_semantics_remain(self) -> None:
        intent = normalize_intent(
            "qui est la derniere persone a effectuer une action en base",
            {
                "status": "query",
                "actions": sorted(action for action in ALLOWED_ACTIONS),
                "aggregate": "latest_users",
                "limit": 1,
                "evidence": ["derniere persone"],
            },
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["actions"], [])
        self.assertEqual(intent["aggregate"], "latest_users")
        self.assertEqual(intent["limit"], 1)

    def test_recency_corrects_model_frequency_confusion(self) -> None:
        intent = normalize_intent(
            "donne moi les deux comptes les plus recemment actifs",
            {
                "status": "query",
                "aggregate": "top_user",
                "limit": 2,
                "evidence": ["deux comptes", "plus recemment actifs"],
            },
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["aggregate"], "latest_users")
        self.assertEqual(intent["limit"], 2)

    def test_comparison_wording_is_not_treated_as_mutation(self) -> None:
        intent = normalize_intent(
            "mets en parallele ce qui s'est passe hier et aujourd'hui",
            {"status": "refusal", "period": "compare_today_yesterday"},
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["status"], "query")
        self.assertEqual(intent["period"], "compare_today_yesterday")
        self.assertEqual(intent["aggregate"], "compare")

    def test_unsupported_model_aggregate_and_limit_are_rejected(self) -> None:
        intent = normalize_intent(
            "que sest il passe aujourdhui ?",
            {
                "status": "query",
                "period": "today",
                "aggregate": "count_distinct_user",
                "limit": 200,
                "evidence": ["aujourdhui"],
            },
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["period"], "today")
        self.assertIsNone(intent["aggregate"])
        self.assertIsNone(intent["limit"])

    def test_unrequested_top_objects_limit_uses_domain_default(self) -> None:
        intent = normalize_intent(
            "quelles ressources ont ete les plus lues ?",
            {
                "status": "query",
                "aggregate": "top_objects",
                "limit": 200,
                "evidence": ["ressources", "plus lues"],
            },
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["aggregate"], "top_objects")
        self.assertEqual(intent["limit"], 5)

    def test_mutation_order_is_refused(self) -> None:
        intent = normalize_intent(
            "Supprime toutes les lignes de CLIENT",
            {"status": "query", "actions": ["DELETE"]},
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["status"], "refusal")
        self.assertEqual(intent["actions"], [])
        with self.assertRaises(UnsafeIntentError):
            build_safe_audit_query(intent)

    def test_ambiguous_reference_requests_clarification(self) -> None:
        intent = normalize_intent("Qui a fait ça hier ?", {}, USERS, OBJECTS)
        self.assertEqual(intent["status"], "clarification")
        self.assertEqual(intent["period"], "yesterday")

    def test_direct_sql_mutation_is_refused(self) -> None:
        intent = normalize_intent("DROP TABLE CLIENT", {"status": "query"}, USERS, OBJECTS)
        self.assertEqual(intent["status"], "refusal")
        self.assertEqual(intent["actions"], [])

    def test_model_refusal_cannot_block_an_explicit_audit_aggregate(self) -> None:
        intent = normalize_intent(
            "Quelle action est la plus fréquente ?",
            {"status": "refusal", "aggregate": "top_action"},
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["status"], "query")
        self.assertEqual(intent["aggregate"], "top_action")

    def test_purge_order_is_refused(self) -> None:
        intent = normalize_intent("Purge immédiatement CLIENT", {}, USERS, OBJECTS)
        self.assertEqual(intent["status"], "refusal")
        self.assertEqual(intent["actions"], [])

    def test_unknown_conversation_reference_is_clarified(self) -> None:
        intent = normalize_intent("De quelle opération parles-tu ?", {}, USERS, OBJECTS)
        self.assertEqual(intent["status"], "clarification")

    def test_all_allowed_oracle_action_keywords_are_recognized(self) -> None:
        cases = {
            "Montre les LOGON": "LOGON",
            "Montre les LOGOFF": "LOGOFF",
            "Montre les SELECT": "SELECT",
            "Montre les INSERT": "INSERT",
            "Montre les UPDATE": "UPDATE",
            "Montre les DELETE": "DELETE",
            "Montre les GRANT": "GRANT",
            "Montre les REVOKE": "REVOKE",
            "Montre les ALTER": "ALTER",
            "Montre les TRUNCATE": "TRUNCATE",
            "Montre les CREATE USER": "CREATE USER",
            "Montre les DROP USER": "DROP USER",
            "Montre les ALTER USER": "ALTER USER",
            "Montre les CREATE TABLE": "CREATE TABLE",
            "Montre les DROP TABLE": "DROP TABLE",
            "Montre les ALTER TABLE": "ALTER TABLE",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                intent = normalize_intent(question, {}, USERS, OBJECTS)
                self.assertIn(expected, intent["actions"])

    def test_french_action_paraphrases_are_recognized(self) -> None:
        cases = {
            "Qui a ajouté des lignes ?": "INSERT",
            "Qui a mis à jour les données ?": "UPDATE",
            "Qui s'est déconnecté ?": "LOGOFF",
            "Qui a retiré les droits ?": "REVOKE",
            "Qui a attribué des privilèges ?": "GRANT",
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                intent = normalize_intent(question, {}, USERS, OBJECTS)
                self.assertIn(expected, intent["actions"])

    def test_model_semantics_are_accepted_for_unseen_person_wording(self) -> None:
        intent = normalize_intent(
            "qui est la derniere persone a effectuer une action en base",
            {
                "status": "query",
                "users": [],
                "objects": [],
                "actions": [],
                "period": None,
                "aggregate": "latest_users",
                "failed_only": False,
                "limit": None,
            },
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["aggregate"], "latest_users")
        self.assertEqual(intent["limit"], 1)

    def test_ranked_quantity_does_not_depend_on_the_noun(self) -> None:
        intent = normalize_intent(
            "donne moi les deux comptes les plus recemment actifs",
            {"status": "query", "aggregate": "top_user"},
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["aggregate"], "latest_users")
        self.assertEqual(intent["limit"], 2)

    def test_generic_article_is_not_mistaken_for_result_count(self) -> None:
        intent = normalize_intent(
            "une personne a effectué une action en base",
            {}, USERS, OBJECTS,
        )
        self.assertIsNone(intent["limit"])

    def test_model_only_action_paraphrase_requests_clarification(self) -> None:
        intent = normalize_intent(
            "qui a alimenté CLIENT ?",
            {
                "status": "query",
                "actions": ["INSERT"],
                "evidence": ["alimenté", "CLIENT"],
            },
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["status"], "clarification")
        self.assertEqual(intent["actions"], [])
        self.assertEqual(intent["objects"], ["CLIENT"])
        self.assertIn("action demandée reste incertaine", intent["clarification"])

    def test_hallucinated_entities_are_removed(self) -> None:
        intent = normalize_intent(
            "Qu'est-ce qui s'est passé aujourd'hui ?",
            {"users": ["REPORT_USER"], "objects": ["CLIENT"], "actions": ["SELECT"]},
            USERS,
            OBJECTS,
        )
        self.assertEqual(intent["users"], [])
        self.assertEqual(intent["objects"], [])
        self.assertEqual(intent["actions"], [])


class SafeSqlBuilderTests(unittest.TestCase):
    def test_values_are_bound_and_sql_is_select(self) -> None:
        query = build_safe_audit_query({
            "status": "query",
            "users": ["CYRILLE"],
            "objects": ["CLIENT"],
            "actions": ["DELETE"],
            "period": "yesterday",
            "aggregate": None,
            "failed_only": False,
            "limit": 5000,
        })
        self.assertTrue(query.sql.startswith("SELECT "))
        self.assertNotIn("CYRILLE", query.sql)
        self.assertNotIn("'CLIENT'", query.sql)
        self.assertEqual(query.binds["user_0"], "CYRILLE")
        self.assertEqual(query.binds["object_0"], "CLIENT")
        self.assertEqual(query.binds["action_0"], "DELETE")
        self.assertIn("FETCH FIRST 200 ROWS ONLY", query.sql)

    def test_configured_limit_caps_model_limit(self) -> None:
        query = build_safe_audit_query({
            "status": "query", "users": [], "objects": [], "actions": [],
            "period": None, "aggregate": None, "failed_only": False, "limit": 200,
        }, default_limit=3)
        self.assertIn("FETCH FIRST 3 ROWS ONLY", query.sql)

    def test_singular_last_event_requests_one_row(self) -> None:
        intent = normalize_intent("Montre le dernier événement", {}, USERS, OBJECTS)
        self.assertEqual(intent["limit"], 1)
        query = build_safe_audit_query(intent, default_limit=10)
        self.assertIn("FETCH FIRST 1 ROWS ONLY", query.sql)

    def test_explicit_smaller_limit_is_respected(self) -> None:
        intent = normalize_intent("Montre les trois derniers événements", {}, USERS, OBJECTS)
        self.assertEqual(intent["limit"], 3)
        query = build_safe_audit_query(intent, default_limit=10)
        self.assertIn("FETCH FIRST 3 ROWS ONLY", query.sql)

    def test_three_latest_distinct_users(self) -> None:
        intent = normalize_intent(
            "quels sont les trois derniers user a avoir fais une action en base ?",
            {}, USERS, OBJECTS,
        )
        self.assertEqual(intent["aggregate"], "latest_users")
        self.assertEqual(intent["limit"], 3)
        query = build_safe_audit_query(intent, default_limit=10)
        self.assertIn("PARTITION BY UPPER(DBUSERNAME)", query.sql)
        self.assertIn("AUDITAI_RN = 1", query.sql)
        self.assertIn("FETCH FIRST 3 ROWS ONLY", query.sql)

    def test_latest_user_who_deleted(self) -> None:
        intent = normalize_intent(
            "qui est le dernier utilisateur a avoir fais un delete ?",
            {}, USERS, OBJECTS,
        )
        self.assertEqual(intent["aggregate"], "latest_users")
        self.assertEqual(intent["actions"], ["DELETE"])
        self.assertEqual(intent["limit"], 1)
        query = build_safe_audit_query(intent, default_limit=10)
        self.assertIn("UPPER(ACTION_NAME) IN (:action_0)", query.sql)
        self.assertEqual(query.binds["action_0"], "DELETE")
        self.assertIn("FETCH FIRST 1 ROWS ONLY", query.sql)

    def test_three_latest_actions_on_employees(self) -> None:
        intent = normalize_intent(
            "quels sont les trois dernieres action effectué sur la table EMPLOYEES",
            {}, USERS, OBJECTS,
        )
        self.assertIsNone(intent["aggregate"])
        self.assertEqual(intent["objects"], ["EMPLOYEES"])
        self.assertEqual(intent["limit"], 3)
        query = build_safe_audit_query(intent, default_limit=10)
        self.assertIn("UPPER(OBJECT_NAME) IN (:object_0)", query.sql)
        self.assertEqual(query.binds["object_0"], "EMPLOYEES")
        self.assertIn("FETCH FIRST 3 ROWS ONLY", query.sql)

    def test_unknown_action_is_rejected(self) -> None:
        with self.assertRaises(UnsafeIntentError):
            build_safe_audit_query({
                "status": "query",
                "users": [],
                "objects": [],
                "actions": ["DROP DATABASE"],
                "period": None,
                "aggregate": None,
                "failed_only": False,
            })

    def test_aggregate_uses_oracle_syntax(self) -> None:
        query = build_safe_audit_query({
            "status": "query",
            "users": [],
            "objects": [],
            "actions": [],
            "period": None,
            "aggregate": "top_action",
            "failed_only": False,
        })
        self.assertIn("FETCH FIRST 1 ROWS ONLY", query.sql)
        self.assertNotIn(" LIMIT ", query.sql.upper())


class SynthesisTests(unittest.TestCase):
    def test_aggregate_keeps_label_and_number(self) -> None:
        answer = build_local_synthesis(
            "Quelle action est la plus fréquente ?",
            [{"ACTION_NAME": "SELECT", "EVENT_COUNT": 626}],
            None,
        )
        self.assertIn("SELECT", answer)
        self.assertIn("626", answer)

    def test_one_row_is_explained_as_a_sentence(self) -> None:
        answer = build_local_synthesis(
            "Qui a consulté CLIENT ?",
            [{"DBUSERNAME": "CYRILLE", "ACTION_NAME": "SELECT", "OBJECT_NAME": "CLIENT"}],
            None,
        )
        self.assertIn("L'utilisateur CYRILLE a réalisé", answer)
        self.assertIn("CLIENT", answer)

    def test_latest_user_answer_names_the_user_directly(self) -> None:
        answer = build_local_synthesis(
            "qui est le dernier utilisateur a avoir fais un delete ?",
            [{"DBUSERNAME": "HR", "ACTION_NAME": "DELETE", "OBJECT_NAME": "FACTURES"}],
            None,
        )
        self.assertIn("Le dernier utilisateur correspondant est HR", answer)
        self.assertNotIn("200", answer)

    def test_three_latest_users_answer_matches_the_question(self) -> None:
        answer = build_local_synthesis(
            "quels sont les trois derniers user a avoir fais une action en base ?",
            [
                {"DBUSERNAME": "A", "ACTION_NAME": "SELECT"},
                {"DBUSERNAME": "B", "ACTION_NAME": "UPDATE"},
                {"DBUSERNAME": "C", "ACTION_NAME": "DELETE"},
            ],
            None,
        )
        self.assertIn("trois derniers utilisateurs", answer)
        self.assertNotIn("200", answer)

    def test_invalid_generated_actor_falls_back_to_factual_answer(self) -> None:
        rows = [
            {"DBUSERNAME": name, "ACTION_NAME": "REVOKE", "OBJECT_NAME": "EMPLOYEES"}
            for name in ["A", "B", "C", "D"]
        ]
        with patch(
            "app.services.local_model_service._chat",
            return_value="L'audit a révoqué les droits pour A, B, C et D.",
        ):
            answer = build_local_synthesis(
                "Qui a retiré les droits sur EMPLOYEES ?", rows, None
            )
        self.assertNotIn("L'audit a", answer)
        self.assertIn("opération « retrait de droits » sur EMPLOYEES", answer)
        self.assertIn("A, B, C, D", answer)

    def test_technical_rows_word_triggers_factual_fallback(self) -> None:
        rows = [
            {"DBUSERNAME": name, "ACTION_NAME": "INSERT", "OBJECT_NAME": "CLIENT"}
            for name in ["A", "B", "C", "D"]
        ]
        with patch(
            "app.services.local_model_service._chat",
            return_value="Le nombre total de lignes est de 4.",
        ):
            answer = build_local_synthesis("Montre les quatre INSERT sur CLIENT", rows, None)
        self.assertNotIn("lignes", answer.lower())
        self.assertIn("CLIENT", answer)

    def test_two_rows_are_explained_as_sentences(self) -> None:
        answer = build_local_synthesis(
            "Qui a modifié CLIENT ?",
            [
                {"DBUSERNAME": "CYRILLE", "ACTION_NAME": "UPDATE", "OBJECT_NAME": "CLIENT"},
                {"DBUSERNAME": "SYSTEM", "ACTION_NAME": "SELECT", "OBJECT_NAME": "CLIENT"},
            ],
            None,
        )
        self.assertIn("Deux événements", answer)
        self.assertIn("CYRILLE", answer)
        self.assertIn("SYSTEM", answer)
        self.assertNotIn("Consultez le tableau", answer)


if __name__ == "__main__":
    unittest.main()

