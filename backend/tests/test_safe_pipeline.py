from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.intent_policy import normalize_intent
from app.services.local_model_service import build_local_synthesis
from app.services.query_plan_service import normalize_query_plan
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


class GeneralQueryPlanTests(unittest.TestCase):
    def _plan(self, **changes):
        plan = {
            "status": "query", "source": "events", "dimensions": [],
            "calculation": None, "filters": [], "time": {"mode": "all"},
            "comparison_ranges": [], "group_by": [], "order_by": [],
            "limit": None, "response_mode": "detail", "clarification": None,
        }
        plan.update(changes)
        return plan

    def test_plan_validation_removes_catalog_values_not_present_in_question(self) -> None:
        plan = normalize_query_plan(
            "Quel compte a le moins d'opérations ?",
            {
                "status": "query", "source": "events",
                "filters": [{"field": "user", "operator": "in", "value": USERS}],
                "response_mode": "ranking",
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["filters"], [])

    def test_plan_validation_normalizes_failure_status(self) -> None:
        plan = normalize_query_plan(
            "Quels événements ont échoué ?",
            {
                "status": "query", "source": "events",
                "filters": [{"field": "return_code", "operator": "eq", "value": "FAILURE"}],
            },
            USERS, OBJECTS,
        )
        self.assertEqual(
            plan["filters"],
            [{"field": "return_code", "operator": "failure", "value": None}],
        )

    def test_inconsistent_catalog_analysis_requests_clarification(self) -> None:
        plan = normalize_query_plan(
            "quelle est la dernière personne",
            {
                "status": "query", "source": "users", "response_mode": "list",
                "order_by": [{"field": "timestamp", "direction": "desc"}],
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["status"], "clarification")

    def test_analytical_catalog_source_is_normalized_to_events(self) -> None:
        plan = normalize_query_plan(
            "quelle action est la plus fréquente",
            {
                "status": "query", "source": "actions",
                "calculation": {"operation": "count", "field": "event"},
                "order_by": {"field": "event_count", "direction": "desc"},
                "limit": 1, "response_mode": "ranking",
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["status"], "query")
        self.assertEqual(plan["source"], "events")
        self.assertEqual(plan["group_by"], ["action"])
        self.assertEqual(plan["order_by"], [{"field": "event_count", "direction": "desc"}])

    def test_incomplete_comparison_requests_clarification(self) -> None:
        plan = normalize_query_plan(
            "compare les périodes",
            {"status": "query", "source": "events", "response_mode": "comparison"},
            USERS, OBJECTS,
        )
        self.assertEqual(plan["status"], "clarification")

    def test_plan_validation_keeps_arbitrary_relative_period(self) -> None:
        plan = normalize_query_plan(
            "activité des 17 dernières heures",
            {
                "status": "query", "source": "events",
                "time": {"mode": "relative_last", "unit": "hour", "value": 17},
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["time"], {"mode": "relative_last", "unit": "hour", "value": 17})

    def test_ranked_user_over_arbitrary_days_is_composable(self) -> None:
        query = build_safe_audit_query(self._plan(
            calculation={"operation": "count", "field": "event"},
            time={"mode": "relative_last", "unit": "day", "value": 10},
            group_by=["user"],
            order_by=[{"field": "event_count", "direction": "desc"}],
            limit=1, response_mode="ranking",
        ), default_limit=10)
        self.assertIn("DBUSERNAME, COUNT(*) AS EVENT_COUNT", query.sql)
        self.assertIn("GROUP BY DBUSERNAME", query.sql)
        self.assertIn("ORDER BY EVENT_COUNT DESC", query.sql)
        self.assertIn("FETCH FIRST 1 ROWS ONLY", query.sql)
        self.assertEqual(query.binds["time_value"], 10)

    def test_least_user_uses_same_plan_with_ascending_order(self) -> None:
        query = build_safe_audit_query(self._plan(
            calculation={"operation": "count", "field": "event"},
            time={"mode": "relative_last", "unit": "day", "value": 5},
            group_by=["user"],
            order_by=[{"field": "event_count", "direction": "asc"}],
            limit=1, response_mode="ranking",
        ))
        self.assertIn("ORDER BY EVENT_COUNT ASC", query.sql)
        self.assertEqual(query.binds["time_value"], 5)

    def test_object_catalog_returns_only_distinct_objects(self) -> None:
        query = build_safe_audit_query(self._plan(
            source="objects", dimensions=["object"], response_mode="list", limit=20,
        ))
        self.assertIn("SELECT DISTINCT OBJECT_NAME", query.sql)
        self.assertNotIn("DBUSERNAME", query.sql)
        self.assertNotIn("ACTION_NAME", query.sql)

    def test_relative_units_are_generic(self) -> None:
        cases = [("minute", 45, "NUMTODSINTERVAL"), ("hour", 6, "NUMTODSINTERVAL"),
                 ("week", 2, "NUMTODSINTERVAL"), ("month", 3, "ADD_MONTHS"),
                 ("year", 1, "ADD_MONTHS")]
        for unit, value, sql_fragment in cases:
            with self.subTest(unit=unit):
                query = build_safe_audit_query(self._plan(
                    time={"mode": "relative_last", "unit": unit, "value": value},
                ))
                self.assertIn(sql_fragment, query.sql)

    def test_calendar_and_explicit_periods_are_supported(self) -> None:
        periods = [
            {"mode": "today"}, {"mode": "yesterday"},
            {"mode": "current", "unit": "week"},
            {"mode": "previous", "unit": "month"},
            {"mode": "between", "start": "2026-09-01", "end": "2026-09-10"},
            {"mode": "before", "end": "2026-09-01"},
            {"mode": "after", "start": "2026-08-01 12:30:00"},
            {"mode": "previous_weekday", "weekday": "friday"},
        ]
        for period in periods:
            with self.subTest(period=period):
                query = build_safe_audit_query(self._plan(time=period))
                self.assertIn("EVENT_TIMESTAMP", query.sql)

    def test_filters_are_bound_and_never_interpolated(self) -> None:
        query = build_safe_audit_query(self._plan(filters=[
            {"field": "object", "operator": "contains", "value": ["CLIENT"]},
            {"field": "return_code", "operator": "failure", "value": None},
        ]))
        self.assertNotIn("%CLIENT%", query.sql)
        self.assertEqual(query.binds["filter_0"], "%CLIENT%")
        self.assertIn("NVL(RETURNCODE, 0) <> 0", query.sql)

    def test_comparison_accepts_multiple_periods(self) -> None:
        query = build_safe_audit_query(self._plan(
            response_mode="comparison",
            comparison_ranges=[
                {"label": "Aujourd'hui", "time": {"mode": "today"}},
                {"label": "Hier", "time": {"mode": "yesterday"}},
            ],
        ))
        self.assertIn("PERIOD_1_COUNT", query.sql)
        self.assertIn("PERIOD_2_COUNT", query.sql)

    def test_list_synthesis_uses_only_executed_rows(self) -> None:
        answer = build_local_synthesis(
            "liste les tables", [{"OBJECT_NAME": "A"}, {"OBJECT_NAME": "B"}], None,
            self._plan(source="objects", dimensions=["object"], response_mode="list"),
        )
        self.assertIn("A, B", answer)
        self.assertNotIn("utilisateur", answer.lower())

    def test_comparison_synthesis_uses_period_labels_and_counts(self) -> None:
        answer = build_local_synthesis(
            "compare hier et aujourd'hui",
            [{"PERIOD_1_COUNT": 12, "PERIOD_2_COUNT": 8}], None,
            self._plan(
                response_mode="comparison",
                comparison_ranges=[
                    {"label": "Aujourd'hui", "time": {"mode": "today"}},
                    {"label": "Hier", "time": {"mode": "yesterday"}},
                ],
            ),
        )
        self.assertIn("Aujourd'hui : 12", answer)
        self.assertIn("Hier : 8", answer)

    def test_long_ranking_keeps_each_label_and_count(self) -> None:
        rows = [{"DBUSERNAME": name, "EVENT_COUNT": count} for name, count in [
            ("A", 9), ("B", 7), ("C", 5), ("D", 2)
        ]]
        answer = build_local_synthesis(
            "classe les comptes", rows, None,
            self._plan(response_mode="ranking"),
        )
        self.assertIn("A (9)", answer)
        self.assertIn("D (2)", answer)

    def test_ascending_rank_synthesis_says_least(self) -> None:
        answer = build_local_synthesis(
            "quel compte a le moins d'opérations",
            [{"DBUSERNAME": "HR", "EVENT_COUNT": 2}], None,
            self._plan(
                calculation={"operation": "count", "field": "event"},
                group_by=["user"],
                order_by=[{"field": "event_count", "direction": "asc"}],
                response_mode="ranking",
            ),
        )
        self.assertIn("ayant le moins d’événements", answer)

    def test_semantic_cues_repair_general_least_user_plan(self) -> None:
        plan = normalize_query_plan(
            "qui sont les deux utilisateur a avoir effectue le moin d'actions ?",
            {
                "status": "query", "source": "events", "dimensions": ["user"],
                "filters": [{"field": "action", "operator": "ne", "value": ["SELECT"]}],
                "order_by": [{"field": "timestamp", "direction": "desc"}],
                "limit": 2, "response_mode": "detail",
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["calculation"], {"operation": "count", "field": "event"})
        self.assertEqual(plan["group_by"], ["user"])
        self.assertEqual(plan["order_by"], [{"field": "event_count", "direction": "asc"}])
        self.assertEqual(plan["limit"], 2)
        self.assertEqual(plan["filters"], [])

    def test_semantic_cues_repair_general_recent_action_plan(self) -> None:
        plan = normalize_query_plan(
            "donne moi les 6 derniers actions dans la base et le utilisateur qui l'on fait",
            {
                "status": "query", "source": "events", "dimensions": ["user", "action"],
                "order_by": [{"field": "action", "direction": "desc"}],
                "limit": 6, "response_mode": "detail",
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["order_by"], [{"field": "timestamp", "direction": "desc"}])
        self.assertEqual(plan["limit"], 6)
        self.assertEqual(plan["dimensions"], ["user", "action"])

    def test_catalog_sql_reports_total_before_limit(self) -> None:
        query = build_safe_audit_query(self._plan(
            source="objects", dimensions=["object"], response_mode="list", limit=10,
        ))
        self.assertIn("COUNT(*) OVER () AS AUDITAI_TOTAL_AVAILABLE", query.sql)
        self.assertIn("FETCH FIRST 10 ROWS ONLY", query.sql)

    def test_ranking_sql_counts_ties_before_limit(self) -> None:
        query = build_safe_audit_query(self._plan(
            dimensions=["user"],
            calculation={"operation": "count", "field": "event"},
            group_by=["user"],
            order_by=[{"field": "event_count", "direction": "asc"}],
            limit=2, response_mode="ranking",
        ))
        self.assertIn("COUNT(*) OVER (PARTITION BY EVENT_COUNT) AS AUDITAI_TIE_COUNT", query.sql)
        self.assertIn("ORDER BY EVENT_COUNT ASC, DBUSERNAME ASC", query.sql)
        self.assertIn("FETCH FIRST 2 ROWS ONLY", query.sql)

    def test_catalog_synthesis_explains_display_limit(self) -> None:
        rows = [{"OBJECT_NAME": f"OBJ_{index}"} for index in range(1, 11)]
        answer = build_local_synthesis(
            "liste les tables", rows, None,
            self._plan(source="objects", dimensions=["object"], response_mode="list"),
            total_available=15,
        )
        self.assertIn("10", answer)
        self.assertIn("15", answer)

    def test_least_ranking_synthesis_explains_ties(self) -> None:
        rows = [
            {"DBUSERNAME": "A", "EVENT_COUNT": 357, "AUDITAI_TIE_COUNT": 11},
            {"DBUSERNAME": "B", "EVENT_COUNT": 357, "AUDITAI_TIE_COUNT": 11},
        ]
        answer = build_local_synthesis(
            "les deux utilisateurs avec le moins d'actions", rows, None,
            self._plan(
                dimensions=["user"],
                calculation={"operation": "count", "field": "event"},
                group_by=["user"],
                order_by=[{"field": "event_count", "direction": "asc"}],
                limit=2, response_mode="ranking",
            ),
        )
        self.assertIn("11", answer)
        self.assertIn("minimum", answer)
        self.assertIn("A", answer)
        self.assertIn("B", answer)

    def test_six_row_synthesis_preserves_every_tuple_without_model_call(self) -> None:
        rows = [
            {"DBUSERNAME": f"USER_{index}", "ACTION_NAME": "SELECT",
             "EVENT_TIMESTAMP": f"2026-09-14T10:0{index}:00"}
            for index in range(6)
        ]
        with patch("app.services.local_model_service._chat") as chat:
            answer = build_local_synthesis(
                "les 6 dernieres actions, la date et l'utilisateur", rows, None,
                self._plan(
                    dimensions=["user", "action", "timestamp"],
                    order_by=[{"field": "timestamp", "direction": "desc"}],
                    limit=6,
                ),
            )
        chat.assert_not_called()
        for index, row in enumerate(rows, 1):
            self.assertIn(f"{index}.", answer)
            self.assertIn(row["DBUSERNAME"], answer)
            self.assertIn(row["EVENT_TIMESTAMP"], answer)

    def test_object_failure_ranking_keeps_relative_period_and_excludes_nulls(self) -> None:
        question = (
            "Sur quels objets y a-t-il eu le plus d'echecs au cours des "
            "deux dernieres semaines ? Donne-moi les trois premiers."
        )
        plan = normalize_query_plan(
            question,
            {
                "status": "query", "source": "events", "dimensions": ["object"],
                "calculation": {"operation": "count", "field": "event"},
                "filters": [{"field": "return_code", "operator": "failure", "value": None}],
                "time": {"mode": "all"}, "group_by": ["object"],
                "order_by": [{"field": "event_count", "direction": "desc"}],
                "limit": 3, "response_mode": "detail",
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["response_mode"], "ranking")
        self.assertEqual(plan["time"], {"mode": "relative_last", "unit": "week", "value": 2})
        self.assertEqual(plan["filters"], [
            {"field": "return_code", "operator": "failure", "value": None}
        ])
        query = build_safe_audit_query(plan)
        self.assertIn("OBJECT_NAME IS NOT NULL", query.sql)
        self.assertIn("NUMTODSINTERVAL(:time_value, 'DAY')", query.sql)
        self.assertEqual(query.binds["time_value"], 14)

    def test_clear_delete_ranking_recovers_from_model_clarification(self) -> None:
        plan = normalize_query_plan(
            "Sur quels table y a-t-il eu le plus de suppression au cours des deux dernieres semaines ?",
            {"status": "clarification", "source": "events", "dimensions": []},
            USERS, OBJECTS,
        )
        self.assertEqual(plan["status"], "query")
        self.assertEqual(plan["group_by"], ["object"])
        self.assertEqual(plan["calculation"], {"operation": "count", "field": "event"})
        self.assertEqual(plan["order_by"], [{"field": "event_count", "direction": "desc"}])
        self.assertEqual(plan["limit"], 1)
        self.assertEqual(plan["time"], {"mode": "relative_last", "unit": "week", "value": 2})
        self.assertIn(
            {"field": "action", "operator": "in", "value": ["DELETE"]},
            plan["filters"],
        )

    def test_who_created_most_tables_ranks_users_and_filters_create_table(self) -> None:
        plan = normalize_query_plan(
            "qui a creer le plus de table ?",
            {
                "status": "query", "source": "events", "dimensions": ["object"],
                "calculation": {"operation": "count_distinct", "field": "object"},
                "group_by": ["object"],
                "order_by": [{"field": "value", "direction": "desc"}],
                "limit": 1, "response_mode": "ranking",
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["dimensions"], ["user"])
        self.assertEqual(plan["group_by"], ["user"])
        self.assertEqual(plan["calculation"], {"operation": "count", "field": "event"})
        self.assertEqual(plan["order_by"], [{"field": "event_count", "direction": "desc"}])
        self.assertIn(
            {"field": "action", "operator": "in", "value": ["CREATE TABLE"]},
            plan["filters"],
        )

    def test_canonical_action_keyword_can_drive_a_ranking(self) -> None:
        plan = normalize_query_plan(
            "Sur quels table y a-t-il eu le plus de delete au cours des 5 dernieres semaines ?",
            {
                "status": "query", "source": "events", "dimensions": ["object"],
                "calculation": None,
                "filters": [{"field": "action", "operator": "in", "value": ["DELETE"]}],
                "time": {"mode": "relative_last", "unit": "week", "value": 5},
                "group_by": [],
                "order_by": [{"field": "timestamp", "direction": "desc"}],
                "limit": 1, "response_mode": "detail",
            },
            USERS, OBJECTS,
        )
        self.assertEqual(plan["group_by"], ["object"])
        self.assertEqual(plan["calculation"], {"operation": "count", "field": "event"})
        self.assertEqual(plan["order_by"], [{"field": "event_count", "direction": "desc"}])
        self.assertEqual(plan["time"], {"mode": "relative_last", "unit": "week", "value": 5})
        self.assertEqual(plan["limit"], 1)
        self.assertIn(
            {"field": "action", "operator": "in", "value": ["DELETE"]},
            plan["filters"],
        )


if __name__ == "__main__":
    unittest.main()

