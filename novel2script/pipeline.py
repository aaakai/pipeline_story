from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .extractors import ChapterSplitter, CharacterExtractor, SceneExtractor, ShotGenerator, StoryCharacterBuilder
from .llm import LLMClient, MockLLMClient, OpenAICompatibleLLMClient
from .loader import load_story_from_txt, load_story_source, split_into_chapters
from .schemas import Chapter, RunReport, StepReport, Story
from .utils import dump_json_pair, ensure_dir, get_logger, load_json, slugify_filename
from .validators import validate_story


class Novel2ScriptPipeline:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        output_dir: Path | str = Path("./output_check"),
    ) -> None:
        self.base_output_dir = ensure_dir(Path(output_dir))
        self.output_dir = self.base_output_dir
        self.logger = get_logger()
        self.llm_client = llm_client or MockLLMClient()
        self.chapter_splitter = ChapterSplitter(self.llm_client)
        self.scene_extractor = SceneExtractor(self.llm_client)
        self.character_extractor = CharacterExtractor(self.llm_client)
        self.story_character_builder = StoryCharacterBuilder()
        self.shot_generator = ShotGenerator(self.llm_client)

    @classmethod
    def from_config(
        cls,
        output_dir: Path | str,
        use_mock: bool = False,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_sec: int = 600,
    ) -> "Novel2ScriptPipeline":
        if use_mock:
            client: LLMClient = MockLLMClient()
        else:
            client = OpenAICompatibleLLMClient(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_sec=timeout_sec,
            )
        return cls(llm_client=client, output_dir=output_dir)

    def run(self, input_path: Path | str, step: str = "all", use_mock: bool = True) -> RunReport:
        input_path = Path(input_path)
        preview_story, _ = load_story_source(input_path)
        self.output_dir = self._make_run_output_dir(preview_story.title)
        report = RunReport(
            story_id=None,
            source_path=str(input_path.resolve()),
            output_dir=str(self.output_dir.resolve()),
            mode="mock" if use_mock else "openai-compatible",
            requested_step=step,
            started_at=datetime.now(),
        )
        started = time.perf_counter()

        try:
            story = self._run_ingest(input_path, report)
            if step in {"scenes", "shots", "all"}:
                story = self._run_scenes(story, report)
            if step in {"shots", "all"}:
                story = self._run_shots(story, report)
            if step == "all":
                self._write_final_story(story, report)
            report.success = True
        except Exception as exc:  # noqa: BLE001
            report.errors.append(str(exc))
            report.success = False
        finally:
            report.finished_at = datetime.now()
            report.duration_sec = round(time.perf_counter() - started, 4)
            self._write_report(report)
        return report

    def _make_run_output_dir(self, story_title: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = slugify_filename(story_title, fallback="untitled_story")
        return ensure_dir(self.base_output_dir / f"{timestamp}_{safe_title}")

    def _run_ingest(self, input_path: Path, report: RunReport) -> Story:
        step = self._start_step(report, "ingest")
        self.logger.info("[ingest] loaded file")
        base_story, raw_text = load_story_source(input_path)
        try:
            story = self.chapter_splitter.split(base_story, raw_text)
            if not story.chapters:
                raise ValueError("LLM chapter splitter returned no chapters.")
        except Exception as exc:  # noqa: BLE001
            self.logger.info("[chapters] llm split failed, fallback to rule-based split: %s", exc)
            fallback_story = load_story_from_txt(input_path)
            story = base_story.model_copy(update={"chapters": split_into_chapters(raw_text, base_story.id)})
            story = story.model_copy(
                update={
                    "title": fallback_story.title,
                    "description": fallback_story.description,
                }
            )
        self.logger.info("[chapters] split into %s chapters", len(story.chapters))
        report.story_id = story.id
        payload = story.model_dump(mode="json")
        compact, pretty = dump_json_pair(
            self.output_dir / "ingested.json",
            payload,
            self.output_dir / "ingested_pretty.json",
        )
        self._finish_step(step, "success", output_files=[str(compact), str(pretty)])
        return story

    def _run_scenes(self, story: Story, report: RunReport) -> Story:
        step = self._start_step(report, "scenes")
        chapters: list[Chapter] = []
        total_scenes = 0
        for chapter in story.chapters:
            enriched = self.scene_extractor.extract(story, chapter)
            scenes = [self.character_extractor.extract(scene) for scene in enriched.scenes]
            total_scenes += len(scenes)
            chapters.append(enriched.model_copy(update={"scenes": scenes}))
        story = story.model_copy(update={"chapters": chapters})
        story = self.story_character_builder.build(story)
        self.logger.info("[scenes] extracted %s scenes", total_scenes)
        scenes_payload = {
            "story_id": story.id,
            "title": story.title,
            "characters": [character.model_dump(mode="json") for character in story.characters],
            "chapters": [
                {
                    "chapter_id": chapter.id,
                    "chapter_index": chapter.chapter_index,
                    "title": chapter.title,
                    "summary": chapter.summary,
                    "scenes": [scene.model_dump(mode="json") for scene in chapter.scenes],
                }
                for chapter in story.chapters
            ],
        }
        compact, pretty = dump_json_pair(
            self.output_dir / "scenes.json",
            scenes_payload,
            self.output_dir / "scenes_pretty.json",
        )
        self._finish_step(step, "success", output_files=[str(compact), str(pretty)])
        return story

    def _run_shots(self, story: Story, report: RunReport) -> Story:
        step = self._start_step(report, "shots")
        chapters: list[Chapter] = []
        total_shots = 0
        for chapter in story.chapters:
            scenes = []
            for scene in chapter.scenes:
                enriched_scene = self.shot_generator.generate(story, chapter, scene)
                total_shots += len(enriched_scene.shots)
                scenes.append(enriched_scene)
            chapters.append(chapter.model_copy(update={"scenes": scenes}))
        story = story.model_copy(update={"chapters": chapters})
        self.logger.info("[shots] generated %s shots", total_shots)
        shots_payload = {
            "story_id": story.id,
            "title": story.title,
            "characters": [character.model_dump(mode="json") for character in story.characters],
            "chapters": [
                {
                    "chapter_id": chapter.id,
                    "chapter_index": chapter.chapter_index,
                    "title": chapter.title,
                    "scenes": [
                        {
                            "scene_id": scene.id,
                            "scene_index": scene.scene_index,
                            "title": scene.title,
                            "shots": [shot.model_dump(mode="json") for shot in scene.shots],
                        }
                        for scene in chapter.scenes
                    ],
                }
                for chapter in story.chapters
            ],
        }
        compact, pretty = dump_json_pair(
            self.output_dir / "shots.json",
            shots_payload,
            self.output_dir / "shots_pretty.json",
        )
        self._finish_step(step, "success", output_files=[str(compact), str(pretty)])
        return story

    def _write_final_story(self, story: Story, report: RunReport) -> None:
        step = self._start_step(report, "finalize")
        compact, pretty = dump_json_pair(
            self.output_dir / "script.json",
            story.model_dump(mode="json"),
            self.output_dir / "script_pretty.json",
        )
        errors = validate_story(story)
        if errors:
            report.errors.extend(errors)
            self._finish_step(
                step,
                "failed",
                error="; ".join(errors),
                output_files=[str(compact), str(pretty)],
            )
            raise ValueError("; ".join(errors))
        self._finish_step(step, "success", output_files=[str(compact), str(pretty)])

    def _write_report(self, report: RunReport) -> None:
        dump_json_pair(
            self.output_dir / "run_report.json",
            report.model_dump(mode="json"),
            self.output_dir / "run_report_pretty.json",
        )

    def _start_step(self, report: RunReport, name: str) -> StepReport:
        step = StepReport(step=name, status="running", started_at=datetime.now())
        report.steps.append(step)
        return step

    def _finish_step(
        self,
        step: StepReport,
        status: str,
        message: str | None = None,
        error: str | None = None,
        output_files: list[str] | None = None,
    ) -> None:
        step.status = status
        step.finished_at = datetime.now()
        if step.started_at and step.finished_at:
            step.duration_sec = round((step.finished_at - step.started_at).total_seconds(), 4)
        step.message = message
        step.error = error
        step.output_files = output_files or []


def load_story_from_output(output_dir: Path) -> Story:
    script_path = output_dir / "script_pretty.json"
    if script_path.exists():
        return Story.model_validate(load_json(script_path))
    ingested_path = output_dir / "ingested.json"
    if ingested_path.exists():
        return Story.model_validate(load_json(ingested_path))
    raise FileNotFoundError("No pipeline artifact found in output directory.")
