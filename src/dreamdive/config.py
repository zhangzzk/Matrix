import os
import ast
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, get_origin

from pydantic import BaseModel, Field


class LLMProfileSettings(BaseModel):
    name: str
    api_key: str = ""
    base_url: str
    model: str
    max_tokens: int = 8_192


LLM_PROVIDER_DEFAULTS: Dict[str, Dict[str, str]] = {
    "moonshot": {
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-k2.5",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "qwen": {
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.5-plus",
    },
}


class SimulationSettings(BaseModel):
    persistence_backend: str = "session"
    database_url: str = Field(
        default="postgresql+psycopg://dreamdive:dreamdive@localhost:5432/dreamdive"
    )
    debug_mode: bool = False
    debug_record_llm: bool = True
    debug_dir: str = ""
    llm_transport: str = "auto"
    llm_timeout_seconds: float = 90.0
    embedding_dimensions: int = 1_536
    working_memory_size: int = 5
    retrieved_memory_candidates: int = 20

    tick_spotlight_min_minutes: int = 1
    tick_spotlight_max_minutes: int = 30
    tick_foreground_min_minutes: int = 60
    tick_foreground_max_minutes: int = 480
    tick_background_min_minutes: int = 1440
    tick_background_max_minutes: int = 10080

    salience_spotlight_threshold: float = 0.8
    salience_foreground_threshold: float = 0.4
    invalidation_emotion_threshold: float = 0.4
    invalidation_knowledge_threshold: float = 0.6
    horizon_multiplier: float = 4.0
    max_horizon_ticks: int = 50
    tick_max_events: int = 15

    compression_interval_ticks: int = 15
    compression_high_salience_threshold: float = 0.7
    compression_discard_threshold: float = 0.2
    arc_update_interval_ticks: int = 8
    llm_retry_attempts: int = 2
    llm_retry_delay_seconds: float = 1.0

    llm_provider_order: list[str] = Field(
        default_factory=lambda: ["moonshot", "gemini", "openai", "qwen"]
    )

    llm_moonshot_api_key: str = ""
    llm_moonshot_base_url: str = LLM_PROVIDER_DEFAULTS["moonshot"]["base_url"]
    llm_moonshot_model: str = LLM_PROVIDER_DEFAULTS["moonshot"]["model"]
    llm_moonshot_max_tokens: int = 8_192

    llm_gemini_api_key: str = ""
    llm_gemini_base_url: str = LLM_PROVIDER_DEFAULTS["gemini"]["base_url"]
    llm_gemini_model: str = LLM_PROVIDER_DEFAULTS["gemini"]["model"]
    llm_gemini_max_tokens: int = 8_192

    llm_openai_api_key: str = ""
    llm_openai_base_url: str = LLM_PROVIDER_DEFAULTS["openai"]["base_url"]
    llm_openai_model: str = LLM_PROVIDER_DEFAULTS["openai"]["model"]
    llm_openai_max_tokens: int = 8_192

    llm_qwen_api_key: str = ""
    llm_qwen_base_url: str = LLM_PROVIDER_DEFAULTS["qwen"]["base_url"]
    llm_qwen_model: str = LLM_PROVIDER_DEFAULTS["qwen"]["model"]
    llm_qwen_max_tokens: int = 8_192

    def primary_profile(self) -> LLMProfileSettings:
        profiles = self.active_llm_profiles()
        if not profiles:
            raise ValueError("No LLM providers are configured")
        return profiles[0]

    def fallback_profile(self) -> LLMProfileSettings:
        profiles = self.active_llm_profiles()
        if len(profiles) < 2:
            raise ValueError("No fallback LLM provider is configured")
        return profiles[1]

    def fallback_profiles(self) -> list[LLMProfileSettings]:
        return self.active_llm_profiles()[1:]

    def llm_profiles(self) -> list[LLMProfileSettings]:
        ordered_names = self._normalized_provider_order()
        return [self.profile_for_provider(name) for name in ordered_names]

    def active_llm_profiles(self) -> list[LLMProfileSettings]:
        profiles = self.llm_profiles()
        configured = [profile for profile in profiles if profile.api_key.strip()]
        return configured or profiles

    def profile_for_provider(self, provider_name: str) -> LLMProfileSettings:
        normalized = provider_name.strip().lower()
        if normalized not in LLM_PROVIDER_DEFAULTS:
            known = ", ".join(sorted(LLM_PROVIDER_DEFAULTS))
            raise ValueError(f"Unsupported LLM provider '{provider_name}'. Known providers: {known}")
        return LLMProfileSettings(
            name=normalized,
            api_key=str(getattr(self, f"llm_{normalized}_api_key")),
            base_url=str(getattr(self, f"llm_{normalized}_base_url")),
            model=str(getattr(self, f"llm_{normalized}_model")),
            max_tokens=int(getattr(self, f"llm_{normalized}_max_tokens")),
        )

    def _normalized_provider_order(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for raw_name in self.llm_provider_order:
            normalized = str(raw_name).strip().lower()
            if not normalized or normalized in seen:
                continue
            if normalized not in LLM_PROVIDER_DEFAULTS:
                known = ", ".join(sorted(LLM_PROVIDER_DEFAULTS))
                raise ValueError(
                    f"Unsupported LLM provider '{raw_name}' in llm_provider_order. "
                    f"Known providers: {known}"
                )
            ordered.append(normalized)
            seen.add(normalized)
        if not ordered:
            raise ValueError("llm_provider_order must include at least one provider")
        return ordered

    @classmethod
    def from_env(
        cls,
        environ: Optional[Dict[str, str]] = None,
        *,
        env_file: Optional[Path] = None,
    ) -> "SimulationSettings":
        env = {
            **load_dotenv_values(env_file),
            **dict(environ or os.environ),
        }
        env = _with_legacy_llm_aliases(env)
        values: Dict[str, object] = {}
        for field_name, field_info in cls.model_fields.items():
            env_name = f"DREAMDIVE_{field_name.upper()}"
            if env_name in env:
                values[field_name] = _coerce_env_value(env[env_name], field_info.annotation)
        return cls.model_validate(values)


def _with_legacy_llm_aliases(env: Dict[str, str]) -> Dict[str, str]:
    normalized = dict(env)
    if "DREAMDIVE_LLM_PROVIDER_ORDER" not in normalized:
        primary_name = normalized.get("DREAMDIVE_LLM_PRIMARY_NAME", "").strip().lower()
        fallback_name = normalized.get("DREAMDIVE_LLM_FALLBACK_NAME", "").strip().lower()
        derived_order = [name for name in [primary_name, fallback_name] if name]
        for provider_name in LLM_PROVIDER_DEFAULTS:
            if provider_name not in derived_order:
                derived_order.append(provider_name)
        if derived_order:
            normalized["DREAMDIVE_LLM_PROVIDER_ORDER"] = str(derived_order)

    legacy_slots = (
        (
            "DREAMDIVE_LLM_PRIMARY_NAME",
            "DREAMDIVE_LLM_PRIMARY_API_KEY",
            "DREAMDIVE_LLM_PRIMARY_BASE_URL",
            "DREAMDIVE_LLM_PRIMARY_MODEL",
            "DREAMDIVE_LLM_PRIMARY_MAX_TOKENS",
        ),
        (
            "DREAMDIVE_LLM_FALLBACK_NAME",
            "DREAMDIVE_LLM_FALLBACK_API_KEY",
            "DREAMDIVE_LLM_FALLBACK_BASE_URL",
            "DREAMDIVE_LLM_FALLBACK_MODEL",
            "DREAMDIVE_LLM_FALLBACK_MAX_TOKENS",
        ),
    )
    for name_key, api_key_key, base_url_key, model_key, max_tokens_key in legacy_slots:
        provider_name = normalized.get(name_key, "").strip().lower()
        if provider_name not in LLM_PROVIDER_DEFAULTS:
            continue
        if api_key_key in normalized:
            normalized.setdefault(
                f"DREAMDIVE_LLM_{provider_name.upper()}_API_KEY",
                normalized[api_key_key],
            )
        if base_url_key in normalized:
            normalized.setdefault(
                f"DREAMDIVE_LLM_{provider_name.upper()}_BASE_URL",
                normalized[base_url_key],
            )
        if model_key in normalized:
            normalized.setdefault(
                f"DREAMDIVE_LLM_{provider_name.upper()}_MODEL",
                normalized[model_key],
            )
        if max_tokens_key in normalized:
            normalized.setdefault(
                f"DREAMDIVE_LLM_{provider_name.upper()}_MAX_TOKENS",
                normalized[max_tokens_key],
            )
    return normalized


def _coerce_env_value(raw_value: Any, annotation: Any) -> Any:
    if not isinstance(raw_value, str):
        return raw_value
    if get_origin(annotation) is list:
        return _parse_env_list(raw_value)
    return raw_value


def _parse_env_list(raw_value: str) -> list[str]:
    text = raw_value.strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        raise ValueError(f"Expected list value, got: {raw_value}")
    return [part.strip() for part in text.split(",") if part.strip()]


def load_dotenv_values(env_file: Optional[Path] = None) -> Dict[str, str]:
    path = env_file or resolve_dotenv_path()
    if path is None:
        return {}
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_dotenv_path(start_dir: Optional[Path] = None) -> Optional[Path]:
    current = (start_dir or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / ".env"
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def get_settings() -> SimulationSettings:
    return SimulationSettings.from_env()
