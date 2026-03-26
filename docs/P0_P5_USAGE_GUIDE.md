# P0 & P5 Usage Guide: User Configuration & Narrative Synthesis

## Overview

This guide covers the new **P0 (User Configuration)** and **P5 (Narrative Synthesis)** features that transform Dreamdive from a data extraction tool into a user-configurable novel generation system.

---

## Quick Start

```bash
# 1. Configure your preferences
dreamdive configure --novel-title "Your Novel" --author "Author Name"

# 2. Ingest with your preferences
dreamdive ingest novel.txt

# 3. Run simulation
dreamdive init-snapshot novel.txt --chapter-id chapter_01
dreamdive run --ticks 20

# 4. Generate novel chapters
dreamdive synthesize --start-tick 0 --end-tick 20

# 5. Read your chapters!
cat .dreamdive/chapters/chapter_001.txt
```

---

## Command Reference

### `dreamdive configure`

Configure user preferences that shape the entire pipeline.

**Usage:**
```bash
dreamdive configure [OPTIONS]
```

**Options:**
- `--workspace DIR` - Directory for config (default: `.dreamdive`)
- `--novel-title TEXT` - Title of the novel
- `--author TEXT` - Author name
- `--output FILE` - Output path (default: `workspace/user_meta.json`)

**What it does:**
1. Shows 6-question conversation prompt
2. Collects your answers interactively
3. Processes via P0 LLM prompt into structured `UserMeta`
4. Saves to `user_meta.json`

**Questions asked:**
1. **Tone**: How should output feel vs original? (faithful/darker/lighter/etc.)
2. **Emphasis**: What aspects to focus on? (psychology/politics/action/etc.)
3. **Divergence seeds**: What should change from original? (optional)
4. **Focus characters**: Who to follow closely? (optional)
5. **Output format**: Chapter length, POV style, pacing
6. **Free preferences**: Anything else?

**Example session:**
```bash
$ dreamdive configure --novel-title "Game of Thrones" --author "George R.R. Martin"

Welcome to Dreamdive novel simulation configuration!
[...questions displayed...]

Please answer the questions above (press Ctrl+D when done):
============================================================
Question 1: I want it darker and more psychological
Question 2: Focus on character psychology and internal conflict
Question 3: I want Ned Stark to survive
Question 4: Ned Stark, Jon Snow
Question 5: 3000 words per chapter, close third person
Question 6: I want more internal monologue
^D

Processing your preferences...

✓ Configuration saved to: .dreamdive/user_meta.json

Summary:
  Tone: darker and more psychological
  Emphasis: psychology, relationships
  Divergence seeds: 1
  Focus characters: Ned Stark, Jon Snow
  Chapter format: 3000 words, close_third
```

**Configuration file (`dreamdive.toml`):**
```toml
[configure]
novel_title = "Your Novel Title"
author = "Author Name"
output = ".dreamdive/user_meta.json"
```

---

### `dreamdive synthesize`

Generate novel chapters from simulation events.

**Usage:**
```bash
dreamdive synthesize [OPTIONS]
```

**Options:**
- `--workspace DIR` - Workspace directory (required)
- `--session-id ID` - Session ID (default: `default`)
- `--start-tick N` - Starting tick (default: `0`)
- `--end-tick N` - Ending tick (default: last tick)
- `--output-dir DIR` - Chapter output directory (default: `workspace/chapters`)
- `--ticks-per-chapter N` - Ticks per chapter (default: `10`)

**What it does:**
1. Loads `user_meta.json` and `novel_meta` from ingestion
2. Loads simulation events from session
3. Calculates chapter boundaries based on pacing preferences
4. For each chapter:
   - Selects high-salience events
   - Prioritizes focus character events
   - Synthesizes prose via P5.1 (chapter synthesis prompt)
   - Generates summary via P5.2 (for next chapter continuity)
5. Writes chapters to output directory

