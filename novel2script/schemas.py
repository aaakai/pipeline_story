from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CharacterRef(BaseModel):
    name: str
    alias: str | None = None
    role_hint: str | None = None


class ActionBeat(BaseModel):
    actor: str | None = None
    action: str
    target: str | None = None
    emotion: str | None = None


class DialogueBeat(BaseModel):
    speaker: str | None = None
    content: str
    emotion: str | None = None


class Shot(BaseModel):
    id: str
    story_id: str
    chapter_id: str
    scene_id: str
    shot_index: int
    shot_type: str
    content: str
    dialogue: str | None = None
    narration: str | None = None
    camera_direction: str | None = None
    emotion: str | None = None
    duration_sec: float | None = None


class Scene(BaseModel):
    id: str
    story_id: str
    chapter_id: str
    scene_index: int
    title: str
    location_name: str | None = None
    time_of_day: str | None = None
    summary: str
    characters: list[CharacterRef] = Field(default_factory=list)
    mood: str | None = None
    actions: list[ActionBeat] = Field(default_factory=list)
    dialogues: list[DialogueBeat] = Field(default_factory=list)
    source_text: str
    shots: list[Shot] = Field(default_factory=list)


class Chapter(BaseModel):
    id: str
    story_id: str
    chapter_index: int
    title: str
    raw_text: str
    summary: str | None = None
    scenes: list[Scene] = Field(default_factory=list)


class Story(BaseModel):
    id: str
    title: str
    description: str | None = None
    source_path: str
    chapters: list[Chapter] = Field(default_factory=list)


class StepReport(BaseModel):
    step: str
    status: Literal["pending", "running", "success", "failed", "skipped"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_sec: float | None = None
    message: str | None = None
    error: str | None = None
    output_files: list[str] = Field(default_factory=list)


class RunReport(BaseModel):
    story_id: str | None = None
    source_path: str | None = None
    output_dir: str
    mode: Literal["mock", "openai-compatible"]
    requested_step: Literal["ingest", "scenes", "shots", "all"]
    started_at: datetime
    finished_at: datetime | None = None
    duration_sec: float | None = None
    steps: list[StepReport] = Field(default_factory=list)
    success: bool = False
    errors: list[str] = Field(default_factory=list)

