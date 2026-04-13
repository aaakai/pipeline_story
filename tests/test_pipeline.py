from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from novel2script.pipeline import Novel2ScriptPipeline
from novel2script.utils import load_json


class PipelineTests(unittest.TestCase):
    def test_mock_pipeline_end_to_end(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            pipeline = Novel2ScriptPipeline.from_config(output_dir=tmp_dir, use_mock=True)
            report = pipeline.run(Path("examples/sample_novel.txt"), step="all", use_mock=True)
            self.assertTrue(report.success)
            self.assertTrue(Path(report.output_dir).exists())
            self.assertEqual(Path(report.output_dir).parent.resolve(), Path(tmp_dir).resolve())

            script = load_json(Path(report.output_dir) / "script_pretty.json")
            self.assertEqual(script["title"], "sample novel")
            self.assertGreaterEqual(len(script["chapters"]), 1)
            self.assertEqual(script["chapters"][0]["chapter_index"], 1)
            self.assertTrue(script["chapters"][0]["title"])
            scene_count = sum(len(chapter["scenes"]) for chapter in script["chapters"])
            shot_count = sum(
                len(scene["shots"])
                for chapter in script["chapters"]
                for scene in chapter["scenes"]
            )
            self.assertGreaterEqual(scene_count, 2)
            self.assertGreaterEqual(shot_count, 2)


if __name__ == "__main__":
    unittest.main()