**Example:**
```bash
$ dreamdive synthesize --start-tick 0 --end-tick 50 --ticks-per-chapter 10

✓ Loaded user preferences from .dreamdive/user_meta.json

Synthesizing 5 chapters from ticks 0 to 50...
============================================================

Chapter 1: ticks 0-9
  ✓ Selected 12 events (8 high-salience)
  ✓ Generated 2847 words
  ✓ Written to .dreamdive/chapters/chapter_001.txt

Chapter 2: ticks 10-19
  ✓ Selected 15 events (10 high-salience)
  ✓ Generated 3124 words
  ✓ Written to .dreamdive/chapters/chapter_002.txt

[...]

✓ All chapters synthesized successfully!
```

**Configuration file (`dreamdive.toml`):**
```toml
[synthesize]
start_tick = 0
# end_tick defaults to last tick
output_dir = ".dreamdive/chapters"
ticks_per_chapter = 10
```

---

## How It Works

### P0: User Configuration

**Input**: Natural language conversation
**Output**: Structured `UserMeta` object

**Schema (`UserMeta`):**
```json
{
  "tone": {
    "overall": "darker and more psychological",
    "vs_original": "darker",
    "specific_notes": "More internal monologue"
  },
  "emphasis": {
    "primary": ["psychology", "relationships"],
    "deprioritize": ["action"],
    "notes": ""
  },
  "divergence_seeds": [
    {
      "description": "Ned Stark survives",
      "character_id": "char_ned_stark",
      "tick_hint": null,
      "strength": "strong"
    }
  ],
  "focus_characters": ["char_ned_stark", "char_jon_snow"],
  "chapter_format": {
    "target_word_count": 3000,
    "pov_style": "close_third",
    "story_time_per_chapter": "one day",
    "chapter_structure": "match_original"
  },
  "free_notes": "More internal monologue"
}
```

**How preferences are used:**

1. **During Ingestion** (P1):
   - [META] section injected into all prompts
   - Extraction emphasizes user's interests
   - Focus characters get more detailed extraction

2. **During Simulation** (P2/P3):
   - **Strong divergence seeds** → Injected as high-priority character goals
   - **Gentle divergence seeds** → Events leading toward them get +20% salience
   - **Focus characters** → Their events get +50% salience boost

3. **During Synthesis** (P5):
   - Chapter length matches user preference
   - POV style matches user preference
   - Emphasis guides what gets page time
   - Focus characters get more screen time

---

### P5: Narrative Synthesis

**Input**: Simulation events + preferences
**Output**: Novel chapter prose

**Process:**

#### 1. Event Window Selection
```python
# Select events for a chapter
window = select_chapter_window(
    events=all_simulation_events,
    start_tick=0,
    end_tick=10,
    user_meta=user_meta,
    min_salience=0.3,  # Filter low-salience events
)

# window.events = [EventSummary(...), ...]
# window.high_salience_events = ["evt_001", "evt_005"]
```

#### 2. Chapter Synthesis (P5.1)
```
Prompt includes:
- [META] section (novel style + user preferences)
- Voice samples from original novel
- Previous chapter summary (for continuity)
- Event window with salience scores
- User's chapter format requirements

LLM generates: Chapter prose in author's voice
```

#### 3. Chapter Summarization (P5.2)
```
Prompt includes:
- Full chapter text

LLM generates: 150-200 word summary for next chapter
```

**Example output (`chapter_001.txt`):**
```
Ned Stark rode through the gates of Winterfell, the weight of
his decision pressing upon him like the northern cold. He had
not expected Robert's offer, nor the burden it would place on
his honor...

[2800 words of prose in George R.R. Martin's style]
```

---

## Integration with Existing Workflow

### Before P0 & P5
```
novel.txt → ingest → simulation → technical data (unusable)
```

### After P0 & P5
```
configure → ingest → simulation → synthesize → novel chapters!
    ↓           ↓          ↓             ↓
  user      shaped    diverged      author's
  prefs    extraction  events         voice
```

