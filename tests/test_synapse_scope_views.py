import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "daemon"
FIXTURE = ROOT / "tests" / "fixtures" / "synapse_scope_views.json"

sys.path.insert(0, str(DAEMON))

import synapse_map
import app
from fastapi import HTTPException


EXPECTED_VIEWS = {
    "personal": {
        "nodes": {"personal:memory", "personal:thread"},
        "edges": {"edge:personal:thread"},
        "scopes": {"personal"},
    },
    "personal_governance": {
        "nodes": {"governance:review", "governance:decision"},
        "edges": {"edge:review:decision"},
        "scopes": {"personal_governance"},
    },
    "imported_knowledge": {
        "nodes": {"imported:source", "imported:record"},
        "edges": {"edge:source:record"},
        "scopes": {"imported"},
    },
    "imported_governance": {
        "nodes": {"imported:candidate"},
        "edges": set(),
        "scopes": {"imported_governance"},
    },
    "developer_history": {
        "nodes": {"developer:milestone", "developer:cluster"},
        "edges": {"edge:milestone:cluster"},
        "scopes": {"developer"},
    },
    "system": {
        "nodes": {"system:layer:alpha", "system:layer:theta"},
        "edges": {"edge:system:layers"},
        "scopes": {"system"},
    },
    "system_doctrine": {
        "nodes": {"doctrine:daemon"},
        "edges": set(),
        "scopes": {"system_doctrine"},
    },
    "companion": {
        "nodes": {
            "personal:memory",
            "personal:thread",
            "governance:review",
            "governance:decision",
            "imported:source",
            "imported:record",
            "imported:candidate",
            "system:layer:alpha",
            "system:layer:theta",
            "doctrine:daemon",
        },
        "edges": {
            "edge:personal:thread",
            "edge:review:decision",
            "edge:source:record",
            "edge:system:layers",
            "edge:personal:system",
            "edge:candidate:record",
            "edge:doctrine:system",
        },
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
        "nodes": {
            "personal:memory",
            "personal:thread",
            "governance:review",
            "governance:decision",
            "imported:source",
            "imported:record",
            "imported:candidate",
            "developer:milestone",
            "developer:cluster",
            "system:layer:alpha",
            "system:layer:theta",
            "doctrine:daemon",
        },
        "edges": {
            "edge:personal:thread",
            "edge:review:decision",
            "edge:source:record",
            "edge:system:layers",
            "edge:personal:system",
            "edge:candidate:record",
            "edge:doctrine:system",
            "edge:personal:developer",
            "edge:developer:system",
            "edge:milestone:cluster",
        },
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


def load_scope_fixture(
    entity_type: str = "",
    relation_type: str = "",
) -> dict:
    payload = synapse_map.read_json(FIXTURE, {})
    nodes = list(payload["nodes"])
    edges = list(payload["edges"])

    if entity_type:
        nodes = [
            node
            for node in nodes
            if node.get("type") == entity_type
        ]

    ids = {
        node["id"]
        for node in nodes
        if node.get("id")
    }

    if relation_type:
        edges = [
            edge
            for edge in edges
            if edge.get("type") == relation_type
        ]

    edges = [
        edge
        for edge in edges
        if (
            edge.get("source") in ids
            and edge.get("target") in ids
        )
    ]

    graph = dict(payload)
    graph["nodes"] = nodes
    graph["edges"] = edges

    meta = dict(payload["meta"])
    meta["node_count"] = len(nodes)
    meta["edge_count"] = len(edges)
    meta["filters"] = {
        "entity_type": entity_type,
        "relation_type": relation_type,
    }
    graph["meta"] = meta
    return graph


def node_ids(payload: dict) -> set[str]:
    return {
        node["id"]
        for node in payload["nodes"]
    }


def edge_ids(payload: dict) -> set[str]:
    return {
        edge["id"]
        for edge in payload["edges"]
    }


def dangling_edges(payload: dict) -> list[dict]:
    ids = node_ids(payload)
    return [
        edge
        for edge in payload["edges"]
        if (
            edge.get("source") not in ids
            or edge.get("target") not in ids
        )
    ]


class SynapseScopeProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_graph = load_scope_fixture()

    def test_default_fixture_graph_remains_unchanged(self):
        self.assertEqual(
            node_ids(self.full_graph),
            EXPECTED_VIEWS["all"]["nodes"],
        )
        self.assertEqual(
            edge_ids(self.full_graph),
            EXPECTED_VIEWS["all"]["edges"],
        )

        filters = self.full_graph["meta"]["filters"]

        self.assertEqual(filters["entity_type"], "")
        self.assertEqual(filters["relation_type"], "")
        self.assertNotIn("scope_view", filters)

    def test_all_named_scope_views(self):
        self.assertEqual(
            set(EXPECTED_VIEWS),
            set(synapse_map.SCOPE_VIEWS),
        )

        for view, expected in EXPECTED_VIEWS.items():
            with self.subTest(view=view):
                projected = synapse_map.project_map_by_scope(
                    self.full_graph,
                    view,
                )

                nodes = projected["nodes"]
                actual_scopes = {
                    node.get("owner_scope")
                    for node in nodes
                }

                self.assertEqual(node_ids(projected), expected["nodes"])
                self.assertEqual(edge_ids(projected), expected["edges"])
                self.assertEqual(actual_scopes, expected["scopes"])
                self.assertEqual(dangling_edges(projected), [])

                self.assertEqual(
                    projected["meta"]["node_count"],
                    len(expected["nodes"]),
                )
                self.assertEqual(
                    projected["meta"]["edge_count"],
                    len(expected["edges"]),
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

        self.assertNotIn("developer:milestone", node_ids(projected))
        self.assertNotIn("developer:cluster", node_ids(projected))
        self.assertNotIn("edge:personal:developer", edge_ids(projected))
        self.assertNotIn("edge:developer:system", edge_ids(projected))
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
        with patch.object(
            app.synapse_map,
            "get_map",
            side_effect=load_scope_fixture,
        ):
            payload = self.run_async(
                app.synapse_map_payload()
            )

        self.assertEqual(
            node_ids(payload),
            EXPECTED_VIEWS["all"]["nodes"],
        )
        self.assertEqual(
            edge_ids(payload),
            EXPECTED_VIEWS["all"]["edges"],
        )
        self.assertNotIn(
            "scope_view",
            payload["meta"]["filters"],
        )

    def test_companion_api_view(self):
        with patch.object(
            app.synapse_map,
            "get_map",
            side_effect=load_scope_fixture,
        ):
            payload = self.run_async(
                app.synapse_map_payload(view="companion")
            )

        self.assertEqual(
            node_ids(payload),
            EXPECTED_VIEWS["companion"]["nodes"],
        )
        self.assertEqual(
            edge_ids(payload),
            EXPECTED_VIEWS["companion"]["edges"],
        )
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
        with patch.object(
            app.synapse_map,
            "get_map",
            side_effect=load_scope_fixture,
        ):
            payload = self.run_async(
                app.synapse_map_payload(
                    view="developer_history"
                )
            )

        self.assertEqual(
            node_ids(payload),
            EXPECTED_VIEWS["developer_history"]["nodes"],
        )
        self.assertEqual(
            edge_ids(payload),
            EXPECTED_VIEWS["developer_history"]["edges"],
        )
        self.assertEqual(
            payload["meta"]["filters"]["scope_view"],
            "developer_history",
        )

    def test_combined_entity_and_scope_filters(self):
        with patch.object(
            app.synapse_map,
            "get_map",
            side_effect=load_scope_fixture,
        ):
            payload = self.run_async(
                app.synapse_map_payload(
                    entity_type="milestone_cluster",
                    view="developer_history",
                )
            )

        self.assertEqual(node_ids(payload), {"developer:cluster"})
        self.assertEqual(edge_ids(payload), set())

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
        with patch.object(
            app.synapse_map,
            "get_map",
            side_effect=load_scope_fixture,
        ):
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


class SynapseCorpusInventoryTests(unittest.TestCase):
    def test_checked_in_corpus_has_consistent_projection_metadata(self):
        payload = synapse_map.get_map()

        self.assertEqual(
            payload["meta"]["node_count"],
            len(payload["nodes"]),
        )
        self.assertEqual(
            payload["meta"]["edge_count"],
            len(payload["edges"]),
        )
        self.assertEqual(dangling_edges(payload), [])

        actual_scopes = {
            node.get("owner_scope")
            for node in payload["nodes"]
        }
        self.assertLessEqual(
            actual_scopes,
            synapse_map.RECOGNIZED_OWNER_SCOPES,
        )


class SynapseUnmockedApiSmokeTests(unittest.TestCase):
    @staticmethod
    def run_async(coroutine):
        return asyncio.run(coroutine)

    def test_real_default_api_payload_is_structurally_consistent(self):
        payload = self.run_async(app.synapse_map_payload())

        self.assertEqual(
            payload["meta"]["node_count"],
            len(payload["nodes"]),
        )
        self.assertEqual(
            payload["meta"]["edge_count"],
            len(payload["edges"]),
        )
        self.assertEqual(dangling_edges(payload), [])

        actual_scopes = {
            node.get("owner_scope")
            for node in payload["nodes"]
        }
        self.assertLessEqual(
            actual_scopes,
            synapse_map.RECOGNIZED_OWNER_SCOPES,
        )

    def test_real_entity_filter_runs_through_production_get_map(self):
        payload = self.run_async(
            app.synapse_map_payload(
                entity_type="milestone_cluster",
            )
        )

        self.assertTrue(payload["nodes"])
        self.assertTrue(
            all(
                node.get("type") == "milestone_cluster"
                for node in payload["nodes"]
            )
        )
        self.assertEqual(dangling_edges(payload), [])

    def test_real_companion_view_excludes_developer_scope(self):
        payload = self.run_async(
            app.synapse_map_payload(view="companion")
        )

        self.assertTrue(
            all(
                node.get("owner_scope") != "developer"
                for node in payload["nodes"]
            )
        )
        self.assertEqual(dangling_edges(payload), [])


if __name__ == "__main__":
    unittest.main()
