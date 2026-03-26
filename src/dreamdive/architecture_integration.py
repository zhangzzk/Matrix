"""
P0.5 Architecture Integration

Orchestrates the complete narrative architecture design workflow:
1. Design overall story arc (macro)
2. Design character development trajectories (micro)
3. Design world expansion (new elements)
4. Design chapter roadmap (meso)

Runs after P1 ingestion, before initialization.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from dreamdive.ingestion.models import AccumulatedExtraction
from dreamdive.language_guidance import build_language_guidance
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.llm.openai_transport import build_transport
from dreamdive.config import get_settings
from dreamdive.narrative_architecture import (
    CharacterArcPlan,
    HiddenWorldbuildingPlan,
    NarrativeArchitecture,
    StoryArcDesign,
    WorldExpansionPlan,
    ChapterPlan,
)
from dreamdive.prompts.p0_5_architecture import (
    build_story_arc_design_prompt,
    build_character_arc_design_prompt,
    build_batched_character_arc_design_prompt,
    build_hidden_worldbuilding_prompt,
    build_world_expansion_design_prompt,
    build_chapter_roadmap_prompt,
)
from dreamdive.user_config import UserMeta

logger = logging.getLogger(__name__)


def _repair_truncated_json_array(text: str) -> str:
    """
    Attempt to repair a truncated JSON array by removing the last incomplete
    object and closing the array.  Returns the repaired string, or the
    original string if repair is not applicable.
    """
    # Only applies to arrays
    stripped = text.strip()
    if not stripped.startswith("["):
        return text

    # Walk backwards: trim trailing whitespace / commas, then check if the
    # array is already closed.
    trimmed = stripped.rstrip().rstrip(",").rstrip()
    if trimmed.endswith("]"):
        return trimmed  # already valid shape

    # Find the last complete object boundary (last '}' that is followed
    # eventually by another '{' or is the final element).
    last_close = trimmed.rfind("}")
    if last_close == -1:
        return text  # nothing to salvage

    # Check whether the text after last '}' contains an opening '{' —
    # that would be the start of a truncated object we need to drop.
    after_last_close = trimmed[last_close + 1:]
    if "{" in after_last_close:
        # Drop the incomplete trailing object
        candidate = trimmed[: last_close + 1].rstrip().rstrip(",")
    else:
        candidate = trimmed[: last_close + 1]

    # Close the array
    if not candidate.rstrip().endswith("]"):
        candidate = candidate.rstrip().rstrip(",") + "\n]"

    return candidate


def _repair_common_json_errors(text: str) -> str:
    """
    Fix common LLM JSON mistakes:
    - Trailing commas before } or ]
    - Unescaped newlines inside strings
    - Missing closing quotes before }, ], or comma
    """
    import re
    # Remove trailing commas: , } or , ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Fix missing closing quote before structural chars.
    # Pattern: an open quote, non-quote content, then directly }, ], or ,
    # without a closing quote.  e.g.  "value}  →  "value"}
    # We look for: "...<not-quote-not-backslash> followed by } ] or ,
    # where there's no closing quote.
    text = re.sub(
        r'(?<=")([^"\\]*?)([}\],])',
        lambda m: _fix_missing_close_quote(m),
        text,
    )
    return text


def _fix_missing_close_quote(m: "re.Match[str]") -> str:
    """Decide whether to insert a missing close-quote."""
    content = m.group(1)
    after = m.group(2)
    # If content ends with a colon + space, this is likely a key — don't fix
    if content.rstrip().endswith(":"):
        return m.group(0)
    # If the content looks like it should end the string value
    # (has actual content and the next char is structural), add closing quote
    if content and not content.endswith('"'):
        return content + '"' + after
    return m.group(0)


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """
    Extract JSON from LLM response that may be wrapped in markdown code blocks.
    Handles truncated responses and common LLM JSON errors.
    """
    import re
    code_block_pattern = r"```(?:json)?\s*\n(.*?)\n```"
    matches = re.findall(code_block_pattern, text, re.DOTALL)

    if matches:
        text = matches[0]

    # Attempt sequence: raw → truncation repair → common error repair → bounds extraction
    attempts = [
        text.strip(),
        _repair_truncated_json_array(text),
        _repair_common_json_errors(text.strip()),
        _repair_common_json_errors(_repair_truncated_json_array(text)),
    ]

    for attempt in attempts:
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue

    # Log the bad payload for debugging
    from pathlib import Path
    try:
        logs_dir = Path.cwd() / "logs"
        logs_dir.mkdir(exist_ok=True)
        with open(logs_dir / "bad_json_trace.txt", "w", encoding="utf-8") as _f:
            _f.write(text.strip())
    except Exception:
        pass

    # Try to find first { and last } or [ and ]
    start_obj = text.find("{")
    end_obj = text.rfind("}")
    start_arr = text.find("[")
    end_arr = text.rfind("]")

    # Extract the widest valid-looking bounds
    candidates = []
    if start_arr != -1 and end_arr != -1 and (start_obj == -1 or start_arr < start_obj) and (end_obj == -1 or end_arr > end_obj):
        candidates.append(text[start_arr:end_arr + 1])
    if start_obj != -1 and end_obj != -1:
        candidates.append(text[start_obj:end_obj + 1])

    for candidate in candidates:
        for transform in [lambda s: s, _repair_common_json_errors, lambda s: _repair_common_json_errors(_repair_truncated_json_array(s))]:
            try:
                return json.loads(transform(candidate))
            except (json.JSONDecodeError, Exception):
                continue

    raise json.JSONDecodeError("Could not extract valid JSON from response", text, 0)


class ArchitectureDesignWorkflow:
    """
    Orchestrates the P0.5 narrative architecture design process.

    Takes ingested source material and user configuration,
    produces complete narrative architecture for simulation.
    """

    def __init__(
        self,
        extraction: AccumulatedExtraction,
        client: StructuredLLMClient,
        user_meta: Optional[UserMeta] = None,
        session_id: str = "default",
    ):
        self.extraction = extraction
        self.client = client
        self.user_meta = user_meta or UserMeta()
        self.session_id = session_id

        # Cache for designed elements
        self.story_arc: Optional[StoryArcDesign] = None
        self.character_arcs: List[CharacterArcPlan] = []
        self.world_expansion: Optional[WorldExpansionPlan] = None
        self.hidden_worldbuilding: Optional[HiddenWorldbuildingPlan] = None
        self.chapter_plans: List[ChapterPlan] = []

    async def design_complete_architecture(
        self,
        continuation_goal: str = "",
    ) -> NarrativeArchitecture:
        """
        Run complete P0.5 design workflow.

        Returns complete NarrativeArchitecture ready for simulation.
        """
        logger.info("Starting P0.5 narrative architecture design workflow")

        # Build language guidance from meta layer
        self._language_guidance = build_language_guidance(self.extraction.meta)

        # Step 1: Design overall story arc
        logger.info("Step 1/4: Designing story arc")
        self.story_arc = await self._design_story_arc(continuation_goal)

        # Steps 2-4: Run character arcs, world expansion, and hidden worldbuilding concurrently
        # (all depend only on stage 1 output, independent of each other)
        logger.info("Steps 2-4/5: Designing character arcs, world expansion, and hidden worldbuilding in parallel")
        self.character_arcs, self.world_expansion, self.hidden_worldbuilding = await asyncio.gather(
            self._design_character_arcs(),
            self._design_world_expansion(),
            self._design_hidden_worldbuilding(),
        )

        # Step 5: Design chapter roadmap
        logger.info("Step 5/5: Designing chapter roadmap")
        self.chapter_plans = await self._design_chapter_roadmap()

        # Assemble complete architecture
        architecture = NarrativeArchitecture(
            architecture_id=f"arch_{self.session_id}",
            created_for_session=self.session_id,
            story_arc=self.story_arc,
            chapter_plans=self.chapter_plans,
            character_arcs=self.character_arcs,
            world_expansion=self.world_expansion,
            hidden_worldbuilding=self.hidden_worldbuilding,
            source_fidelity_requirements={
                "must_preserve_character_traits": True,
                "must_preserve_world_rules": True,
                "must_match_source_tone": True,
                "style_adherence_threshold": 0.9,
            },
            creative_freedom_bounds={
                "can_create_new_characters": True,
                "can_create_new_locations": True,
                "can_create_new_plot_threads": True,
                "must_feel_native_to_source": True,
            },
            default_gravity_strength=0.7,
            allow_emergent_override=True,
            override_threshold=0.8,
        )

        logger.info("P0.5 architecture design complete")
        return architecture

    async def _design_story_arc(self, continuation_goal: str) -> StoryArcDesign:
        """Step 1: Design overall story arc with narrative nodes."""
        # Prepare source material summary
        source_summary = self._build_source_summary()

        # Extract meta and fate layers
        meta_dict = self.extraction.meta.model_dump(mode="json")
        fate_dict = (
            self.extraction.fate.model_dump(mode="json")
            if self.extraction.fate
            else {}
        )

        # Build prompt
        user_config = self.user_meta.model_dump(mode="json")
        prompt_req = build_story_arc_design_prompt(
            source_material_summary=source_summary,
            extracted_meta=meta_dict,
            extracted_fate=fate_dict,
            user_config=user_config,
            continuation_goal=continuation_goal,
            language_guidance=self._language_guidance,
        )

        # Call LLM
        response = await self.client.call_text(prompt_req)

        # Parse and validate
        arc_data = _extract_json_from_response(response)

        # Convert to StoryArcDesign
        story_arc = StoryArcDesign(
            arc_id=f"arc_{self.session_id}",
            **arc_data
        )

        return story_arc

    async def _design_character_arcs(self) -> List[CharacterArcPlan]:
        """Step 2: Design development trajectories for all extracted characters.

        Uses a single batched LLM call. Major characters get detailed arcs;
        minor characters get concise summaries — the LLM handles this
        distinction based on the amount of source material for each.
        """
        # Include all extracted characters — the batched prompt handles
        # varying detail levels based on each character's importance.
        focus_characters = list(self.extraction.characters)

        # Narrow to user-specified subset only if explicitly configured
        if self.user_meta.focus_characters:
            focus_characters = [
                char for char in focus_characters
                if char.id in self.user_meta.focus_characters or char.name in self.user_meta.focus_characters
            ]

        meta_dict = self.extraction.meta.model_dump(mode="json")

        # Build batched character summaries
        char_summaries = []
        for character in focus_characters:
            char_summaries.append({
                "character_id": character.id,
                "name": character.name,
                "background": " ".join(character.identity.get("core_traits", [])),
                "identity": character.identity,
                "current_state": character.current_state.model_dump(mode="json"),
            })

        logger.info(f"Designing arcs for {len(char_summaries)} characters in single batch")

        # Single batched call
        prompt_req = build_batched_character_arc_design_prompt(
            characters=char_summaries,
            story_arc=self.story_arc.model_dump(mode="json"),
            extracted_meta=meta_dict,
            language_guidance=self._language_guidance,
        )

        response = await self.client.call_text(prompt_req)
        arcs_data = _extract_json_from_response(response)

        # Handle both array and wrapped-object responses
        if isinstance(arcs_data, dict) and "character_arcs" in arcs_data:
            arcs_data = arcs_data["character_arcs"]
        if not isinstance(arcs_data, list):
            arcs_data = [arcs_data]

        character_arcs = [CharacterArcPlan(**arc) for arc in arcs_data]
        return character_arcs

    async def _design_world_expansion(self) -> WorldExpansionPlan:
        """Step 3: Design new characters, locations, and plot threads."""
        # Prepare existing world and characters
        existing_world = self.extraction.world.model_dump(mode="json")
        existing_characters = [
            {
                "id": char.id,
                "name": char.name,
                "role": char.identity.get("role", ""),
            }
            for char in self.extraction.characters
        ]

        meta_dict = self.extraction.meta.model_dump(mode="json")

        # Build prompt
        prompt_req = build_world_expansion_design_prompt(
            story_arc=self.story_arc.model_dump(mode="json"),
            existing_world=existing_world,
            existing_characters=existing_characters,
            extracted_meta=meta_dict,
            language_guidance=self._language_guidance,
        )

        # Call LLM
        response = await self.client.call_text(prompt_req)

        # Parse
        expansion_data = _extract_json_from_response(response)
        world_expansion = WorldExpansionPlan(**expansion_data)

        return world_expansion

    async def _design_hidden_worldbuilding(self) -> HiddenWorldbuildingPlan:
        """Step 4: Infer hidden world-building details not explicit in source.

        Fills in invisible settings at the author level: character abilities,
        world rules, hidden backstories — things the author had in mind but
        didn't spell out in the text.
        """
        source_summary = self._build_source_summary()

        # Build character summaries with existing domain attributes
        char_summaries = []
        for character in self.extraction.characters:
            char_summaries.append({
                "character_id": character.id,
                "name": character.name,
                "background": " ".join(character.identity.get("core_traits", [])),
                "identity": character.identity,
                "domain_attributes": character.identity.get("domain_attributes", {}),
            })

        # Gather domain systems from extraction (if available)
        domain_systems: List[Dict[str, Any]] = []
        if hasattr(self.extraction, "domain_registry") and self.extraction.domain_registry:
            registry = self.extraction.domain_registry
            if hasattr(registry, "world_systems"):
                domain_systems = [
                    s.model_dump(mode="json") if hasattr(s, "model_dump") else dict(s)
                    for s in registry.world_systems
                ]
            elif isinstance(registry, dict):
                domain_systems = registry.get("world_systems", [])

        meta_dict = self.extraction.meta.model_dump(mode="json")

        prompt_req = build_hidden_worldbuilding_prompt(
            source_material_summary=source_summary,
            story_arc=self.story_arc.model_dump(mode="json"),
            characters=char_summaries,
            domain_systems=domain_systems,
            extracted_meta=meta_dict,
            language_guidance=self._language_guidance,
        )

        response = await self.client.call_text(prompt_req)
        worldbuilding_data = _extract_json_from_response(response)

        if isinstance(worldbuilding_data, list):
            # LLM returned a list — probably just the character_attributes array
            worldbuilding_data = {"character_attributes": worldbuilding_data}

        plan = HiddenWorldbuildingPlan(**worldbuilding_data)
        logger.info(
            "Hidden worldbuilding: inferred %d character attributes, "
            "%d world rules, %d backstories",
            len(plan.character_attributes),
            len(plan.world_rules),
            len(plan.backstories),
        )
        return plan

    async def _design_chapter_roadmap(self) -> List[ChapterPlan]:
        """Step 4: Design rough roadmap for chapters."""
        estimated_chapters = self.story_arc.estimated_chapter_count

        # Build prompt
        prompt_req = build_chapter_roadmap_prompt(
            story_arc=self.story_arc.model_dump(mode="json"),
            character_arcs=[arc.model_dump(mode="json") for arc in self.character_arcs],
            estimated_chapter_count=estimated_chapters,
            language_guidance=self._language_guidance,
        )

        # Call LLM
        response = await self.client.call_text(prompt_req)

        # Parse - should return array
        plans_data = _extract_json_from_response(response)
        if not isinstance(plans_data, list):
            # If response is wrapped in object, try to extract array
            if isinstance(plans_data, dict) and "chapter_plans" in plans_data:
                plans_data = plans_data["chapter_plans"]
            elif isinstance(plans_data, dict):
                # Single plan returned, wrap in list
                plans_data = [plans_data]
            else:
                raise ValueError(f"Expected array of chapter plans, got {type(plans_data)}")
        chapter_plans = [ChapterPlan(**plan) for plan in plans_data]

        return chapter_plans

    def _build_source_summary(self) -> str:
        """Build concise summary of source material for prompts."""
        lines = []

        # World context
        if self.extraction.world.setting:
            lines.append(f"Setting: {self.extraction.world.setting}")

        if self.extraction.world.time_period:
            lines.append(f"Time Period: {self.extraction.world.time_period}")

        # Characters
        if self.extraction.characters:
            lines.append("\nCharacters:")
            for char in self.extraction.characters:
                traits = ", ".join(char.identity.get("core_traits", [])[:3])
                lines.append(f"- {char.name}: {traits}")

        # Central dramatic question (if available)
        if self.extraction.fate and self.extraction.fate.extracted:
            question = self.extraction.fate.extracted.central_question
            if question:
                lines.append(f"\nCentral Question: {question}")

        # Current state
        if self.extraction.world.rules_and_constraints:
            lines.append("\nWorld Rules:")
            for rule in self.extraction.world.rules_and_constraints[:3]:
                lines.append(f"- {rule}")

        return "\n".join(lines)


def save_architecture_to_workspace(
    architecture: NarrativeArchitecture,
    workspace_path: Path,
) -> Path:
    """
    Save narrative architecture to workspace.

    Stored as JSON for easy loading during simulation.
    """
    arch_file = workspace_path / "narrative_architecture.json"

    with open(arch_file, "w", encoding="utf-8") as f:
        json.dump(
            architecture.model_dump(mode="json"),
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info(f"Saved narrative architecture to {arch_file}")
    return arch_file


def load_architecture_from_workspace(
    workspace_path: Path,
) -> Optional[NarrativeArchitecture]:
    """
    Load narrative architecture from workspace.

    Returns None if not found.
    """
    arch_file = workspace_path / "narrative_architecture.json"

    if not arch_file.exists():
        return None

    with open(arch_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    architecture = NarrativeArchitecture(**data)
    logger.info(f"Loaded narrative architecture from {arch_file}")

    return architecture


async def run_architecture_design_phase(
    workspace_path: Path,
    continuation_goal: str = "",
    client: Optional[StructuredLLMClient] = None,
    user_meta: Optional[UserMeta] = None,
) -> NarrativeArchitecture:
    """
    Run complete P0.5 architecture design phase.

    Loads extraction from workspace, designs architecture, saves result.

    This should be called after P1 ingestion, before initialization.
    """
    # Load extraction
    from dreamdive.simulation.workflow import load_accumulated_extraction
    
    extraction = load_accumulated_extraction(workspace_path)
    if not extraction.characters:
        raise FileNotFoundError(
            f"No valid extraction found at {workspace_path}/artifacts. "
            "Run P1 ingestion first."
        )

    # Create LLM client if not provided
    if client is None:
        settings = get_settings()
        transport = build_transport(settings)
        client = StructuredLLMClient.from_settings(transport, settings)

    # Determine session ID from workspace
    session_id = workspace_path.name

    # Run design workflow
    workflow = ArchitectureDesignWorkflow(
        extraction=extraction,
        client=client,
        user_meta=user_meta,
        session_id=session_id,
    )

    architecture = await workflow.design_complete_architecture(
        continuation_goal=continuation_goal,
    )

    # Save to workspace
    save_architecture_to_workspace(architecture, workspace_path)

    return architecture


__all__ = [
    "ArchitectureDesignWorkflow",
    "save_architecture_to_workspace",
    "load_architecture_from_workspace",
    "run_architecture_design_phase",
]
