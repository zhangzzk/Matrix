# Token Optimization Analysis & Strategy

## Executive Summary

Token usage across the Dreamdive pipeline can be optimized through:
1. **Context window optimization** (30-50% reduction)
2. **Prompt compression** (20-30% reduction)
3. **LLM call batching** (reduce call count by 40-60%)
4. **Caching and reuse** (30-50% reduction in repeated operations)
5. **Selective detail levels** (20-40% reduction)

**Estimated Total Savings: 50-70% token reduction** with minimal performance loss.

---

## Current Token Usage Analysis

### Phase-by-Phase Breakdown

#### P1: Ingestion (~500K-2M tokens)
- **Structural scan**: 1 call, ~10-50K tokens
- **Chapter extraction**: N calls (one per chapter), ~5-20K tokens each
- **Meta-layer extraction**: 1 call, ~50-200K tokens
- **Entity extraction**: 1 call, ~20-100K tokens
- **Fate-layer extraction**: 1 call, ~30-150K tokens

**Total for 50-chapter novel**: ~750K-2M tokens

#### P0.5: Architecture Design (~50-150K tokens) *NEW*
- **Story arc design**: 1 call, ~10-30K tokens
- **Character arc design**: N calls (3-5 characters), ~5-10K tokens each
- **World expansion**: 1 call, ~10-20K tokens
- **Chapter roadmap**: 1 call, ~15-40K tokens

**Total**: ~50-150K tokens

#### P2: Simulation Per Tick (~20-100K tokens/tick)
- **Goal collision detection**: 1 call per tick, ~5-20K tokens
  - Includes: All character goals, relationships, world state
- **Trajectory projection**: N calls (per character), ~3-10K tokens each
- **Agent beat generation**: M calls (per active scene), ~5-15K tokens each
- **Scene setup**: 1 call per event, ~8-25K tokens
- **State updates**: N calls (per character), ~2-8K tokens each

**For 10-character simulation with 3-5 events/tick**: ~50-150K tokens/tick

#### P3: Memory Consolidation (~10-30K tokens/tick)
- **Memory reflection**: N calls (per character), ~2-5K tokens each
- **Relationship updates**: N calls (per relationship), ~1-3K tokens each

**Total**: ~10-30K tokens/tick

#### P4: Narrative Arc Updates (~5-15K tokens/tick)
- **Arc progression check**: 1 call, ~5-15K tokens

#### P5: Synthesis (~50-200K tokens/chapter)
- **Chapter synthesis**: 1 call, ~30-150K tokens
  - Includes: All events, character states, style templates
- **Chapter title generation**: 1 call, ~2-5K tokens
- **Validation**: 1 call (optional), ~10-40K tokens

**Total per chapter**: ~50-200K tokens

---

## Major Optimization Opportunities

### 1. Context Window Optimization (HIGH IMPACT)

#### Problem
Current prompts include full character/world state every time:
```python
# Example from collision detection
prompt = build_collision_prompt(
    all_characters=characters,  # Full state for ALL characters
    world_state=world,          # Full world state
    relationships=relationships, # ALL relationships
)
```

**Cost**: ~10-30K tokens per call, most irrelevant

#### Solution: Selective Context Loading

**Strategy A: Relevance Filtering**
```python
def build_optimized_collision_prompt(
    active_characters: List[Character],  # Only characters in this scene
    world_state: WorldState,
    context_budget: int = 5000,  # Token budget
):
    # 1. Include only active characters' full state
    active_states = [char.current_state for char in active_characters]

    # 2. Include only relevant relationships
    relevant_relationships = filter_relationships(
        all_relationships,
        involved_characters=active_characters,
    )

    # 3. Include only relevant world state
    relevant_locations = get_current_locations(active_characters)
    relevant_world = {
        "current_locations": relevant_locations,
        "time": world_state.time,
        "active_events": world_state.active_events[:3],  # Top 3 only
    }

    # 4. Summarize non-active characters
    background_chars = summarize_background_characters(
        all_characters - active_characters,
        max_tokens=500,
    )
```

