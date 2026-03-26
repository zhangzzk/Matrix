"""Web-augmented author research for enriching the meta layer.

This module performs web searches to gather external information about
the author and the novel, then synthesizes it into structured context
that enriches the P1.3 meta layer extraction.

The research covers:
- Author biography and literary reputation
- Literary criticism and scholarly analysis
- Author interviews about their craft and intentions
- Historical and cultural context of the work
- The author's broader body of work and recurring themes
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

from dreamdive.llm.client import StructuredLLMClient
from dreamdive.schemas import PromptRequest

logger = logging.getLogger(__name__)


@dataclass
class AuthorResearchResult:
    """Structured result from web-augmented author research."""

    author_name: str = ""
    novel_title: str = ""

    # Biography and career
    biographical_context: str = ""
    literary_reputation: str = ""
    known_influences: List[str] = field(default_factory=list)

    # Craft and style
    author_on_their_craft: List[str] = field(default_factory=list)
    recurring_themes_across_works: List[str] = field(default_factory=list)
    critical_consensus_on_style: str = ""

    # This specific work
    critical_reception: str = ""
    scholarly_interpretations: List[str] = field(default_factory=list)
    historical_context_of_writing: str = ""

    # Constraints for simulation
    what_author_would_never_write: List[str] = field(default_factory=list)
    aesthetic_commitments: List[str] = field(default_factory=list)

    # Raw search snippets for provenance
    raw_snippets: List[str] = field(default_factory=list)


@runtime_checkable
class WebSearcher(Protocol):
    """Protocol for web search capability."""

    async def search(self, query: str, *, max_results: int = 5) -> List[str]:
        """Search the web and return text snippets."""
        ...


class LLMKnowledgeSearcher:
    """WebSearcher implementation backed by LLM knowledge.

    Uses the LLM's built-in knowledge to generate relevant information
    about authors and genres, satisfying the WebSearcher protocol without
    requiring an external search API.  Swap with a real web searcher
    (e.g. Google, Bing, Tavily) for production use.
    """

    def __init__(self, llm_client: StructuredLLMClient) -> None:
        self._client = llm_client

    async def search(self, query: str, *, max_results: int = 5) -> List[str]:
        prompt = PromptRequest(
            system=(
                "You are a literary knowledge base. For the given query, "
                "return a JSON array of short factual text snippets (each "
                "2-4 sentences) as if they were search results from literary "
                "databases and review sites. Be specific and factual."
            ),
            user=(
                f"Query: {query}\n\n"
                f"Return a JSON array of {max_results} snippets. "
                "Each snippet should be a standalone factual paragraph."
            ),
            max_tokens=1_500,
            metadata={"prompt_name": "llm_knowledge_search"},
        )
        try:
            result = await self._client.call_json(prompt, list)
            if isinstance(result, list):
                return [str(s) for s in result[:max_results]]
        except Exception:
            logger.warning("LLM knowledge search failed for: %s", query)
        return []


class AuthorResearchAgent:
    """Agent that performs web searches to enrich the author meta profile.

    The agent runs a series of targeted searches, then synthesizes the
    results into a structured AuthorResearchResult that can be fed into
    the P1.3 meta layer prompt as additional context.
    """

    def __init__(
        self,
        *,
        web_searcher: WebSearcher,
        llm_client: StructuredLLMClient,
    ) -> None:
        self.web_searcher = web_searcher
        self.llm_client = llm_client

    async def research(
        self,
        *,
        author_name: str,
        novel_title: str,
        primary_language: str = "",
    ) -> AuthorResearchResult:
        """Run targeted web searches and synthesize author research.

        Performs searches in both the primary language and English to
        maximize coverage. Returns structured research that enriches
        the meta layer extraction.
        """
        if not author_name and not novel_title:
            return AuthorResearchResult()

        # Build search queries — search in both primary language and English
        queries = self._build_search_queries(
            author_name=author_name,
            novel_title=novel_title,
            primary_language=primary_language,
        )

        # Execute searches concurrently
        all_snippets: List[str] = []
        search_tasks = [
            self.web_searcher.search(query, max_results=5)
            for query in queries
        ]

        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Search failed: %s", result)
                continue
            all_snippets.extend(result)

        if not all_snippets:
            logger.info("No web search results found for %s / %s", author_name, novel_title)
            return AuthorResearchResult(
                author_name=author_name,
                novel_title=novel_title,
            )

        # Synthesize raw snippets into structured research
        return await self._synthesize(
            author_name=author_name,
            novel_title=novel_title,
            raw_snippets=all_snippets,
        )

    def _build_search_queries(
        self,
        *,
        author_name: str,
        novel_title: str,
        primary_language: str,
    ) -> List[str]:
        """Build targeted search queries for different aspects of the author."""
        queries: List[str] = []

        if author_name:
            queries.extend([
                f'"{author_name}" writing style literary analysis',
                f'"{author_name}" interview craft fiction',
                f'"{author_name}" biography literary career',
                f'"{author_name}" recurring themes preoccupations',
            ])

        if novel_title:
            queries.extend([
                f'"{novel_title}" literary criticism analysis',
                f'"{novel_title}" historical context writing',
            ])

        if author_name and novel_title:
            queries.append(
                f'"{author_name}" "{novel_title}" scholarly interpretation'
            )

        # If the primary language is not English, also search in that language
        if primary_language and primary_language.lower() not in ("english", "en"):
            if author_name:
                queries.append(f"{author_name} 创作风格 文学评论")
                queries.append(f"{author_name} 访谈 写作")
            if novel_title:
                queries.append(f"{novel_title} 文学分析 评论")

        return queries

    async def _synthesize(
        self,
        *,
        author_name: str,
        novel_title: str,
        raw_snippets: List[str],
    ) -> AuthorResearchResult:
        """Use LLM to synthesize raw search snippets into structured research."""
        # Dedupe and truncate snippets
        seen: set[str] = set()
        unique_snippets: List[str] = []
        for snippet in raw_snippets:
            normalized = snippet.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_snippets.append(normalized)
        unique_snippets = unique_snippets[:30]  # cap to avoid prompt overflow

        snippets_text = "\n\n---\n\n".join(
            f"[snippet {i + 1}]\n{snippet}"
            for i, snippet in enumerate(unique_snippets)
        )

        prompt = PromptRequest(
            system=(
                "You are a literary research assistant. Synthesize web search results "
                "about an author and their work into structured research. "
                "Be specific and evidence-based. Do not invent claims not supported "
                "by the provided snippets. Return valid JSON only."
            ),
            user=(
                f"AUTHOR: {author_name}\n"
                f"NOVEL: {novel_title}\n\n"
                "WEB SEARCH RESULTS:\n"
                f"{snippets_text}\n\n"
                "Synthesize these into structured research covering:\n"
                "1. biographical_context: Key biographical facts relevant to understanding their work\n"
                "2. literary_reputation: How they are regarded in the literary world\n"
                "3. known_influences: Authors, movements, or traditions that influenced them\n"
                "4. author_on_their_craft: Direct quotes or paraphrases of the author on writing\n"
                "5. recurring_themes_across_works: Themes that appear across their body of work\n"
                "6. critical_consensus_on_style: What critics agree about their style\n"
                "7. critical_reception: How this specific novel was received\n"
                "8. scholarly_interpretations: Academic readings of this work\n"
                "9. historical_context_of_writing: What was happening when they wrote this\n"
                "10. what_author_would_never_write: Based on their aesthetic commitments\n"
                "11. aesthetic_commitments: Core artistic values they hold\n\n"
                "Return JSON matching this schema:\n"
                f"{json.dumps(_RESEARCH_SCHEMA, indent=2, ensure_ascii=False)}"
            ),
            max_tokens=4_000,
            metadata={
                "prompt_name": "author_research_synthesis",
            },
        )

        try:
            result_dict = (
                await self.llm_client.call_json(prompt, AuthorResearchResult)
            ).model_dump(mode="json") if hasattr(AuthorResearchResult, 'model_dump') else {}
        except Exception:
            # If LLM synthesis fails, return what we have
            logger.warning("Author research synthesis failed, returning raw snippets")
            return AuthorResearchResult(
                author_name=author_name,
                novel_title=novel_title,
                raw_snippets=unique_snippets[:10],
            )

        return AuthorResearchResult(
            author_name=author_name,
            novel_title=novel_title,
            biographical_context=result_dict.get("biographical_context", ""),
            literary_reputation=result_dict.get("literary_reputation", ""),
            known_influences=result_dict.get("known_influences", []),
            author_on_their_craft=result_dict.get("author_on_their_craft", []),
            recurring_themes_across_works=result_dict.get("recurring_themes_across_works", []),
            critical_consensus_on_style=result_dict.get("critical_consensus_on_style", ""),
            critical_reception=result_dict.get("critical_reception", ""),
            scholarly_interpretations=result_dict.get("scholarly_interpretations", []),
            historical_context_of_writing=result_dict.get("historical_context_of_writing", ""),
            what_author_would_never_write=result_dict.get("what_author_would_never_write", []),
            aesthetic_commitments=result_dict.get("aesthetic_commitments", []),
            raw_snippets=unique_snippets[:10],
        )


def format_research_for_prompt(research: AuthorResearchResult) -> str:
    """Format research results as additional context for the P1.3 meta prompt."""
    if not research.author_name and not research.novel_title:
        return ""

    lines: list[str] = [
        "WEB-AUGMENTED AUTHOR RESEARCH:",
        f"Author: {research.author_name}",
        f"Novel: {research.novel_title}",
    ]

    if research.biographical_context:
        lines.append(f"Biographical context: {research.biographical_context}")
    if research.literary_reputation:
        lines.append(f"Literary reputation: {research.literary_reputation}")
    if research.known_influences:
        lines.append(f"Known influences: {', '.join(research.known_influences[:5])}")
    if research.author_on_their_craft:
        for quote in research.author_on_their_craft[:3]:
            lines.append(f"Author on craft: {quote}")
    if research.recurring_themes_across_works:
        lines.append(
            f"Recurring themes: {', '.join(research.recurring_themes_across_works[:5])}"
        )
    if research.critical_consensus_on_style:
        lines.append(f"Critical consensus: {research.critical_consensus_on_style}")
    if research.critical_reception:
        lines.append(f"Reception of this novel: {research.critical_reception}")
    if research.scholarly_interpretations:
        for interp in research.scholarly_interpretations[:2]:
            lines.append(f"Scholarly interpretation: {interp}")
    if research.historical_context_of_writing:
        lines.append(f"Historical context: {research.historical_context_of_writing}")
    if research.what_author_would_never_write:
        lines.append(
            f"Would never write: {'; '.join(research.what_author_would_never_write[:3])}"
        )
    if research.aesthetic_commitments:
        lines.append(
            f"Aesthetic commitments: {'; '.join(research.aesthetic_commitments[:3])}"
        )

    if len(lines) <= 3:  # Only header lines
        return ""

    return "\n".join(lines) + "\n"


_RESEARCH_SCHEMA = {
    "biographical_context": "Key biographical facts",
    "literary_reputation": "How regarded in literary world",
    "known_influences": ["Influence 1", "Influence 2"],
    "author_on_their_craft": ["Quote or paraphrase about writing"],
    "recurring_themes_across_works": ["Theme"],
    "critical_consensus_on_style": "What critics agree about",
    "critical_reception": "How this novel was received",
    "scholarly_interpretations": ["Academic reading"],
    "historical_context_of_writing": "Historical moment",
    "what_author_would_never_write": ["Aesthetic refusal"],
    "aesthetic_commitments": ["Core artistic value"],
}


# ---------------------------------------------------------------------------
# Genre Taste Agent — finds genre masters via web search
# ---------------------------------------------------------------------------

from dreamdive.ingestion.models import GenreTasteRecord

_GENRE_TASTE_SCHEMA = {
    "detected_genres": ["genre 1", "genre 2"],
    "reference_masters": [
        {"name": "Author Name", "why": "What makes them the gold standard in this genre"},
    ],
    "taste_profile": (
        "A concise paragraph describing the shared qualities, preferences, "
        "and standards of excellence that the best authors in this genre exhibit. "
        "This serves as a taste guide for the simulation."
    ),
}


class GenreTasteAgent:
    """Identifies genre masters via web search and distils a taste benchmark.

    Flow:
    1. Accept genre/style cues already extracted from the material.
    2. Build search queries to find the most acclaimed authors in those genres.
    3. Synthesize their shared taste into a concise profile that guides the
       simulation's design and synthesis stages.
    """

    def __init__(
        self,
        *,
        web_searcher: WebSearcher,
        llm_client: StructuredLLMClient,
    ) -> None:
        self.web_searcher = web_searcher
        self.llm_client = llm_client

    async def research(
        self,
        *,
        genres: List[str],
        style_description: str = "",
        primary_language: str = "",
    ) -> GenreTasteRecord:
        """Search for genre masters and synthesize a taste profile.

        Parameters
        ----------
        genres : list[str]
            Detected genres from the meta layer (e.g. ["fantasy", "adventure"]).
        style_description : str
            Prose description of the material's writing style.
        primary_language : str
            Primary language of the source material.
        """
        if not genres:
            return GenreTasteRecord()

        queries = self._build_queries(genres, primary_language)

        # Execute searches concurrently
        all_snippets: List[str] = []
        search_tasks = [
            self.web_searcher.search(query, max_results=5)
            for query in queries
        ]
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Genre taste search failed: %s", result)
                continue
            all_snippets.extend(result)

        if not all_snippets:
            logger.info("No web results for genre taste research (%s)", genres)
            return GenreTasteRecord(detected_genres=genres)

        return await self._synthesize(
            genres=genres,
            style_description=style_description,
            primary_language=primary_language,
            raw_snippets=all_snippets,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _build_queries(genres: List[str], primary_language: str) -> List[str]:
        genre_str = " ".join(genres)
        # International / English-language masters
        queries = [
            f"best {genre_str} fiction authors of all time",
            f"greatest {genre_str} novelists literary quality",
            f"most acclaimed {genre_str} writers craft style",
        ]
        for genre in genres[:3]:
            queries.append(f"best {genre} novels literary masterpiece")

        # Native-language masters — search in the material's own language
        lang_lower = (primary_language or "").lower()
        if lang_lower and lang_lower not in ("english", "en"):
            queries.extend([
                f"{genre_str} 最佳作家 文学 风格 品味",
                f"{genre_str} 经典小说 大师级 作者",
                f"best {genre_str} authors writing in {primary_language}",
            ])
            for genre in genres[:2]:
                queries.append(f"{genre} {primary_language} literature best authors")
        return queries

    async def _synthesize(
        self,
        *,
        genres: List[str],
        style_description: str,
        primary_language: str,
        raw_snippets: List[str],
    ) -> GenreTasteRecord:
        seen: set[str] = set()
        unique: List[str] = []
        for s in raw_snippets:
            n = s.strip()
            if n and n not in seen:
                seen.add(n)
                unique.append(n)
        unique = unique[:30]

        snippets_text = "\n\n---\n\n".join(
            f"[snippet {i + 1}]\n{s}" for i, s in enumerate(unique)
        )

        lang_note = ""
        if primary_language and primary_language.lower() not in ("english", "en"):
            lang_note = (
                f"\n\nIMPORTANT: The source material is written in {primary_language}. "
                f"Include masters from BOTH the international canon AND the "
                f"{primary_language}-language literary tradition. For example, if the "
                f"material is Chinese fantasy/wuxia, include both Western masters "
                f"(e.g. Tolkien, Martin) AND Chinese masters (e.g. 金庸, 江南). "
                f"Do not limit the search to English-language authors only."
            )

        prompt = PromptRequest(
            system=(
                "You are a literary analyst identifying the gold-standard taste for "
                "a given genre. From the web search results, identify the most acclaimed "
                "authors in the genre and distill what makes their work excellent into "
                "a concise taste profile. Return valid JSON only."
            ),
            user=(
                f"DETECTED GENRES: {json.dumps(genres, ensure_ascii=False)}\n"
                f"SOURCE MATERIAL LANGUAGE: {primary_language or 'English'}\n"
                f"SOURCE MATERIAL STYLE: {style_description or '(not provided)'}\n\n"
                "WEB SEARCH RESULTS:\n"
                f"{snippets_text}\n\n"
                "Instructions:\n"
                "1. Identify the 3-6 most universally acclaimed authors in these genres.\n"
                "   Include masters from BOTH the international/Western canon AND the\n"
                "   source material's own literary tradition if non-English.\n"
                "   For each, explain in one sentence WHY they are the gold standard.\n"
                "2. Synthesize their shared qualities into a 'taste_profile' — a concise\n"
                "   paragraph (3-5 sentences) that captures the preferences, instincts,\n"
                "   and standards of excellence these masters share. Think of it as:\n"
                "   'What would a reader with the BEST taste in this genre care about?'\n"
                "3. Focus on craft qualities (pacing, world-building depth, character\n"
                "   complexity, thematic resonance, prose quality) rather than plot tropes."
                f"{lang_note}\n\n"
                "Return JSON matching this schema:\n"
                f"{json.dumps(_GENRE_TASTE_SCHEMA, indent=2, ensure_ascii=False)}"
            ),
            max_tokens=2_000,
            metadata={"prompt_name": "genre_taste_synthesis"},
        )

        try:
            result = await self.llm_client.call_json(prompt, GenreTasteRecord)
            if isinstance(result, GenreTasteRecord):
                return result
            # call_json may return dict via model_dump
            result_dict = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        except Exception:
            logger.warning("Genre taste synthesis failed, returning genres only")
            return GenreTasteRecord(detected_genres=genres)

        return GenreTasteRecord(
            detected_genres=result_dict.get("detected_genres", genres),
            reference_masters=[
                _to_genre_master(m)
                for m in result_dict.get("reference_masters", [])
            ],
            taste_profile=result_dict.get("taste_profile", ""),
        )


def _to_genre_master(raw: dict | object) -> "GenreMasterRecord":
    from dreamdive.ingestion.models import GenreMasterRecord

    if isinstance(raw, dict):
        return GenreMasterRecord(name=raw.get("name", ""), why=raw.get("why", ""))
    return GenreMasterRecord(name=getattr(raw, "name", ""), why=getattr(raw, "why", ""))
