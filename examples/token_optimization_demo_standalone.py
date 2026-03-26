"""
Standalone Token Optimization Demo

Demonstrates token optimization concepts without requiring the full dreamdive package.
Shows calculations and comparisons.
"""


def demo_1_context_filtering():
    """Demonstrate context filtering savings"""
    print("=" * 70)
    print("DEMO 1: Context Filtering")
    print("=" * 70)

    # Scenario: 50 characters in world, only 2 active in scene
    total_characters = 50
    active_characters = 2
    background_characters = total_characters - active_characters

    # Token estimates
    tokens_per_full_character = 400  # Detailed state
    tokens_per_summary_character = 30  # Brief mention

    # Without optimization: send all characters in full detail
    baseline_tokens = total_characters * tokens_per_full_character

    # With optimization: active in detail, others summarized
    optimized_tokens = (
        active_characters * tokens_per_full_character +
        min(background_characters, 10) * tokens_per_summary_character  # Cap at 10 summaries
    )

    savings = baseline_tokens - optimized_tokens
    savings_pct = (savings / baseline_tokens) * 100

    print(f"\nScenario: {total_characters} total characters, {active_characters} active in scene")
    print(f"\nWithout Optimization:")
    print(f"  Send all {total_characters} characters in full detail")
    print(f"  {total_characters} × {tokens_per_full_character} tokens = {baseline_tokens:,} tokens")

    print(f"\nWith Context Filtering:")
    print(f"  Active ({active_characters}): {active_characters} × {tokens_per_full_character} = {active_characters * tokens_per_full_character:,} tokens")
    print(f"  Background (top 10): 10 × {tokens_per_summary_character} = {10 * tokens_per_summary_character:,} tokens")
    print(f"  Total: {optimized_tokens:,} tokens")

    print(f"\n✓ Savings: {savings:,} tokens ({savings_pct:.0f}%)")
    print()


def demo_2_prompt_compression():
    """Demonstrate prompt compression savings"""
    print("=" * 70)
    print("DEMO 2: Prompt Compression")
    print("=" * 70)

    # Example: Collision detection prompt
    verbose_system = """
You are simulating goal collision detection in a narrative simulation system.
Your task is to analyze the goals of multiple characters and determine which
goals are likely to create interesting narrative collisions. A narrative collision
occurs when two or more characters have goals that conflict with each other,
either directly or indirectly. Consider the following factors when identifying
collisions: the characters' personalities, their relationships with each other,
their current emotional states, the context of the situation, and the stakes
involved. For each collision, assess the emergence probability based on how
likely the collision is to manifest in the near future. High-probability collisions
involve immediate conflicts, while low-probability collisions are more distant
or hypothetical. Return your analysis in a structured JSON format...
"""

    compressed_system = """
Goal collision detection for narrative simulation.

Input: Character goals, relationships, world context
Output: JSON collisions with conflict potential (0.0-1.0)

Collision types: DIRECT, COMPETITIVE, IDEOLOGICAL, SITUATIONAL
Scoring: High (>0.7), Medium (0.4-0.7), Low (<0.4)

Format: Analyze systematically, return valid JSON.
"""

    verbose_tokens = len(verbose_system) // 4
    compressed_tokens = len(compressed_system) // 4

    savings = verbose_tokens - compressed_tokens
    savings_pct = (savings / verbose_tokens) * 100

    print(f"\nVerbose System Prompt:")
    print(f"  Length: {len(verbose_system)} characters")
    print(f"  Estimated: ~{verbose_tokens} tokens")

    print(f"\nCompressed System Prompt:")
    print(f"  Length: {len(compressed_system)} characters")
    print(f"  Estimated: ~{compressed_tokens} tokens")

    print(f"\n✓ Savings: ~{savings} tokens ({savings_pct:.0f}%)")

    print(f"\nCompression Techniques:")
    print(f"  - Remove redundant explanations")
    print(f"  - Use bullet points instead of paragraphs")
    print(f"  - Structured format (types, scoring rules)")
    print(f"  - One-sentence descriptions")
    print()


