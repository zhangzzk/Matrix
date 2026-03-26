from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Sequence

from dreamdive.ingestion.extractor import ChapterSource


CHAPTER_HEADING_RE = re.compile(
    r"^(?:#\s*)?(?:"
    r"(?P<english>(?:chapter\s+\d+|chapter\s+[ivxlcdm]+|prologue|epilogue)\b[^\n]*)"
    r"|(?P<cn_special>(?:序章|序幕|楔子|尾声)[^\n]*)"
    r"|(?P<cn_numbered>第[零〇一二两三四五六七八九十百千万\d]+[章节幕卷部回][^\n]*)"
    r")$",
    re.IGNORECASE | re.MULTILINE,
)

SOURCE_TEXT_ENCODINGS = (
    "utf-8",
    "utf-8-sig",
    "gb18030",
    "gbk",
)


def load_text(path: Path) -> str:
    payload = path.read_bytes()
    for encoding in SOURCE_TEXT_ENCODINGS:
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    tried = ", ".join(SOURCE_TEXT_ENCODINGS)
    raise UnicodeDecodeError(
        "dreamdive-source-loader",
        payload,
        0,
        min(1, len(payload)),
        f"Unable to decode {path} using supported encodings: {tried}",
    )


def split_into_chapters(text: str) -> List[ChapterSource]:
    matches = list(CHAPTER_HEADING_RE.finditer(text))
    if not matches:
        stripped = text.strip()
        if not stripped:
            return []
        return [
            ChapterSource(
                chapter_id="001",
                title="Full Text",
                order_index=1,
                text=stripped,
            )
        ]

    chapters: List[ChapterSource] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_title = match.group(0).strip().lstrip("#").strip()
        title = _normalize_heading_title(raw_title)
        chapter_text = text[start:end].strip()
        chapters.append(
            ChapterSource(
                chapter_id="{:03d}".format(index + 1),
                title=title,
                order_index=index + 1,
                text=chapter_text,
            )
        )
    return chapters


_CHINESE_HEADING_DETAIL_RE = re.compile(
    r"^第(?P<number>[零〇一二两三四五六七八九十百千万\d]+)(?P<kind>[章节幕卷部回])\s*(?P<suffix>.*)$"
)

_ENGLISH_CHAPTER_RE = re.compile(
    r"^(?P<label>chapter)\s+(?P<number>\d+|[ivxlcdm]+)(?:\s+(?P<suffix>.*))?$",
    re.IGNORECASE,
)

_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

_CHINESE_UNITS = {
    "十": 10,
    "百": 100,
    "千": 1000,
    "万": 10000,
}


def _normalize_heading_title(raw_title: str) -> str:
    title = raw_title.strip()
    if not title:
        return title

    lower = title.lower()
    if lower.startswith("prologue"):
        return "Prologue"
    if lower.startswith("epilogue"):
        return "Epilogue"

    english_match = _ENGLISH_CHAPTER_RE.match(title)
    if english_match:
        number = english_match.group("number") or ""
        suffix = (english_match.group("suffix") or "").strip()
        label = f"Chapter {number.upper() if number.isalpha() else number}"
        return f"{label} · {suffix}" if suffix else label

    if title.startswith(("序章", "序幕", "楔子")):
        suffix = title[2:].strip()
        return f"Prologue · {suffix}" if suffix else "Prologue"
    if title.startswith("尾声"):
        suffix = title[2:].strip()
        return f"Epilogue · {suffix}" if suffix else "Epilogue"

    chinese_match = _CHINESE_HEADING_DETAIL_RE.match(title)
    if chinese_match:
        number = _parse_chinese_number(chinese_match.group("number"))
        suffix = (chinese_match.group("suffix") or "").strip()
        label = f"Chapter {number}" if number > 0 else "Chapter"
        return f"{label} · {suffix}" if suffix else label

    return title


def _parse_chinese_number(value: str) -> int:
    stripped = value.strip()
    if not stripped:
        return 0
    if stripped.isdigit():
        return int(stripped)

    total = 0
    section = 0
    number = 0
    for char in stripped:
        if char in _CHINESE_DIGITS:
            number = _CHINESE_DIGITS[char]
            continue
        unit = _CHINESE_UNITS.get(char)
        if unit is None:
            continue
        if unit == 10000:
            section = (section + (number or 1)) * unit
            total += section
            section = 0
            number = 0
            continue
        section += (number or 1) * unit
        number = 0
    return total + section + number


def looks_like_chapter_heading(line: str) -> bool:
    """Return True if *line* looks like a chapter heading (Chinese or English)."""
    stripped = line.strip()
    if not stripped:
        return False
    return CHAPTER_HEADING_RE.match(stripped) is not None


