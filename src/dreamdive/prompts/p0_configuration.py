from __future__ import annotations

from dreamdive.prompts.common import build_json_contract
from dreamdive.schemas import PromptRequest


def build_configuration_conversation_prompt() -> str:
    """Build the user-facing configuration conversation prompt."""
    return """
Welcome to Dreamdive novel simulation configuration!

I'll ask you a few questions to understand how you want the simulation to run.
Your answers will shape the tone, emphasis, and structure of the generated chapters.

Question 1: Tone and register
How do you want the output to feel compared to the original novel?
  - Faithful to the source
  - Darker or grittier
  - More psychological/introspective
  - More action-driven
  - More comedic
  - Your own description

Question 2: Thematic emphasis
What aspects of the story interest you most?
  - Character psychology and internal conflict
  - Political maneuvering and power dynamics
  - Relationships and loyalty
  - Action and consequences
  - World-building and lore
  - Something else (specify)

Question 3: Divergence seeds (optional)
Is there anything you want to happen differently from the original?
  - A character who survives instead of dying
  - A decision made differently
  - A relationship that develops differently
  - Or do you want the simulation to run freely without directed changes?

Question 4: Focus characters (optional)
Are there specific characters you want more attention on?
Characters whose POV you want to follow more closely?

Question 5: Output format
  - Target chapter length (word count)?
  - Should chapters alternate POVs like the original, or follow one character?
  - How fast should story time pass per chapter?

Question 6: Free preferences
Anything else about how you want this to feel or what you want to get out of it?

Please answer these questions in natural language. You can skip any question.
    """.strip()


def build_configuration_processing_prompt(
    conversation_transcript: str,
    *,
    novel_title: str = "",
    author: str = "",
) -> PromptRequest:
    """P0: Process user configuration conversation into structured user_meta."""
    output_contract = build_json_contract(
        {
            "tone": {
                "overall": "期望的输出基调描述",
                "vs_original": "faithful",
                "specific_notes": "具体的基调指示或null",
            },
            "emphasis": {
                "primary": ["psychology", "politics", "action", "relationships", "worldbuilding"],
                "deprioritize": ["需要弱化的方面"],
                "notes": "具体的侧重指示或null",
            },
            "divergence_seeds": [
                {
                    "description": "用户希望发生的不同情节",
                    "character_id": "char_001 or null",
                    "tick_hint": "故事中的时间点（如指定）或null",
                    "strength": "strong",
                }
            ],
            "focus_characters": ["char_001", "char_002"],
            "chapter_format": {
                "target_word_count": 2000,
                "pov_style": "alternating",
                "story_time_per_chapter": "一天或variable或null",
                "chapter_structure": "match_original",
            },
            "free_notes": "以上未涵盖的其他偏好或null",
        }
    )
    novel_context = ""
    if novel_title:
        novel_context = f"\nNOVEL BEING SIMULATED:\n{novel_title}"
        if author:
            novel_context += f" by {author}"
        novel_context += "\n\n"
    return PromptRequest(
        system=(
            "You are initializing a novel simulation system for a user. "
            "You have just had a configuration conversation with them. "
            "Process their preferences into a structured user_meta object. "
            "This object will be injected into the [META] section of every prompt in the system. "
            "It must be specific and actionable. Return valid JSON only."
        ),
        user=(
            "CONVERSATION TRANSCRIPT:\n"
            f"{conversation_transcript}\n\n"
            f"{novel_context}"
            "Process their preferences into a structured user_meta object.\n"
            "Be specific: translate vague preferences into concrete instructions.\n"
            "For divergence seeds, identify character IDs if mentioned, otherwise leave null.\n"
            "For focus characters, extract character names and convert to IDs if possible, "
            "otherwise store names and note they will be resolved during ingestion.\n\n"
            "Rules:\n"
            "- If the user wants the simulation to run freely without directed changes, "
            "leave divergence_seeds as an empty array.\n"
            "- If they didn't specify something, use sensible defaults or null.\n"
            "- The strength field for divergence seeds: 'strong' means inject as goal stack entry, "
            "'gentle' means increase salience weighting.\n"
            "- Output only JSON matching the user_meta schema.\n\n"
            "OUTPUT CONTRACT:\n"
            f"{output_contract}"
        ),
        max_tokens=2_000,
        stream=False,
        metadata={
            "prompt_name": "p0_configuration_processing",
            "response_schema": "UserMeta",
        },
    )


__all__ = [
    "build_configuration_conversation_prompt",
    "build_configuration_processing_prompt",
]
