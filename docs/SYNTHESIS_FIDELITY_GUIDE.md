# Synthesis Fidelity System - Complete Guide

## Philosophy

**The Core Principle**: Synthesis is **RENDERING**, not **CREATING**.

Think of it like filmmaking:
- **Simulation** = The screenplay (plot, dialogue, character actions)
- **Synthesis** = Cinematography (how to film it, lighting, camera angles)
- **Original Style** = The director's signature style

The LLM should act like a cinematographer who:
- ✅ **MUST** follow the screenplay exactly (simulation events)
- ✅ **MUST** film in the director's style (original author's voice)
- ❌ **CANNOT** change the plot
- ❌ **CANNOT** add new scenes not in the screenplay

## Two Critical Requirements

### Requirement 1: Simulation Fidelity

**Generated chapters MUST follow simulated results exactly.**

**WHY**: The simulation engine carefully tracks:
- Character states and goals
- Relationship dynamics
- Location changes
- Plot causality
- Emergent outcomes

If synthesis invents new content, it breaks continuity and makes subsequent simulation invalid.

**Example of VIOLATION**:
```
Simulation: Lu Mingfei activates the mechanism.诺诺 pulls him to safety. They escape.

BAD Synthesis: Lu Mingfei hesitates.诺诺 argues with him. Finally, after a long debate,
he activates it. But the mechanism fails! They have to find another way out...

(❌ Changed outcome, invented dialogue, added plot points)
```

**Example of CORRECT synthesis**:
```
Simulation: Lu Mingfei activates the mechanism. 诺诺 pulls him to safety. They escape.

GOOD Synthesis: 路明非的手指触碰到冰冷的金属凹槽。那一瞬间,所有的声音都消失了...
他猛地按下开关。通道开启了,诺诺拉着他冲向出口,身后的青铜城在崩塌...

(✅ Same outcome, same actions, but with sensory details and atmosphere)
```

### Requirement 2: Style Transfer

**Top-level writing style MUST match original material.**

**WHY**: Readers should not be able to tell which parts are from the original novel vs. simulation-generated.

**What is "top-level style"?**
- Sentence rhythm and cadence
- Descriptive techniques
- Narrative voice and POV
- Tone and register
- Paragraph pacing
- Metaphor patterns

**Example**:

**Original style** (Dragon Raja):
```
真烦。路明非想着,这种宿命感就像是早八点的闹钟,吵得人想砸烂它。
但他还是伸出手,指尖触到那片金色的碎屑。周围的黑暗像潮水一样漫上来。
```

**GOOD synthesis** (matches style):
```
这地方太吵了。他在心里说,全是那种嗡嗡的声音,听得我头疼。
但他知道那声音不是噪音,那是龙吟,是这座活着的城市在咀嚼骨头。
```

**BAD synthesis** (wrong style):
```
The location was very noisy. He thought to himself that it was annoying.
He knew the sound was dragon roars. The city was alive and making noise.
```

(Even if translated to Chinese, this is too flat, no rhythm, no metaphor, no voice)

---

## System Architecture

### 1. Grounded Event Summaries

**File**: [src/dreamdive/synthesis_fidelity.py](src/dreamdive/synthesis_fidelity.py)

Events are enhanced with **mandatory facts** that MUST appear in prose:

```python
GroundedEventSummary(
    event_id="evt_001",
    description="Lu Mingfei activates the mechanism",
    outcome_summary="The escape passage opens",
    mandatory_facts=[
        SimulationFact(
            fact_type="action",
            fact_statement="Lu Mingfei pressed the switch",
            is_mandatory=True,
            salience=0.9,
        ),
        SimulationFact(
            fact_type="state_change",
            fact_statement="Passage state changed to 'open'",
            is_mandatory=True,
            salience=1.0,
        ),
    ],
    canonical_dialogue=[
        {"speaker": "诺诺", "line": "准备好了吗?"},
        {"speaker": "路明非", "line": "真烦."},
    ],
    state_changes=[...],
)
```

