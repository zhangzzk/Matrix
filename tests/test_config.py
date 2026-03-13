import tempfile
import unittest
from pathlib import Path

from dreamdive.config import SimulationSettings, load_dotenv_values, resolve_dotenv_path


class ConfigTests(unittest.TestCase):
    def test_load_dotenv_values_parses_quotes_and_export_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                (
                    "# comment\n"
                    "DREAMDIVE_LLM_MOONSHOT_API_KEY=\"moonshot-key\"\n"
                    "export DREAMDIVE_LLM_GEMINI_API_KEY='gemini-key'\n"
                    "IGNORED_LINE\n"
                ),
                encoding="utf-8",
            )

            values = load_dotenv_values(env_path)

            self.assertEqual(values["DREAMDIVE_LLM_MOONSHOT_API_KEY"], "moonshot-key")
            self.assertEqual(values["DREAMDIVE_LLM_GEMINI_API_KEY"], "gemini-key")
            self.assertNotIn("IGNORED_LINE", values)

    def test_from_env_uses_dotenv_and_environment_overrides_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                (
                    "DREAMDIVE_LLM_PROVIDER_ORDER=['moonshot','gemini','openai']\n"
                    "DREAMDIVE_LLM_MOONSHOT_API_KEY=from-dotenv\n"
                    "DREAMDIVE_PERSISTENCE_BACKEND=postgres\n"
                ),
                encoding="utf-8",
            )

            settings = SimulationSettings.from_env(
                {
                    "DREAMDIVE_LLM_MOONSHOT_API_KEY": "from-environment",
                },
                env_file=env_path,
            )

            self.assertEqual(settings.llm_moonshot_api_key, "from-environment")
            self.assertEqual(settings.llm_provider_order, ["moonshot", "gemini", "openai"])
            self.assertEqual(settings.persistence_backend, "postgres")

    def test_from_env_maps_legacy_primary_and_fallback_to_provider_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("", encoding="utf-8")
            settings = SimulationSettings.from_env(
                {
                    "DREAMDIVE_LLM_PRIMARY_NAME": "moonshot",
                    "DREAMDIVE_LLM_PRIMARY_API_KEY": "moonshot-key",
                    "DREAMDIVE_LLM_PRIMARY_MAX_TOKENS": "4096",
                    "DREAMDIVE_LLM_FALLBACK_NAME": "gemini",
                    "DREAMDIVE_LLM_FALLBACK_API_KEY": "gemini-key",
                },
                env_file=env_path,
            )

            self.assertEqual(
                settings.llm_provider_order,
                ["moonshot", "gemini", "openai", "qwen"],
            )
            self.assertEqual(settings.llm_moonshot_api_key, "moonshot-key")
            self.assertEqual(settings.llm_gemini_api_key, "gemini-key")
            self.assertEqual(settings.llm_moonshot_max_tokens, 4096)

    def test_active_llm_profiles_skip_unconfigured_providers(self) -> None:
        settings = SimulationSettings(
            llm_provider_order=["moonshot", "gemini", "openai", "qwen"],
            llm_moonshot_api_key="moonshot-key",
            llm_openai_api_key="openai-key",
        )

        self.assertEqual(
            [profile.name for profile in settings.active_llm_profiles()],
            ["moonshot", "openai"],
        )

    def test_profile_for_provider_uses_provider_specific_max_tokens(self) -> None:
        settings = SimulationSettings(llm_openai_max_tokens=12000)

        profile = settings.profile_for_provider("openai")

        self.assertEqual(profile.max_tokens, 12000)

    def test_default_gemini_model_uses_documented_stable_name(self) -> None:
        settings = SimulationSettings()

        self.assertEqual(settings.llm_gemini_model, "gemini-2.5-flash-lite")

    def test_resolve_dotenv_path_searches_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "src" / "dreamdive"
            nested.mkdir(parents=True)
            env_path = root / ".env"
            env_path.write_text("DREAMDIVE_LLM_MOONSHOT_API_KEY=from-parent\n", encoding="utf-8")

            resolved = resolve_dotenv_path(nested)
            values = load_dotenv_values(resolved)

            self.assertEqual(resolved.resolve(), env_path.resolve())
            self.assertEqual(values["DREAMDIVE_LLM_MOONSHOT_API_KEY"], "from-parent")


if __name__ == "__main__":
    unittest.main()
