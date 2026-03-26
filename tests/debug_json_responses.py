"""Debug why some models fail JSON validation."""
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dreamdive.llm.openai_transport import OpenAICompatibleTransport
from dreamdive.config import LLMProfileSettings
from dreamdive.schemas import PromptRequest

def test_provider(name, api_key, base_url, model):
    """Test a provider and show raw response."""
    print(f"\n{'='*70}")
    print(f"Testing: {name.upper()} ({model})")
    print(f"{'='*70}")

    transport = OpenAICompatibleTransport(timeout_seconds=60.0)
    profile = LLMProfileSettings(
        name=name,
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=4000,
    )

    prompt = PromptRequest(
        system="You are a helpful assistant. Return ONLY valid JSON, no other text.",
        user="""Return this exact JSON structure with Chinese content:
{
  "emotional_state": {
    "dominant": "沮丧但保持冷静",
    "secondary": ["焦虑", "期待"]
  },
  "immediate_tension": "刚被拒绝，站在雨中思考下一步",
  "unspoken_subtext": "不想让别人看到自己的脆弱",
  "physical_state": {
    "injuries_or_constraints": "淋雨有些冷",
    "location": "学校门口",
    "current_activity": "站着发呆"
  },
  "knowledge_state": {
    "new_knowledge": ["她确实不喜欢我"],
    "active_misbeliefs": []
  }
}

Return ONLY the JSON, nothing else.""",
        max_tokens=800,
        stream=False,
        metadata={"prompt_name": "test", "response_schema": "SnapshotInference"},
    )

    try:
        import asyncio
        print("\nSending request...")
        start = time.time()
        result = asyncio.run(transport.complete(profile, prompt))
        elapsed = time.time() - start

        print(f"✓ Response received in {elapsed:.2f}s")
        print(f"\nRaw response length: {len(result)} chars")
        print(f"\nFirst 500 chars:")
        print("-" * 70)
        print(result[:500])
        print("-" * 70)

        # Try to parse JSON
        import json
        try:
            parsed = json.loads(result)
            print("\n✓ Valid JSON!")
            print(f"Keys: {list(parsed.keys())}")
        except json.JSONDecodeError as e:
            print(f"\n✗ JSON Parse Error: {e}")
            print(f"Error at position {e.pos}")
            if e.pos < len(result):
                start = max(0, e.pos - 50)
                end = min(len(result), e.pos + 50)
                print(f"\nContext around error:")
                print(result[start:end])
                print(" " * (e.pos - start) + "^")

            # Check for common issues
            if result.strip().startswith("```"):
                print("\n⚠️  Response wrapped in markdown code blocks")
            if "思考过程" in result or "分析" in result or "reasoning" in result.lower():
                print("\n⚠️  Response includes thinking/reasoning text")
            if not result.strip().startswith("{"):
                print("\n⚠️  Response doesn't start with '{'")

    except Exception as e:
        print(f"\n✗ Request failed: {e}")

# Test each provider
providers = [
    ("qwen", "sk-aeaab486d8ea4b32bdc3d372a8786c43",
     "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen3.5-flash"),
    ("moonshot", "sk-SXIXZAnw5Qj6NikY3NgOJ9XsiTyXJxDSY8BRcuN7PLz5cK0q",
     "https://api.moonshot.ai/v1", "kimi-k2.5"),
    ("gemini", "AIzaSyBeuupU7bwJZyAWjpA0ZF4W1DJwXKmQTEM",
     "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
]

print("="*70)
print("JSON Response Debugging")
print("="*70)
print("\nThis will test each provider and show why JSON validation fails.\n")

for name, key, url, model in providers:
    test_provider(name, key, url, model)

print("\n" + "="*70)
print("ANALYSIS")
print("="*70)
print("""
Common JSON failure patterns:

1. **Markdown wrapping**: Response like ```json {...} ```
   → Model adds code blocks despite instructions

2. **Thinking mode**: Model shows reasoning before JSON
   → Need to disable thinking or extract JSON from mixed content

3. **Extra text**: Model adds explanation before/after JSON
   → Need better prompt engineering or post-processing

4. **Invalid JSON syntax**: Missing commas, trailing commas, etc.
   → Model doesn't strictly follow JSON spec

5. **Character encoding**: Unicode issues in Chinese text
   → Usually not the problem with UTF-8

Solutions in code:
- Line 389-417 in client.py: _json_candidates() tries to extract JSON
- Line 95-100 in openai_transport.py: Handles response_format and thinking
""")
