from __future__ import annotations

import unittest

from app.services.intent_policy import normalize_intent
from app.services.local_model_service import build_local_synthesis
from app.services.safe_sql_builder import UnsafeIntentError, build_safe_audit_query


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

    def test_purge_order_is_refused(self) -> None:
        intent = normalize_intent("Purge immédiatement CLIENT", {}, USERS, OBJECTS)
        self.assertEqual(intent["status"], "refusal")
        self.assertEqual(intent["actions"], [])

    def test_unknown_conversation_reference_is_clarified(self) -> None:
        intent = normalize_intent("De quelle opération parles-tu ?", {}, USERS, OBJECTS)
        self.assertEqual(intent["status"], "clarification")

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