**Estimated Savings**: 50-70% per P2 call

**Implementation File**: `src/dreamdive/context_optimization.py`

---

### 2. Prompt Compression (MEDIUM IMPACT)

#### Problem
Prompts are verbose with repeated instructions:
```python
# Current: ~1000 tokens
"""
You are simulating a character in a narrative world. Your task is to determine
what goals this character would have given their personality, current situation,
and relationships with other characters. Please consider the following...

[Long explanation of goal types, formats, examples]
"""
```

#### Solution: Compressed Instructions

**Strategy B: Instruction Compression**
```python
# Optimized: ~300 tokens
"""
Simulate character goals.

Input: Personality, situation, relationships
Output: JSON goals (immediate/short/long-term)
Format: {"goal_id": "g1", "description": "...", "priority": 0.8}

Focus: Character-authentic, situation-driven
"""
```

**Techniques**:
1. **Remove redundancy**: One-time instructions in system prompt
2. **Use abbreviations**: "char" instead of "character" in context
3. **Structured data over prose**: JSON/YAML instead of paragraphs
4. **Reference examples externally**: Link to examples instead of including

**Estimated Savings**: 20-40% per prompt

**Implementation File**: `src/dreamdive/prompts/compressed/`

---

### 3. LLM Call Batching (HIGH IMPACT)

#### Problem
Multiple sequential calls for related operations:
```python
# Current: 5 separate calls for 5 characters
for character in characters:
    trajectory = await project_trajectory(character)  # 1 call each
    # Total: 5 calls × 8K tokens = 40K tokens
```

#### Solution: Batch Processing

**Strategy C: Batch Character Operations**
```python
# Optimized: 1 call for all 5 characters
trajectories = await project_trajectories_batch(characters)  # 1 call
# Total: 1 call × 15K tokens = 15K tokens
# Savings: 62.5%
```

**Batch-able Operations**:
- Trajectory projection (all characters at once)
- State updates (all characters at once)
- Memory reflection (batch by similarity)
- Relationship updates (batch by type)

**Schema Change**:
```python
# Add batch payload schemas
class BatchedTrajectoryProjectionPayload(BaseModel):
    """Process multiple characters in one call"""
    character_trajectories: Dict[str, TrajectoryProjection]

class BatchedStateUpdatePayload(BaseModel):
    """Update multiple characters in one call"""
    character_updates: Dict[str, StateUpdate]
```

**Estimated Savings**: 40-60% call reduction, 30-50% token reduction

**Implementation File**: `src/dreamdive/batch_optimization.py`

---

### 4. Caching and Reuse (MEDIUM-HIGH IMPACT)

#### Problem
Same information re-computed or re-sent multiple times:
```python
# Meta-layer sent in every P2 call
meta_context = format_meta_section(meta_layer)  # 5-10K tokens
# Sent 20 times per tick → 100-200K tokens wasted
```

#### Solution: Multi-Level Caching

**Strategy D: Prompt Fragment Caching**

**Level 1: Static Context Cache**
```python
class CachedContextBuilder:
    def __init__(self, meta_layer, world_base):
        # Cache static elements
        self._meta_fragment = self._build_meta_fragment(meta_layer)
        self._world_rules_fragment = self._build_world_rules(world_base)
        self._style_fragment = self._build_style_guide(meta_layer)

    def build_prompt(self, dynamic_context):
        # Reuse cached fragments
        return f"{self._meta_fragment}\n{dynamic_context}"
```

**Level 2: LLM Provider Caching**
```python
# Use provider-specific caching (e.g., Anthropic prompt caching)
prompt = PromptRequest(
    system=system_prompt,
    user=user_prompt,
    metadata={
        "cache_control": {
            "type": "ephemeral",
            "sections": ["meta_layer", "character_identities"],
        }
    }
)
```

