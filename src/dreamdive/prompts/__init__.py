"""Central prompt builders organized by pipeline stage.

Legacy prompt modules re-export these builders for compatibility. New code
should import prompt builders from this package directly.
"""

from .p1_ingestion import (
    build_chapter_extraction_prompt,
    build_dramatic_blueprint_prompt,
    build_entity_extraction_context,
    build_entity_extraction_prompt,
    build_fate_extension_prompt,
    build_meta_layer_prompt,
    build_structural_scan_prompt,
)
from .p2_character import (
    build_batched_trajectory_projection_prompt,
    build_goal_seed_prompt,
    build_snapshot_inference_prompt,
    build_trajectory_projection_prompt,
)
from .p2_collisions import build_goal_collision_prompt
from .p2_scene import (
    build_agent_beat_prompt,
    build_background_event_prompt,
    build_resolution_check_prompt,
    build_spotlight_setup_prompt,
    build_state_update_prompt,
)
from .p3_memory import (
    build_arc_update_prompt,
    build_memory_compression_prompt,
)
from .p5_synthesis import (
    build_chapter_summary_prompt,
    build_chapter_synthesis_prompt,
    build_unified_synthesis_prompt,
)


PROMPT_GROUPS: dict[str, tuple[str, ...]] = {
    "p1_ingestion": (
        "build_structural_scan_prompt",
        "build_chapter_extraction_prompt",
        "build_meta_layer_prompt",
        "build_entity_extraction_context",
        "build_entity_extraction_prompt",
        "build_dramatic_blueprint_prompt",
        "build_fate_extension_prompt",
    ),
    "p2_character": (
        "build_snapshot_inference_prompt",
        "build_goal_seed_prompt",
        "build_trajectory_projection_prompt",
        "build_batched_trajectory_projection_prompt",
    ),
    "p2_collisions": ("build_goal_collision_prompt",),
    "p2_scene": (
        "build_background_event_prompt",
        "build_spotlight_setup_prompt",
        "build_agent_beat_prompt",
        "build_resolution_check_prompt",
        "build_state_update_prompt",
    ),
    "p3_memory": (
        "build_memory_compression_prompt",
        "build_arc_update_prompt",
    ),
    "p5_synthesis": (
        "build_chapter_synthesis_prompt",
        "build_chapter_summary_prompt",
        "build_unified_synthesis_prompt",
    ),
}


__all__ = [
    "PROMPT_GROUPS",
    "build_agent_beat_prompt",
    "build_arc_update_prompt",
    "build_background_event_prompt",
    "build_batched_trajectory_projection_prompt",
    "build_chapter_extraction_prompt",
    "build_dramatic_blueprint_prompt",
    "build_chapter_summary_prompt",
    "build_chapter_synthesis_prompt",
    "build_entity_extraction_context",
    "build_entity_extraction_prompt",
    "build_fate_extension_prompt",
    "build_goal_collision_prompt",
    "build_goal_seed_prompt",
    "build_memory_compression_prompt",
    "build_meta_layer_prompt",
    "build_resolution_check_prompt",
    "build_snapshot_inference_prompt",
    "build_spotlight_setup_prompt",
    "build_state_update_prompt",
    "build_structural_scan_prompt",
    "build_trajectory_projection_prompt",
    "build_unified_synthesis_prompt",
]
