from pathlib import Path
import unittest

from novel2script.loader import load_story_from_txt


class LoaderTests(unittest.TestCase):
    def test_load_story_splits_chapters(self) -> None:
        path = Path("examples/sample_novel.txt")
        story = load_story_from_txt(path)
        self.assertEqual(story.title, "雾城旧事")
        self.assertEqual(len(story.chapters), 2)
        self.assertEqual(story.chapters[0].chapter_index, 1)
        self.assertIn("林深", story.chapters[0].raw_text)


if __name__ == "__main__":
    unittest.main()