def format_synthesized_chapter_heading(
    chapter_number: int,
    source_heading_examples: List[str],
) -> str:
    """Synthesize a chapter heading that matches the source style.

    Examines *source_heading_examples* to detect whether the source uses
    Chinese numbered headings (第N章) or English ones (Chapter N) and
    returns a heading string in the same style.  Returns ``""`` if the
    style cannot be determined.
    """
    if not source_heading_examples:
        return ""

    # Detect dominant style from examples
    chinese_count = 0
    english_count = 0
    chinese_kind = "章"
    for example in source_heading_examples:
        stripped = example.strip().lstrip("#").strip()
        cn_match = _CHINESE_HEADING_DETAIL_RE.match(stripped)
        if cn_match:
            chinese_count += 1
            chinese_kind = cn_match.group("kind") or "章"
            continue
        if _ENGLISH_CHAPTER_RE.match(stripped):
            english_count += 1

    if chinese_count >= english_count and chinese_count > 0:
        # Build Chinese-style heading: 第N章
        from dreamdive.ingestion.source_loader import _int_to_chinese_number
        return f"第{_int_to_chinese_number(chapter_number)}{chinese_kind}"
    if english_count > 0:
        return f"Chapter {chapter_number}"
    return ""


def _int_to_chinese_number(n: int) -> str:
    """Convert a positive integer to Chinese numeral string (up to 9999)."""
    if n <= 0:
        return "零"
    _digits = "零一二三四五六七八九"
    if n < 10:
        return _digits[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        result = ("" if tens == 1 else _digits[tens]) + "十"
        return result + (_digits[ones] if ones else "")
    if n < 1000:
        hundreds, remainder = divmod(n, 100)
        result = _digits[hundreds] + "百"
        if remainder == 0:
            return result
        if remainder < 10:
            return result + "零" + _digits[remainder]
        return result + _int_to_chinese_number(remainder)
    thousands, remainder = divmod(n, 1000)
    result = _digits[thousands] + "千"
    if remainder == 0:
        return result
    if remainder < 100:
        return result + "零" + _int_to_chinese_number(remainder)
    return result + _int_to_chinese_number(remainder)


def load_chapters(path: Path) -> List[ChapterSource]:
    return split_into_chapters(load_text(path))


def select_chapters(
    chapters: Sequence[ChapterSource],
    *,
    chapter_ids: Iterable[str] | None = None,
    max_chapters: int | None = None,
) -> List[ChapterSource]:
    if chapter_ids is not None:
        wanted = {chapter_id.strip() for chapter_id in chapter_ids if chapter_id.strip()}
        selected = [chapter for chapter in chapters if chapter.chapter_id in wanted]
    else:
        selected = list(chapters)
    if max_chapters is not None and max_chapters > 0:
        selected = selected[:max_chapters]
    return selected


def render_chapter_subset(
    chapters: Sequence[ChapterSource],
    *,
    chapter_ids: Iterable[str] | None = None,
    max_chapters: int | None = None,
) -> str:
    selected = select_chapters(
        chapters,
        chapter_ids=chapter_ids,
        max_chapters=max_chapters,
    )
    return "\n\n".join(chapter.text.strip() for chapter in selected if chapter.text.strip())


def write_clean_source_subset(
    source_path: Path,
    output_path: Path,
    *,
    chapter_ids: Iterable[str] | None = None,
    max_chapters: int | None = None,
) -> List[ChapterSource]:
    chapters = load_chapters(source_path)
    selected = select_chapters(
        chapters,
        chapter_ids=chapter_ids,
        max_chapters=max_chapters,
    )
    payload = render_chapter_subset(
        selected,
        max_chapters=None,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")
    return selected


def sample_representative_excerpts(
    chapters: List[ChapterSource],
    *,
    excerpt_chars: int = 1_200,
    max_sections: int = 4,
) -> List[str]:
    if not chapters:
        return []

    if len(chapters) <= max_sections:
        selected = chapters
    else:
        candidate_indices = [0, len(chapters) // 3, (2 * len(chapters)) // 3, len(chapters) - 1]
        seen = set()
        selected = []
        for index in candidate_indices:
            if index in seen:
                continue
            seen.add(index)
            selected.append(chapters[index])

    excerpts = []
    for chapter in selected[:max_sections]:
        excerpt = chapter.text.strip()[:excerpt_chars]
        excerpts.append(f"[{chapter.chapter_id} | {chapter.title or chapter.chapter_id}]\n{excerpt}")
    return excerpts
