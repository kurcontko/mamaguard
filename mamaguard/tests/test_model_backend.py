import os
import unittest
from unittest.mock import patch

from mamaguard.shared.model_backend import build_agent_model


class TestModelBackend(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.copy()
        for key in (
            "MAMAGUARD_MODEL_BACKEND",
            "MAMAGUARD_GEMINI_MODEL",
            "MAMAGUARD_MODEL",
            "OPENAI_MODEL",
            "MAMAGUARD_OPENAI_BASE_URL",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
            "MAMAGUARD_OPENAI_API_KEY",
            "OPENAI_API_KEY",
        ):
            os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)

    def test_default_backend_is_gemini_flash(self):
        self.assertEqual(build_agent_model(), "gemini-2.5-flash")

    def test_custom_gemini_model(self):
        os.environ["MAMAGUARD_GEMINI_MODEL"] = "gemini-test"
        self.assertEqual(build_agent_model(), "gemini-test")

    def test_openai_backend_requires_configuration(self):
        os.environ["MAMAGUARD_MODEL_BACKEND"] = "openai"
        with self.assertRaisesRegex(RuntimeError, "MAMAGUARD_MODEL"):
            build_agent_model()

    def test_openai_backend_builds_litellm(self):
        os.environ["MAMAGUARD_MODEL_BACKEND"] = "openai"
        os.environ["MAMAGUARD_MODEL"] = "openrouter/test-model"
        os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
        os.environ["OPENAI_API_KEY"] = "test-key"

        with patch("google.adk.models.lite_llm.LiteLlm") as lite_llm:
            build_agent_model()

        lite_llm.assert_called_once_with(
            model="openai/openrouter/test-model",
            api_base="https://openrouter.ai/api/v1",
            api_key="test-key",
        )

    def test_openai_prefix_is_not_duplicated(self):
        os.environ["MAMAGUARD_MODEL_BACKEND"] = "openrouter"
        os.environ["OPENAI_MODEL"] = "openai/google/gemini-2.5-flash"
        os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
        os.environ["OPENAI_API_KEY"] = "test-key"

        with patch("google.adk.models.lite_llm.LiteLlm") as lite_llm:
            build_agent_model()

        self.assertEqual(lite_llm.call_args.kwargs["model"], "openai/google/gemini-2.5-flash")


if __name__ == "__main__":
    unittest.main()