This makes simulation results **explicit** so the LLM cannot ignore them.

### 2. Synthesis Constraints

Define what's allowed vs. forbidden:

```python
SynthesisConstraints(
    # What must be included
    must_include_events=["evt_001", "evt_002", "evt_003"],
    mandatory_outcomes=["Passage opens", "Characters escape"],

    # What's allowed
    allow_scene_expansion=True,  # ✅ Add sensory details
    allow_internal_monologue_invention=True,  # ✅ Add thoughts (if consistent)
    allow_transitional_scenes=True,  # ✅ Brief transitions

    # What's forbidden
    allow_dialogue_paraphrasing=False,  # ❌ Must use exact dialogue
    forbidden_inventions=[
        "New plot events",
        "Character actions not in simulation",
        "Different outcomes",
    ],
)
```

### 3. Style Templates

Extract patterns from original material:

```python
StyleTemplate(
    sentence_rhythm_examples=[
        "黑暗像一堵湿漉漉的墙,把所有人推搡着往下坠.",
        "水不是水,是黑色的巨蟒在血管里游动.",
    ],
    description_technique_examples=[
        "路明非觉得自己像一颗被扔进滚筒洗衣机的葡萄干...",
    ],
    narrative_voice_description="Third-person limited with frequent internal monologue",
    pov_style="Focalized through protagonist with cynical, self-deprecating tone",
)
```

These guide **HOW** to write (not WHAT to write).

---

## Prompt Structure

The fidelity-first prompt has three main sections:

### Section 1: Grounded Events (WHAT to write)

```markdown
# SIMULATION EVENTS (CANONICAL - MUST FOLLOW EXACTLY)

## ⚠️ CRITICAL FIDELITY RULES

**ALLOWED**:
- ✅ Add sensory details (sights, sounds, smells) to make scenes vivid
- ✅ Invent internal monologue (as long as consistent with character state)
- ✅ Add brief transitions between events

**FORBIDDEN**:
- ❌ Change outcomes of events
- ❌ Invent new plot points not in simulation
- ❌ Alter character locations or states
- ❌ Add dialogue not from simulation
- ❌ Skip high-salience events

---

## Event 1: evt_escape_activation
**Location**: Bronze City depths
**Participants**: 路明非, 诺诺
**Salience**: 0.95

**What happened (from simulation)**:
Lu Mingfei overcomes fear and activates the escape mechanism

**Outcome (from simulation)**:
The passage opens, allowing escape

**Mandatory facts (MUST appear in prose)**:
1. 🔴 [action] Lu Mingfei pressed the switch
2. 🔴 [state_change] Passage state → open
3. 🟡 [location_change] Characters move toward exit

**Dialogue (use exact wording)**:
- **诺诺**: "准备好了吗?"
- **路明非**: "真烦."

**State changes (must be reflected)**:
- 路明非: emotional_state → determined_resignation
- 路明非: location → passage_entrance
```

### Section 2: Style Template (HOW to write)

```markdown
# STYLE TEMPLATE (Match original author's writing style)

Your job is to write in THIS style while rendering the simulation events above.

**Narrative voice**: Third-person limited with rich internal monologue,
cynical and self-deprecating tone mixing mundane observations with cosmic stakes

**POV**: Focalized through protagonist

**Tense**: past

## Sentence Rhythm Examples (from original)

Study these to match the author's rhythm and cadence:

1. 黑暗像一堵湿漉漉的墙,把所有人推搡着往下坠。

2. 水不是水,是黑色的巨蟒在血管里游动。路明非觉得自己像一颗被扔进滚筒洗衣机的葡萄干...

## Description Technique Examples (from original)

Notice how the author renders sensory details and atmosphere:

1. 周围的空气开始扭曲,原本漆黑的背景里浮现出无数金色的眼睛,它们在虚空中眨动,像是一群窥探猎物的蛇...

---

**Your task**: Render the simulation events in THIS writing style.
- Match the rhythm, tone, and techniques shown above
- But the CONTENT must come from simulation, not invention
```

