from __future__ import annotations

import re
from typing import Any

from .llm import LLMClient
from .prompts import (
    chapter_to_scenes_prompt,
    scene_characters_prompt,
    scene_to_shots_prompt,
    story_to_chapters_prompt,
)
from .schemas import ActionBeat, Chapter, CharacterRef, DialogueBeat, Scene, Shot, Story, StoryCharacter
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
        for index, item in enumerate(self._ensure_list(result.get("scenes")), start=1):
            normalized = self._normalize_scene_item(item, chapter.raw_text)
            scene = Scene(
                id=stable_id("scene", story.id, chapter.id, str(index), normalized.get("title", "")),
                story_id=story.id,
                chapter_id=chapter.id,
                scene_index=index,
                title=normalized.get("title") or f"Scene {index}",
                location_name=normalized.get("location_name"),
                time_of_day=normalized.get("time_of_day"),
                summary=normalized.get("summary") or "",
                characters=[CharacterRef.model_validate(obj) for obj in normalized.get("characters", [])],
                mood=normalized.get("mood"),
                actions=[ActionBeat.model_validate(obj) for obj in normalized.get("actions", [])],
                dialogues=[DialogueBeat.model_validate(obj) for obj in normalized.get("dialogues", [])],
                source_text=normalized.get("source_text") or chapter.raw_text,
                shots=[],
            )
            scenes.append(scene)

        return chapter.model_copy(update={"summary": result.get("summary"), "scenes": scenes})

    def _normalize_scene_item(self, item: Any, chapter_text: str) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {
                "title": "Scene",
                "location_name": None,
                "time_of_day": None,
                "summary": "",
                "characters": [],
                "mood": None,
                "actions": [],
                "dialogues": [],
                "source_text": chapter_text,
            }

        actions = self._normalize_actions(item.get("actions"))
        dialogues = self._normalize_dialogues(item.get("dialogues"))

        for extra in self._ensure_list(item.get("actions")):
            if self._looks_like_dialogue(extra):
                dialogues.extend(self._normalize_dialogues([extra]))
        for extra in self._ensure_list(item.get("dialogues")):
            if self._looks_like_action(extra):
                actions.extend(self._normalize_actions([extra]))

        return {
            "title": self._as_text(item.get("title")) or "Scene",
            "location_name": self._as_optional_text(item.get("location_name")),
            "time_of_day": self._as_optional_text(item.get("time_of_day")),
            "summary": self._as_text(item.get("summary")),
            "characters": self._normalize_characters(item.get("characters")),
            "mood": self._as_optional_text(item.get("mood")),
            "actions": actions,
            "dialogues": dialogues,
            "source_text": self._as_text(item.get("source_text")) or chapter_text,
        }

    def _normalize_characters(self, value: Any) -> list[dict[str, Any]]:
        characters: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in self._ensure_list(value):
            if isinstance(item, str):
                name = self._as_text(item)
                if not name:
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                characters.append({"name": name, "alias": None, "role_hint": None})
                continue
            if not isinstance(item, dict):
                continue
            name = self._as_text(item.get("name") or item.get("speaker") or item.get("actor"))
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            characters.append(
                {
                    "name": name,
                    "alias": self._as_optional_text(item.get("alias")),
                    "role_hint": self._as_optional_text(item.get("role_hint")),
                }
            )
        return characters

    def _normalize_actions(self, value: Any) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for item in self._ensure_list(value):
            if not isinstance(item, dict):
                text = self._as_text(item)
                if text:
                    actions.append({"actor": None, "action": text, "target": None, "emotion": None})
                continue
            if self._looks_like_dialogue(item) and not self._looks_like_action(item):
                continue
            action_text = self._as_text(
                item.get("action") or item.get("content") or item.get("description") or item.get("summary")
            )
            if not action_text:
                continue
            actions.append(
                {
                    "actor": self._as_optional_text(item.get("actor") or item.get("speaker")),
                    "action": action_text,
                    "target": self._as_optional_text(item.get("target")),
                    "emotion": self._as_optional_text(item.get("emotion")),
                }
            )
        return actions

    def _normalize_dialogues(self, value: Any) -> list[dict[str, Any]]:
        dialogues: list[dict[str, Any]] = []
        for item in self._ensure_list(value):
            if not isinstance(item, dict):
                text = self._as_text(item)
                if text:
                    dialogues.append({"speaker": None, "content": text, "emotion": None})
                continue
            content = self._as_text(
                item.get("content") or item.get("dialogue") or item.get("line") or item.get("text")
            )
            if not content:
                continue
            dialogues.append(
                {
                    "speaker": self._as_optional_text(item.get("speaker") or item.get("actor")),
                    "content": content,
                    "emotion": self._as_optional_text(item.get("emotion")),
                }
            )
        return dialogues

    def _ensure_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _as_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
        return ""

    def _as_optional_text(self, value: Any) -> str | None:
        text = self._as_text(value)
        return text or None

    def _looks_like_dialogue(self, item: Any) -> bool:
        return isinstance(item, dict) and any(key in item for key in ("speaker", "content", "dialogue", "line"))

    def _looks_like_action(self, item: Any) -> bool:
        return isinstance(item, dict) and any(key in item for key in ("action", "actor", "target", "description"))


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


