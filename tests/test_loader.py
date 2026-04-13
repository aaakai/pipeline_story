from pathlib import Path
import unittest

from novel2script.loader import load_story_from_txt


class LoaderTests(unittest.TestCase):
    def test_load_story_splits_chapters(self) -> None:
        path = Path("examples/sample_novel.txt")
        story = load_story_from_txt(path)
        self.assertEqual(story.title, "sample novel")
        self.assertGreaterEqual(len(story.chapters), 1)
        self.assertEqual(story.chapters[0].chapter_index, 1)
        self.assertTrue(story.chapters[0].raw_text.strip())


if __name__ == "__main__":
    unittest.main()
