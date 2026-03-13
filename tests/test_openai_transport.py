import json
import socket
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from dreamdive.config import LLMProfileSettings, SimulationSettings
from dreamdive.llm.openai_transport import (
    OpenAICompatibleTransport,
    OpenAISDKTransport,
    TransportError,
    build_transport,
)
from dreamdive.schemas import PromptRequest


class FakeTransport(OpenAICompatibleTransport):
    def __init__(self, payload):
        super().__init__(timeout_seconds=0.01)
        self.payload = payload
        self.calls = []

    def _urlopen(self, url, body, headers):
        self.calls.append((url, body, headers))
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class OpenAICompatibleTransportTests(unittest.TestCase):
    def test_transport_raises_clear_error_when_api_key_missing(self) -> None:
        transport = FakeTransport({"choices": []})
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        with self.assertRaises(TransportError) as ctx:
            transport._complete_sync(profile, PromptRequest(system="s", user="u"))

        self.assertIn("API key is missing", str(ctx.exception))

    def test_transport_posts_openai_shape_and_extracts_string_content(self) -> None:
        transport = FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"ok": true}'
                        }
                    }
                ]
            }
        )
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="secret",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )
        prompt = PromptRequest(system="system text", user="user text", max_tokens=321)

        result = transport._complete_sync(profile, prompt)

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(transport.calls[0][0], "https://api.moonshot.ai/v1/chat/completions")
        body = json.loads(transport.calls[0][1].decode("utf-8"))
        self.assertEqual(body["model"], "kimi-k2.5")
        self.assertEqual(body["max_tokens"], 321)
        self.assertFalse(body["stream"])
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(transport.calls[0][2]["Authorization"], "Bearer secret")

    def test_transport_does_not_clip_prompt_max_tokens_to_old_profile_default(self) -> None:
        transport = FakeTransport({"choices": [{"message": {"content": '{"ok": true}'}}]})
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="secret",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        transport._complete_sync(
            profile,
            PromptRequest(system="system text", user="user text", max_tokens=5000),
        )

        body = json.loads(transport.calls[0][1].decode("utf-8"))
        self.assertEqual(body["max_tokens"], 5000)

    def test_transport_supports_segmented_content(self) -> None:
        transport = FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": '{"hello": '},
                                {"type": "text", "text": '"world"}'},
                            ]
                        }
                    }
                ]
            }
        )
        profile = LLMProfileSettings(
            name="gemini",
            api_key="secret",
            base_url="https://example.com/v1beta/openai",
            model="gemini-3.1-flash-lite-preview",
        )

        result = transport._complete_sync(profile, PromptRequest(system="s", user="u"))

        self.assertEqual(result, '{"hello": "world"}')

    def test_transport_supports_streaming_sse_deltas(self) -> None:
        transport = FakeTransport(
            {
                "choices": [
                    {
                        "delta": {
                            "content": '{"hello": "'
                        }
                    }
                ]
            }
        )
        transport.payload = (
            b'data: {"choices":[{"delta":{"content":"{\\"hello\\": \\""}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"world\\"}"}}]}\n\n'
            b"data: [DONE]\n"
        )
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="secret",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        result = transport._complete_sync(
            profile,
            PromptRequest(system="s", user="u", stream=True),
        )

        self.assertEqual(result, '{"hello": "world"}')
        body = json.loads(transport.calls[0][1].decode("utf-8"))
        self.assertTrue(body["stream"])

    def test_transport_disables_qwen_thinking_for_structured_prompts(self) -> None:
        transport = FakeTransport({"choices": [{"message": {"content": '{"ok": true}'}}]})
        profile = LLMProfileSettings(
            name="qwen",
            api_key="secret",
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            model="qwen3.5-flash",
        )

        transport._complete_sync(
            profile,
            PromptRequest(
                system="s",
                user="u",
                metadata={"response_schema": "AccumulatedExtraction"},
            ),
        )

        body = json.loads(transport.calls[0][1].decode("utf-8"))
        self.assertFalse(body["enable_thinking"])

    def test_transport_raises_on_missing_choices(self) -> None:
        transport = FakeTransport({"choices": []})
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="secret",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        with self.assertRaises(TransportError):
            transport._complete_sync(profile, PromptRequest(system="s", user="u"))

    def test_transport_includes_http_error_body_excerpt(self) -> None:
        transport = OpenAICompatibleTransport(timeout_seconds=0.01)
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="secret",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        def raising_urlopen(_url, _body, _headers):
            raise HTTPError(
                url="https://api.moonshot.ai/v1/chat/completions",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=None,
            )

        with patch.object(transport, "_urlopen", side_effect=raising_urlopen), patch.object(
            transport,
            "_read_http_error",
            return_value='{"error":"bad payload"}',
        ):
            with self.assertRaises(TransportError) as ctx:
                transport._complete_sync(profile, PromptRequest(system="s", user="u"))

        self.assertIn("HTTP error: 400", str(ctx.exception))
        self.assertIn("bad payload", str(ctx.exception))

    def test_transport_wraps_socket_timeout_with_clear_message(self) -> None:
        transport = OpenAICompatibleTransport(timeout_seconds=90.0)
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="secret",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        def raising_urlopen(_url, _body, _headers):
            raise socket.timeout("The read operation timed out")

        with patch.object(transport, "_urlopen", side_effect=raising_urlopen):
            with self.assertRaises(TransportError) as ctx:
                transport._complete_sync(profile, PromptRequest(system="s", user="u"))

        self.assertIn("timed out after 90 seconds", str(ctx.exception))


class FakeSDKCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeSDKClient:
    def __init__(self, responses):
        self.completions = FakeSDKCompletions(responses)
        self.chat = type("Chat", (), {"completions": self.completions})()


class OpenAISDKTransportTests(unittest.TestCase):
    def test_sdk_transport_posts_chat_completion_shape(self) -> None:
        fake_client = FakeSDKClient(
            [
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"ok": true}'
                            }
                        }
                    ]
                }
            ]
        )
        transport = OpenAISDKTransport(
            timeout_seconds=1.5,
            openai_client_factory=lambda **kwargs: fake_client,
        )
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="secret",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        result = transport._complete_sync(
            profile,
            PromptRequest(system="system text", user="user text", max_tokens=321),
        )

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(fake_client.completions.calls[0]["model"], "kimi-k2.5")
        self.assertEqual(fake_client.completions.calls[0]["max_tokens"], 321)
        self.assertFalse(fake_client.completions.calls[0]["stream"])
        self.assertEqual(fake_client.completions.calls[0]["messages"][0]["role"], "system")

    def test_sdk_transport_supports_streaming_chunks(self) -> None:
        fake_client = FakeSDKClient(
            [
                [
                    {"choices": [{"delta": {"content": '{"hello": "'}}]},
                    {"choices": [{"delta": {"content": 'world"}'}}]},
                ]
            ]
        )
        transport = OpenAISDKTransport(
            openai_client_factory=lambda **kwargs: fake_client,
        )
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="secret",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        result = transport._complete_sync(
            profile,
            PromptRequest(system="s", user="u", stream=True),
        )

        self.assertEqual(result, '{"hello": "world"}')
        self.assertTrue(fake_client.completions.calls[0]["stream"])

    def test_sdk_transport_passes_qwen_extra_body_for_structured_prompts(self) -> None:
        fake_client = FakeSDKClient(
            [
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"ok": true}'
                            }
                        }
                    ]
                }
            ]
        )
        transport = OpenAISDKTransport(
            openai_client_factory=lambda **kwargs: fake_client,
        )
        profile = LLMProfileSettings(
            name="qwen",
            api_key="secret",
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            model="qwen3.5-flash",
        )

        transport._complete_sync(
            profile,
            PromptRequest(
                system="s",
                user="u",
                metadata={"response_schema": "AccumulatedExtraction"},
            ),
        )

        self.assertEqual(
            fake_client.completions.calls[0]["extra_body"],
            {"enable_thinking": False},
        )

    def test_sdk_transport_raises_clear_error_when_api_key_missing(self) -> None:
        fake_client = FakeSDKClient([])
        transport = OpenAISDKTransport(
            openai_client_factory=lambda **kwargs: fake_client,
        )
        profile = LLMProfileSettings(
            name="moonshot",
            api_key="",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        )

        with self.assertRaises(TransportError) as ctx:
            transport._complete_sync(profile, PromptRequest(system="s", user="u"))

        self.assertIn("API key is missing", str(ctx.exception))

    def test_build_transport_prefers_sdk_when_available(self) -> None:
        settings = SimulationSettings(llm_transport="auto", llm_timeout_seconds=12.0)
        with patch(
            "dreamdive.llm.openai_transport.openai_sdk_available",
            return_value=True,
        ):
            transport = build_transport(settings)
        self.assertIsInstance(transport, OpenAISDKTransport)
        self.assertEqual(transport.timeout_seconds, 12.0)

    def test_build_transport_falls_back_to_urllib_when_sdk_missing(self) -> None:
        settings = SimulationSettings(llm_transport="auto", llm_timeout_seconds=7.0)
        with patch(
            "dreamdive.llm.openai_transport.openai_sdk_available",
            return_value=False,
        ):
            transport = build_transport(settings)
        self.assertIsInstance(transport, OpenAICompatibleTransport)
        self.assertEqual(transport.timeout_seconds, 7.0)


if __name__ == "__main__":
    unittest.main()