### Section 3: Synthesis Instructions (length, density, etc.)

Standard chapter requirements: target length, scene count, etc.

---

## Integration

### Basic Usage

```python
from dreamdive.prompts.p5_synthesis_fidelity import build_fidelity_first_synthesis_prompt

# Collect simulation details
beat_details_by_event = {
    "evt_001": [
        {"character_id": "路明非", "dialogue": "真烦.", "physical_action": "按下开关"},
        {"character_id": "诺诺", "dialogue": "准备好了吗?", "physical_action": "拉住路明非的手"},
    ],
}

state_changes_by_event = {
    "evt_001": [
        {"character_id": "路明非", "dimension": "emotional_state", "to_value": "determined"},
        {"character_id": "路明非", "dimension": "location", "to_value": "passage_entrance"},
    ],
}

# Build prompt
prompt = build_fidelity_first_synthesis_prompt(
    event_window=window,
    novel_meta=meta,
    user_meta=user_meta,
    chapter_number=67,
    beat_details_by_event=beat_details_by_event,
    state_changes_by_event=state_changes_by_event,
)

# Generate
chapter = llm_client.generate(prompt)
```

### With Validation

```python
from dreamdive.prompts.p5_synthesis_fidelity import build_synthesis_validation_prompt
from dreamdive.synthesis_fidelity import build_grounded_event_summary

# Build grounded summaries
grounded_events = [
    build_grounded_event_summary(event, beat_details_by_event.get(event.event_id))
    for event in window.events
]

# Generate chapter
chapter = llm_client.generate(synthesis_prompt)

# Validate
validation_prompt = build_synthesis_validation_prompt(
    chapter_text=chapter,
    grounded_events=grounded_events,
    constraints=constraints,
)

validation_result = llm_client.generate(validation_prompt)
# Returns JSON with fidelity_score, missing_facts, contradictions, etc.
```

---

## What's Allowed vs. Forbidden

### ✅ ALLOWED: Scene Expansion

**Simulation says**: "Lu Mingfei activates the mechanism"

**Synthesis can add**:
- Sensory details: "指尖触到冰冷的金属,触感粗糙得像握住了巨人的心脏"
- Atmosphere: "周围的空气凝固了,只剩下心跳声在耳膜里回荡"
- Internal monologue: "真烦。但他还是伸出了手,因为身后已经无路可退"

**WHY**: These add literary richness without changing facts.

### ✅ ALLOWED: Internal Monologue (if consistent)

**Simulation provides**: Character state = "frustrated but determined"

**Synthesis can invent**: "真烦,为什么总是我去救世界? 但他知道,如果不做,这世界会继续腐烂下去"

**WHY**: As long as thoughts match character state from simulation, they enhance characterization.

### ✅ ALLOWED: Transitional Scenes

**Simulation has gap**: Event at Bronze City → Event at surface

**Synthesis can add**: Brief transition showing movement between locations

**CONSTRAINT**: Transition must be SHORT (1-2 paragraphs) and NOT introduce new plot.

### ❌ FORBIDDEN: Changing Outcomes

**Simulation**: "Mechanism activates successfully. Passage opens."

**FORBIDDEN synthesis**: "Mechanism fails! They must find another way..."

**WHY**: Breaks simulation continuity. Future events assume passage opened.

### ❌ FORBIDDEN: Inventing Dialogue

**Simulation dialogue**: 诺诺: "准备好了吗?" 路明非: "真烦."

**FORBIDDEN**: Adding a long conversation not in simulation

**WHY**: Dialogue reveals character states and relationships. Invented dialogue can contradict simulation's model.

### ❌ FORBIDDEN: Adding New Plot Points

**Simulation**: 3 events happen

**FORBIDDEN synthesis**: Adding a 4th event not in simulation (e.g., "Suddenly, a dragon appears!")

**WHY**: Breaks the simulation's causal chain.

### ⚠️ BORDERLINE: Paraphrasing Dialogue

