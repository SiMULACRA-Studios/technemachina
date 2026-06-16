import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_ROOT = REPO_ROOT / "daemon"

if str(DAEMON_ROOT) not in sys.path:
    sys.path.insert(0, str(DAEMON_ROOT))

import app


PERMITTED_NODE_ID = "personal:test-node"
RELATED_NODE_ID = "system:related-node"
EXCLUDED_NODE_ID = "developer:excluded-node"


def build_companion_graph(description: str = "Permitted personal context.") -> dict:
    return {
        "view": "companion",
        "read_only": True,
        "nodes": [
            {
                "id": PERMITTED_NODE_ID,
                "title": "Test Personal Node",
                "description": description,
                "owner_scope": "personal",
            },
            {
                "id": RELATED_NODE_ID,
                "title": "Related System Node",
                "description": "A permitted system association.",
                "owner_scope": "system",
            },
        ],
        "edges": [
            {
                "source": PERMITTED_NODE_ID,
                "target": RELATED_NODE_ID,
                "type": "associated_with",
            }
        ],
    }


class CompanionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app.app, base_url="http://localhost")

    def post_companion(
        self,
        *,
        node_id: str = PERMITTED_NODE_ID,
        view: str = "companion",
        message: str = "What does this node mean?",
        graph: dict | None = None,
        answer: str = "A grounded synthetic answer.",
    ):
        companion_graph = graph or build_companion_graph()

        with (
            patch.object(
                app,
                "synapse_map_payload",
                new_callable=AsyncMock,
                return_value=companion_graph,
            ) as map_mock,
            patch.object(
                app.ai,
                "query_model",
                return_value=answer,
            ) as route_mock,
        ):
            response = self.client.post(
                "/companion/respond",
                json={
                    "user_message": message,
                    "selected_node_id": node_id,
                    "view": view,
                },
            )

        return response, map_mock, route_mock

    def test_companion_request_model_exists(self):
        self.assertTrue(
            hasattr(app, "CompanionRequest"),
            "daemon/app.py must define CompanionRequest",
        )

        model_fields = getattr(app.CompanionRequest, "model_fields", None)

        if model_fields is None:
            model_fields = getattr(app.CompanionRequest, "__fields__", {})

        self.assertTrue(
            {
                "user_message",
                "selected_node_id",
                "view",
            }.issubset(set(model_fields)),
            "CompanionRequest must contain user_message, selected_node_id, and view",
        )

    def test_companion_respond_route_is_registered_once(self):
        matching_routes = [
            route
            for route in app.app.routes
            if getattr(route, "path", None) == "/companion/respond"
            and "POST" in (getattr(route, "methods", set()) or set())
        ]

        self.assertEqual(
            len(matching_routes),
            1,
            "Expected exactly one POST /companion/respond route",
        )

    def test_rejects_non_companion_view(self):
        response, map_mock, route_mock = self.post_companion(
            view="developer_history",
            node_id=EXCLUDED_NODE_ID,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("view=companion", response.json()["detail"])
        map_mock.assert_not_called()
        route_mock.assert_not_called()

    def test_rejects_node_absent_from_companion_projection(self):
        response, map_mock, route_mock = self.post_companion(
            node_id=EXCLUDED_NODE_ID,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Companion view", response.json()["detail"])
        map_mock.assert_awaited_once_with(view="companion")
        route_mock.assert_not_called()

    def test_returns_grounded_semantic_contract(self):
        response, map_mock, route_mock = self.post_companion()

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["view"], "companion")
        self.assertEqual(payload["answer"], "A grounded synthetic answer.")

        self.assertEqual(payload["selected_node"]["id"], PERMITTED_NODE_ID)
        self.assertEqual(payload["selected_node"]["owner_scope"], "personal")

        self.assertEqual(payload["grounding"]["primary"], "synapse")
        self.assertEqual(
            payload["grounding"]["selected_node_id"],
            PERMITTED_NODE_ID,
        )
        self.assertFalse(payload["grounding"]["live_web"])
        self.assertFalse(payload["grounding"]["description_truncated"])

        self.assertEqual(
            payload["permissions"]["memory_mutation"],
            "oracle_gated",
        )
        self.assertTrue(payload["permissions"]["read_only"])
        self.assertEqual(payload["permissions"]["surface"], "map_local")

        map_mock.assert_awaited_once_with(view="companion")
        route_mock.assert_called_once()

    def test_returns_only_permitted_associations(self):
        response, _, _ = self.post_companion()

        self.assertEqual(response.status_code, 200)
        associations = response.json()["associations"]

        self.assertEqual(len(associations), 1)
        self.assertEqual(associations[0]["id"], RELATED_NODE_ID)
        self.assertEqual(associations[0]["owner_scope"], "system")

        association_ids = {item["id"] for item in associations}
        self.assertNotIn(EXCLUDED_NODE_ID, association_ids)

    def test_returns_actionable_suggestions(self):
        response, _, _ = self.post_companion()

        self.assertEqual(response.status_code, 200)
        suggestions = response.json()["suggestions"]

        self.assertGreater(len(suggestions), 0)
        self.assertEqual(suggestions[0]["action"], "inspect_association")
        self.assertEqual(suggestions[0]["node_id"], RELATED_NODE_ID)

    def test_fallback_suggestion_preserves_selected_node_context(self):
        graph = build_companion_graph()
        graph["edges"] = []

        response, _, _ = self.post_companion(graph=graph)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["associations"], [])

        suggestion = response.json()["suggestions"][0]
        self.assertEqual(suggestion["action"], "ask_follow_up")
        self.assertEqual(suggestion["node_id"], PERMITTED_NODE_ID)

    def test_router_receives_bounded_grounding_prompt(self):
        question = "Explain why these two nodes are associated."

        response, _, route_mock = self.post_companion(message=question)

        self.assertEqual(response.status_code, 200)
        route_mock.assert_called_once()

        grounded_prompt = route_mock.call_args.args[0]

        self.assertIn("Surface: Map-local", grounded_prompt)
        self.assertIn("View: companion", grounded_prompt)
        self.assertIn("Read-only", grounded_prompt)
        self.assertIn("Memory mutation is Oracle-gated", grounded_prompt)
        self.assertIn(PERMITTED_NODE_ID, grounded_prompt)
        self.assertIn("Test Personal Node", grounded_prompt)
        self.assertIn("Permitted personal context.", grounded_prompt)
        self.assertIn(RELATED_NODE_ID, grounded_prompt)
        self.assertIn("Related System Node", grounded_prompt)
        self.assertIn(question, grounded_prompt)

        self.assertEqual(
            route_mock.call_args.args[1],
            "auto",
        )
        self.assertEqual(
            route_mock.call_args.kwargs,
            {},
        )

    def test_truncates_oversized_description_and_reports_it(self):
        oversized_description = "X" * 5000
        graph = build_companion_graph(description=oversized_description)

        response, _, route_mock = self.post_companion(graph=graph)

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["grounding"]["description_truncated"])

        grounded_prompt = route_mock.call_args.args[0]

        self.assertIn("[...truncated]", grounded_prompt)
        self.assertNotIn(oversized_description, grounded_prompt)
        self.assertLess(len(grounded_prompt), len(oversized_description))

    def test_empty_message_is_rejected_before_provider_call(self):
        response, _, route_mock = self.post_companion(message="   ")

        self.assertEqual(response.status_code, 400)
        self.assertIn("user_message", response.json()["detail"])
        route_mock.assert_not_called()

    def test_empty_selected_node_id_is_rejected_before_provider_call(self):
        response, _, route_mock = self.post_companion(node_id="   ")

        self.assertEqual(response.status_code, 400)
        self.assertIn("selected_node_id", response.json()["detail"])
        route_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
