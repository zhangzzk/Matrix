"""Quick timing diagnostic for DreamDive operations."""
import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def time_operation(name, func):
    """Time a function call."""
    start = time.time()
    result = func()
    elapsed = time.time() - start
    print(f"{name}: {elapsed:.2f}s")
    return result, elapsed

def test_embedding():
    """Test embedding performance."""
    from dreamdive.memory.retrieval import embed_text
    texts = [f"Test text {i}" for i in range(100)]

    def run():
        for text in texts:
            embed_text(text)

    return run

def test_llm_call():
    """Test a single LLM call (requires API key)."""
    from dreamdive.llm.client import StructuredLLMClient
    from dreamdive.llm.openai_transport import OpenAICompatibleTransport
    from dreamdive.config import get_settings
    from dreamdive.schemas import SnapshotInference, PromptRequest

    settings = get_settings()
    transport = OpenAICompatibleTransport()
    client = StructuredLLMClient.from_settings(transport, settings)

    prompt = PromptRequest(
        system="You are a helpful assistant.",
        user="Return a simple JSON with emotional_state, immediate_tension, unspoken_subtext, physical_state, and knowledge_state fields. Keep it minimal.",
        max_tokens=500,
        stream=False,
        metadata={"prompt_name": "test", "response_schema": "SnapshotInference"},
    )

    def run():
        import asyncio
        return asyncio.run(client.call_json(prompt, SnapshotInference))

    return run

if __name__ == "__main__":
    print("=== DreamDive Performance Diagnostics ===\n")

    # Test local operations
    print("Testing local operations:")
    time_operation("100 embeddings (local)", test_embedding())

    # Test LLM call
    print("\nTesting LLM operations:")
    try:
        time_operation("1 LLM call", test_llm_call())
    except Exception as e:
        print(f"LLM test failed: {e}")
        print("(This is expected if API keys aren't configured)")

    print("\n=== Summary ===")
    print("If LLM calls take >1s each and you have many agents,")
    print("that's your bottleneck. Optimize by:")
    print("  1. Increasing --max-workers")
    print("  2. Using faster LLM providers")
    print("  3. Batching LLM calls")
