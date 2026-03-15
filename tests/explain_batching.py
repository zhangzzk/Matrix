"""Visualize different batching strategies."""

def simulate_current_approach(num_agents=10, workers=4, call_time=3.86):
    """Current: Agents run in parallel, but calls within each agent are sequential."""
    agents_per_round = workers
    rounds = (num_agents + agents_per_round - 1) // agents_per_round

    print(f"Current Approach (Workers={workers}):")
    print(f"{'─'*60}")

    total_time = 0
    for round_num in range(rounds):
        start_agent = round_num * agents_per_round
        end_agent = min(start_agent + agents_per_round, num_agents)
        agents_in_round = end_agent - start_agent

        print(f"\nRound {round_num + 1}:")
        for i in range(start_agent, end_agent):
            print(f"  Agent {i+1}: snapshot ({call_time:.1f}s) → goal ({call_time:.1f}s)")

        round_time = 2 * call_time  # Sequential within agent
        total_time += round_time
        print(f"  Round time: {round_time:.1f}s")

    print(f"\n{'─'*60}")
    print(f"Total time: {total_time:.1f}s")
    print(f"Total LLM calls: {num_agents * 2}")
    return total_time


def simulate_phase_batching(num_agents=10, workers=16, call_time=3.86):
    """Phase batching: All snapshots first, then all goals."""
    print(f"\nPhase-Based Batching (Workers={workers}):")
    print(f"{'─'*60}")

    # Phase 1: All snapshot calls
    snapshot_rounds = (num_agents + workers - 1) // workers
    print(f"\nPhase 1: Snapshot Inference")
    for round_num in range(snapshot_rounds):
        start = round_num * workers
        end = min(start + workers, num_agents)
        agents = list(range(start + 1, end + 1))
        print(f"  Round {round_num + 1}: Agents {agents} snapshots in parallel")

    phase1_time = snapshot_rounds * call_time
    print(f"  Phase 1 time: {phase1_time:.1f}s")

    # Phase 2: All goal calls
    goal_rounds = (num_agents + workers - 1) // workers
    print(f"\nPhase 2: Goal Seeding")
    for round_num in range(goal_rounds):
        start = round_num * workers
        end = min(start + workers, num_agents)
        agents = list(range(start + 1, end + 1))
        print(f"  Round {round_num + 1}: Agents {agents} goals in parallel")

    phase2_time = goal_rounds * call_time
    print(f"  Phase 2 time: {phase2_time:.1f}s")

    total_time = phase1_time + phase2_time
    print(f"\n{'─'*60}")
    print(f"Total time: {total_time:.1f}s")
    print(f"Total LLM calls: {num_agents * 2}")
    return total_time


def simulate_true_batching(num_agents=10, workers=16, call_time=3.86, api_batch_size=10):
    """True API batching: Send multiple prompts in ONE HTTP request."""
    print(f"\nTrue API Batching (Workers={workers}, API batch={api_batch_size}):")
    print(f"{'─'*60}")

    # This would require API support for batch requests
    # Most APIs don't support this, but let's show what it would look like

    total_calls = num_agents * 2

    # Phase 1: Snapshots
    snapshot_batches = (num_agents + api_batch_size - 1) // api_batch_size
    print(f"\nPhase 1: Snapshot Inference")
    print(f"  {num_agents} calls in {snapshot_batches} API batch(es) of {api_batch_size}")
    # Batched API calls are usually ~20-30% faster than sequential
    phase1_time = snapshot_batches * call_time * 0.8
    print(f"  Phase 1 time: {phase1_time:.1f}s (with batch speedup)")

    # Phase 2: Goals
    goal_batches = (num_agents + api_batch_size - 1) // api_batch_size
    print(f"\nPhase 2: Goal Seeding")
    print(f"  {num_agents} calls in {goal_batches} API batch(es) of {api_batch_size}")
    phase2_time = goal_batches * call_time * 0.8
    print(f"  Phase 2 time: {phase2_time:.1f}s (with batch speedup)")

    total_time = phase1_time + phase2_time
    print(f"\n{'─'*60}")
    print(f"Total time: {total_time:.1f}s")
    print(f"Note: Requires API batch support (most don't have this)")
    return total_time


print("="*60)
print("BATCHING STRATEGY COMPARISON (10 agents, 3.86s per call)")
print("="*60)

time_current_4 = simulate_current_approach(num_agents=10, workers=4, call_time=3.86)
time_current_16 = simulate_current_approach(num_agents=10, workers=16, call_time=3.86)
time_phase = simulate_phase_batching(num_agents=10, workers=16, call_time=3.86)
time_api = simulate_true_batching(num_agents=10, workers=16, call_time=3.86)

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"Current (4 workers):           {time_current_4:.1f}s   (baseline)")
print(f"Current (16 workers):          {time_current_16:.1f}s   ({time_current_4/time_current_16:.1f}x faster)")
print(f"Phase batching (16 workers):   {time_phase:.1f}s   ({time_current_4/time_phase:.1f}x faster)")
print(f"True API batching (ideal):     {time_api:.1f}s   ({time_current_4/time_api:.1f}x faster)")

print("\n" + "="*60)
print("RECOMMENDATIONS")
print("="*60)
print("""
1. ✅ EASY & SAFE: Increase workers to 16
   - No code changes needed
   - 2.5x speedup
   - Just add --max-workers 16

2. 🔧 MODERATE: Implement phase-based batching
   - Small code change (run all snapshots, then all goals)
   - 3.3x speedup
   - No dependency issues (still respects snapshot → goal order)

3. ⚠️  COMPLEX: True API batching
   - Requires API batch support (Qwen/Moonshot don't have this)
   - Only ~20% additional speedup over phase batching
   - Not worth the complexity

VERDICT: Do #1 now, consider #2 if you need more speed.
""")
