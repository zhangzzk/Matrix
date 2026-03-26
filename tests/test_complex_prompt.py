"""Test why complex prompts fail JSON validation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dreamdive.llm.openai_transport import OpenAICompatibleTransport
from dreamdive.config import LLMProfileSettings
from dreamdive.schemas import PromptRequest
import json

def test_prompt_style(name, api_key, base_url, model, prompt_style):
    """Test different prompt styles."""
    transport = OpenAICompatibleTransport(timeout_seconds=60.0)
    profile = LLMProfileSettings(name=name, api_key=api_key, base_url=base_url, model=model, max_tokens=4000)

    if prompt_style == "simple":
        prompt = PromptRequest(
            system="You are a helpful assistant. Return ONLY valid JSON.",
            user="""Return JSON: {"emotional_state": {"dominant": "...", "secondary": []},
"immediate_tension": "...", "unspoken_subtext": "...",
"physical_state": {"injuries_or_constraints": "", "location": "", "current_activity": ""},
"knowledge_state": {"new_knowledge": [], "active_misbeliefs": []}}""",
            max_tokens=800,
            stream=False,
            metadata={"prompt_name": "test", "response_schema": "SnapshotInference"},
        )
    else:  # complex - from test_llm_timing.py
        prompt = PromptRequest(
            system="You are analyzing a character's state.",
            user="""Analyze this character state and return JSON:
Character: 路明非 (Lu Mingfei)
Scene: Standing in the rain outside the school gate, thinking about his crush
Recent events: Got rejected again, feeling down

Return JSON with: emotional_state (with dominant, secondary, confidence),
immediate_tension, unspoken_subtext, physical_state (energy, injuries_or_constraints,
location, current_activity), knowledge_state (new_knowledge, active_misbeliefs).""",
            max_tokens=800,
            stream=False,
            metadata={"prompt_name": "test_snapshot", "response_schema": "SnapshotInference"},
        )

    print(f"\n{'='*70}")
    print(f"{name.upper()} - {prompt_style} prompt")
    print(f"{'='*70}")

    try:
        import asyncio, time
        start = time.time()
        result = asyncio.run(transport.complete(profile, prompt))
        elapsed = time.time() - start

        # Check if valid JSON
        try:
            parsed = json.loads(result)
            print(f"✓ Valid JSON ({elapsed:.2f}s)")
            return True
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON ({elapsed:.2f}s)")
            print(f"  Error: {str(e)[:100]}")
            print(f"  First 200 chars: {result[:200]}")

            # Check for issues
            if "```" in result:
                print("  Issue: Markdown code blocks")
            if result.count("{") > 1 and not result.strip().startswith("{"):
                print("  Issue: Extra text before JSON")
            if "思考" in result or "分析" in result:
                print("  Issue: Chinese reasoning text included")
            if "thinking" in result.lower() or "reasoning" in result.lower():
                print("  Issue: English reasoning text included")

            return False
    except Exception as e:
        print(f"✗ Request failed: {e}")
        return False

# Test each provider with both prompt styles
providers = [
    ("qwen", "sk-aeaab486d8ea4b32bdc3d372a8786c43",
     "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen3.5-flash"),
    ("moonshot", "sk-SXIXZAnw5Qj6NikY3NgOJ9XsiTyXJxDSY8BRcuN7PLz5cK0q",
     "https://api.moonshot.ai/v1", "kimi-k2.5"),
]

print("Testing prompt complexity impact on JSON validation...")

results = {}
for name, key, url, model in providers:
    results[name] = {}
    for style in ["simple", "complex"]:
        results[name][style] = test_prompt_style(name, key, url, model, style)

print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
for name, styles in results.items():
    print(f"\n{name.upper()}:")
    for style, success in styles.items():
        status = "✓" if success else "✗"
        print(f"  {style:10} {status}")

print(f"\n{'='*70}")
print("CONCLUSION")
print(f"{'='*70}")
print("""
If complex prompts fail but simple ones succeed, the issue is likely:

1. **Narrative context triggers reasoning mode**
   - Solution: Add "Return ONLY JSON, no analysis or reasoning"

2. **Model interprets task as analysis rather than data extraction**
   - Solution: Make prompt more directive: "Output this exact JSON structure..."

3. **Token budget allows for additional thinking with complex context**
   - Solution: Lower max_tokens to discourage extra text

4. **System prompt needs to be more explicit**
   - Solution: "You are a JSON generator. Never include any text outside JSON."
""")
