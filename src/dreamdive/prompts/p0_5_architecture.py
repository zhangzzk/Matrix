"""
P0.5: Narrative Architecture Design Prompts

Designs the story BEFORE simulation begins, creating gravitational structure
that guides emergence while preserving creative freedom.

DESIGN PHILOSOPHY:
- Learn patterns from source material (meta-layer, fate layer)
- Design continuation that feels native to source
- Create GRAVITY (pull) not RAILS (scripts)
- Balance: Planned arcs + Emergent dynamics
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from dreamdive.language_guidance import build_language_guidance, format_language_guidance_block
from dreamdive.meta_injection import format_meta_section
from dreamdive.prompts.common import REASONING_INSTRUCTION, CLARITY_INSTRUCTION, FIDELITY_INSTRUCTION
from dreamdive.schemas import PromptRequest


def build_story_arc_design_prompt(
    source_material_summary: str,
    extracted_meta: Dict[str, Any],
    extracted_fate: Dict[str, Any],
    user_config: Dict[str, Any],
    continuation_goal: str = "",
    language_guidance: str = "",
) -> PromptRequest:
    """
    P0.5.1: Design overall story arc for simulation.

    Like planning a TV season: what's the big question, what are the major beats?
    """
    # Format meta-layer elements
    themes = extracted_meta.get("authorial", {}).get("themes", [])
    themes_text = "\n".join([f"- {t.get('name', '')}: {t.get('description', '')}" for t in themes[:5]])

    design_tendencies = extracted_meta.get("design_tendencies", {})
    story_arch_desc = design_tendencies.get("story_architecture", {}).get("structure_and_pacing", "")

    genre_taste = extracted_meta.get("genre_taste", {})
    taste_profile = genre_taste.get("taste_profile", "")
    taste_masters = genre_taste.get("reference_masters", [])

    # Format existing fate layer
    existing_arcs = extracted_fate.get("extracted", {}).get("character_arcs", [])
    arcs_text = "\n".join([
        f"- {arc.get('character_id', '')}: {arc.get('central_tension', '')}"
        for arc in existing_arcs[:5]
    ])

    central_question = extracted_fate.get("extracted", {}).get("dramatic_blueprint", {}).get("central_question", "")

    system = (
        "You are a narrative architect designing a story arc that continues from source material. "
        "You must be LOYAL to source patterns while being CREATIVE on top. "
        "Think: 'If the original author continued this story, how would they structure it?'"
    )

    language_block = format_language_guidance_block(language_guidance)

    user = (
        f"{language_block}"
        "# TASK: Design Story Arc\n\n"
        "Design a narrative arc for simulation that:\n"
        "1. Feels native to the source material (could be written by original author)\n"
        "2. Follows learned patterns from source\n"
        "3. Is creative and original (not just rehashing source)\n"
        "4. Creates GRAVITATIONAL PULL (waypoints) not RAILS (scripted events)\n\n"
        "---\n\n"
        "# SOURCE MATERIAL CONTEXT\n\n"
        f"{source_material_summary}\n\n"
        "## Themes from Source\n\n"
        f"{themes_text}\n\n"
        "## Story Structure Patterns\n\n"
        f"{story_arch_desc}\n\n"
        + (
            "## Genre Taste Benchmark\n\n"
            f"{taste_profile}\n\n"
            + (
                "Reference masters: "
                + "; ".join(f"{m.get('name', '')} — {m.get('why', '')}" for m in taste_masters[:4] if m.get("name"))
                + "\n\n"
                if taste_masters else ""
            )
            if taste_profile else ""
        )
        + "## Existing Character Arcs (from source)\n\n"
        f"{arcs_text}\n\n"
        "## Central Dramatic Question (from source)\n\n"
        f"{central_question}\n\n"
        "---\n\n"
        "# USER CONFIGURATION\n\n"
        f"Continuation goal: {continuation_goal or 'Continue story naturally'}\n"
        f"User preferences: {json.dumps(user_config, ensure_ascii=False, indent=2)}\n\n"
        "---\n\n"
        "# DESIGN REQUIREMENTS\n\n"
        "1. **Central Dramatic Question**: What's the big question driving this arc?\n"
        "   - Should echo source's themes\n"
        "   - Should feel like natural continuation\n\n"
        "2. **Narrative Nodes**: Design 5-8 waypoints that create gravitational pull\n"
        "   - Each node = major narrative beat (revelation, turning point, confrontation)\n"
        "   - Nodes are DESTINATIONS not ROUTES (let simulation find path)\n"
        "   - Example: 'By mid-arc, the secret should be revealed' (gravity)\n"
        "   - NOT: 'In chapter 15, character X tells character Y the secret' (script)\n\n"
        "3. **Gravity Strength**: Assign pull strength (0.0-1.0)\n"
        "   - 1.0 = Inevitable (must happen for story to work)\n"
        "   - 0.7 = Strong pull (probable but can be delayed)\n"
        "   - 0.5 = Moderate pull (possible alternate paths)\n"
        "   - 0.3 = Weak pull (nice if happens, not essential)\n\n"
        "4. **Allowed Phases**: Each node's `phase` MUST be exactly one of: 'setup', 'rising_action', 'midpoint', 'complications', 'climax', 'resolution', or 'epilogue'.\n\n"
        "5. **Meta-Adherence**: What must be preserved from source?\n"
        "   - Character core traits\n"
        "   - World rules and constraints\n"
        "   - Tone and themes\n\n"
        "6. **Creative Freedom**: Where can we invent?\n"
        "   - New characters (if they feel native)\n"
        "   - New plot threads (if they fit themes)\n"
        "   - Unexpected twists (if they respect character logic)\n\n"
        f"{REASONING_INSTRUCTION}\n\n"
        "# OUTPUT FORMAT\n\n"
        "Return JSON:\n\n"
        "```json\n"
        "{\n"
        '  "arc_name": "此篇章的标题",\n'
        '  "central_dramatic_question": "驱动此篇章的核心问题",\n'
        '  "thematic_payload": "此篇章探索的主题",\n'
        '  "estimated_chapter_count": 30,\n'
        '  "narrative_nodes": [\n'
        "    {\n"
        '      "node_id": "node_revelation_1",\n'
        '      "phase": "midpoint",\n'
        '      "estimated_chapter_range": "Ch 15-20",\n'
        '      "narrative_significance": "此节点为何重要",\n'
        '      "desired_outcome": "世界应达到的状态",\n'
        '      "dramatic_function": "revelation",\n'
        '      "gravity_strength": 0.9,\n'
        '      "prerequisites": ["铺垫完成", "信任建立"],\n'
        '      "unlocks": ["新的冲突层面", "角色成长"]\n'
        "    }\n"
        "  ],\n"
        '  "must_respect": ["角色核心特质", "世界规则"],\n'
        '  "can_invent": ["新配角", "支线剧情"]\n'
        "}\n"
        "```\n\n"
        f"{FIDELITY_INSTRUCTION}\n"
        f"{CLARITY_INSTRUCTION}"
    )

    return PromptRequest(
        system=system,
        user=user,
        max_tokens=3_000,
        metadata={"prompt_name": "p0_5_1_arc_design"},
    )


def build_character_arc_design_prompt(
    character_id: str,
    character_summary: Dict[str, Any],
    story_arc: Dict[str, Any],
    extracted_meta: Dict[str, Any],
    language_guidance: str = "",
) -> PromptRequest:
    """
    P0.5.2: Design development trajectory for a character across the arc.
    """
    char_name = character_summary.get("name", character_id)
    char_background = character_summary.get("background", "")
    char_traits = character_summary.get("identity", {}).get("core_traits", [])
    char_starting_goals = character_summary.get("current_state", {}).get("goal_stack", [])

    arc_question = story_arc.get("central_dramatic_question", "")
    arc_nodes = story_arc.get("narrative_nodes", [])

    genre_taste = extracted_meta.get("genre_taste", {})
    taste_profile = genre_taste.get("taste_profile", "")

    system = (
        "You are a character development architect. "
        "Design a growth trajectory that:\n"
        "1. Respects character's core traits from source\n"
        "2. Feels psychologically realistic\n"
        "3. Serves the overall story arc\n"
        "4. Creates waypoints for development, not a rigid path"
    )

    language_block = format_language_guidance_block(language_guidance)

    user = (
        f"{language_block}"
        f"# TASK: Design Character Arc for {char_name}\n\n"
        "Design how this character should develop across the story arc.\n\n"
        "---\n\n"
        "# CHARACTER CONTEXT\n\n"
        f"**Name**: {char_name}\n\n"
        f"**Background**: {char_background}\n\n"
        f"**Core Traits** (MUST preserve):\n" +
        "\n".join([f"- {t}" for t in char_traits[:5]]) + "\n\n"
        f"**Starting Goals**:\n" +
        "\n".join([f"- {g}" for g in char_starting_goals[:3]]) + "\n\n"
        "---\n\n"
        "# STORY ARC CONTEXT\n\n"
        f"**Central Question**: {arc_question}\n\n"
        f"**Major Nodes**: {len(arc_nodes)} planned waypoints\n\n"
        + (f"**Genre Taste Benchmark**: {taste_profile}\n\n" if taste_profile else "")
        + "---\n\n"
        "# DESIGN REQUIREMENTS\n\n"
        "1. **Starting State**: Character's psychological state at arc beginning\n"
        "2. **Ending State**: Where they should arrive (if things go as designed)\n"
        "3. **Development Trajectory**: Overall shape of change\n"
        "   - Example: 'Reluctant hero → Willing sacrifice'\n"
        "   - Example: 'Naive trust → Cynical wisdom → Earned hope'\n"
        "4. **Milestones**: 3-5 key points in development\n"
        "   - Each milestone = internal shift that manifests externally\n"
        "   - Create pull, not fixed timeline\n"
        "5. **Core Conflict**: What internal tension drives this arc?\n"
        "6. **Preservation**: What traits CANNOT change?\n"
        "7. **Evolution**: What traits CAN grow?\n\n"
        f"{REASONING_INSTRUCTION}\n\n"
        "# OUTPUT FORMAT\n\n"
        "```json\n"
        "{\n"
        f'  "character_id": "{character_id}",\n'
        '  "arc_starting_state": "篇章开始时的心理状态",\n'
        '  "arc_ending_state": "按设计路径发展后的终点",\n'
        '  "development_trajectory": "变化的形态",\n'
        '  "central_internal_conflict": "责任与欲望的冲突",\n'
        '  "milestones": [\n'
        "    {\n"
        '      "milestone_id": "m1_acceptance",\n'
        '      "description": "接受现实",\n'
        '      "estimated_timing": "前期",\n'
        '      "trigger_conditions": ["面对无法否认的证据"],\n'
        '      "internal_change": "否认 → 接受",\n'
        '      "external_change": "不再逃避，开始准备",\n'
        '      "manifests_as": ["认真对待训练", "主动提问"]\n'
        "    }\n"
        "  ],\n"
        '  "must_preserve_traits": ["核心特质"],\n'
        '  "can_evolve_traits": ["可成长的特质"]\n'
        "}\n"
        "```"
    )

    return PromptRequest(
        system=system,
        user=user,
        max_tokens=2_000,
        metadata={"prompt_name": "p0_5_2_character_arc", "character_id": character_id},
    )


def build_world_expansion_design_prompt(
    story_arc: Dict[str, Any],
    existing_world: Dict[str, Any],
    existing_characters: List[Dict[str, Any]],
    extracted_meta: Dict[str, Any],
    language_guidance: str = "",
) -> PromptRequest:
    """
    P0.5.3: Design new characters, locations, and plot threads.

    All new elements must feel native to source material.
    """
    # Extract source patterns
    char_construction = extracted_meta.get("design_tendencies", {}).get("character_construction", {})
    world_building = extracted_meta.get("design_tendencies", {}).get("world_building", {})

    recurring_types = char_construction.get("recurring_types", [])
    world_priorities = world_building.get("priorities", [])

    system = (
        "You are a world expansion architect. "
        "Design new story elements that feel NATIVE to the source material. "
        "If readers saw these new elements, they should think 'this could be from the original.'"
    )

    language_block = format_language_guidance_block(language_guidance)

    user = (
        f"{language_block}"
        "# TASK: Design World Expansion\n\n"
        "Design new characters, locations, and plot threads for this arc.\n"
        "ALL new elements must follow source material patterns.\n\n"
        "---\n\n"
        "# SOURCE PATTERNS TO FOLLOW\n\n"
        "## Character Archetypes (from source)\n\n" +
        "\n".join([f"- {t}" for t in recurring_types[:5]]) + "\n\n"
        "## World-Building Priorities (from source)\n\n" +
        "\n".join([f"- {p}" for p in world_priorities[:5]]) + "\n\n"
        "---\n\n"
        "# DESIGN REQUIREMENTS\n\n"
        "1. **New Characters** (if needed):\n"
        "   - Must serve story function (not decoration)\n"
        "   - Must match source character archetype patterns\n"
        "   - Name should fit source naming conventions\n"
        "   - Personality should feel like source\n"
        "   - Design when to introduce (timing)\n\n"
        "2. **New Locations** (if needed):\n"
        "   - Must advance plot or character development\n"
        "   - Must match source aesthetic\n"
        "   - Describe atmospheric qualities\n\n"
        "3. **New Plot Threads** (if needed):\n"
        "   - Must interweave with main arc\n"
        "   - Must feel thematically coherent\n\n"
        "4. **Meta-Adherence**:\n"
        "   - Style adherence: 0.9+ (nearly indistinguishable from source)\n"
        "   - Every new element should answer: 'Why does this feel native?'\n\n"
        f"{REASONING_INSTRUCTION}\n\n"
        "# OUTPUT FORMAT\n\n"
        "```json\n"
        "{\n"
        '  "new_characters": [\n'
        "    {\n"
        '      "character_id": "new_mentor_1",\n'
        '      "name": "符合原作风格的名字",\n'
        '      "role_in_story": "成长的催化剂",\n'
        '      "introduction_timing": "上升期前段",\n'
        '      "archetype_from_source": "神秘导师型",\n'
        '      "personality_sketch": "简要性格描述",\n'
        '      "background_sketch": "简要背景故事",\n'
        '      "matches_source_patterns": ["匹配的原作模式1", "匹配的原作模式2"]\n'
        "    }\n"
        "  ],\n"
        '  "new_locations": [\n'
        "    {\n"
        '      "location_id": "loc_1",\n'
        '      "name": "地点名称",\n'
        '      "role_in_story": "隐藏真相之处",\n'
        '      "introduction_timing": "中段",\n'
        '      "description_sketch": "视觉描述",\n'
        '      "atmospheric_qualities": ["压抑", "古老"],\n'
        '      "matches_source_aesthetic": "与原作风格契合的说明"\n'
        "    }\n"
        "  ],\n"
        '  "new_plot_threads": [\n'
        "    {\n"
        '      "thread_id": "thread_1",\n'
        '      "role_in_story": "给主线施压的副线悬念",\n'
        '      "introduction_timing": "上升期前段",\n'
        '      "summary": "关于被遗忘契约的传言使主角的主要目标更加复杂。",\n'
        '      "matches_source_patterns": [\n'
        '        "神话元素融入个人命运",\n'
        '        "与原作情节推进绑定的缓慢揭示"\n'
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "style_adherence_requirement": 0.9\n'
        "}\n"
        "```"
    )

    return PromptRequest(
        system=system,
        user=user,
        max_tokens=2_500,
        metadata={"prompt_name": "p0_5_3_world_expansion"},
    )


def build_chapter_roadmap_prompt(
    story_arc: Dict[str, Any],
    character_arcs: List[Dict[str, Any]],
    estimated_chapter_count: int,
    language_guidance: str = "",
) -> PromptRequest:
    """
    P0.5.4: Create rough roadmap for chapters.

    NOT scripts - high-level guidance about purpose and focus.
    """
    arc_nodes = story_arc.get("narrative_nodes", [])
    arc_question = story_arc.get("central_dramatic_question", "")

    system = (
        "You are creating a chapter roadmap - rough guidance, not scripts. "
        "Each chapter should have PURPOSE and DIRECTION while allowing emergence."
    )

    language_block = format_language_guidance_block(language_guidance)

    user = (
        f"{language_block}"
        "# TASK: Create Chapter Roadmap\n\n"
        f"Create a rough plan for {estimated_chapter_count} chapters.\n\n"
        "Each chapter plan should provide:\n"
        "- Purpose (MUST BE: setup, development, revelation, confrontation, transition, or reflection)\n"
        "- Which arc nodes it advances toward\n"
        "- Character focus\n"
        "- Thematic emphasis\n"
        "- Emotional arc\n\n"
        "**Allowed Purposes**: Each chapter's `purpose` MUST be exactly one of: 'setup', 'development', 'revelation', 'confrontation', 'transition', or 'reflection'.\n\n"
        "**IMPORTANT**: This is GUIDANCE not SCRIPT\n"
        "- Allow deviation if character dynamics demand it\n"
        "- Flexible timing\n"
        "- Room for emergent events\n\n"
        "---\n\n"
        f"# ARC CONTEXT\n\n"
        f"**Central Question**: {arc_question}\n\n"
        f"**Narrative Nodes**:\n" +
        "\n".join([
            f"- {node.get('node_id', '')}: {node.get('desired_outcome', '')} "
            f"({node.get('estimated_chapter_range', '')})"
            for node in arc_nodes
        ]) + "\n\n"
        "---\n\n"
        "# OUTPUT FORMAT\n\n"
        "Return array of chapter plans:\n\n"
        "```json\n"
        "[\n"
        "  {\n"
        '    "chapter_number": 1,\n'
        '    "purpose": "setup",\n'
        '    "advances_toward": ["node_id_1"],\n'
        '    "primary_pov_characters": ["char1", "char2"],\n'
        '    "key_character_moments": {"char1": "初识新的现实"},\n'
        '    "thematic_threads": ["身份认同", "责任"],\n'
        '    "target_emotional_arc": "困惑 → 逐渐觉醒",\n'
        '    "allow_deviation": true,\n'
        '    "deviation_threshold": 0.3\n'
        "  }\n"
        "]\n"
        "```"
    )

    return PromptRequest(
        system=system,
        user=user,
        max_tokens=16_000,
        metadata={"prompt_name": "p0_5_4_chapter_roadmap"},
    )


def build_hidden_worldbuilding_prompt(
    source_material_summary: str,
    story_arc: Dict[str, Any],
    characters: List[Dict[str, Any]],
    domain_systems: List[Dict[str, Any]],
    extracted_meta: Dict[str, Any],
    language_guidance: str = "",
) -> PromptRequest:
    """
    P0.5.2b: Infer hidden world-building details.

    Fills in the invisible settings that exist in the author's mind but
    aren't explicitly stated in the source material. Examples:
    - In Dragon Raja, each halfblood should have a 言灵 even if unnamed
    - In Harry Potter, each wizard should have a wand wood/core
    - Hidden faction hierarchies, prophecy details, secret backstories
    """
    # Format character summaries
    char_blocks = []
    for char in characters:
        char_id = char.get("character_id", char.get("id", "unknown"))
        char_name = char.get("name", char_id)
        traits = char.get("identity", {}).get("core_traits", [])
        background = char.get("background", "")
        existing_attrs = char.get("domain_attributes", {})
        block = (
            f"### {char_name} ({char_id})\n"
            f"Background: {background}\n"
            f"Traits: {', '.join(traits[:5])}\n"
        )
        if existing_attrs:
            block += f"Known attributes: {json.dumps(existing_attrs, ensure_ascii=False)}\n"
        else:
            block += "Known attributes: (none extracted from source)\n"
        char_blocks.append(block)

    # Format domain systems
    systems_text = ""
    if domain_systems:
        systems_blocks = []
        for sys in domain_systems:
            sys_name = sys.get("display_name", sys.get("system_key", ""))
            sys_desc = sys.get("description", "")
            sys_rules = sys.get("rules", [])
            block = f"- **{sys_name}**: {sys_desc}"
            if sys_rules:
                block += "\n  Rules: " + "; ".join(str(r) for r in sys_rules[:5])
            systems_blocks.append(block)
        systems_text = "\n".join(systems_blocks)
    else:
        systems_text = "(No domain systems explicitly identified — infer from source patterns)"

    system = (
        "You are a world-building architect operating at the AUTHOR level. "
        "Your job is to fill in the invisible settings that the original author "
        "had in mind but didn't explicitly state in the text. "
        "Think: 'What did the author design in their notes that never made it into the published text?'\n\n"
        "You must be:\n"
        "- CREATIVE: Invent details that feel genuinely part of this world\n"
        "- CONSISTENT: Everything must fit the source material's tone and rules\n"
        "- RESTRAINED: Only infer what the world's logic demands — don't over-embellish\n"
        "- THOUGHTFUL: Each inference should serve potential narrative purpose"
    )

    language_block = format_language_guidance_block(language_guidance)

    user = (
        f"{language_block}"
        "# TASK: Infer Hidden World-Building Details\n\n"
        "Fill in the invisible settings that the original author would have designed "
        "but didn't explicitly reveal in the source material.\n\n"
        "Think about:\n"
        "- What abilities/attributes SHOULD characters have based on the world's rules?\n"
        "- What world rules are IMPLIED but never explicitly stated?\n"
        "- What hidden backstories explain character behavior patterns?\n"
        "- What faction secrets, prophecies, or power hierarchies exist beneath the surface?\n\n"
        "---\n\n"
        "# SOURCE CONTEXT\n\n"
        f"{source_material_summary}\n\n"
        "## Domain Systems in This World\n\n"
        f"{systems_text}\n\n"
        "## Story Arc\n\n"
        f"Central question: {story_arc.get('central_dramatic_question', '')}\n"
        f"Themes: {story_arc.get('thematic_payload', '')}\n\n"
        "---\n\n"
        "# CHARACTERS TO DESIGN FOR\n\n" +
        "\n".join(char_blocks) + "\n"
        "---\n\n"
        "# DESIGN REQUIREMENTS\n\n"
        "1. **Character Attributes**: For each character who SHOULD have a domain attribute "
        "(based on the world's rules) but doesn't have one explicitly stated:\n"
        "   - Infer what their attribute would be\n"
        "   - Make it consistent with their personality, background, and role\n"
        "   - Decide visibility (public/private/hidden)\n"
        "   - Consider if it can evolve during the story\n\n"
        "2. **Hidden World Rules**: What rules are implied?\n"
        "   - Power system mechanics not fully explained\n"
        "   - Social hierarchy details\n"
        "   - Consequences of certain actions\n"
        "   - How different systems interact\n\n"
        "3. **Hidden Backstories**: What backstory elements explain behavior?\n"
        "   - Past events implied by current behavior\n"
        "   - Relationships before the story began\n"
        "   - Secrets characters are keeping\n\n"
        "4. **Restraint**: Do NOT infer attributes for characters who clearly don't belong "
        "to the relevant system (e.g., don't give a muggle a wand, "
        "don't give a pure human a 言灵).\n\n"
        f"{REASONING_INSTRUCTION}\n\n"
        "# OUTPUT FORMAT\n\n"
        "```json\n"
        "{\n"
        '  "character_attributes": [\n'
        "    {\n"
        '      "character_id": "char_id",\n'
        '      "character_name": "角色名",\n'
        '      "attribute_key": "word_spirit",\n'
        '      "attribute_value": {\n'
        '        "name": "属性名称",\n'
        '        "description": "属性描述",\n'
        '        "power_level": "等级或程度"\n'
        "      },\n"
        '      "visibility": "hidden",\n'
        '      "reasoning": "为什么推断此角色拥有这个属性",\n'
        '      "can_evolve": true,\n'
        '      "evolution_triggers": ["可能触发变化的条件"]\n'
        "    }\n"
        "  ],\n"
        '  "world_rules": [\n'
        "    {\n"
        '      "rule_id": "rule_1",\n'
        '      "description": "推断出的世界规则",\n'
        '      "evidence": ["来自原作的支持证据"],\n'
        '      "confidence": "high",\n'
        '      "affects_systems": ["相关的世界体系"]\n'
        "    }\n"
        "  ],\n"
        '  "backstories": [\n'
        "    {\n"
        '      "character_id": "char_id",\n'
        '      "character_name": "角色名",\n'
        '      "backstory_elements": ["推断出的背景故事细节"],\n'
        '      "reasoning": "为什么这些背景与原作一致"\n'
        "    }\n"
        "  ],\n"
        '  "design_notes": "整体设计思路和注意事项"\n'
        "}\n"
        "```\n\n"
        f"{FIDELITY_INSTRUCTION}\n"
        f"{CLARITY_INSTRUCTION}"
    )

    return PromptRequest(
        system=system,
        user=user,
        max_tokens=6_000,
        metadata={"prompt_name": "p0_5_2b_hidden_worldbuilding"},
    )


def build_batched_character_arc_design_prompt(
    characters: List[Dict[str, Any]],
    story_arc: Dict[str, Any],
    extracted_meta: Dict[str, Any],
    language_guidance: str = "",
) -> PromptRequest:
    """
    P0.5.2 (batched): Design development trajectories for ALL focus characters
    in a single call instead of one call per character.
    """
    arc_question = story_arc.get("central_dramatic_question", "")
    arc_nodes = story_arc.get("narrative_nodes", [])

    character_blocks = []
    character_ids = []
    for char in characters:
        char_id = char.get("character_id", "unknown")
        char_name = char.get("name", char_id)
        char_background = char.get("background", "")
        char_traits = char.get("identity", {}).get("core_traits", [])
        char_goals = char.get("current_state", {}).get("goal_stack", [])
        character_ids.append(char_id)
        character_blocks.append(
            f"### {char_name} ({char_id})\n"
            f"Background: {char_background}\n"
            f"Core traits: {', '.join(char_traits[:5])}\n"
            f"Starting goals: {', '.join(str(g) for g in char_goals[:3])}\n"
        )

    system = (
        "You are a character development architect. "
        "Design growth trajectories for ALL characters below that:\n"
        "1. Respect each character's core traits from source\n"
        "2. Feel psychologically realistic\n"
        "3. Serve the overall story arc\n"
        "4. Create waypoints for development, not rigid paths"
    )

    language_block = format_language_guidance_block(language_guidance)

    user = (
        f"{language_block}"
        f"# TASK: Design Character Arcs (Batched)\n\n"
        f"Design development trajectories for {len(characters)} characters.\n\n"
        "---\n\n"
        "# STORY ARC CONTEXT\n\n"
        f"**Central Question**: {arc_question}\n"
        f"**Major Nodes**: {len(arc_nodes)} planned waypoints\n\n"
        "---\n\n"
        "# CHARACTERS\n\n" +
        "\n".join(character_blocks) + "\n"
        "---\n\n"
        "# OUTPUT FORMAT\n\n"
        "Return a JSON array of character arc objects:\n\n"
        "```json\n"
        "[\n"
        "  {\n"
        '    "character_id": "<id>",\n'
        '    "arc_starting_state": "篇章开始时的心理状态",\n'
        '    "arc_ending_state": "按设计路径发展后的终点",\n'
        '    "development_trajectory": "变化的形态",\n'
        '    "central_internal_conflict": "责任与欲望的冲突",\n'
        '    "milestones": [\n'
        "      {\n"
        '        "milestone_id": "m1",\n'
        '        "description": "关键转变",\n'
        '        "estimated_timing": "前期",\n'
        '        "trigger_conditions": ["证据"],\n'
        '        "internal_change": "否认 → 接受",\n'
        '        "external_change": "不再逃避",\n'
        '        "manifests_as": ["可观察到的行为变化"]\n'
        "      }\n"
        "    ],\n"
        '    "must_preserve_traits": ["核心特质"],\n'
        '    "can_evolve_traits": ["可成长的特质"]\n'
        "  }\n"
        "]\n"
        "```\n\n"
        f"{REASONING_INSTRUCTION}"
    )

    return PromptRequest(
        system=system,
        user=user,
        max_tokens=6_000,
        metadata={
            "prompt_name": "p0_5_2_character_arc_batched",
            "character_count": len(characters),
        },
    )


__all__ = [
    "build_story_arc_design_prompt",
    "build_character_arc_design_prompt",
    "build_batched_character_arc_design_prompt",
    "build_hidden_worldbuilding_prompt",
    "build_world_expansion_design_prompt",
    "build_chapter_roadmap_prompt",
]
