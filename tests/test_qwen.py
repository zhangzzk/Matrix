
import os
import json
import asyncio
from dreamdive.config import get_settings
from dreamdive.llm.openai_transport import build_transport
from dreamdive.schemas import PromptRequest

async def test_qwen():
    settings = get_settings()
    # Find the qwen profile
    qwen_profile = next((p for p in settings.llm_profiles() if p.name == "qwen"), None)
    if not qwen_profile:
        print("Qwen profile not found in settings")
        return

    print(f"Testing Qwen with:")
    print(f"  Base URL: {qwen_profile.base_url}")
    print(f"  Model: {qwen_profile.model}")
    print(f"  API Key: {qwen_profile.api_key[:5]}...{qwen_profile.api_key[-5:]}")

    transport = build_transport(settings)
    prompt = PromptRequest(
        system="You are a helpful assistant.",
        user="Say hello.",
        metadata={"prompt_name": "test"}
    )

    try:
        print("\nAttempting completion...")
        # We use OpenAICompatibleTransport or OpenAISDKTransport depending on build_transport
        # For direct testing, let's use the one from settings profile
        response = await transport.complete(qwen_profile, prompt)
        print(f"\nSuccess! Response: {response}")
    except Exception as e:
        print(f"\nFAILED with error type: {type(e).__name__}")
        print(f"Error message: {e}")
        if hasattr(e, '__cause__') and e.__cause__:
            print(f"Cause: {e.__cause__}")

if __name__ == "__main__":
    asyncio.run(test_qwen())