**Configuration dependent**: `allow_dialogue_paraphrasing`

**If FALSE**: Must use exact dialogue from simulation
**If TRUE**: Can rephrase while preserving meaning

**Recommendation**: Set to FALSE for most accurate simulation fidelity.

---

## Extracting Beat Details for Grounding

To get the most faithful synthesis, you need to pass detailed beat information:

### From Scene Resolution

If using P2 scene resolution, beats include:

```python
{
    "character_id": "路明非",
    "internal": {
        "thought": "这地方太吵了",
        "emotion_now": "overwhelmed_but_resolute",
    },
    "external": {
        "dialogue": "真烦。",
        "physical_action": "伸手按向开关",
        "tone": "resigned",
    },
}
```

**Extract for grounding**:

```python
beat_details_by_event = {}
for event in events:
    if event.resolution_mode == "scene":
        beats = []
        for agent_beat in event.agent_beats:
            beats.append({
                "character_id": agent_beat.character_id,
                "dialogue": agent_beat.external.dialogue,
                "physical_action": agent_beat.external.physical_action,
                "thought": agent_beat.internal.thought,
            })
        beat_details_by_event[event.event_id] = beats
```

### From Background Events

If using background resolution:

```python
{
    "narrative_summary": "Lu Mingfei overcomes fear and activates mechanism",
    "outcomes": [
        {"agent_id": "路明非", "goal_status": "achieved", "emotional_delta": "relief mixed with exhaustion"},
    ],
}
```

**Extract**:

```python
# Background events don't have detailed beats
# Use narrative_summary as the mandatory fact
SimulationFact(
    fact_statement=background_event.narrative_summary,
    is_mandatory=True,
)
```

---

## Configuration Options

### Adjust Fidelity Strictness

```python
# STRICT (highest fidelity)
constraints = SynthesisConstraints(
    allow_scene_expansion=True,  # Sensory details OK
    allow_internal_monologue_invention=False,  # No invented thoughts
    allow_dialogue_paraphrasing=False,  # Exact dialogue only
    allow_transitional_scenes=False,  # No transitions
)

# BALANCED (recommended)
constraints = SynthesisConstraints(
    allow_scene_expansion=True,
    allow_internal_monologue_invention=True,  # If consistent with state
    allow_dialogue_paraphrasing=False,
    allow_transitional_scenes=True,  # Brief transitions OK
)

# LOOSE (more creative freedom)
constraints = SynthesisConstraints(
    allow_scene_expansion=True,
    allow_internal_monologue_invention=True,
    allow_dialogue_paraphrasing=True,  # Can rephrase
    allow_transitional_scenes=True,
)
```

### Extract More Style Examples

```python
# Manually add more style examples
style_template.sentence_rhythm_examples.extend([
    "Example sentence 1 from original",
    "Example sentence 2 from original",
])

style_template.description_technique_examples.extend([
    "How author describes action sequences",
    "How author describes emotional moments",
])
```

---

## Before/After Comparison

### Before: Standard Synthesis (No Fidelity Enforcement)

**Simulation Events**:
1. Lu Mingfei approaches mechanism (salience: 0.9)
2. Dialogue: 诺诺 "准备好了吗?" 路明非 "真烦." (salience: 0.8)
3. Lu Mingfei activates mechanism (salience: 1.0)
4. Passage opens (salience: 1.0)

**Generated Chapter** (problematic):
```
路明非站在机关前,犹豫了很久。诺诺问他是否准备好,他说有点烦。

突然,一条龙出现了! (❌ INVENTED - not in simulation)

经过一番激烈的战斗,路明非击败了龙,然后才激活机关。(❌ CHANGED OUTCOME)

机关启动后,他们顺利逃脱,还遇到了其他幸存者。(❌ INVENTED CONTENT)
```

**Problems**:
- Invented dragon fight
- Changed sequence (should activate first)
- Added characters not in simulation
- Lost exact dialogue

### After: Fidelity-First Synthesis

