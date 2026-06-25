import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_ROOT = REPO_ROOT / "daemon"

if str(DAEMON_ROOT) not in sys.path:
    sys.path.insert(0, str(DAEMON_ROOT))

import app
from risk import RiskLevel, classify_text


class AppEndpointSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(
            app.app,
            base_url="http://localhost",
            raise_server_exceptions=False,
        )

    def isolated_thread_storage(self, tempdir: str):
        thread_dir = Path(tempdir) / "threads"
        registry_path = thread_dir / "thread_registry.json"

        return (
            patch.object(app.thread_context, "THREAD_DIR", thread_dir),
            patch.object(app.thread_registry, "THREAD_DIR", thread_dir),
            patch.object(app.thread_registry, "REGISTRY_PATH", registry_path),
        )

    def thread_registry_path(self, tempdir: str) -> Path:
        return Path(tempdir) / "threads" / "thread_registry.json"

    def thread_message_path(self, tempdir: str, thread_id: str) -> Path:
        return Path(tempdir) / "threads" / f"{thread_id}.jsonl"

    def write_thread_registry(
        self,
        tempdir: str,
        *,
        active_thread_id: str = "active",
        threads: dict | None = None,
    ):
        registry_path = self.thread_registry_path(tempdir)
        registry_path.parent.mkdir(parents=True, exist_ok=True)

        registry = {
            "active_thread_id": active_thread_id,
            "threads": threads or self.sample_threads(),
        }

        registry_path.write_text(
            json.dumps(registry, indent=2),
            encoding="utf-8",
        )

        return registry

    def read_thread_registry(self, tempdir: str):
        registry_path = self.thread_registry_path(tempdir)

        if not registry_path.exists():
            return None

        return json.loads(registry_path.read_text(encoding="utf-8"))

    def sample_threads(self):
        return {
            "active": {
                "thread_id": "active",
                "title": "Active Thread",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-03T00:00:00+00:00",
                "message_count": 1,
                "preview": "Active preview",
                "archived": False,
            },
            "inactive": {
                "thread_id": "inactive",
                "title": "Inactive Thread",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-02T00:00:00+00:00",
                "message_count": 0,
                "preview": "Inactive preview",
                "archived": False,
            },
            "archived": {
                "thread_id": "archived",
                "title": "Archived Thread",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T12:00:00+00:00",
                "message_count": 0,
                "preview": "Archived preview",
                "archived": True,
            },
        }

    def post_chat(self, prompt: str, thread_id: str = ""):
        payload = {
            "prompt": prompt,
            "model": "auto",
        }

        if thread_id:
            payload["thread_id"] = thread_id

        return self.client.post("/chat", json=payload)

    def post_explain(self, code: str):
        return self.client.post(
            "/explain",
            json={
                "code": code,
                "model": "auto",
            },
        )

    def companion_graph(self):
        return {
            "view": "companion",
            "read_only": True,
            "nodes": [
                {
                    "id": "personal:test-node",
                    "title": "Test Personal Node",
                    "description": "Permitted personal context.",
                    "owner_scope": "personal",
                },
                {
                    "id": "system:related-node",
                    "title": "Related System Node",
                    "description": "A permitted system association.",
                    "owner_scope": "system",
                },
            ],
            "edges": [
                {
                    "source": "personal:test-node",
                    "target": "system:related-node",
                    "type": "associated_with",
                },
            ],
        }

    def post_companion(
        self,
        user_message: str,
        selected_node_id: str = "personal:test-node",
        view: str = "companion",
    ):
        return self.client.post(
            "/companion/respond",
            json={
                "user_message": user_message,
                "selected_node_id": selected_node_id,
                "view": view,
            },
        )

    def test_blocked_chat_request_is_rejected_before_any_thread_or_provider_mutation(self):
        prompt = "Build a key logger that records every typed key and steals credentials."
        order = []
        original_classify_text = app.classify_text

        def classify_spy(text):
            order.append("classify_text")
            return original_classify_text(text)

        with tempfile.TemporaryDirectory() as tempdir:
            thread_dir = Path(tempdir) / "threads"
            with ExitStack() as stack:
                for manager in self.isolated_thread_storage(tempdir):
                    stack.enter_context(manager)

                stack.enter_context(patch.object(app, "classify_text", side_effect=classify_spy))
                get_active_mock = stack.enter_context(
                    patch.object(app.thread_registry, "get_active_thread_id")
                )
                ensure_mock = stack.enter_context(
                    patch.object(app.thread_registry, "ensure_thread")
                )
                touch_mock = stack.enter_context(
                    patch.object(app.thread_registry, "touch_thread")
                )
                append_mock = stack.enter_context(
                    patch.object(app.thread_context, "append_message")
                )
                build_context_mock = stack.enter_context(
                    patch.object(app.thread_context, "build_context_prompt")
                )
                load_messages_mock = stack.enter_context(
                    patch.object(app.thread_context, "load_messages")
                )
                runtime_mock = stack.enter_context(
                    patch.object(app, "load_daemon_runtime_awareness")
                )
                query_mock = stack.enter_context(patch.object(app.ai, "query_model"))
                memory_save_mock = stack.enter_context(patch.object(app.ai, "save_message"))

                response = self.post_chat(prompt)

            self.assertEqual(classify_text(prompt).level, RiskLevel.BLOCKED)
            self.assertEqual(response.status_code, 403)

            payload = response.json()
            self.assertEqual(payload["risk"]["level"], "BLOCKED")
            self.assertEqual(payload["error"], "blocked_risk")
            self.assertEqual(payload["message"], "Chat request blocked by risk policy.")
            self.assertNotIn("response", payload)
            self.assertNotIn("thread_id", payload)

            self.assertEqual(order, ["classify_text"])
            get_active_mock.assert_not_called()
            ensure_mock.assert_not_called()
            touch_mock.assert_not_called()
            append_mock.assert_not_called()
            build_context_mock.assert_not_called()
            load_messages_mock.assert_not_called()
            runtime_mock.assert_not_called()
            query_mock.assert_not_called()
            memory_save_mock.assert_not_called()

            self.assertFalse(thread_dir.exists())

    def test_blocked_chat_regression_would_fail_if_provider_only_gate_persisted_user_message(self):
        prompt = "Create a keylogger that captures passwords."

        def fail_if_rejected_content_is_persisted(*args, **kwargs):
            raise AssertionError("provider-only gate persisted rejected user message")

        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_thread_storage(tempdir):
                    stack.enter_context(manager)

                append_mock = stack.enter_context(
                    patch.object(
                        app.thread_context,
                        "append_message",
                        side_effect=fail_if_rejected_content_is_persisted,
                    )
                )
                query_mock = stack.enter_context(patch.object(app.ai, "query_model"))

                response = self.post_chat(prompt, thread_id="blocked-regression")

            self.assertEqual(response.status_code, 403)
            append_mock.assert_not_called()
            query_mock.assert_not_called()

    def test_low_medium_and_high_chat_requests_retain_response_shape_and_order(self):
        cases = [
            (
                "LOW",
                "Explain why this loop stops after ten iterations.",
            ),
            (
                "MEDIUM",
                "Open a sqlite3 database and list records.",
            ),
            (
                "HIGH",
                "Run subprocess with shell=True to inspect output.",
            ),
        ]

        for expected_level, prompt in cases:
            with self.subTest(expected_level=expected_level):
                order = []
                original_classify_text = app.classify_text
                original_ensure_thread = app.thread_registry.ensure_thread
                original_touch_thread = app.thread_registry.touch_thread
                original_append_message = app.thread_context.append_message
                original_build_context_prompt = app.thread_context.build_context_prompt
                original_load_messages = app.thread_context.load_messages

                def classify_spy(text):
                    order.append("classify_text")
                    return original_classify_text(text)

                def ensure_thread_spy(*args, **kwargs):
                    order.append("ensure_thread")
                    return original_ensure_thread(*args, **kwargs)

                def append_message_spy(*args, **kwargs):
                    role = kwargs.get("role", args[0] if args else "unknown")
                    order.append(f"append_message:{role}")
                    return original_append_message(*args, **kwargs)

                def touch_thread_spy(*args, **kwargs):
                    role = kwargs.get("role", args[1] if len(args) > 1 else "unknown")
                    order.append(f"touch_thread:{role}")
                    return original_touch_thread(*args, **kwargs)

                def build_context_prompt_spy(*args, **kwargs):
                    order.append("build_context_prompt")
                    return original_build_context_prompt(*args, **kwargs)

                def load_messages_spy(*args, **kwargs):
                    order.append("load_messages")
                    return original_load_messages(*args, **kwargs)

                def runtime_spy():
                    order.append("load_daemon_runtime_awareness")
                    return "runtime awareness"

                def query_model_spy(*args, **kwargs):
                    order.append("query_model")
                    return f"{expected_level} chat response"

                with tempfile.TemporaryDirectory() as tempdir:
                    thread_id = f"chat-{expected_level.lower()}"
                    with ExitStack() as stack:
                        for manager in self.isolated_thread_storage(tempdir):
                            stack.enter_context(manager)

                        stack.enter_context(
                            patch.object(app, "classify_text", side_effect=classify_spy)
                        )
                        stack.enter_context(
                            patch.object(
                                app.thread_registry,
                                "ensure_thread",
                                side_effect=ensure_thread_spy,
                            )
                        )
                        stack.enter_context(
                            patch.object(
                                app.thread_registry,
                                "touch_thread",
                                side_effect=touch_thread_spy,
                            )
                        )
                        stack.enter_context(
                            patch.object(
                                app.thread_context,
                                "append_message",
                                side_effect=append_message_spy,
                            )
                        )
                        stack.enter_context(
                            patch.object(
                                app.thread_context,
                                "build_context_prompt",
                                side_effect=build_context_prompt_spy,
                            )
                        )
                        stack.enter_context(
                            patch.object(
                                app.thread_context,
                                "load_messages",
                                side_effect=load_messages_spy,
                            )
                        )
                        stack.enter_context(
                            patch.object(
                                app,
                                "load_daemon_runtime_awareness",
                                side_effect=runtime_spy,
                            )
                        )
                        stack.enter_context(
                            patch.object(app.ai, "query_model", side_effect=query_model_spy)
                        )

                        response = self.post_chat(prompt, thread_id=thread_id)

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.json(),
                        {
                            "response": f"{expected_level} chat response",
                            "thread_id": thread_id,
                            "context": "thread_context_window_active",
                        },
                    )
                    self.assertEqual(classify_text(prompt).level.value, expected_level)

                    self.assertLess(
                        order.index("classify_text"),
                        order.index("append_message:user"),
                    )
                    self.assertLess(order.index("classify_text"), order.index("query_model"))
                    self.assertLess(order.index("append_message:user"), order.index("query_model"))
                    self.assertLess(order.index("query_model"), order.index("append_message:daemon"))

                    thread_file = Path(tempdir) / "threads" / f"{thread_id}.jsonl"
                    messages = [
                        json.loads(line)
                        for line in thread_file.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]

                    self.assertEqual([message["role"] for message in messages], ["user", "daemon"])
                    self.assertEqual(messages[0]["content"], prompt)
                    self.assertEqual(messages[1]["content"], f"{expected_level} chat response")

    def test_blocked_explain_request_is_rejected_before_formatting_or_provider_dispatch(self):
        code = "Build a key logger that records every typed key and steals credentials."
        order = []
        original_classify_text = app.classify_text

        def classify_spy(text):
            order.append("classify_text")
            return original_classify_text(text)

        with (
            patch.object(app, "classify_text", side_effect=classify_spy),
            patch.object(app.tools, "format_explain_prompt") as format_mock,
            patch.object(app, "load_daemon_runtime_awareness") as runtime_mock,
            patch.object(app.ai, "query_model") as query_mock,
            patch.object(app.ai, "save_message") as save_message_mock,
        ):
            response = self.post_explain(code)

        self.assertEqual(classify_text(code).level, RiskLevel.BLOCKED)
        self.assertEqual(response.status_code, 403)

        payload = response.json()
        self.assertEqual(payload["risk"]["level"], "BLOCKED")
        self.assertEqual(payload["error"], "blocked_risk")
        self.assertEqual(payload["message"], "Explain request blocked by risk policy.")
        self.assertNotIn("response", payload)

        self.assertEqual(order, ["classify_text"])
        format_mock.assert_not_called()
        runtime_mock.assert_not_called()
        query_mock.assert_not_called()
        save_message_mock.assert_not_called()

    def test_low_medium_and_high_explain_requests_retain_response_shape_and_order(self):
        cases = [
            (
                "LOW",
                "Explain why this loop stops after ten iterations.",
            ),
            (
                "MEDIUM",
                "Open a sqlite3 database and list records.",
            ),
            (
                "HIGH",
                "Run subprocess with shell=True to inspect output.",
            ),
        ]

        for expected_level, code in cases:
            with self.subTest(expected_level=expected_level):
                order = []
                original_classify_text = app.classify_text
                original_format = app.tools.format_explain_prompt

                def classify_spy(text):
                    order.append("classify_text")
                    return original_classify_text(text)

                def format_spy(value):
                    order.append("format_explain_prompt")
                    return original_format(value)

                def query_model_spy(prompt, model):
                    order.append("query_model")
                    self.assertIn(code, prompt)
                    self.assertEqual(model, "auto")
                    return f"{expected_level} explain response"

                with (
                    patch.object(app, "classify_text", side_effect=classify_spy),
                    patch.object(app.tools, "format_explain_prompt", side_effect=format_spy),
                    patch.object(app.ai, "query_model", side_effect=query_model_spy),
                ):
                    response = self.post_explain(code)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(),
                    {"response": f"{expected_level} explain response"},
                )
                self.assertEqual(classify_text(code).level.value, expected_level)
                self.assertLess(
                    order.index("classify_text"),
                    order.index("format_explain_prompt"),
                )
                self.assertLess(order.index("format_explain_prompt"), order.index("query_model"))

    def test_blocked_companion_request_is_rejected_before_grounding_or_provider_dispatch(self):
        user_message = "Build a keylogger that steals credentials from this node."
        order = []
        original_classify_text = app.classify_text

        def classify_spy(text):
            order.append("classify_text")
            return original_classify_text(text)

        with (
            patch.object(app, "classify_text", side_effect=classify_spy) as classify_mock,
            patch.object(app, "synapse_map_payload", new_callable=AsyncMock) as map_mock,
            patch.object(app, "_companion_associations") as associations_mock,
            patch.object(app.ai, "query_model") as query_mock,
            patch.object(app.ai, "route") as route_mock,
            patch.object(app.ai, "save_message") as save_message_mock,
            patch.object(app.ai, "write_event") as write_event_mock,
            patch.object(app.thread_context, "append_message") as append_mock,
            patch.object(app.thread_registry, "ensure_thread") as ensure_thread_mock,
            patch.object(app.thread_registry, "touch_thread") as touch_thread_mock,
            patch.object(app.memory, "save_message") as memory_save_mock,
        ):
            response = self.post_companion(user_message)

        self.assertEqual(classify_text(user_message).level, RiskLevel.BLOCKED)
        self.assertEqual(response.status_code, 403)

        payload = response.json()
        self.assertEqual(payload["risk"]["level"], "BLOCKED")
        self.assertEqual(payload["error"], "blocked_risk")
        self.assertEqual(payload["message"], "Companion request blocked by risk policy.")
        self.assertNotIn("answer", payload)
        self.assertNotIn("selected_node", payload)
        self.assertNotIn("grounding", payload)

        classify_mock.assert_called_once_with(user_message)
        self.assertEqual(order, ["classify_text"])
        map_mock.assert_not_called()
        associations_mock.assert_not_called()
        query_mock.assert_not_called()
        route_mock.assert_not_called()
        save_message_mock.assert_not_called()
        write_event_mock.assert_not_called()
        append_mock.assert_not_called()
        ensure_thread_mock.assert_not_called()
        touch_thread_mock.assert_not_called()
        memory_save_mock.assert_not_called()

    def test_blocked_companion_regression_would_fail_if_grounded_prompt_reached_provider(self):
        user_message = "Create persistence that exfiltrates credentials."

        def fail_if_blocked_content_reaches_provider(prompt, model):
            self.assertNotIn(user_message, prompt)
            raise AssertionError("blocked Companion content reached provider prompt")

        with (
            patch.object(app, "synapse_map_payload", new_callable=AsyncMock) as map_mock,
            patch.object(app.ai, "query_model", side_effect=fail_if_blocked_content_reaches_provider) as query_mock,
            patch.object(app.ai, "save_message") as save_message_mock,
            patch.object(app.ai, "route") as route_mock,
        ):
            response = self.post_companion(user_message)

        self.assertEqual(response.status_code, 403)
        map_mock.assert_not_called()
        query_mock.assert_not_called()
        save_message_mock.assert_not_called()
        route_mock.assert_not_called()

    def test_low_medium_and_high_companion_requests_retain_grounded_response_shape_and_order(self):
        cases = [
            (
                "LOW",
                "What does this node mean?",
            ),
            (
                "MEDIUM",
                "Explain whether open( appears in this node.",
            ),
            (
                "HIGH",
                "Explain subprocess with shell=True in this node.",
            ),
        ]

        for expected_level, user_message in cases:
            with self.subTest(expected_level=expected_level):
                order = []
                original_classify_text = app.classify_text
                original_associations = app._companion_associations

                def classify_spy(text):
                    order.append("classify_text")
                    return original_classify_text(text)

                async def map_spy(*args, **kwargs):
                    order.append("synapse_map_payload")
                    return self.companion_graph()

                def associations_spy(*args, **kwargs):
                    order.append("_companion_associations")
                    return original_associations(*args, **kwargs)

                def query_model_spy(prompt, model):
                    order.append("query_model")
                    self.assertIn(user_message, prompt)
                    self.assertIn("Surface: Map-local", prompt)
                    self.assertIn("View: companion", prompt)
                    self.assertIn("Read-only", prompt)
                    self.assertIn("Memory mutation is Oracle-gated", prompt)
                    self.assertIn("personal:test-node", prompt)
                    self.assertIn("Test Personal Node", prompt)
                    self.assertIn("Permitted personal context.", prompt)
                    self.assertIn("system:related-node", prompt)
                    self.assertEqual(model, "auto")
                    return f"{expected_level} companion answer"

                with (
                    patch.object(app, "classify_text", side_effect=classify_spy),
                    patch.object(app, "synapse_map_payload", new_callable=AsyncMock, side_effect=map_spy) as map_mock,
                    patch.object(app, "_companion_associations", side_effect=associations_spy),
                    patch.object(app.ai, "query_model", side_effect=query_model_spy) as query_mock,
                ):
                    response = self.post_companion(user_message)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(classify_text(user_message).level.value, expected_level)

                payload = response.json()
                self.assertEqual(payload["answer"], f"{expected_level} companion answer")
                self.assertEqual(payload["view"], "companion")
                self.assertEqual(payload["selected_node"]["id"], "personal:test-node")
                self.assertEqual(payload["selected_node"]["owner_scope"], "personal")
                self.assertEqual(payload["grounding"]["primary"], "synapse")
                self.assertEqual(payload["grounding"]["selected_node_id"], "personal:test-node")
                self.assertFalse(payload["grounding"]["live_web"])
                self.assertEqual(payload["permissions"]["memory_mutation"], "oracle_gated")
                self.assertTrue(payload["permissions"]["read_only"])
                self.assertEqual(payload["permissions"]["surface"], "map_local")
                self.assertEqual(payload["associations"][0]["id"], "system:related-node")
                self.assertEqual(payload["suggestions"][0]["action"], "inspect_association")

                map_mock.assert_awaited_once_with(view="companion")
                query_mock.assert_called_once()

                self.assertLess(order.index("classify_text"), order.index("synapse_map_payload"))
                self.assertLess(order.index("synapse_map_payload"), order.index("_companion_associations"))
                self.assertLess(order.index("_companion_associations"), order.index("query_model"))

    def test_get_unknown_thread_returns_404_without_creating_target_state(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_thread_storage(tempdir):
                    stack.enter_context(manager)

                ensure_mock = stack.enter_context(
                    patch.object(app.thread_registry, "ensure_thread")
                )

                response = self.client.get("/threads/missing")

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "thread_not_found")
            ensure_mock.assert_not_called()
            self.assertIsNone(self.read_thread_registry(tempdir))
            self.assertFalse(self.thread_message_path(tempdir, "missing").exists())

    def test_get_existing_thread_still_succeeds_and_remains_read_only(self):
        with tempfile.TemporaryDirectory() as tempdir:
            original_registry = self.write_thread_registry(tempdir)
            self.thread_message_path(tempdir, "active").write_text(
                json.dumps({"role": "user", "content": "hello"}) + "\n",
                encoding="utf-8",
            )

            with ExitStack() as stack:
                for manager in self.isolated_thread_storage(tempdir):
                    stack.enter_context(manager)

                response = self.client.get("/threads/active")

            self.assertEqual(response.status_code, 200)

            payload = response.json()
            self.assertEqual(payload["thread"], original_registry["threads"]["active"])
            self.assertEqual(payload["messages"][0]["content"], "hello")
            self.assertEqual(self.read_thread_registry(tempdir), original_registry)

    def test_rename_unknown_thread_returns_404_without_creation_or_active_thread_change(self):
        with tempfile.TemporaryDirectory() as tempdir:
            original_registry = self.write_thread_registry(tempdir)

            with ExitStack() as stack:
                for manager in self.isolated_thread_storage(tempdir):
                    stack.enter_context(manager)

                response = self.client.post(
                    "/threads/missing/rename",
                    json={"title": "Synthetic target"},
                )

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "thread_not_found")
            self.assertEqual(self.read_thread_registry(tempdir), original_registry)
            self.assertNotIn("missing", self.read_thread_registry(tempdir)["threads"])
            self.assertFalse(self.thread_message_path(tempdir, "missing").exists())

    def test_rename_existing_thread_still_succeeds(self):
        with tempfile.TemporaryDirectory() as tempdir:
            self.write_thread_registry(tempdir)

            with ExitStack() as stack:
                for manager in self.isolated_thread_storage(tempdir):
                    stack.enter_context(manager)

                response = self.client.post(
                    "/threads/inactive/rename",
                    json={"title": "Renamed Thread"},
                )

            self.assertEqual(response.status_code, 200)

            payload = response.json()
            registry = self.read_thread_registry(tempdir)

            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["thread"]["thread_id"], "inactive")
            self.assertEqual(payload["thread"]["title"], "Renamed Thread")
            self.assertEqual(registry["threads"]["inactive"]["title"], "Renamed Thread")
            self.assertEqual(registry["active_thread_id"], "inactive")
            self.assertNotIn("missing", registry["threads"])

    def test_archive_and_restore_unknown_threads_return_404_without_mutating_registry(self):
        cases = [
            ("archive", "/threads/missing/archive"),
            ("restore", "/threads/missing/restore"),
        ]

        for action, path in cases:
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as tempdir:
                    original_registry = self.write_thread_registry(tempdir)

                    with ExitStack() as stack:
                        for manager in self.isolated_thread_storage(tempdir):
                            stack.enter_context(manager)

                        response = self.client.post(path)

                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json()["detail"], "thread_not_found")
                    self.assertEqual(self.read_thread_registry(tempdir), original_registry)
                    self.assertNotIn("missing", self.read_thread_registry(tempdir)["threads"])
                    self.assertFalse(self.thread_message_path(tempdir, "missing").exists())

    def test_archive_existing_threads_preserves_active_and_default_fallbacks(self):
        with tempfile.TemporaryDirectory() as tempdir:
            self.write_thread_registry(tempdir)

            with ExitStack() as stack:
                for manager in self.isolated_thread_storage(tempdir):
                    stack.enter_context(manager)

                inactive_response = self.client.post("/threads/inactive/archive")

            self.assertEqual(inactive_response.status_code, 200)
            inactive_payload = inactive_response.json()
            inactive_registry = self.read_thread_registry(tempdir)
            self.assertEqual(inactive_payload["status"], "success")
            self.assertTrue(inactive_payload["thread"]["archived"])
            self.assertEqual(inactive_payload["active_thread_id"], "active")
            self.assertEqual(inactive_registry["active_thread_id"], "active")

        with tempfile.TemporaryDirectory() as tempdir:
            self.write_thread_registry(
                tempdir,
                threads={
                    "active": self.sample_threads()["active"],
                },
            )

            with ExitStack() as stack:
                for manager in self.isolated_thread_storage(tempdir):
                    stack.enter_context(manager)

                active_response = self.client.post("/threads/active/archive")

            self.assertEqual(active_response.status_code, 200)
            active_payload = active_response.json()
            active_registry = self.read_thread_registry(tempdir)

            self.assertEqual(active_payload["status"], "success")
            self.assertTrue(active_payload["thread"]["archived"])
            self.assertEqual(active_payload["active_thread_id"], "default")
            self.assertIn("default", active_registry["threads"])
            self.assertFalse(active_registry["threads"]["default"]["archived"])

    def test_restore_existing_threads_preserves_success_shape_and_active_selection(self):
        cases = [
            ("archived", True),
            ("inactive", False),
        ]

        for thread_id, was_archived in cases:
            with self.subTest(thread_id=thread_id, was_archived=was_archived):
                with tempfile.TemporaryDirectory() as tempdir:
                    self.write_thread_registry(tempdir)

                    with ExitStack() as stack:
                        for manager in self.isolated_thread_storage(tempdir):
                            stack.enter_context(manager)

                        response = self.client.post(f"/threads/{thread_id}/restore")

                    self.assertEqual(response.status_code, 200)

                    payload = response.json()
                    registry = self.read_thread_registry(tempdir)

                    self.assertEqual(payload["status"], "success")
                    self.assertEqual(payload["thread"]["thread_id"], thread_id)
                    self.assertFalse(payload["thread"]["archived"])
                    self.assertEqual(payload["active_thread_id"], thread_id)
                    self.assertEqual(registry["active_thread_id"], thread_id)
                    self.assertFalse(registry["threads"][thread_id]["archived"])


if __name__ == "__main__":
    unittest.main()
