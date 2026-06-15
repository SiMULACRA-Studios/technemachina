import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "daemon"

sys.path.insert(0, str(DAEMON))

import synapse_map
import app
from fastapi import HTTPException


EXPECTED_VIEWS = {
    "personal": {
        "nodes": 10,
        "edges": 0,
        "scopes": {"personal"},
    },
    "personal_governance": {
        "nodes": 10,
        "edges": 4,
        "scopes": {"personal_governance"},
    },
    "imported_knowledge": {
        "nodes": 4,
        "edges": 2,
        "scopes": {"imported"},
    },
    "imported_governance": {
        "nodes": 1,
        "edges": 0,
        "scopes": {"imported_governance"},
    },
    "developer_history": {
        "nodes": 229,
        "edges": 656,
        "scopes": {"developer"},
    },
    "system": {
        "nodes": 2,
        "edges": 0,
        "scopes": {"system"},
    },
    "system_doctrine": {
        "nodes": 1,
        "edges": 0,
        "scopes": {"system_doctrine"},
    },
    "companion": {
        "nodes": 28,
        "edges": 18,
        "scopes": {
            "personal",
            "personal_governance",
            "imported",
            "imported_governance",
            "system",
            "system_doctrine",
        },
    },
    "all": {
        "nodes": 257,
        "edges": 675,
        "scopes": {
            "personal",
            "personal_governance",
            "imported",
            "imported_governance",
            "developer",
            "system",
            "system_doctrine",
        },
    },
}


class SynapseScopeProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_graph = synapse_map.get_map()

    def test_default_graph_remains_unchanged(self):
        self.assertEqual(len(self.full_graph["nodes"]), 257)
        self.assertEqual(len(self.full_graph["edges"]), 675)

        filters = self.full_graph["meta"]["filters"]

        self.assertEqual(filters["entity_type"], "")
        self.assertEqual(filters["relation_type"], "")
        self.assertNotIn("scope_view", filters)

    def test_all_named_scope_views(self):
        for view, expected in EXPECTED_VIEWS.items():
            with self.subTest(view=view):
                projected = synapse_map.project_map_by_scope(
                    self.full_graph,
                    view,
                )

                nodes = projected["nodes"]
                edges = projected["edges"]
                node_ids = {node["id"] for node in nodes}

                actual_scopes = {
                    node.get("owner_scope")
                    for node in nodes
                }

                dangling_edges = [
                    edge
                    for edge in edges
                    if (
                        edge.get("source") not in node_ids
                        or edge.get("target") not in node_ids
                    )
                ]

                self.assertEqual(len(nodes), expected["nodes"])
                self.assertEqual(len(edges), expected["edges"])
                self.assertEqual(actual_scopes, expected["scopes"])
                self.assertEqual(dangling_edges, [])

                self.assertEqual(
                    projected["meta"]["node_count"],
                    len(nodes),
                )
                self.assertEqual(
                    projected["meta"]["edge_count"],
                    len(edges),
                )
                self.assertEqual(
                    projected["meta"]["filters"]["scope_view"],
                    view,
                )

    def test_companion_view_excludes_developer_history(self):
        projected = synapse_map.project_map_by_scope(
            self.full_graph,
            "companion",
        )

        self.assertTrue(
            all(
                node.get("owner_scope") != "developer"
                for node in projected["nodes"]
            )
        )

    def test_projection_does_not_mutate_full_graph(self):
        original_node_count = len(self.full_graph["nodes"])
        original_edge_count = len(self.full_graph["edges"])
        original_filters = dict(self.full_graph["meta"]["filters"])

        synapse_map.project_map_by_scope(
            self.full_graph,
            "companion",
        )

        self.assertEqual(
            len(self.full_graph["nodes"]),
            original_node_count,
        )
        self.assertEqual(
            len(self.full_graph["edges"]),
            original_edge_count,
        )
        self.assertEqual(
            self.full_graph["meta"]["filters"],
            original_filters,
        )

    def test_unknown_projection_view_fails_closed(self):
        with self.assertRaises(ValueError):
            synapse_map.project_map_by_scope(
                self.full_graph,
                "invalid_view",
            )


class SynapseScopeApiTests(unittest.TestCase):
    def run_async(self, coroutine):
        return asyncio.run(coroutine)

    def test_default_api_response_is_backward_compatible(self):
        payload = self.run_async(
            app.synapse_map_payload()
        )

        self.assertEqual(len(payload["nodes"]), 257)
        self.assertEqual(len(payload["edges"]), 675)
        self.assertNotIn(
            "scope_view",
            payload["meta"]["filters"],
        )

    def test_companion_api_view(self):
        payload = self.run_async(
            app.synapse_map_payload(view="companion")
        )

        self.assertEqual(len(payload["nodes"]), 28)
        self.assertEqual(len(payload["edges"]), 18)
        self.assertEqual(
            payload["meta"]["filters"]["scope_view"],
            "companion",
        )

        self.assertTrue(
            all(
                node.get("owner_scope") != "developer"
                for node in payload["nodes"]
            )
        )

    def test_developer_history_api_view(self):
        payload = self.run_async(
            app.synapse_map_payload(
                view="developer_history"
            )
        )

        self.assertEqual(len(payload["nodes"]), 229)
        self.assertEqual(len(payload["edges"]), 656)
        self.assertEqual(
            payload["meta"]["filters"]["scope_view"],
            "developer_history",
        )

    def test_combined_entity_and_scope_filters(self):
        payload = self.run_async(
            app.synapse_map_payload(
                entity_type="milestone_cluster",
                view="developer_history",
            )
        )

        self.assertEqual(len(payload["nodes"]), 9)
        self.assertEqual(len(payload["edges"]), 0)

        self.assertTrue(
            all(
                node.get("type") == "milestone_cluster"
                for node in payload["nodes"]
            )
        )
        self.assertTrue(
            all(
                node.get("owner_scope") == "developer"
                for node in payload["nodes"]
            )
        )

    def test_invalid_api_view_returns_http_400(self):
        with self.assertRaises(HTTPException) as context:
            self.run_async(
                app.synapse_map_payload(
                    view="invalid_view"
                )
            )

        self.assertEqual(
            context.exception.status_code,
            400,
        )
        self.assertIn(
            "Unknown Synapse scope view",
            context.exception.detail,
        )


if __name__ == "__main__":
    unittest.main()