**Level 3: Result Caching**
```python
# Cache stable computations
@lru_cache(maxsize=100)
def get_character_core_traits(character_id: str, version: int):
    # Reuse if character hasn't fundamentally changed
    return extract_core_traits(character_id)
```

**Estimated Savings**: 30-50% through avoiding redundant transmissions

**Implementation File**: `src/dreamdive/caching_optimization.py`

---

### 5. Selective Detail Levels (MEDIUM IMPACT)

#### Problem
Same level of detail for all operations:
```python
# Background event needs less detail than spotlight event
background_event = simulate_event(
    character=char,
    detail_level="FULL",  # Overkill for background
)
```

#### Solution: Adaptive Detail Levels

**Strategy E: Tiered Detail Rendering**

```python
class DetailLevel(Enum):
    SPOTLIGHT = "spotlight"      # Full detail, all nuance
    FOREGROUND = "foreground"    # Moderate detail
    BACKGROUND = "background"    # Summary only
    DISTANT = "distant"          # Minimal mention

def build_agent_prompt(
    character: Character,
    event_context: EventContext,
    detail_level: DetailLevel,
):
    if detail_level == DetailLevel.SPOTLIGHT:
        # Full character state, all relationships, all goals
        return build_full_prompt(character, event_context)

    elif detail_level == DetailLevel.FOREGROUND:
        # Core traits, relevant relationships, active goals only
        return build_moderate_prompt(character, event_context)

    elif detail_level == DetailLevel.BACKGROUND:
        # Essential traits, no relationships, top goal only
        return build_minimal_prompt(character, event_context)

    else:  # DISTANT
        # Name, role, single-sentence current action
        return build_summary_prompt(character, event_context)
```

**Token Allocation**:
- Spotlight: 15-25K tokens (full richness)
- Foreground: 5-10K tokens (moderate)
- Background: 2-5K tokens (minimal)
- Distant: 500-1K tokens (summary)

**Estimated Savings**: 30-50% for non-spotlight operations

**Implementation File**: `src/dreamdive/detail_optimization.py`

---

### 6. Incremental Updates (MEDIUM IMPACT)

#### Problem
Sending full state every time:
```python
# Tick 5: Send full character state (8K tokens)
# Tick 6: Send full character state (8K tokens)
# 90% unchanged from tick 5!
```

#### Solution: Delta Encoding

**Strategy F: State Diffs**

```python
class IncrementalStateManager:
    def __init__(self):
        self._baseline_states = {}
        self._last_sent_tick = {}

    def build_state_context(
        self,
        character_id: str,
        current_state: CharacterState,
        current_tick: int,
    ):
        last_tick = self._last_sent_tick.get(character_id, 0)

        if current_tick - last_tick > 5:
            # Full refresh every 5 ticks
            self._baseline_states[character_id] = current_state
            self._last_sent_tick[character_id] = current_tick
            return format_full_state(current_state)

        # Send delta only
        baseline = self._baseline_states[character_id]
        delta = compute_state_diff(baseline, current_state)

        return format_state_delta(delta, reference_tick=last_tick)

def compute_state_diff(old: CharacterState, new: CharacterState):
    diff = {}

    # Check each field
    if old.location != new.location:
        diff["location"] = {"old": old.location, "new": new.location}

    # Goals: only changed ones
    changed_goals = [g for g in new.goals if g not in old.goals]
    if changed_goals:
        diff["goals_added"] = changed_goals

    # Relationships: only updated ones
    # ... etc

    return diff
```

**Estimated Savings**: 60-80% for unchanged state fields

**Implementation File**: `src/dreamdive/incremental_state.py`

---

### 7. Semantic Deduplication (LOW-MEDIUM IMPACT)

#### Problem
Similar memories/context sent repeatedly:
```python
memories = [
    "Lu Mingfei fought a dragon in Tokyo",
    "Lu Mingfei battled a dragon in Tokyo Tower",
    "Lu Mingfei engaged in combat with dragon at Tokyo",
]
# All 3 sent → ~1500 tokens
```