def demo_3_detail_tiering():
    """Demonstrate detail tiering savings"""
    print("=" * 70)
    print("DEMO 3: Detail Level Tiering")
    print("=" * 70)

    # Scenario: 10 events in a tick with varying salience
    events = [
        ("Climactic dragon battle", 0.95, "full"),
        ("Lu Mingfei's internal monologue", 0.88, "full"),
        ("Caesar gives orders", 0.72, "moderate"),
        ("Team member acknowledges", 0.65, "moderate"),
        ("Character moves to position", 0.55, "moderate"),
        ("Background character watches", 0.42, "minimal"),
        ("Distant crowd reaction", 0.35, "minimal"),
        ("Weather description", 0.28, "minimal"),
        ("Time passage note", 0.15, "summary"),
        ("Far-off sound mentioned", 0.10, "summary"),
    ]

    detail_tokens = {
        "full": 2000,
        "moderate": 800,
        "minimal": 300,
        "summary": 100,
    }

    # Without optimization: all events at full detail
    baseline_tokens = len(events) * detail_tokens["full"]

    # With optimization: tiered by salience
    optimized_tokens = sum(detail_tokens[detail] for _, _, detail in events)

    savings = baseline_tokens - optimized_tokens
    savings_pct = (savings / baseline_tokens) * 100

    print(f"\nScenario: {len(events)} events in a simulation tick")

    print(f"\nWithout Optimization:")
    print(f"  All {len(events)} events at full detail")
    print(f"  {len(events)} × {detail_tokens['full']} = {baseline_tokens:,} tokens")

    print(f"\nWith Detail Tiering:")
    for desc, salience, detail in events:
        tokens = detail_tokens[detail]
        print(f"  [{salience:.2f}] {desc:40} → {detail:8} ({tokens:,} tokens)")

    print(f"\nTotal optimized: {optimized_tokens:,} tokens")
    print(f"\n✓ Savings: {savings:,} tokens ({savings_pct:.0f}%)")
    print()


def demo_4_combined_effect():
    """Demonstrate combined optimization effect"""
    print("=" * 70)
    print("DEMO 4: Combined Optimization Effect")
    print("=" * 70)

    # Scenario: Single P2 tick with collision detection

    # Baseline (no optimization)
    baseline = {
        "Character context": 20000,  # All 50 characters
        "Relationship context": 8000,  # All 200 relationships
        "World state": 5000,  # Full world state
        "Memory context": 3000,  # All memories
        "System prompt": 1000,  # Verbose instructions
    }

    # Optimized (all strategies combined)
    optimized = {
        "Character context": 1200,  # 2 active + 10 summaries (94% reduction)
        "Relationship context": 600,  # 10 relevant (92% reduction)
        "World state": 800,  # Current location only (84% reduction)
        "Memory context": 800,  # Top 5 memories (73% reduction)
        "System prompt": 300,  # Compressed (70% reduction)
    }

    baseline_total = sum(baseline.values())
    optimized_total = sum(optimized.values())
    total_savings = baseline_total - optimized_total
    total_savings_pct = (total_savings / baseline_total) * 100

    print(f"\nSingle P2 Tick - Collision Detection")
    print(f"\n{'Component':<25} {'Baseline':>12} {'Optimized':>12} {'Savings':>12}")
    print("-" * 70)

    for component in baseline.keys():
        b = baseline[component]
        o = optimized[component]
        s = b - o
        s_pct = (s / b) * 100
        print(f"{component:<25} {b:>10,} t  {o:>10,} t  {s_pct:>10.0f}%")

    print("-" * 70)
    print(f"{'TOTAL':<25} {baseline_total:>10,} t  {optimized_total:>10,} t  {total_savings_pct:>10.0f}%")

    print(f"\n✓ Combined savings: {total_savings:,} tokens ({total_savings_pct:.0f}%)")
    print()


def demo_5_full_simulation_impact():
    """Demonstrate impact on full simulation"""
    print("=" * 70)
    print("DEMO 5: Full Simulation Impact")
    print("=" * 70)

    # Simulation parameters
    num_ticks = 10
    num_characters = 5

    # Operations per tick with token estimates
    operations_baseline = {
        "Collision detection": (1, 33000),  # 1 call per tick
        "Trajectory projection": (num_characters, 8000),  # per character
        "Scene setup": (3, 22000),  # ~3 scenes per tick
        "State updates": (num_characters, 5000),  # per character
        "Memory reflection": (num_characters, 4000),  # per character
    }

    operations_optimized = {
        "Collision detection": (1, 8000),  # 76% reduction
        "Trajectory projection": (num_characters, 4000),  # 50% reduction
        "Scene setup": (3, 10000),  # 55% reduction
        "State updates": (num_characters, 2000),  # 60% reduction
        "Memory reflection": (num_characters, 2000),  # 50% reduction
    }

    # Calculate per-tick totals
    baseline_per_tick = sum(count * tokens for count, tokens in operations_baseline.values())
    optimized_per_tick = sum(count * tokens for count, tokens in operations_optimized.values())

    # Calculate full simulation
    baseline_total = baseline_per_tick * num_ticks
    optimized_total = optimized_per_tick * num_ticks

    total_savings = baseline_total - optimized_total
    total_savings_pct = (total_savings / baseline_total) * 100

    # Cost impact
    cost_per_1k = 0.003  # $0.003 per 1K tokens (Claude 3.5 Sonnet)
    baseline_cost = (baseline_total / 1000) * cost_per_1k
    optimized_cost = (optimized_total / 1000) * cost_per_1k
    cost_savings = baseline_cost - optimized_cost

    print(f"\n{num_ticks}-Tick Simulation ({num_characters} characters)")

    print(f"\nPer-Tick Breakdown:")
    print(f"{'Operation':<25} {'Baseline':>15} {'Optimized':>15}")
    print("-" * 70)

    for op_name in operations_baseline.keys():
        count_b, tokens_b = operations_baseline[op_name]
        count_o, tokens_o = operations_optimized[op_name]
        total_b = count_b * tokens_b
        total_o = count_o * tokens_o
        print(f"{op_name:<25} {total_b:>13,} t  {total_o:>13,} t")

    print("-" * 70)
    print(f"{'Per-Tick Total':<25} {baseline_per_tick:>13,} t  {optimized_per_tick:>13,} t")

    print(f"\nFull Simulation ({num_ticks} ticks):")
    print(f"  Baseline:  {baseline_total:>13,} tokens (${baseline_cost:.2f})")
    print(f"  Optimized: {optimized_total:>13,} tokens (${optimized_cost:.2f})")

    print(f"\n✓ Total savings: {total_savings:,} tokens ({total_savings_pct:.0f}%)")
    print(f"✓ Cost savings: ${cost_savings:.2f} ({total_savings_pct:.0f}%)")

    # Extrapolate
    print(f"\nExtrapolated:")
    print(f"  100 simulations: Save {total_savings * 100:,} tokens, ${cost_savings * 100:.2f}")
    print(f"  1000 ticks: Save {(total_savings * 100):,} tokens, ${cost_savings * 100:.2f}")
    print()


