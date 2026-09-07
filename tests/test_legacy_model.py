import unittest
from datetime import datetime, timezone

from scala_security.legacy_analysis import SECURITY_WEIGHTS, contributor_metrics, health, reach


def edge(a, b, kind="runtime", optional=False, exact=True):
    return dict(source=a, target=b, kind=kind, optional=optional, exact=exact)


class ModelTests(unittest.TestCase):
    def test_shared_dependency_and_cycles_count_once(self):
        graph = {
            "a": [edge("a", "b"), edge("a", "c")],
            "b": [edge("b", "d")],
            "c": [edge("c", "d")],
            "d": [edge("d", "a")],
        }
        self.assertEqual(set(reach("a", graph, 5)), {"b", "c", "d"})
        self.assertEqual(len(reach("a", graph, 5)["d"]), 2)

    def test_versions_do_not_merge_paths(self):
        graph = {"a@1": [edge("a@1", "b@1")], "b@2": [edge("b@2", "vulnerable@1")]}
        self.assertNotIn("vulnerable@1", reach("a@1", graph, 3))

    def test_scope_and_optional_rules(self):
        graph = {
            "a": [
                edge("a", "test", "test"),
                edge("a", "optional", optional=True),
                edge("a", "range", exact=False),
            ],
            "test": [edge("test", "runtime"), edge("test", "nested-test", "test")],
        }
        self.assertEqual(reach("a", graph, 3), {})
        self.assertEqual(set(reach("a", graph, 3, True)), {"test", "runtime"})

    def test_depth_limit(self):
        graph = {"a": [edge("a", "b")], "b": [edge("b", "c")], "c": [edge("c", "d")]}
        self.assertEqual(set(reach("a", graph, 2)), {"b", "c"})

    def test_unknown_is_not_zero(self):
        result = health({}, datetime(2026, 9, 7, tzinfo=timezone.utc))
        self.assertIsNone(result["maintenance"])
        self.assertIsNone(result["security"])

    def test_unavailable_checks_excluded_and_stale_results_withheld(self):
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        checks = [dict(name=k, score=10) for k in SECURITY_WEIGHTS]
        checks[0]["score"] = -1
        r = health({"scorecard": {"date": "2026-09-01", "checks": checks}}, now)
        self.assertEqual(r["security"], 1)
        self.assertLess(r["security_coverage"], 1)
        r = health({"scorecard": {"date": "2025-01-01", "checks": checks}}, now)
        self.assertIsNone(r["security"])

    def test_bots_and_concentration(self):
        c = {
            "past_year_committers": [
                {"login": "dependabot[bot]", "count": 900},
                {"login": "alice", "count": 6},
                {"login": "bob", "count": 4},
            ]
        }
        self.assertEqual(contributor_metrics(c), (2, 1, 10))


if __name__ == "__main__":
    unittest.main()