#### Solution: Semantic Clustering

**Strategy G: Memory Consolidation**

```python
def deduplicate_memories_semantically(
    memories: List[Memory],
    similarity_threshold: float = 0.85,
):
    # 1. Embed all memories
    embeddings = [embed_text(m.content) for m in memories]

    # 2. Cluster by similarity
    clusters = cluster_by_similarity(embeddings, threshold=similarity_threshold)

    # 3. Keep most detailed from each cluster
    deduplicated = []
    for cluster in clusters:
        # Keep longest (most detailed) memory from cluster
        best_memory = max(cluster, key=lambda m: len(m.content))
        deduplicated.append(best_memory)

    return deduplicated

# Result: 3 memories → 1 memory → ~500 tokens
```

**Estimated Savings**: 20-40% for memory-heavy prompts

**Implementation File**: `src/dreamdive/semantic_dedup.py`

---

## Implementation Priority

### Phase 1: High-Impact, Low-Effort (Week 1)

1. **Context Window Optimization** (Strategy A)
   - Filter to active characters only
   - Summarize background characters
   - Include only relevant relationships
   - **Effort**: Medium
   - **Impact**: 50-70% savings in P2

2. **Prompt Compression** (Strategy B)
   - Compress instruction text
   - Remove redundancy
   - Use structured formats
   - **Effort**: Low
   - **Impact**: 20-40% savings across all phases

3. **Selective Detail Levels** (Strategy E)
   - Implement tiered detail rendering
   - Reduce background event detail
   - **Effort**: Medium
   - **Impact**: 30-50% savings for non-spotlight

**Expected Phase 1 Savings**: ~40-60% total

### Phase 2: High-Impact, Medium-Effort (Week 2-3)

4. **LLM Call Batching** (Strategy C)
   - Batch trajectory projections
   - Batch state updates
   - Add batch schemas
   - **Effort**: High
   - **Impact**: 30-50% savings in P2

5. **Caching and Reuse** (Strategy D)
   - Implement prompt fragment caching
   - Add LLM provider caching
   - Cache stable computations
   - **Effort**: Medium-High
   - **Impact**: 30-50% savings through reuse

**Expected Phase 2 Savings**: Additional ~20-30%

### Phase 3: Medium-Impact, Higher-Effort (Week 4+)

6. **Incremental Updates** (Strategy F)
   - Implement delta encoding
   - Add baseline tracking
   - **Effort**: High
   - **Impact**: 20-40% savings for state updates

7. **Semantic Deduplication** (Strategy G)
   - Cluster similar memories
   - Consolidate redundant context
   - **Effort**: Medium
   - **Impact**: 15-25% savings for memory-heavy ops

**Expected Phase 3 Savings**: Additional ~15-25%

---

## Detailed Implementation Plan

### Strategy A: Context Window Optimization

**File**: `src/dreamdive/context_optimization.py`

