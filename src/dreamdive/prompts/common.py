from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence


SOURCE_LANGUAGE_RULES = (
    "Language policy:\n"
    "- Keep ALL free-text values in the same language as the source text.\n"
    "- JSON keys may remain English to match the schema, but every description, "
    "summary, theme, motivation, trait, dialogue, analysis, and other narrative "
    "or analytical text MUST be written in the manuscript language.\n"
    "- Do not translate source material into English.\n"
    "- Preserve original wording, names, titles, and culturally specific terms "
    "unless a normalized ID is required.\n"
    "- The example values in the output contract below are English placeholders — "
    "you MUST replace them with values in the manuscript's own language.\n"
)

# Shared compact JSON-output rules for prompts returning structured data.
# Import this instead of defining _MANUSCRIPT_LANGUAGE_RULES per-file.
MANUSCRIPT_JSON_RULES: list[str] = [
    "No prose outside the JSON.",
    "All free-text values in manuscript language; do not invent English labels.",
]

REASONING_INSTRUCTION = "Think step-by-step before producing the final JSON."
CLARITY_INSTRUCTION = "Be clear and concise."
FIDELITY_INSTRUCTION = "Maintain high fidelity to the original source material's tone and style."


def meta_block(meta_section: str) -> str:
    """Format a [META] section for prompt injection. Shared across P2/P3."""
    text = str(meta_section or "").strip()
    if not text:
        return ""
    return f"{text}\n\n"

_PROMPT_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# ───────────────────────────────────────────────────────────────────────
# JSON contract builder
# ───────────────────────────────────────────────────────────────────────


def build_json_contract(
    example: dict[str, Any],
    *,
    extra_rules: list[str] | None = None,
) -> str:
    rules = [
        "Return exactly one JSON object using these exact keys.",
        "Do not rename keys, do not add extra keys, and do not wrap the JSON in markdown fences.",
    ]
    if extra_rules:
        rules.extend(extra_rules)
    rules.append("Keep every string concise and concrete.")
    return (
        "\n".join(rules)
        + "\n"
        + f"{json.dumps(example, indent=2, ensure_ascii=False, sort_keys=True)}\n\n"
    )


def build_source_language_policy(*texts: str) -> str:
    joined = "\n".join(texts)
    primary_language = "Chinese" if _PROMPT_CJK_RE.search(joined) else "English"
    return f"Primary language: {primary_language}\n{SOURCE_LANGUAGE_RULES}"


# ═══════════════════════════════════════════════════════════════════════
# Character Isolation Utilities
#
# These utilities enforce epistemic isolation — the principle that each
# character should only see, think, feel, and know what THEY would know.
# They are the primary defense against cross-character contamination.
# ═══════════════════════════════════════════════════════════════════════

_ISOLATION_SEPARATOR = "═" * 60


def build_character_isolation_header(
    *,
    character_id: str,
    character_name: str,
    role_instruction: str = "You are simulating this character.",
) -> str:
    """Create a visually prominent header that locks the LLM to one character.

    This should appear at the top of any prompt that operates on a single
    character's perspective. The visual markers reduce the LLM's tendency
    to drift into another character's voice or knowledge.
    """
    return (
        f"{_ISOLATION_SEPARATOR}\n"
        f"TARGET: {character_name} (ID: {character_id})\n"
        f"{role_instruction}\n"
        f"RULE: You are ONLY {character_name}. No other character's thoughts, feelings, "
        "knowledge, or voice. Others' inner states in context are invisible to you.\n"
        f"{_ISOLATION_SEPARATOR}\n"
    )


def build_participant_roster(
    participants: Sequence[Dict[str, Any]],
    *,
    label: str = "PARTICIPANTS IN THIS SCENE",
) -> str:
    """Create a clearly labeled roster so the LLM never confuses who is who.

    Each participant gets a block with their ID, name, and role clearly marked.
    This prevents the common failure mode where the LLM swaps participant A's
    goal with participant B's emotional state.
    """
    if not participants:
        return ""
    lines = [f"{label}:"]
    for i, p in enumerate(participants, 1):
        char_id = p.get("character_id", p.get("id", f"unknown_{i}"))
        name = p.get("name", char_id)
        lines.append(f"  [{i}] {name} (ID: {char_id})")
    lines.append("")
    return "\n".join(lines)


def build_information_barrier(
    *,
    from_character: str = "",
    to_character: str = "",
) -> str:
    """Insert an explicit information barrier between characters in batch prompts.

    The barrier serves as a visual and semantic break that tells the LLM:
    'stop thinking as character A, start thinking as character B.'
    """
    barrier = (
        f"\n{'━' * 40}\n"
        "⚠ BARRIER: Characters above and below are SEPARATE. "
        "No knowledge/emotion/voice transfer.\n"
    )
    if from_character and to_character:
        barrier += f"Leaving {from_character} → Entering {to_character}\n"
    return barrier + f"{'━' * 40}\n"


def build_multi_agent_preamble(
    agent_names: Sequence[str],
) -> str:
    """Preamble for any prompt that involves multiple agents.

    Establishes the epistemic isolation contract before any character
    data appears.
    """
    roster = ", ".join(agent_names)
    return (
        "MULTI-AGENT ISOLATION:\n"
        f"{len(agent_names)} characters: {roster}.\n"
        "Each character is epistemically isolated — their fears, secrets, plans, "
        "voice, and vocabulary are INVISIBLE to others. Only shared/public information crosses.\n\n"
    )


def format_character_block(
    *,
    character_id: str,
    character_name: str,
    data: Dict[str, Any],
    block_index: int | None = None,
    total_blocks: int | None = None,
) -> str:
    """Format a single character's data as a clearly bounded block.

    Used in multi-character prompts to visually separate each character's
    information and reduce cross-contamination.
    """
    index_label = ""
    if block_index is not None and total_blocks is not None:
        index_label = f" ({block_index}/{total_blocks})"
    return (
        f"┌── {character_name} (ID: {character_id}){index_label} ──┐\n"
        f"{json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)}\n"
        f"└── end {character_name} ──┘\n"
    )
