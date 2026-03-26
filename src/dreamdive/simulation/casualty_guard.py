"""Mass casualty safeguard for the simulation pipeline.

Prevents the simulation from killing or permanently incapacitating
multiple major characters in a single event unless the Fate layer
explicitly justifies it.

The guard operates at two levels:
1. **Prompt-level**: Injects constraints into event prompts to discourage
   the LLM from generating mass death outcomes.
2. **Post-hoc validation**: After event simulation but before state commit,
   scans outcome text for lethal indicators and blocks or dampens events
   that exceed the casualty threshold.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class CharacterStatus(str, Enum):
    """Tracked status for each character in the simulation."""
    ALIVE = "alive"
    INCAPACITATED = "incapacitated"
    DEAD = "dead"


# -------------------------------------------------------------------
# Lethal-language detection
# -------------------------------------------------------------------

# Patterns that strongly indicate character death or permanent incapacitation.
# Bilingual: covers both Chinese and English since the simulation may output either.
_DEATH_PATTERNS_ZH = [
    r"死亡",
    r"死了",
    r"去世",
    r"身亡",
    r"丧命",
    r"殒命",
    r"毙命",
    r"殉",
    r"牺牲",
    r"生命.*归零",
    r"生命值.*归零",
    r"心跳.*停止",
    r"彻底.*崩溃",
    r"精神.*崩溃.*疯狂",
    r"全员.*死",
    r"全灭",
    r"团灭",
    r"无一.*幸免",
    r"无人.*生还",
]

_DEATH_PATTERNS_EN = [
    r"\bdied?\b",
    r"\bdead\b",
    r"\bkilled?\b",
    r"\bperished?\b",
    r"\bslain\b",
    r"\bfatal\b",
    r"\blethal\b",
    r"\bdeath\b",
    r"\bincapacitated\b",
    r"\bpermanently.*disabled\b",
    r"\blife.*drained\b",
    r"\bno.*survivors?\b",
    r"\bwipe.*out\b",
    r"\btotal.*loss\b",
    r"\bmental.*(?:collapse|breakdown).*(?:permanent|irreversible)\b",
]

_COMPILED_DEATH_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in _DEATH_PATTERNS_ZH + _DEATH_PATTERNS_EN
]


def detect_lethal_language(text: str) -> List[str]:
    """Return list of matched lethal-language patterns found in text."""
    matches: List[str] = []
    for pattern in _COMPILED_DEATH_PATTERNS:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return matches


def count_affected_characters(
    text: str,
    character_ids: List[str],
    character_names: Dict[str, str],
) -> Set[str]:
    """Identify which characters are referenced near lethal language.

    Scans the text for each character's ID and name, then checks if they
    appear within a window of lethal-language matches.
    """
    affected: Set[str] = set()
    lethal_spans = _find_lethal_spans(text)
    if not lethal_spans:
        return affected

    text_lower = text.lower()
    for char_id in character_ids:
        # Check if this character's ID or name appears near any lethal span
        name = character_names.get(char_id, "")
        char_markers = []
        for marker in [char_id, name]:
            if not marker:
                continue
            marker_lower = marker.lower()
            start = 0
            while True:
                pos = text_lower.find(marker_lower, start)
                if pos == -1:
                    break
                char_markers.append((pos, pos + len(marker_lower)))
                start = pos + 1

        for char_start, char_end in char_markers:
            for lethal_start, lethal_end in lethal_spans:
                # Within 200 characters of each other
                if abs(char_start - lethal_start) <= 200 or abs(char_end - lethal_end) <= 200:
                    affected.add(char_id)
                    break
            if char_id in affected:
                break

    # Special case: if text contains "全员" (all members) patterns, all are affected
    if re.search(r"全员|全灭|团灭|无一.*幸免|无人.*生还|no.*survivors?", text, re.IGNORECASE):
        affected = set(character_ids)

    return affected


def _find_lethal_spans(text: str) -> List[tuple[int, int]]:
    """Find character positions of lethal-language matches."""
    spans: List[tuple[int, int]] = []
    for pattern in _COMPILED_DEATH_PATTERNS:
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end()))
    return spans


# -------------------------------------------------------------------
# Casualty validation
# -------------------------------------------------------------------

@dataclass
class CasualtyAssessment:
    """Result of assessing an event outcome for mass casualties."""

    event_id: str
    outcome_text: str
    lethal_patterns_found: List[str] = field(default_factory=list)
    affected_character_ids: Set[str] = field(default_factory=set)
    total_participants: int = 0
    is_mass_casualty: bool = False
    allowed_by_fate: bool = False
    action: str = "allow"  # "allow", "dampen", "block"
    reason: str = ""


# Default thresholds
MAX_CASUALTIES_PER_EVENT = 1
MAX_CASUALTY_RATIO = 0.4  # At most 40% of participants can die in one event


@dataclass
class CasualtyGuardConfig:
    """Configuration for the casualty guard."""

    # Maximum number of characters that can die/be incapacitated in one event
    max_casualties_per_event: int = MAX_CASUALTIES_PER_EVENT
    # Maximum ratio of participants that can be casualties
    max_casualty_ratio: float = MAX_CASUALTY_RATIO
    # If True, completely block the event; if False, dampen to non-lethal
    block_on_violation: bool = False
    # Character IDs that the Fate layer has explicitly marked for death
    fate_sanctioned_deaths: Set[str] = field(default_factory=set)
    # Events explicitly designed to be mass-casualty (e.g., war, disaster arcs)
    mass_casualty_event_types: Set[str] = field(default_factory=set)


class CasualtyGuard:
    """Validates event outcomes against mass casualty thresholds.

    Integrates with the Fate layer: if the dramatic blueprint explicitly
    marks certain characters for death or a mass-casualty arc, the guard
    respects that design. Otherwise, it prevents the LLM from gratuitously
    killing characters.
    """

    def __init__(self, config: CasualtyGuardConfig | None = None) -> None:
        self.config = config or CasualtyGuardConfig()

    def assess_outcome(
        self,
        *,
        event_id: str,
        outcome_text: str,
        participant_ids: List[str],
        character_names: Dict[str, str],
        seed_type: str = "",
        character_statuses: Dict[str, CharacterStatus] | None = None,
    ) -> CasualtyAssessment:
        """Assess whether an event outcome contains mass casualties.

        Returns a CasualtyAssessment with the recommended action:
        - "allow": Outcome is fine, proceed normally.
        - "dampen": Outcome has too many casualties; rewrite to non-lethal.
        - "block": Outcome is catastrophic; skip this event entirely.
        """
        assessment = CasualtyAssessment(
            event_id=event_id,
            outcome_text=outcome_text,
            total_participants=len(participant_ids),
        )

        # Step 1: Detect lethal language
        assessment.lethal_patterns_found = detect_lethal_language(outcome_text)
        if not assessment.lethal_patterns_found:
            assessment.action = "allow"
            assessment.reason = "No lethal language detected"
            return assessment

        # Step 2: Identify affected characters
        assessment.affected_character_ids = count_affected_characters(
            outcome_text, participant_ids, character_names
        )
        if not assessment.affected_character_ids:
            assessment.action = "allow"
            assessment.reason = "Lethal language found but no specific characters affected"
            return assessment

        # Step 3: Check if this is a Fate-sanctioned event
        if seed_type in self.config.mass_casualty_event_types:
            assessment.allowed_by_fate = True
            assessment.action = "allow"
            assessment.reason = f"Event type '{seed_type}' is Fate-sanctioned for mass casualties"
            return assessment

        fate_sanctioned = assessment.affected_character_ids & self.config.fate_sanctioned_deaths
        unsanctioned = assessment.affected_character_ids - self.config.fate_sanctioned_deaths

        # Step 4: Check thresholds for unsanctioned casualties
        casualty_count = len(unsanctioned)
        if casualty_count <= 0:
            assessment.allowed_by_fate = True
            assessment.action = "allow"
            assessment.reason = "All casualties are Fate-sanctioned"
            return assessment

        casualty_ratio = (
            casualty_count / len(participant_ids) if participant_ids else 0
        )
        exceeds_count = casualty_count > self.config.max_casualties_per_event
        exceeds_ratio = casualty_ratio > self.config.max_casualty_ratio

        if exceeds_count or exceeds_ratio:
            assessment.is_mass_casualty = True
            if self.config.block_on_violation:
                assessment.action = "block"
                assessment.reason = (
                    f"Mass casualty blocked: {casualty_count} unsanctioned deaths "
                    f"(max {self.config.max_casualties_per_event}, "
                    f"ratio {casualty_ratio:.1%} > {self.config.max_casualty_ratio:.0%}). "
                    f"Affected: {', '.join(sorted(unsanctioned))}"
                )
            else:
                assessment.action = "dampen"
                assessment.reason = (
                    f"Mass casualty dampened: {casualty_count} unsanctioned deaths "
                    f"reduced to non-lethal. "
                    f"Affected: {', '.join(sorted(unsanctioned))}"
                )
            logger.warning(
                "CasualtyGuard triggered for event %s: %s",
                event_id,
                assessment.reason,
            )
        else:
            assessment.action = "allow"
            assessment.reason = (
                f"{casualty_count} casualty/ies within threshold"
            )

        return assessment

    def dampen_outcome_text(
        self,
        outcome_text: str,
        affected_ids: Set[str],
        character_names: Dict[str, str],
    ) -> str:
        """Rewrite an outcome to replace lethal consequences with severe-but-survivable ones.

        This is a text-level transformation that replaces death language with
        incapacitation language, preserving the dramatic weight while keeping
        characters alive for future narrative development.
        """
        dampened = outcome_text

        # Chinese replacements
        dampened = re.sub(r"死亡", "重伤昏迷", dampened)
        dampened = re.sub(r"死了", "倒下了", dampened)
        dampened = re.sub(r"去世", "陷入昏迷", dampened)
        dampened = re.sub(r"身亡", "重伤", dampened)
        dampened = re.sub(r"丧命", "濒死", dampened)
        dampened = re.sub(r"殒命", "濒临死亡", dampened)
        dampened = re.sub(r"毙命", "重伤不起", dampened)
        dampened = re.sub(r"全员.*死", "多人重伤", dampened)
        dampened = re.sub(r"全灭", "几近全灭，但仍有幸存", dampened)
        dampened = re.sub(r"团灭", "严重伤亡", dampened)
        dampened = re.sub(r"无一.*幸免", "大部分人受伤严重", dampened)
        dampened = re.sub(r"无人.*生还", "只有少数人勉强存活", dampened)
        dampened = re.sub(r"生命.*归零", "生命垂危", dampened)
        dampened = re.sub(r"生命值.*归零", "生命值几近归零", dampened)
        dampened = re.sub(r"心跳.*停止", "心跳微弱", dampened)
        dampened = re.sub(r"彻底.*崩溃", "精神几近崩溃", dampened)
        dampened = re.sub(r"精神.*崩溃.*疯狂", "精神严重受创", dampened)

        # English replacements
        dampened = re.sub(r"\bdied\b", "collapsed", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\bdead\b", "critically wounded", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\bkilled\b", "gravely injured", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\bperished\b", "fell unconscious", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\bslain\b", "incapacitated", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\bfatal\b", "severe", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\blethal\b", "devastating", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\bdeath\b", "near-death", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\bno survivors\b", "few survivors", dampened, flags=re.IGNORECASE)
        dampened = re.sub(r"\bwipe.*out\b", "devastate", dampened, flags=re.IGNORECASE)

        return dampened


# -------------------------------------------------------------------
# Prompt-level constraint injection
# -------------------------------------------------------------------

CASUALTY_CONSTRAINT_ZH = (
    "角色生死约束（强制）：\n"
    "- 不得在单个事件中杀死或永久伤残超过一名角色，除非命运层明确允许。\n"
    "- 角色可以受重伤、陷入危机、精神崩溃边缘——但不要轻易让他们死亡。\n"
    "- 死亡应该是叙事的高潮时刻，而非随意的集体灾难。\n"
    "- 如果场景的戏剧张力确实指向死亡，最多只允许一名角色死亡，"
    "其他角色应以重伤、昏迷或精神重创的形式存活。\n"
)

CASUALTY_CONSTRAINT_EN = (
    "CHARACTER MORTALITY CONSTRAINT (MANDATORY):\n"
    "- Do NOT kill or permanently incapacitate more than one character per event.\n"
    "- Characters may be severely injured, in crisis, or on the verge of breakdown — "
    "but do not casually kill them.\n"
    "- Death should be a climactic narrative moment, not a random mass disaster.\n"
    "- If dramatic tension genuinely points toward death, at most ONE character may die; "
    "others survive with severe injuries, unconsciousness, or psychological trauma.\n"
)


def build_casualty_constraint(language: str = "zh") -> str:
    """Build the casualty constraint block for prompt injection.

    Args:
        language: "zh" for Chinese, "en" for English, "both" for bilingual.
    """
    if language == "en":
        return CASUALTY_CONSTRAINT_EN
    if language == "both":
        return CASUALTY_CONSTRAINT_ZH + "\n" + CASUALTY_CONSTRAINT_EN
    return CASUALTY_CONSTRAINT_ZH