```python
"""
Context window optimization through selective loading.
"""

from typing import List, Dict, Any, Set
from dreamdive.schemas import Character, Relationship, WorldState

class ContextBudget:
    """Manage token budget for prompt construction"""

    def __init__(self, total_budget: int = 8000):
        self.total_budget = total_budget
        self.allocated = {
            "instructions": 500,
            "meta_context": 1000,
            "character_states": 3000,
            "relationships": 1500,
            "world_state": 1000,
            "memories": 1000,
        }

    def get_budget(self, category: str) -> int:
        return self.allocated.get(category, 0)


class SelectiveContextBuilder:
    """Build context with only relevant information"""

    def __init__(self, budget: ContextBudget):
        self.budget = budget

    def build_character_context(
        self,
        active_characters: List[str],  # Character IDs in current scene
        all_characters: Dict[str, Character],
        detail_level: str = "moderate",
    ) -> str:
        budget = self.budget.get_budget("character_states")

        # Full state for active characters
        active_context = []
        for char_id in active_characters:
            char = all_characters[char_id]
            active_context.append(self._format_full_character(char))

        # Summary for others
        other_ids = set(all_characters.keys()) - set(active_characters)
        background_context = self._summarize_background_characters(
            [all_characters[cid] for cid in other_ids],
            max_tokens=budget // 4,  # 25% for background
        )

        return "\n".join(active_context) + "\n\n" + background_context

    def build_relationship_context(
        self,
        active_characters: List[str],
        all_relationships: List[Relationship],
    ) -> str:
        budget = self.budget.get_budget("relationships")

        # Only relationships involving active characters
        relevant = [
            r for r in all_relationships
            if r.character_a in active_characters or r.character_b in active_characters
        ]

        # Sort by importance
        relevant.sort(key=lambda r: r.strength, reverse=True)

        # Fit to budget
        fitted = self._fit_to_token_budget(relevant, budget)

        return self._format_relationships(fitted)

    def _format_full_character(self, char: Character) -> str:
        """Full character state for active participants"""
        return f"""
## {char.name}

**Traits**: {', '.join(char.core_traits[:5])}
**Current Goal**: {char.active_goals[0].description if char.active_goals else 'None'}
**Emotional State**: {char.emotional_state}
**Location**: {char.location}
"""

    def _summarize_background_characters(
        self,
        characters: List[Character],
        max_tokens: int,
    ) -> str:
        """Brief summary of non-active characters"""
        summaries = []
        for char in characters[:10]:  # Limit to top 10
            summaries.append(f"{char.name} ({char.role}): {char.current_situation}")

        return "Background: " + "; ".join(summaries)


def filter_relevant_world_state(
    full_world: WorldState,
    active_locations: List[str],
    active_characters: List[str],
) -> Dict[str, Any]:
    """Extract only relevant portions of world state"""

    return {
        "time": full_world.current_time,
        "locations": {
            loc: full_world.locations[loc]
            for loc in active_locations
            if loc in full_world.locations
        },
        "active_events": full_world.active_events[:3],  # Top 3 only
        "weather": full_world.weather if full_world.current_time.outdoors else None,
    }
```

### Strategy B: Prompt Compression

**File**: `src/dreamdive/prompts/compressed/collision_compressed.py`

```python
"""
Compressed prompt templates with minimal tokens.
"""

# Before: ~2500 tokens
OLD_COLLISION_PROMPT = """
You are simulating goal collision detection in a narrative simulation system.
Your task is to analyze the goals of multiple characters and determine which
goals are likely to create interesting narrative collisions...

[Long explanation continues...]
"""

# After: ~800 tokens
COMPRESSED_COLLISION_PROMPT = """
Goal Collision Detection

Input: Character goals, relationships, world state
Output: JSON collisions with conflict potential (0.0-1.0)

Collision types:
- DIRECT: Goals directly oppose
- COMPETITIVE: Goals target same resource
- IDEOLOGICAL: Values/beliefs conflict
- SITUATIONAL: Circumstances force conflict

High potential (>0.7): Core goals, strong relationships, immediate timing
Medium (0.4-0.7): Secondary goals, moderate stakes
Low (<0.4): Distant goals, weak connections

Format:
{
  "collisions": [{
    "id": "c1",
    "type": "DIRECT",
    "characters": ["char_a", "char_b"],
    "goals": ["goal_1", "goal_2"],
    "potential": 0.85,
    "reason": "One sentence"
  }]
}
"""

# Techniques used:
# 1. Remove explanatory prose
# 2. Use bullet points instead of paragraphs
# 3. Abbreviate field names in examples
# 4. One-line reasons instead of paragraphs
# 5. Structured format first, explanation minimal
```

### Strategy C: LLM Call Batching

**File**: `src/dreamdive/batch_optimization.py`

