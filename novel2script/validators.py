from __future__ import annotations

from pathlib import Path

from .schemas import Story
from .utils import load_json


def validate_story_file(path: Path) -> list[str]:
    payload = load_json(path)
    story = Story.model_validate(payload)
    return validate_story(story)


def validate_story(story: Story) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_required_fields(story))
    errors.extend(_validate_indices(story))
    errors.extend(_validate_character_drift(story))
    return errors


def _validate_required_fields(story: Story) -> list[str]:
    errors: list[str] = []
    if not story.id:
        errors.append("Story id is empty.")
    if not story.title:
        errors.append("Story title is empty.")
    character_ids = {character.id for character in story.characters}
    for chapter in story.chapters:
        if not chapter.raw_text.strip():
            errors.append(f"Chapter {chapter.chapter_index} raw_text is empty.")
        for scene in chapter.scenes:
            if not scene.title.strip():
                errors.append(f"Scene {scene.scene_index} in chapter {chapter.chapter_index} has empty title.")
            if not scene.summary.strip():
                errors.append(f"Scene {scene.scene_index} in chapter {chapter.chapter_index} has empty summary.")
            for character in scene.characters:
                if character.character_id and character.character_id not in character_ids:
                    errors.append(
                        f"Scene {scene.scene_index} in chapter {chapter.chapter_index} references missing character_id {character.character_id}."
                    )
            for shot in scene.shots:
                if not shot.content.strip():
                    errors.append(
                        f"Shot {shot.shot_index} in scene {scene.scene_index} chapter {chapter.chapter_index} has empty content."
                    )
    return errors


def _validate_indices(story: Story) -> list[str]:
    errors: list[str] = []
    chapter_indices = [chapter.chapter_index for chapter in story.chapters]
    if chapter_indices != list(range(1, len(chapter_indices) + 1)):
        errors.append("Chapter indices are not continuous.")
    for chapter in story.chapters:
        scene_indices = [scene.scene_index for scene in chapter.scenes]
        if scene_indices != list(range(1, len(scene_indices) + 1)):
            errors.append(f"Scene indices are not continuous in chapter {chapter.chapter_index}.")
        for scene in chapter.scenes:
            shot_indices = [shot.shot_index for shot in scene.shots]
            if shot_indices != list(range(1, len(shot_indices) + 1)):
                errors.append(
                    f"Shot indices are not continuous in chapter {chapter.chapter_index}, scene {scene.scene_index}."
                )
    return errors


def _validate_character_drift(story: Story) -> list[str]:
    errors: list[str] = []
    canonical: dict[str, set[str]] = {}
    for chapter in story.chapters:
        for scene in chapter.scenes:
            for character in scene.characters:
                name = character.name.strip()
                if not name:
                    continue
                key = name[0].lower()
                canonical.setdefault(key, set()).add(name.lower())
    for key, names in canonical.items():
        if len(names) > 5:
            errors.append(f"Character names under initial '{key}' drift too much: {sorted(names)}")
    return errors
