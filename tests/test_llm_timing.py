"""Test LLM API timing for DreamDive operations."""
import asyncio
import time
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dreamdive.llm.client import StructuredLLMClient
from dreamdive.llm.openai_transport import OpenAICompatibleTransport
from dreamdive.config import get_settings, LLMProfileSettings
from dreamdive.schemas import SnapshotInference, GoalSeedPayload, PromptRequest


def create_test_client(provider_name: str):
    """Create a client for a specific provider."""
    settings = get_settings()
    profiles = settings.active_llm_profiles()

    # Find the requested provider
    profile = None
    for p in profiles:
        if p.name.lower() == provider_name.lower():
            profile = p
            break

    if not profile:
        raise ValueError(f"Provider '{provider_name}' not found in settings")

    transport = OpenAICompatibleTransport(timeout_seconds=60.0)
    return StructuredLLMClient(
        profiles=[profile],
        transport=transport,
        retry_attempts=1,
    )


def test_single_call(client, schema_name="snapshot"):
    """Test a single LLM call."""
    if schema_name == "snapshot":
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
        schema = SnapshotInference
    else:  # goal
        prompt = PromptRequest(
            system="You are analyzing character goals.",
            user="""Analyze character goals and return JSON:
Character: 路明非 (Lu Mingfei)
Current state: Feeling rejected, standing in rain
Emotional state: Dejected but trying to stay positive

Return JSON with: goal_stack (array of goals with priority, goal, motivation, obstacle,
time_horizon, emotional_charge, abandon_condition), actively_avoiding,
most_uncertain_relationship.""",
            max_tokens=800,
            stream=False,
            metadata={"prompt_name": "test_goal", "response_schema": "GoalSeedPayload"},
        )
        schema = GoalSeedPayload

    start = time.time()
    try:
        result = asyncio.run(client.call_json(prompt, schema))
        elapsed = time.time() - start
        return elapsed, True, None
    except Exception as e:
        elapsed = time.time() - start
        return elapsed, False, str(e)


def test_parallel_calls(client, num_calls=4, max_workers=4):
    """Test parallel LLM calls."""
    def make_call(call_id):
        schema = "snapshot" if call_id % 2 == 0 else "goal"
        return test_single_call(client, schema)

    start = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(make_call, i): i for i in range(num_calls)}
        for future in as_completed(futures):
            call_id = futures[future]
            elapsed, success, error = future.result()
            results.append((call_id, elapsed, success, error))

    total_elapsed = time.time() - start
    return results, total_elapsed


def estimate_workload(single_call_time, num_agents=10, max_workers=4):
    """Estimate time for typical workloads."""
    # Each agent needs 2 calls: snapshot + goal
    total_calls = num_agents * 2

    # Sequential time
    sequential_time = total_calls * single_call_time

    # Parallel time (current implementation)
    # Agents are parallelized, but calls within each agent are sequential
    rounds = (num_agents + max_workers - 1) // max_workers
    parallel_time = rounds * 2 * single_call_time

    # Fully optimized (all calls batched)
    fully_parallel_rounds = (total_calls + max_workers - 1) // max_workers
    optimized_time = fully_parallel_rounds * single_call_time

    return {
        "total_calls": total_calls,
        "sequential_estimate": sequential_time,
        "current_parallel_estimate": parallel_time,
        "optimized_estimate": optimized_time,
    }


def main():
    print("=" * 70)
    print("DreamDive LLM API Performance Test")
    print("=" * 70)

    providers_to_test = ["moonshot", "gemini", "qwen"]

    results = {}

    for provider in providers_to_test:
        print(f"\n{'='*70}")
        print(f"Testing: {provider.upper()}")
        print(f"{'='*70}")

        try:
            client = create_test_client(provider)

            # Test 1: Single snapshot call
            print(f"\n1. Single snapshot inference call...")
            elapsed, success, error = test_single_call(client, "snapshot")
            if success:
                print(f"   ✓ Success: {elapsed:.2f}s")
                snapshot_time = elapsed
            else:
                print(f"   ✗ Failed: {error}")
                continue

            # Test 2: Single goal call
            print(f"\n2. Single goal seeding call...")
            elapsed, success, error = test_single_call(client, "goal")
            if success:
                print(f"   ✓ Success: {elapsed:.2f}s")
                goal_time = elapsed
            else:
                print(f"   ✗ Failed: {error}")
                continue

            avg_call_time = (snapshot_time + goal_time) / 2

            # Test 3: Parallel calls
            print(f"\n3. Testing 8 parallel calls (4 workers)...")
            call_results, total_time = test_parallel_calls(client, num_calls=8, max_workers=4)
            successes = sum(1 for _, _, success, _ in call_results if success)
            print(f"   ✓ {successes}/8 succeeded in {total_time:.2f}s")
            print(f"   Average speedup: {8 * avg_call_time / total_time:.1f}x")

            # Estimate workloads
            print(f"\n4. Workload estimates (avg call time: {avg_call_time:.2f}s)")
            print(f"   {'Scenario':<30} {'Time':<15} {'Details'}")
            print(f"   {'-'*60}")

            for num_agents in [5, 10, 20]:
                est = estimate_workload(avg_call_time, num_agents, max_workers=4)
                scenario = f"{num_agents} agents (current, 4 workers):"
                print(f"   {scenario:<30} "
                      f"{est['current_parallel_estimate']:.1f}s          "
                      f"{est['total_calls']} calls")

            print()
            for num_agents in [5, 10, 20]:
                est = estimate_workload(avg_call_time, num_agents, max_workers=16)
                scenario = f"{num_agents} agents (16 workers):"
                speedup = 16/4
                print(f"   {scenario:<30} "
                      f"{est['total_calls'] * avg_call_time / 16:.1f}s          "
                      f"~{speedup:.0f}x faster")

            print()
            for num_agents in [5, 10, 20]:
                est = estimate_workload(avg_call_time, num_agents, max_workers=16)
                scenario = f"{num_agents} agents (optimized):"
                print(f"   {scenario:<30} "
                      f"{est['optimized_estimate']:.1f}s          "
                      f"max theoretical")

            results[provider] = {
                "snapshot_time": snapshot_time,
                "goal_time": goal_time,
                "avg_time": avg_call_time,
                "parallel_speedup": 8 * avg_call_time / total_time,
            }

        except Exception as e:
            print(f"   ✗ Error testing {provider}: {e}")
            continue

    # Summary comparison
    if len(results) > 1:
        print(f"\n{'='*70}")
        print("PROVIDER COMPARISON")
        print(f"{'='*70}")
        print(f"{'Provider':<15} {'Avg Call Time':<20} {'Parallel Speedup'}")
        print(f"{'-'*60}")
        for provider, data in sorted(results.items(), key=lambda x: x[1]['avg_time']):
            print(f"{provider:<15} {data['avg_time']:.2f}s{'':<15} {data['parallel_speedup']:.1f}x")

        fastest = min(results.items(), key=lambda x: x[1]['avg_time'])
        print(f"\n🏆 Fastest: {fastest[0]} ({fastest[1]['avg_time']:.2f}s per call)")

    print(f"\n{'='*70}")
    print("RECOMMENDATIONS")
    print(f"{'='*70}")
    print("1. Increase --max-workers to 16 for ~4x speedup")
    print("2. Consider using the fastest provider for bulk operations")
    print("3. Implement request batching for additional 1.5-2x speedup")
    print("4. Monitor your provider's rate limits")


if __name__ == "__main__":
    main()