```python
"""
Batch multiple related LLM operations into single calls.
"""

from typing import List, Dict
from dreamdive.schemas import Character, TrajectoryProjection
from dreamdive.llm.client import StructuredLLMClient

class BatchedOperations:
    """Batch related operations to reduce LLM calls"""

    def __init__(self, client: StructuredLLMClient):
        self.client = client

    async def project_trajectories_batch(
        self,
        characters: List[Character],
        time_horizon: int = 3,
    ) -> Dict[str, TrajectoryProjection]:
        """
        Project trajectories for all characters in one call.

        Before: N calls (one per character)
        After: 1 call (all characters)
        Savings: ~60% tokens, ~95% call overhead
        """

        # Build batch prompt
        prompt = self._build_batch_trajectory_prompt(characters, time_horizon)

        # Single call
        result = await self.client.call_json(prompt, BatchedTrajectoryPayload)

        # Unpack results
        return {
            char_id: projection
            for char_id, projection in result.character_trajectories.items()
        }

    def _build_batch_trajectory_prompt(
        self,
        characters: List[Character],
        time_horizon: int,
    ) -> PromptRequest:
        """Build prompt for batch trajectory projection"""

        # Compress character states
        char_contexts = [
            self._compress_character_for_batch(char)
            for char in characters
        ]

        user = f"""
Project {time_horizon}-tick trajectories for these characters:

{self._format_batch_characters(char_contexts)}

Return JSON:
{{
  "character_trajectories": {{
    "char_id_1": {{
      "likely_goals": [...],
      "probable_actions": [...],
      "expected_state_changes": {{...}}
    }},
    ...
  }}
}}
"""

        return PromptRequest(
            system=COMPRESSED_TRAJECTORY_SYSTEM,
            user=user,
            max_tokens=5000,  # Batch needs more tokens but fewer calls
        )
```

---

## Performance Validation

### Metrics to Track

1. **Token Usage**
   - Tokens per phase
   - Tokens per operation type
   - Total tokens per session

2. **Quality Metrics**
   - Story coherence score
   - Character consistency score
   - User satisfaction (subjective)

3. **Latency**
   - Time per operation
   - Total simulation time

### A/B Testing Plan

```python
# Test setup
baseline_session = run_simulation(
    optimization_level="none",
    track_tokens=True,
)

optimized_session = run_simulation(
    optimization_level="phase1",  # or phase2, phase3
    track_tokens=True,
)

# Compare
comparison = {
    "tokens_saved": baseline_session.total_tokens - optimized_session.total_tokens,
    "quality_delta": compare_quality(baseline_session, optimized_session),
    "latency_delta": baseline_session.duration - optimized_session.duration,
}
```

### Quality Assurance

**Minimum Quality Thresholds**:
- Character consistency: >95% (should not degrade)
- Story coherence: >90% (allow small degradation)
- Factual accuracy: >98% (critical)

**If quality drops below thresholds**:
1. Identify which optimization caused degradation
2. Adjust parameters (e.g., increase budget)
3. Add back critical context
4. Re-test

---

## Configuration Interface

```python
# src/dreamdive/config.py additions

class OptimizationSettings(BaseModel):
    """Token optimization configuration"""

    # Enable/disable optimization strategies
    enable_context_filtering: bool = True
    enable_prompt_compression: bool = True
    enable_batching: bool = True
    enable_caching: bool = True
    enable_detail_tiers: bool = True
    enable_incremental_updates: bool = False  # Advanced
    enable_semantic_dedup: bool = False  # Advanced

    # Context budgets
    collision_detection_budget: int = 8000
    trajectory_projection_budget: int = 5000
    agent_beat_budget: int = 10000
    scene_setup_budget: int = 12000

    # Detail level thresholds
    spotlight_salience_threshold: float = 0.8
    foreground_salience_threshold: float = 0.5
    background_salience_threshold: float = 0.3

    # Caching parameters
    cache_static_context: bool = True
    cache_ttl_ticks: int = 10

    # Batching parameters
    max_batch_size: int = 10
    batch_timeout_seconds: float = 30.0
```