class StoryCharacterBuilder:
    def build(self, story: Story) -> Story:
        registry: dict[str, dict[str, Any]] = {}
        key_to_registry_id: dict[str, str] = {}
        chapters = []

        for chapter in story.chapters:
            scenes = []
            for scene in chapter.scenes:
                scene_characters = []
                for character in scene.characters:
                    keys = self._character_keys(character)
                    if not keys:
                        continue
                    registry_id = self._resolve_registry_id(keys, key_to_registry_id)
                    entry = registry.get(registry_id) if registry_id else None
                    if entry is None:
                        canonical_name = character.name.strip()
                        character_id = stable_id("char", story.id, canonical_name)
                        entry = {
                            "id": character_id,
                            "canonical_name": canonical_name,
                            "aliases": set(),
                            "role_hint": character.role_hint,
                            "chapter_ids": [],
                            "scene_ids": [],
                            "scene_count": 0,
                            "first_chapter_index": chapter.chapter_index,
                            "first_scene_id": scene.id,
                        }
                        registry[character_id] = entry
                        registry_id = character_id

                    if character.name.strip() and character.name.strip() != entry["canonical_name"]:
                        entry["aliases"].add(character.name.strip())
                    if character.alias:
                        entry["aliases"].add(character.alias.strip())
                    if character.role_hint and not entry["role_hint"]:
                        entry["role_hint"] = character.role_hint
                    if chapter.id not in entry["chapter_ids"]:
                        entry["chapter_ids"].append(chapter.id)
                    if scene.id not in entry["scene_ids"]:
                        entry["scene_ids"].append(scene.id)
                    entry["scene_count"] += 1
                    self._register_character_keys(entry, key_to_registry_id)

                    scene_characters.append(
                        character.model_copy(
                            update={
                                "character_id": entry["id"],
                                "name": entry["canonical_name"],
                                "role_hint": character.role_hint or entry["role_hint"],
                            }
                        )
                    )

                scenes.append(scene.model_copy(update={"characters": scene_characters}))
            chapters.append(chapter.model_copy(update={"scenes": scenes}))

        deduped_entries: dict[str, dict[str, Any]] = {}
        for entry in registry.values():
            existing = deduped_entries.get(entry["id"])
            if existing is None:
                deduped_entries[entry["id"]] = entry
                continue
            existing["aliases"].update(entry["aliases"])
            if not existing["role_hint"] and entry["role_hint"]:
                existing["role_hint"] = entry["role_hint"]
            for chapter_id in entry["chapter_ids"]:
                if chapter_id not in existing["chapter_ids"]:
                    existing["chapter_ids"].append(chapter_id)
            for scene_id in entry["scene_ids"]:
                if scene_id not in existing["scene_ids"]:
                    existing["scene_ids"].append(scene_id)
            existing["scene_count"] = max(existing["scene_count"], entry["scene_count"])

        story_characters = [
            StoryCharacter(
                id=entry["id"],
                canonical_name=entry["canonical_name"],
                aliases=sorted(alias for alias in entry["aliases"] if alias and alias != entry["canonical_name"]),
                role_hint=entry["role_hint"],
                chapter_ids=entry["chapter_ids"],
                scene_ids=entry["scene_ids"],
                scene_count=entry["scene_count"],
                first_chapter_index=entry["first_chapter_index"],
                first_scene_id=entry["first_scene_id"],
            )
            for entry in sorted(
                deduped_entries.values(),
                key=lambda item: (
                    item["first_chapter_index"] or 999999,
                    item["canonical_name"].lower(),
                ),
            )
        ]

        return story.model_copy(update={"chapters": chapters, "characters": story_characters})

    def _character_keys(self, character: CharacterRef) -> list[str]:
        values = [character.name, character.alias]
        keys: list[str] = []
        for value in values:
            if not value:
                continue
            normalized = value.strip().lower()
            normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
            if normalized and normalized not in keys:
                keys.append(normalized)
        return keys

    def _resolve_registry_id(self, keys: list[str], key_to_registry_id: dict[str, str]) -> str | None:
        for key in keys:
            if key in key_to_registry_id:
                return key_to_registry_id[key]
        return None

    def _register_character_keys(self, entry: dict[str, Any], key_to_registry_id: dict[str, str]) -> None:
        values = [entry["canonical_name"], *entry["aliases"]]
        for value in values:
            normalized = value.strip().lower()
            normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
            if normalized:
                key_to_registry_id[normalized] = entry["id"]


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
        normalized_shots = self._normalize_shots(result.get("shots"))
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
            for index, item in enumerate(normalized_shots, start=1)
        ]
        return scene.model_copy(update={"shots": shots})

    def _normalize_shots(self, value: Any) -> list[dict[str, Any]]:
        shots: list[dict[str, Any]] = []
        for item in self._ensure_list(value):
            if isinstance(item, str):
                content = item.strip()
                if not content:
                    continue
                shots.append(self._build_shot(content=content))
                continue
            if not isinstance(item, dict):
                continue
            content = self._as_text(item.get("content") or item.get("summary") or item.get("description"))
            dialogue = self._as_optional_text(item.get("dialogue") or item.get("content") if "speaker" in item else item.get("dialogue"))
            if not content and dialogue:
                content = f"{item.get('speaker') or '人物'}对白镜头"
            if not content:
                continue
            duration = item.get("duration_sec")
            if not isinstance(duration, (int, float)) or duration <= 0:
                duration = 2.0
            shots.append(
                self._build_shot(
                    shot_type=self._as_text(item.get("shot_type")) or "medium",
                    content=content,
                    dialogue=dialogue,
                    narration=self._as_optional_text(item.get("narration")),
                    camera_direction=self._as_optional_text(item.get("camera_direction")),
                    emotion=self._as_optional_text(item.get("emotion")),
                    duration_sec=float(duration),
                )
            )
        return shots

    def _build_shot(
        self,
        content: str,
        shot_type: str = "medium",
        dialogue: str | None = None,
        narration: str | None = None,
        camera_direction: str | None = None,
        emotion: str | None = None,
        duration_sec: float = 2.0,
    ) -> dict[str, Any]:
        return {
            "shot_type": shot_type,
            "content": content,
            "dialogue": dialogue,
            "narration": narration,
            "camera_direction": camera_direction,
            "emotion": emotion,
            "duration_sec": duration_sec,
        }

    def _ensure_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _as_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
        return ""

    def _as_optional_text(self, value: Any) -> str | None:
        text = self._as_text(value)
        return text or None