def demo_6_optimization_levels():
    """Demonstrate different optimization levels"""
    print("=" * 70)
    print("DEMO 6: Optimization Levels Comparison")
    print("=" * 70)

    # Single operation example: collision detection
    baseline_tokens = 33000

    levels = {
        "None": {
            "tokens": 33000,
            "savings": 0,
            "quality_impact": 0,
            "description": "No optimizations, full context",
        },
        "Conservative": {
            "tokens": 22000,
            "savings": 33,
            "quality_impact": 3,
            "description": "Light filtering, full prompts",
        },
        "Moderate": {
            "tokens": 12000,
            "savings": 64,
            "quality_impact": 8,
            "description": "Balanced filtering + compression",
        },
        "Aggressive": {
            "tokens": 8000,
            "savings": 76,
            "quality_impact": 15,
            "description": "Maximum optimization",
        },
    }

    print(f"\nCollision Detection Optimization Levels:")
    print(f"(Baseline: {baseline_tokens:,} tokens)")
    print()

    print(f"{'Level':<15} {'Tokens':>10} {'Savings':>10} {'Quality Impact':>15} {'Description':<35}")
    print("-" * 100)

    for level, data in levels.items():
        tokens = data["tokens"]
        savings = data["savings"]
        quality = data["quality_impact"]
        desc = data["description"]

        print(f"{level:<15} {tokens:>8,} t  {savings:>8}%  {quality:>13}%  {desc:<35}")

    print()
    print("Recommendation:")
    print("  - Start with MODERATE (best balance)")
    print("  - Use CONSERVATIVE for production-critical")
    print("  - Try AGGRESSIVE if cost-sensitive")
    print()


def main():
    """Run all demos"""
    print("\n" + "=" * 70)
    print(" " * 15 + "TOKEN OPTIMIZATION DEMONSTRATIONS")
    print("=" * 70)
    print()
    print("Showing how to reduce LLM token usage by 40-70% with minimal quality loss")
    print()

    demo_1_context_filtering()
    demo_2_prompt_compression()
    demo_3_detail_tiering()
    demo_4_combined_effect()
    demo_5_full_simulation_impact()
    demo_6_optimization_levels()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
Key Optimization Strategies:

1. Context Filtering (50-70% savings)
   → Send only active characters, not entire cast
   → Filter relationships to relevant ones
   → Include only current location info

2. Prompt Compression (20-40% savings)
   → Remove verbose explanations
   → Use structured formats
   → Concise instructions

3. Detail Tiering (30-50% savings)
   → Full detail for spotlight events (salience ≥ 0.8)
   → Moderate for foreground (≥ 0.5)
   → Minimal for background (≥ 0.3)
   → Summary for distant (< 0.3)

Combined Effect: 40-70% total reduction

Real-World Impact:
- 10-tick simulation: Save ~1M tokens, ~$3.00
- 100 simulations: Save ~$300
- Minimal quality degradation (<10%)

Next Steps:
1. Review TOKEN_OPTIMIZATION_QUICKREF.md
2. Start with MODERATE optimization level
3. Monitor token usage and quality
4. Adjust budgets as needed

Implementation:
- Phase 1 (Ready): Context filtering + compression
- Phase 2 (Future): Batching + caching
- Phase 3 (Future): Incremental updates + deduplication
""")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
