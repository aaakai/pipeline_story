from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Iterable

import orjson


LOGGER_NAME = "novel2script"


def get_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path, encoding: str = "utf-8") -> str:
    return path.read_text(encoding=encoding)


def write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding=encoding)


def dump_json(path: Path, data: Any, pretty: bool = False) -> None:
    ensure_dir(path.parent)
    if pretty:
        path.write_bytes(
            orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
        )
    else:
        path.write_bytes(orjson.dumps(data))


def dump_json_pair(base_path: Path, data: Any, pretty_path: Path | None = None) -> tuple[Path, Path]:
    dump_json(base_path, data, pretty=False)
    if pretty_path is None:
        pretty_path = base_path.with_name(f"{base_path.stem}_pretty{base_path.suffix}")
    dump_json(pretty_path, data, pretty=True)
    return base_path, pretty_path


def load_json(path: Path) -> Any:
    return orjson.loads(path.read_bytes())


def stable_id(prefix: str, *parts: str) -> str:
    seed = "::".join([prefix, *parts])
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:12]}"


def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ")
    lines = [line.rstrip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def guess_story_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        candidate = line.strip().strip("#").strip()
        if not candidate:
            continue
        if len(candidate) <= 40 and not re.match(r"^第[\d一二三四五六七八九十百零两]+[章节回卷部]", candidate):
            return candidate
        break
    return fallback


def split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def chunk_paragraphs_by_length(paragraphs: Iterable[str], max_chars: int = 1800) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        size = len(paragraph)
        if current and current_len + size + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = size
        else:
            current.append(paragraph)
            current_len += size + 2

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def try_parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    if not match:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(match.group(1))

