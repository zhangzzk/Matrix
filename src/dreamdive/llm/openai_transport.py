from __future__ import annotations

import importlib.util
import json
import socket
from typing import Any, Callable, Dict, Optional
from urllib import request
from urllib.error import HTTPError, URLError

from dreamdive.config import LLMProfileSettings, SimulationSettings, get_settings
from dreamdive.schemas import PromptRequest


class TransportError(RuntimeError):
    pass


def _get_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def openai_sdk_available() -> bool:
    return importlib.util.find_spec("openai") is not None


class OpenAICompatibleTransport:
    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def complete(self, profile: LLMProfileSettings, prompt: PromptRequest) -> str:
        return self._complete_sync(profile, prompt)

    def _complete_sync(self, profile: LLMProfileSettings, prompt: PromptRequest) -> str:
        self._validate_profile(profile)
        endpoint = profile.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": profile.model,
            "max_tokens": min(prompt.max_tokens, profile.max_tokens),
            "stream": prompt.stream,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
        }
        payload.update(self._provider_request_options(profile, prompt))
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {profile.api_key}",
        }

        try:
            response = self._urlopen(endpoint, body, headers)
        except HTTPError as exc:
            detail = self._read_http_error(exc)
            message = f"LLM HTTP error: {exc.code}"
            if detail:
                message += f" - {detail}"
            raise TransportError(message) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise TransportError(
                f"LLM transport timed out after {int(self.timeout_seconds)} seconds"
            ) from exc
        except URLError as exc:
            raise TransportError("LLM transport could not reach the endpoint") from exc

        try:
            if prompt.stream:
                return self._extract_stream_content(response)
            parsed = json.loads(response.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise TransportError("LLM transport received invalid JSON") from exc

        return self._extract_content(parsed)

    def _urlopen(self, url: str, body: bytes, headers: Dict[str, str]) -> bytes:
        req = request.Request(url=url, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            return response.read()

    @staticmethod
    def _validate_profile(profile: LLMProfileSettings) -> None:
        if not profile.api_key.strip():
            raise TransportError(f"LLM API key is missing for profile '{profile.name}'")

    @staticmethod
    def _provider_request_options(
        profile: LLMProfileSettings,
        prompt: PromptRequest,
    ) -> Dict[str, Any]:
        # Qwen 3.5 models enable thinking by default. For schema-bound JSON prompts,
        # explicitly disable it to reduce latency and avoid malformed structured output.
        if (
            profile.name == "qwen"
            and bool(prompt.metadata.get("response_schema"))
        ):
            return {"enable_thinking": False}
        return {}

    @staticmethod
    def _read_http_error(error: HTTPError) -> str:
        try:
            payload = error.read().decode("utf-8", errors="replace").strip()
        except Exception:
            return ""
        if not payload:
            return ""
        return payload[:500]

    @staticmethod
    def _extract_content(payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise TransportError("LLM response contained no choices")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            if parts:
                return "".join(parts)
        raise TransportError("LLM response content was missing or unsupported")

    @classmethod
    def _extract_stream_content(cls, payload_bytes: bytes) -> str:
        parts = []
        for raw_line in payload_bytes.decode("utf-8").splitlines():
            line = raw_line.strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError as exc:
                raise TransportError("LLM transport received invalid streaming JSON") from exc
            choices = payload.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str):
                parts.append(content)
                continue
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
        if parts:
            return "".join(parts)
        raise TransportError("LLM streaming response contained no text content")


class OpenAISDKTransport:
    def __init__(
        self,
        timeout_seconds: float = 30.0,
        openai_client_factory: Optional[Callable[..., object]] = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._openai_client_factory = openai_client_factory
        self._clients: Dict[tuple[str, str], object] = {}

    async def complete(self, profile: LLMProfileSettings, prompt: PromptRequest) -> str:
        return self._complete_sync(profile, prompt)

    def _complete_sync(self, profile: LLMProfileSettings, prompt: PromptRequest) -> str:
        OpenAICompatibleTransport._validate_profile(profile)
        client = self._client_for_profile(profile)
        request_kwargs = {
            "model": profile.model,
            "max_tokens": min(prompt.max_tokens, profile.max_tokens),
            "stream": prompt.stream,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
        }
        provider_options = OpenAICompatibleTransport._provider_request_options(profile, prompt)
        if provider_options:
            request_kwargs["extra_body"] = provider_options
        response = client.chat.completions.create(
            **request_kwargs,
        )
        if prompt.stream:
            return self._extract_stream_content(response)
        return self._extract_content(response)

    def _client_for_profile(self, profile: LLMProfileSettings) -> object:
        key = (profile.base_url, profile.api_key)
        existing = self._clients.get(key)
        if existing is not None:
            return existing
        factory = self._openai_client_factory or self._default_openai_client_factory
        client = factory(
            api_key=profile.api_key,
            base_url=profile.base_url,
            timeout=self.timeout_seconds,
        )
        self._clients[key] = client
        return client

    @staticmethod
    def _default_openai_client_factory(**kwargs) -> object:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise TransportError(
                "OpenAI SDK transport requested but the `openai` package is not installed"
            ) from exc
        return OpenAI(**kwargs)

    @classmethod
    def _extract_content(cls, payload: Any) -> str:
        choices = _get_field(payload, "choices", []) or []
        if not choices:
            raise TransportError("LLM response contained no choices")

        message = _get_field(choices[0], "message", {}) or {}
        content = _get_field(message, "content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if _get_field(item, "type") == "text":
                    parts.append(str(_get_field(item, "text", "")))
            if parts:
                return "".join(parts)
        raise TransportError("LLM response content was missing or unsupported")

    @classmethod
    def _extract_stream_content(cls, stream: Any) -> str:
        parts = []
        for chunk in stream:
            choices = _get_field(chunk, "choices", []) or []
            if not choices:
                continue
            delta = _get_field(choices[0], "delta", {}) or {}
            content = _get_field(delta, "content")
            if isinstance(content, str):
                parts.append(content)
                continue
            if isinstance(content, list):
                for item in content:
                    if _get_field(item, "type") == "text":
                        parts.append(str(_get_field(item, "text", "")))
        if parts:
            return "".join(parts)
        raise TransportError("LLM streaming response contained no text content")


def build_transport(settings: Optional[SimulationSettings] = None) -> object:
    active_settings = settings or get_settings()
    backend = active_settings.llm_transport.lower().strip()
    timeout_seconds = active_settings.llm_timeout_seconds

    if backend == "openai_sdk":
        return OpenAISDKTransport(timeout_seconds=timeout_seconds)
    if backend == "urllib":
        return OpenAICompatibleTransport(timeout_seconds=timeout_seconds)
    if backend == "auto":
        if openai_sdk_available():
            return OpenAISDKTransport(timeout_seconds=timeout_seconds)
        return OpenAICompatibleTransport(timeout_seconds=timeout_seconds)
    raise ValueError(f"Unsupported LLM transport backend: {active_settings.llm_transport}")
