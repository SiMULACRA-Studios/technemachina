import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
