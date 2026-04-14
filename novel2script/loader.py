from __future__ import annotations

import re
from pathlib import Path

from .schemas import Chapter, Story
from .utils import (
    chunk_paragraphs_by_length,
    clean_text,
    guess_story_title,
    read_text,
    split_paragraphs,
    stable_id,
)


CHAPTER_PATTERN = re.compile(
    r"(?m)^(?P<title>(?:第[\d一二三四五六七八九十百零两]+[章节回卷部]|chapter\s+\d+|chap\.\s*\d+)[^\n]*)$",
    flags=re.IGNORECASE,
)


def load_story_source(path: Path) -> tuple[Story, str]:
    raw_text = read_text(path)
    cleaned = clean_text(raw_text)
    fallback_title = path.stem.replace("_", " ").strip() or "Untitled Story"
    title = guess_story_title(cleaned, fallback_title)
    story_id = stable_id("story", str(path.resolve()), cleaned[:200])
    story = Story(
        id=story_id,
        title=title,
        description=f"Imported from {path.name}",
        source_path=str(path.resolve()),
        characters=[],
        chapters=[],
    )
    return story, cleaned


def load_story_from_txt(path: Path) -> Story:
    story, cleaned = load_story_source(path)
    chapters = split_into_chapters(cleaned, story.id)
    return story.model_copy(update={"chapters": chapters})


def split_into_chapters(text: str, story_id: str) -> list[Chapter]:
    matches = list(CHAPTER_PATTERN.finditer(text))
    if not matches:
        return _fallback_chapters(text, story_id)

    chapters: list[Chapter] = []
    for index, match in enumerate(matches, start=1):
        start = match.start()
        end = matches[index].start() if index < len(matches) else len(text)
        block = text[start:end].strip()
        lines = block.splitlines()
        title = lines[0].strip() if lines else f"Chapter {index}"
        body = "\n".join(lines[1:]).strip()
        chapters.append(
            Chapter(
                id=stable_id("chapter", story_id, str(index), title),
                story_id=story_id,
                chapter_index=index,
                title=title,
                raw_text=body or block,
                summary=None,
                scenes=[],
            )
        )
    return chapters


def _fallback_chapters(text: str, story_id: str) -> list[Chapter]:
    paragraphs = split_paragraphs(text)
    chunks = chunk_paragraphs_by_length(paragraphs, max_chars=2200)
    chapters: list[Chapter] = []
    for index, chunk in enumerate(chunks, start=1):
        chapters.append(
            Chapter(
                id=stable_id("chapter", story_id, str(index), chunk[:50]),
                story_id=story_id,
                chapter_index=index,
                title=f"Segment {index}",
                raw_text=chunk,
                summary=None,
                scenes=[],
            )
        )
    return chapters
