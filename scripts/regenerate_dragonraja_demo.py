from __future__ import annotations

import argparse
from pathlib import Path

from dreamdive.ingestion.source_loader import write_clean_source_subset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Regenerate a clean UTF-8 Dragon Raja demo file from the full source.",
    )
    parser.add_argument(
        "--source",
        default="resources/dragonraja1.txt",
        help="Path to the clean full Dragon Raja source.",
    )
    parser.add_argument(
        "--output",
        default="resources/dragonraja1_demo.txt",
        help="Path to write the clean UTF-8 demo file.",
    )
    parser.add_argument(
        "--chapter-id",
        action="append",
        dest="chapter_ids",
        help="Specific chapter IDs to include. Can be passed multiple times.",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        default=2,
        help="Number of leading chapters to include when chapter IDs are not provided.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    selected = write_clean_source_subset(
        Path(args.source),
        Path(args.output),
        chapter_ids=args.chapter_ids,
        max_chapters=args.max_chapters if not args.chapter_ids else None,
    )
    print(
        f"Wrote {len(selected)} chapter(s) to {args.output}: "
        + ", ".join(chapter.title or chapter.chapter_id for chapter in selected)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
