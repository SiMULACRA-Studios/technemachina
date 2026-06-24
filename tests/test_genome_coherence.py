import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_ROOT = REPO_ROOT / "daemon"

if str(DAEMON_ROOT) not in sys.path:
    sys.path.insert(0, str(DAEMON_ROOT))

import brain_router
import genome
from providers import gemini_provider, openrouter_provider


class GenomeCoherenceTests(unittest.TestCase):
    def test_load_genome_reads_canonical_markdown_fresh(self):
        with tempfile.TemporaryDirectory() as tempdir:
            genome_path = Path(tempdir) / "daemon_genome.md"

            with patch.object(genome, "GENOME_PATH", genome_path):
                genome_path.write_text("first genome", encoding="utf-8")
                self.assertEqual(genome.load_genome(), "first genome")

                genome_path.write_text("updated genome", encoding="utf-8")
                self.assertEqual(genome.load_genome(), "updated genome")

    def test_genome_summary_uses_executable_provider_order(self):
        with patch.object(brain_router, "PROVIDER_ORDER", ["openrouter", "gemini"]):
            summary = genome.get_genome_summary()

        self.assertIn("Current executable provider order: openrouter -> gemini.", summary)
        self.assertNotIn("Gemini primary brain, OpenRouter fallback brain", summary)
        self.assertNotIn("Gemini primary provider", summary)
        self.assertNotIn("automatic Gemini to OpenRouter failover", summary)

    def test_checked_in_genome_describes_current_provider_order(self):
        text = genome.load_genome()

        self.assertIn("Current executable auto provider order:", text)
        self.assertIn("- OpenRouter", text)
        self.assertIn("- Gemini", text)
        self.assertIn("automatic provider failover using the executable router order", text)

        stale_claims = [
            "Gemini primary provider",
            "OpenRouter fallback provider",
            "automatic Gemini to OpenRouter failover",
            "Primary brain:",
            "Fallback brain:",
        ]

        for claim in stale_claims:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, text)

    def test_genome_summary_carries_stable_current_architecture_concepts(self):
        summary = genome.get_genome_summary()

        required_concepts = [
            "governed memory",
            "Decision Ledger",
            "Synapse",
            "Companion",
            "BLOCKED debug requests",
            "Confirmed unsafe requests must not trigger provider-shopping.",
        ]

        for concept in required_concepts:
            with self.subTest(concept=concept):
                self.assertIn(concept, summary)

    def test_provider_prompts_include_runtime_derived_genome_summary(self):
        generated = Mock(text="Gemini answer.")
        client = Mock()
        client.models.generate_content.return_value = generated

        with (
            patch.object(gemini_provider, "get_client", return_value=client),
            patch.object(gemini_provider, "get_context_summary", return_value="context"),
            patch.object(
                gemini_provider,
                "get_genome_summary",
                return_value="runtime-derived genome summary",
            ) as summary_mock,
        ):
            response = gemini_provider.query("Explain the router.")

        self.assertEqual(response, "Gemini answer.")
        summary_mock.assert_called_once_with()

        contents = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("Daemon Genome:\nruntime-derived genome summary", contents)
        self.assertIn("Runtime Brain Provider: gemini", contents)

    def test_openrouter_prompt_includes_runtime_derived_genome_summary(self):
        response_body = json.dumps({
            "choices": [
                {
                    "message": {
                        "content": "OpenRouter answer.",
                    }
                }
            ]
        }).encode("utf-8")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return response_body

        captured = {}

        def fake_urlopen(request, timeout):
            captured["data"] = request.data.decode("utf-8")
            captured["timeout"] = timeout
            return FakeResponse()

        with (
            patch.object(openrouter_provider, "get_api_key", return_value="test-key"),
            patch.object(openrouter_provider, "get_context_summary", return_value="context"),
            patch.object(
                openrouter_provider,
                "get_genome_summary",
                return_value="runtime-derived genome summary",
            ) as summary_mock,
            patch.object(openrouter_provider.urllib.request, "urlopen", side_effect=fake_urlopen),
        ):
            response = openrouter_provider.call_openrouter("test/model", "Explain the router.")

        self.assertEqual(response, "OpenRouter answer.")
        summary_mock.assert_called_once_with()

        payload = json.loads(captured["data"])
        prompt = payload["messages"][0]["content"]
        self.assertIn("Daemon Genome:\nruntime-derived genome summary", prompt)
        self.assertIn("Runtime Brain Provider: openrouter", prompt)
        self.assertIn("Runtime Provider Model: test/model", prompt)

    def test_security_governance_map_matches_executable_provider_order(self):
        doc = (DAEMON_ROOT / "docs" / "security_governance_map.md").read_text(
            encoding="utf-8"
        )
        provider_order = " -> ".join(brain_router.PROVIDER_ORDER)

        self.assertIn(f"auto: {provider_order}", doc)
        self.assertNotIn("auto: gemini -> openrouter", doc)


if __name__ == "__main__":
    unittest.main()