**Same Simulation Events**

**Generated Chapter** (correct):
```
路明非跪在青铜城的街道上,膝盖底下的石板冷得像冰窖里的尸体。(✅ Scene expansion)
他伸手去摸地上的东西,指尖触到一片碎屑。(✅ Sensory detail)

这地方太吵了,他想。全是那种嗡嗡的声音,听得我头疼。(✅ Internal monologue, consistent with state)

前面就是逃生通道的入口,一扇被藤蔓缠绕的石门。如果不去触碰那个开关,这里就会彻底塌掉。(✅ Stakes from simulation)

"准备好了吗?"诺诺问。她的声音很轻,却穿透了厚重的水汽。(✅ EXACT dialogue from simulation)

"真烦。"路明非低声回答,然后站了起来。(✅ EXACT dialogue, with action)

他伸出手,指尖触碰到那个冰冷的金属凹槽。那一瞬间,所有的声音都消失了。(✅ Scene expansion)
他猛地按下开关。(✅ MANDATORY FACT - activation)

通道开启了。零的声音恢复了平静,"建议立刻撤离。"(✅ OUTCOME from simulation)
```

**Correct**:
- No invented plot points
- Exact dialogue preserved
- All mandatory facts included (approach, dialogue, activation, outcome)
- Rich sensory details added
- Matches original style
- Preserves causality

---

## Validation

Use the validation prompt to check fidelity:

```python
validation = llm_client.generate(build_synthesis_validation_prompt(...))

# Example response:
{
    "fidelity_score": 0.95,
    "missing_facts": [],
    "contradictions": [],
    "invented_content": [],
    "overall_assessment": "Excellent fidelity. All simulation events rendered accurately with rich stylistic detail."
}
```

**Low score example**:
```json
{
    "fidelity_score": 0.65,
    "missing_facts": ["Lu Mingfei activating the switch is not clearly shown"],
    "contradictions": ["Chapter shows passage failing to open, but simulation had it succeeding"],
    "invented_content": ["Added a dragon fight scene not in simulation"],
    "overall_assessment": "Poor fidelity. Multiple inventions and outcome changes."
}
```

---

## Best Practices

### 1. Provide Detailed Beat Information

The more detail you extract from simulation, the better:

```python
# GOOD
beat_details_by_event = {
    "evt_001": [
        {"character_id": "路明非", "dialogue": "真烦.", "physical_action": "按下开关", "thought": "为什么总是我"},
        {"character_id": "诺诺", "dialogue": "准备好了吗?", "physical_action": "握紧武器"},
    ],
}

# LESS IDEAL (missing details)
beat_details_by_event = {}  # Empty - LLM has less to ground on
```

### 2. Extract Style Examples During Ingestion

During P1, save representative passages:

```python
# In meta-layer extraction
meta.writing_style.sample_passages = [
    {
        "text": "黑暗像一堵湿漉漉的墙...",
        "why_representative": "Typical metaphorical description style",
    },
    ...
]
```

### 3. Use Validation in Production

Don't just generate and publish - validate:

```python
chapter = generate_chapter(...)

validation = validate_chapter(chapter, grounded_events)

if validation["fidelity_score"] < 0.85:
    # Log warning or regenerate
    print(f"Low fidelity: {validation['overall_assessment']}")
```

### 4. Iterate on Style Templates

If generated prose doesn't match style:

1. Add more style examples
2. Make voice description more specific
3. Include counter-examples ("NOT like this...")

---

## Summary

✅ **Simulation Fidelity**: Content comes from simulation, not invention
✅ **Style Transfer**: Writing style matches original author
✅ **Grounded Events**: Explicit mandatory facts prevent drift
✅ **Constraints**: Clear rules about allowed vs. forbidden
✅ **Validation**: Check fidelity after generation

**The key insight**: Synthesis is RENDERING (like cinematography), not CREATING (like screenwriting).

**Result**: Chapters that faithfully reflect simulation outcomes while reading like the original novel.