### Modified Commands

**`dreamdive ingest`** now:
- Looks for `user_meta.json` in workspace
- If found, injects [META] into all extraction prompts
- Stores `user_meta` alongside `novel_meta` in `AccumulatedExtraction`

**No changes needed** to:
- `init-snapshot`
- `tick`
- `run`
- (Simulation will use divergence seeds when that integration is completed)

---

## Advanced Usage

### Custom Divergence Seeds

**Strong seed** (character pursues this actively):
```json
{
  "description": "Ned discovers Cersei's secret early",
  "character_id": "char_ned_stark",
  "tick_hint": "early chapters",
  "strength": "strong"
}
```

**Gentle seed** (opportunities arise, character chooses):
```json
{
  "description": "Jon and Arya grow closer",
  "character_id": null,  // affects multiple characters
  "tick_hint": null,
  "strength": "gentle"
}
```

### Variable Chapter Pacing

Set `story_time_per_chapter: "variable"` to let salience determine chapter breaks:
- High tension → shorter chapters (more frequent breaks)
- Low tension → longer chapters (more story time)

### Multiple Synthesis Passes

Generate chapters for different tick ranges:
```bash
# Part 1: Early story
dreamdive synthesize --start-tick 0 --end-tick 20 --output-dir chapters/part1

# Part 2: Mid story
dreamdive synthesize --start-tick 21 --end-tick 50 --output-dir chapters/part2
```

---

## File Structure

```
.dreamdive/
├── user_meta.json              # P0 output
├── ingestion_manifest.json     # Contains user_meta + novel_meta
├── artifacts/                  # Ingestion artifacts
├── simulation_data/            # Simulation state
└── chapters/                   # P5 output
    ├── chapter_001.txt
    ├── chapter_002.txt
    └── chapter_003.txt
```

---

## Troubleshooting

### "No user preferences found"
**Solution**: Run `dreamdive configure` before synthesizing.

### "Failed to load novel meta"
**Solution**: Run `dreamdive ingest` before synthesizing.

### "Failed to load simulation session"
**Solution**: Run `dreamdive init-snapshot` and `dreamdive run` before synthesizing.

### Chapters don't match user preferences
**Check**:
1. `user_meta.json` exists and contains your preferences
2. Ingestion was run AFTER configuration
3. User preferences are reasonable (LLM interprets them)

### Voice doesn't match original
**Check**:
1. Meta layer was extracted during ingestion
2. Voice samples exist in `novel_meta.writing_style.sample_passages`
3. Try increasing sample count or improving meta layer extraction

---

## API Reference

### UserMeta Fields

| Field | Type | Description |
|-------|------|-------------|
| `tone.overall` | str | Desired output tone description |
| `tone.vs_original` | enum | faithful/darker/lighter/more_psychological/divergent |
| `emphasis.primary` | list[str] | Aspects to emphasize |
| `divergence_seeds` | list[DivergenceSeed] | Story changes to introduce |
| `focus_characters` | list[str] | Character IDs to prioritize |
| `chapter_format.target_word_count` | int | Target words per chapter |
| `chapter_format.pov_style` | enum | alternating/single/close_third/omniscient |

### DivergenceSeed Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | str | What should change |
| `character_id` | str\|None | Character ID if specific, else None |
| `tick_hint` | str\|None | When to introduce (optional) |
| `strength` | enum | "strong" (goal) or "gentle" (opportunity) |

---

## Examples

See [examples/](examples/) for complete workflows:
- `game_of_thrones_darker.sh` - Making GoT darker
- `dragon_raja_faster_pacing.sh` - Faster chapter pacing
- `custom_divergence.json` - Complex divergence seed examples

---

**Documentation**: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
**Technical Details**: [FINAL_IMPLEMENTATION_SUMMARY.md](FINAL_IMPLEMENTATION_SUMMARY.md)