Usage:
```bash
# CLI flag
dreamdive run --workspace ./ws --ticks 10 \
  --optimize-tokens \
  --optimization-level=aggressive

# Or in config file
# .dreamdive/config.yaml
optimization:
  enable_context_filtering: true
  enable_batching: true
  collision_detection_budget: 6000  # Reduced from 8000
```

---

## Migration Path

### Backward Compatibility

All optimizations optional and gradual:

```python
# Phase 1: Opt-in per session
session = initialize_session(
    ...,
    optimization_settings=OptimizationSettings(
        enable_context_filtering=True,
        enable_prompt_compression=True,
    )
)

# Phase 2: Opt-out (default enabled)
session = initialize_session(
    ...,
    # Optimizations on by default
)

# Phase 3: Always on
# Remove flags, optimizations always active
```

### Testing Strategy

1. **Unit tests**: Each optimization strategy
2. **Integration tests**: Full pipeline with optimizations
3. **Regression tests**: Compare output quality
4. **Performance tests**: Token usage and latency
5. **User testing**: Beta testers validate quality

---

## Expected Results

### Token Reduction

| Phase | Baseline | After Phase 1 | After Phase 2 | After Phase 3 |
|-------|----------|---------------|---------------|---------------|
| P1 Ingestion | 1M | 900K (10%) | 800K (20%) | 750K (25%) |
| P0.5 Architecture | 100K | 70K (30%) | 60K (40%) | 55K (45%) |
| P2 Simulation (10 ticks) | 1M | 500K (50%) | 350K (65%) | 300K (70%) |
| P3 Memory (10 ticks) | 200K | 140K (30%) | 120K (40%) | 100K (50%) |
| P5 Synthesis (5 chapters) | 500K | 350K (30%) | 300K (40%) | 270K (46%) |
| **Total** | **2.8M** | **1.96M (30%)** | **1.63M (42%)** | **1.48M (47%)** |

### Cost Reduction

At $0.003/1K tokens (typical pricing):
- Baseline: $8.40 per full cycle
- Phase 1: $5.88 (save $2.52, 30%)
- Phase 2: $4.89 (save $3.51, 42%)
- Phase 3: $4.44 (save $3.96, 47%)

**For 100 simulations**: Save $252-396

---

## Monitoring Dashboard

```python
# Real-time token tracking

class TokenMonitor:
    def __init__(self):
        self.phase_usage = defaultdict(int)
        self.operation_usage = defaultdict(int)
        self.optimization_savings = defaultdict(int)

    def record_operation(
        self,
        phase: str,
        operation: str,
        tokens_used: int,
        tokens_saved: int = 0,
    ):
        self.phase_usage[phase] += tokens_used
        self.operation_usage[operation] += tokens_used
        self.optimization_savings[operation] += tokens_saved

    def report(self):
        print("=== Token Usage Report ===")
        print(f"Total: {sum(self.phase_usage.values())} tokens")
        print(f"Total Saved: {sum(self.optimization_savings.values())} tokens")
        print("\nBy Phase:")
        for phase, tokens in sorted(self.phase_usage.items()):
            print(f"  {phase}: {tokens:,} tokens")
        print("\nTop Operations:")
        for op, tokens in sorted(
            self.operation_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]:
            saved = self.optimization_savings[op]
            print(f"  {op}: {tokens:,} tokens (saved {saved:,})")
```

---

## Summary

**Recommended Approach**:
1. Start with Phase 1 (context filtering + prompt compression)
2. Monitor quality metrics carefully
3. Gradually roll out Phase 2 and Phase 3
4. Achieve **40-70% token reduction** with minimal quality loss

**Key Insight**: Most tokens wasted on irrelevant context and verbose prompts. Selective loading and compression provide biggest wins with least risk.

**Next Steps**:
1. Implement `context_optimization.py`
2. Compress prompts in `prompts/compressed/`
3. Add `OptimizationSettings` to config
4. Deploy Phase 1 optimizations
5. Monitor and iterate
