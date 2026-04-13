from __future__ import annotations

from typing import Any

from .llm import LLMClient
from .prompts import (
    chapter_to_scenes_prompt,
    scene_characters_prompt,
    scene_to_shots_prompt,
    story_to_chapters_prompt,
)
from .schemas import ActionBeat, Chapter, CharacterRef, DialogueBeat, Scene, Shot, Story
from .utils import stable_id


class ChapterSplitter:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def split(self, story: Story, raw_text: str) -> Story:
        payload = {
            "title": story.title,
            "description": story.description,
            "source_path": story.source_path,
            "raw_text": raw_text,
        }
        prompt = story_to_chapters_prompt(payload)
        result = self.llm_client.generate_json("story_to_chapters", prompt, payload)

        chapters: list[Chapter] = []
        for index, item in enumerate(result.get("chapters", []), start=1):
            title = item.get("title") or f"Segment {index}"
            chapters.append(
                Chapter(
                    id=stable_id("chapter", story.id, str(index), title),
                    story_id=story.id,
                    chapter_index=item.get("chapter_index") or index,
                    title=title,
                    raw_text=item.get("raw_text") or "",
                    summary=item.get("summary"),
                    scenes=[],
                )
            )

        return story.model_copy(
            update={
                "title": result.get("title") or story.title,
                "description": result.get("description") or story.description,
                "chapters": chapters,
            }
        )


class SceneExtractor:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def extract(self, story: Story, chapter: Chapter) -> Chapter:
        payload = {
            "story_title": story.title,
            "chapter_index": chapter.chapter_index,
            "title": chapter.title,
            "raw_text": chapter.raw_text,
        }
        prompt = chapter_to_scenes_prompt(payload)
        result = self.llm_client.generate_json("chapter_to_scenes", prompt, payload)

        scenes: list[Scene] = []
        for index, item in enumerate(result.get("scenes", []), start=1):
            scene = Scene(
                id=stable_id("scene", story.id, chapter.id, str(index), item.get("title", "")),
                story_id=story.id,
                chapter_id=chapter.id,
                scene_index=index,
                title=item.get("title") or f"Scene {index}",
                location_name=item.get("location_name"),
                time_of_day=item.get("time_of_day"),
                summary=item.get("summary") or "",
                characters=[CharacterRef.model_validate(obj) for obj in item.get("characters", [])],
                mood=item.get("mood"),
                actions=[ActionBeat.model_validate(obj) for obj in item.get("actions", [])],
                dialogues=[DialogueBeat.model_validate(obj) for obj in item.get("dialogues", [])],
                source_text=item.get("source_text") or chapter.raw_text,
                shots=[],
            )
            scenes.append(scene)

        return chapter.model_copy(update={"summary": result.get("summary"), "scenes": scenes})


class CharacterExtractor:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def extract(self, scene: Scene) -> Scene:
        payload = {
            "title": scene.title,
            "summary": scene.summary,
            "source_text": scene.source_text,
            "existing_characters": [character.model_dump() for character in scene.characters],
        }
        prompt = scene_characters_prompt(payload)
        result = self.llm_client.generate_json("scene_characters", prompt, payload)
        merged = self._merge_characters(scene.characters, result.get("characters", []))
        return scene.model_copy(update={"characters": merged})

    def _merge_characters(
        self, existing: list[CharacterRef], incoming: list[dict[str, Any]]
    ) -> list[CharacterRef]:
        ordered: list[CharacterRef] = []
        seen: set[str] = set()

        for item in [*existing, *[CharacterRef.model_validate(obj) for obj in incoming]]:
            key = item.name.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(item)
        return ordered


class ShotGenerator:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def generate(self, story: Story, chapter: Chapter, scene: Scene) -> Scene:
        payload = {
            "scene_title": scene.title,
            "location_name": scene.location_name,
            "time_of_day": scene.time_of_day,
            "summary": scene.summary,
            "mood": scene.mood,
            "source_text": scene.source_text,
            "characters": [item.model_dump() for item in scene.characters],
            "actions": [item.model_dump() for item in scene.actions],
            "dialogues": [item.model_dump() for item in scene.dialogues],
        }
        prompt = scene_to_shots_prompt(payload)
        result = self.llm_client.generate_json("scene_to_shots", prompt, payload)
        shots = [
            Shot(
                id=stable_id("shot", story.id, chapter.id, scene.id, str(index), item.get("content", "")),
                story_id=story.id,
                chapter_id=chapter.id,
                scene_id=scene.id,
                shot_index=index,
                shot_type=item.get("shot_type") or "medium",
                content=item.get("content") or "",
                dialogue=item.get("dialogue"),
                narration=item.get("narration"),
                camera_direction=item.get("camera_direction"),
                emotion=item.get("emotion"),
                duration_sec=item.get("duration_sec"),
            )
            for index, item in enumerate(result.get("shots", []), start=1)
        ]
        return scene.model_copy(update={"shots": shots})
