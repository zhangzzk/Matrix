"""Quick Moonshot API timing test."""
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dreamdive.llm.openai_transport import OpenAICompatibleTransport
from dreamdive.config import LLMProfileSettings
from dreamdive.schemas import PromptRequest
import json

# Moonshot config from .env
transport = OpenAICompatibleTransport(timeout_seconds=60.0)
profile = LLMProfileSettings(
    name="moonshot",
    api_key="sk-SXIXZAnw5Qj6NikY3NgOJ9XsiTyXJxDSY8BRcuN7PLz5cK0q",
    base_url="https://api.moonshot.ai/v1",
    model="kimi-k2.5",
    max_tokens=4000,
)

prompt = PromptRequest(
    system="You are analyzing a character's state. Return valid JSON only.",
    user="""Analyze this character and return JSON:
Character: 路明非
Scene: Standing outside school in rain
Feeling: Dejected after rejection

Return JSON with these fields:
{
  "emotional_state": {"dominant": "...", "secondary": [], "confidence": 0.5},
  "immediate_tension": "...",
  "unspoken_subtext": "...",
  "physical_state": {"energy": 0.5, "injuries_or_constraints": "", "location": "", "current_activity": ""},
  "knowledge_state": {"new_knowledge": [], "active_misbeliefs": []}
}""",
    max_tokens=800,
    stream=False,
    metadata={"prompt_name": "test", "response_schema": "SnapshotInference"},
)

print("Testing Moonshot API (kimi-k2.5)...")
print("Endpoint:", profile.base_url)
print("Model:", profile.model)
print("-" * 60)

# Test 3 calls to get average
times = []
for i in range(3):
    print(f"\nCall {i+1}/3...", end=" ", flush=True)
    start = time.time()
    try:
        import asyncio
        result = asyncio.run(transport.complete(profile, prompt))
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"✓ {elapsed:.2f}s")

        # Show first response
        if i == 0:
            try:
                parsed = json.loads(result)
                print(f"  Response keys: {list(parsed.keys())}")
            except:
                print(f"  Response preview: {result[:100]}...")
    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ Failed ({elapsed:.2f}s): {str(e)[:100]}")

if times:
    avg = sum(times) / len(times)
    print(f"\n{'='*60}")
    print(f"Average call time: {avg:.2f}s")
    print(f"Min: {min(times):.2f}s, Max: {max(times):.2f}s")
    print(f"{'='*60}")

    print("\nWorkload estimates (init-snapshot with 10 agents):")
    print(f"  Sequential (20 calls):        {20 * avg:.1f}s")
    print(f"  Current (4 workers):          {5 * 2 * avg:.1f}s")
    print(f"  With 16 workers:              {2 * avg:.1f}s (~4x faster)")
    print(f"  Optimized (batched):          {(20/16) * avg:.1f}s (theoretical max)")
else:
    print("\nAll calls failed. Check API key and network connection.")
