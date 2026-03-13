import tempfile
import unittest
from pathlib import Path

from dreamdive.ingestion.source_loader import (
    load_text,
    load_chapters,
    render_chapter_subset,
    sample_representative_excerpts,
    split_into_chapters,
    write_clean_source_subset,
)


class SourceLoaderTests(unittest.TestCase):
    def test_split_into_chapters_detects_markdown_and_plain_headings(self) -> None:
        text = (
            "# Chapter 1\n"
            "First chapter text.\n\n"
            "Chapter 2\n"
            "Second chapter text."
        )

        chapters = split_into_chapters(text)

        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0].chapter_id, "001")
        self.assertIn("First chapter text.", chapters[0].text)
        self.assertEqual(chapters[1].title, "Chapter 2")

    def test_split_into_chapters_falls_back_to_single_document(self) -> None:
        chapters = split_into_chapters("A short story without headings.")

        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "Full Text")

    def test_split_into_chapters_detects_chinese_headings_and_normalizes_titles(self) -> None:
        text = (
            "序幕 白帝城\n"
            "起始。\n\n"
            "第一幕 卡塞尔之门\n"
            "进入学院。\n\n"
            "第二幕 黄金瞳\n"
            "考试开始。\n\n"
            "尾声\n"
            "结束。"
        )

        chapters = split_into_chapters(text)

        self.assertEqual(len(chapters), 4)
        self.assertEqual(chapters[0].title, "Prologue · 白帝城")
        self.assertEqual(chapters[1].title, "Chapter 1 · 卡塞尔之门")
        self.assertEqual(chapters[2].title, "Chapter 2 · 黄金瞳")
        self.assertEqual(chapters[3].title, "Epilogue")

    def test_load_chapters_reads_from_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "novel.md"
            path.write_text("Prologue\nA dark and stormy night.", encoding="utf-8")

            chapters = load_chapters(path)

            self.assertEqual(len(chapters), 1)
            self.assertEqual(chapters[0].title, "Prologue")

    def test_load_text_supports_gb18030_encoded_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "novel.txt"
            expected = "声明：路明非说不出话。"
            path.write_bytes(expected.encode("gb18030"))

            loaded = load_text(path)

            self.assertEqual(loaded, expected)

    def test_load_chapters_supports_gb18030_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "novel.txt"
            content = "Prologue\n路明非说不出话。"
            path.write_bytes(content.encode("gb18030"))

            chapters = load_chapters(path)

            self.assertEqual(len(chapters), 1)
            self.assertEqual(chapters[0].title, "Prologue")
            self.assertIn("路明非说不出话。", chapters[0].text)

    def test_render_chapter_subset_keeps_clean_chinese_text(self) -> None:
        chapters = load_chapters(Path("resources/dragonraja1.txt"))

        demo_text = render_chapter_subset(chapters, max_chapters=2)

        self.assertIn("序幕 白帝城", demo_text)
        self.assertIn("第一幕 卡塞尔之门", demo_text)
        self.assertNotIn("第二幕 黄金瞳", demo_text)

    def test_write_clean_source_subset_regenerates_clean_demo_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "dragonraja_demo.txt"

            selected = write_clean_source_subset(
                Path("resources/dragonraja1.txt"),
                output_path,
                max_chapters=2,
            )
            chapters = load_chapters(output_path)

            self.assertEqual(len(selected), 2)
            self.assertEqual(len(chapters), 2)
            self.assertEqual(chapters[0].title, "Prologue · 白帝城")
            self.assertEqual(chapters[1].title, "Chapter 1 · 卡塞尔之门")
            clean_text = load_text(output_path)
            self.assertIn("序幕 白帝城", clean_text)
            self.assertIn("第一幕 卡塞尔之门", clean_text)
            self.assertNotIn("��������", clean_text)

    def test_sample_representative_excerpts_spreads_across_book(self) -> None:
        chapters = split_into_chapters(
            "# Chapter 1\nOne.\n\n"
            "# Chapter 2\nTwo.\n\n"
            "# Chapter 3\nThree.\n\n"
            "# Chapter 4\nFour.\n\n"
            "# Chapter 5\nFive."
        )

        excerpts = sample_representative_excerpts(chapters, excerpt_chars=20, max_sections=4)

        self.assertEqual(len(excerpts), 4)
        self.assertIn("[001 | Chapter 1]", excerpts[0])
        self.assertTrue(any("[005 | Chapter 5]" in excerpt for excerpt in excerpts))


if __name__ == "__main__":
    unittest.main()
