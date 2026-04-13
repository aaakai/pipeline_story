from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .utils import try_parse_json


class LLMClientError(RuntimeError):
    """Raised when the LLM client cannot return valid JSON."""


class LLMClient(ABC):
    @abstractmethod
    def generate_json(self, prompt_name: str, prompt: str, payload: dict[str, Any]) -> Any:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """Deterministic mock implementation for local end-to-end tests."""

    def generate_json(self, prompt_name: str, prompt: str, payload: dict[str, Any]) -> Any:
        if prompt_name == "story_to_chapters":
            return self._story_to_chapters(payload)
        if prompt_name == "chapter_to_scenes":
            return self._chapter_to_scenes(payload)
        if prompt_name == "scene_characters":
            return self._scene_characters(payload)
        if prompt_name == "scene_to_shots":
            return self._scene_to_shots(payload)
        raise LLMClientError(f"Unsupported mock prompt: {prompt_name}")

    def _story_to_chapters(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload["raw_text"]
        title = payload.get("title") or "Untitled Story"
        chapters = self._split_chapters(text)
        return {
            "title": title,
            "description": payload.get("description"),
            "chapters": chapters,
        }

    def _chapter_to_scenes(self, payload: dict[str, Any]) -> dict[str, Any]:
        chapter_text = payload["raw_text"]
        title = payload["title"]
        chunks = self._split_scene_like_blocks(chapter_text)
        scenes: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks, start=1):
            characters = self._extract_character_refs(chunk)
            dialogues = self._extract_dialogues(chunk)
            actions = self._extract_actions(chunk, characters)
            scenes.append(
                {
                    "title": f"{title}-Scene {index}",
                    "location_name": self._guess_location(chunk),
                    "time_of_day": self._guess_time(chunk),
                    "summary": self._summarize(chunk),
                    "characters": characters,
                    "mood": self._guess_mood(chunk),
                    "actions": actions,
                    "dialogues": dialogues,
                    "source_text": chunk,
                }
            )
        return {"summary": self._summarize(chapter_text), "scenes": scenes}

    def _scene_characters(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("source_text") or payload.get("summary") or ""
        return {"characters": self._extract_character_refs(text)}

    def _scene_to_shots(self, payload: dict[str, Any]) -> dict[str, Any]:
        scene_text = payload.get("source_text") or payload.get("summary") or ""
        actions = payload.get("actions") or []
        dialogues = payload.get("dialogues") or []

        shots: list[dict[str, Any]] = [
            {
                "shot_type": "establishing",
                "content": payload.get("location_name") or self._guess_location(scene_text) or "环境建立镜头",
                "dialogue": None,
                "narration": payload.get("summary"),
                "camera_direction": "slow pan",
                "emotion": payload.get("mood"),
                "duration_sec": 3.0,
            }
        ]

        for item in actions[:3]:
            shots.append(
                {
                    "shot_type": "medium",
                    "content": item.get("action") or "角色动作",
                    "dialogue": None,
                    "narration": None,
                    "camera_direction": "follow action",
                    "emotion": item.get("emotion") or payload.get("mood"),
                    "duration_sec": 2.5,
                }
            )

        for item in dialogues[:2]:
            shots.append(
                {
                    "shot_type": "close_up",
                    "content": f"{item.get('speaker') or '人物'}对白镜头",
                    "dialogue": item.get("content"),
                    "narration": None,
                    "camera_direction": "push in",
                    "emotion": item.get("emotion") or payload.get("mood"),
                    "duration_sec": 2.0,
                }
            )

        if len(shots) == 1:
            sentences = [part.strip() for part in re.split(r"[。！？!?]", scene_text) if part.strip()]
            for sentence in sentences[:2]:
                shots.append(
                    {
                        "shot_type": "medium",
                        "content": sentence[:60],
                        "dialogue": None,
                        "narration": None,
                        "camera_direction": "static",
                        "emotion": payload.get("mood"),
                        "duration_sec": 2.0,
                    }
                )

        return {"shots": shots[:6]}

    def _split_scene_like_blocks(self, text: str) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if len(paragraphs) <= 1:
            sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])", text) if part.strip()]
            midpoint = max(1, len(sentences) // 2)
            left = "".join(sentences[:midpoint]).strip()
            right = "".join(sentences[midpoint:]).strip()
            return [chunk for chunk in [left, right] if chunk]

        chunks: list[str] = []
        current: list[str] = []
        for paragraph in paragraphs:
            current.append(paragraph)
            if len(current) >= 2:
                chunks.append("\n\n".join(current))
                current = []
        if current:
            chunks.append("\n\n".join(current))
        return chunks or [text]

    def _split_chapters(self, text: str) -> list[dict[str, Any]]:
        pattern = re.compile(
            r"(?m)^(?P<title>(?:第[\d一二三四五六七八九十百零两]+[章节回卷部]|chapter\s+\d+|chap\.\s*\d+)[^\n]*)$",
            flags=re.IGNORECASE,
        )
        matches = list(pattern.finditer(text))
        chapters: list[dict[str, Any]] = []
        if matches:
            for index, match in enumerate(matches, start=1):
                start = match.start()
                end = matches[index].start() if index < len(matches) else len(text)
                block = text[start:end].strip()
                lines = block.splitlines()
                title = lines[0].strip() if lines else f"Segment {index}"
                body = "\n".join(lines[1:]).strip() or block
                chapters.append(
                    {
                        "chapter_index": index,
                        "title": title,
                        "raw_text": body,
                        "summary": self._summarize(body),
                    }
                )
            return chapters

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for paragraph in paragraphs:
            size = len(paragraph)
            if current and current_len + size + 2 > 2200:
                chunks.append("\n\n".join(current))
                current = [paragraph]
                current_len = size
            else:
                current.append(paragraph)
                current_len += size + 2
        if current:
            chunks.append("\n\n".join(current))

        for index, chunk in enumerate(chunks or [text], start=1):
            chapters.append(
                {
                    "chapter_index": index,
                    "title": f"Segment {index}",
                    "raw_text": chunk,
                    "summary": self._summarize(chunk),
                }
            )
        return chapters

    def _extract_character_refs(self, text: str) -> list[dict[str, Any]]:
        names: list[str] = []
        patterns = [
            r"[“\"]?([A-Z][a-z]{1,15})[”\"]?",
            r"[“\"]?([\u4e00-\u9fff]{2,4})[”\"]?",
        ]
        stop_words = {"我们", "他们", "这里", "时候", "夜色", "空气", "Segment", "Scene"}
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip()
                if name in stop_words:
                    continue
                if re.fullmatch(r"第[\d一二三四五六七八九十百零两]+", name):
                    continue
                if name not in names:
                    names.append(name)
                if len(names) >= 4:
                    break
            if names:
                break

        return [{"name": name, "alias": None, "role_hint": None} for name in names[:4]]

    def _extract_dialogues(self, text: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for match in re.finditer(r"[“\"]([^”\"]{2,60})[”\"]", text):
            results.append(
                {
                    "speaker": None,
                    "content": match.group(1).strip(),
                    "emotion": self._guess_mood(match.group(1)),
                }
            )
            if len(results) >= 3:
                break
        return results

    def _extract_actions(self, text: str, characters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sentences = [part.strip() for part in re.split(r"[。！？!?]", text) if part.strip()]
        actor = characters[0]["name"] if characters else None
        actions: list[dict[str, Any]] = []
        for sentence in sentences[:3]:
            action = sentence[:40]
            if not action:
                continue
            actions.append(
                {
                    "actor": actor,
                    "action": action,
                    "target": None,
                    "emotion": self._guess_mood(sentence),
                }
            )
        return actions

    def _guess_location(self, text: str) -> str | None:
        keywords = ["房间", "街道", "巷子", "庭院", "客厅", "学校", "车站", "酒馆", "森林", "桥边", "library", "street", "room"]
        for keyword in keywords:
            if keyword.lower() in text.lower():
                return keyword
        return None

    def _guess_time(self, text: str) -> str | None:
        mapping = {
            "清晨": "morning",
            "早晨": "morning",
            "上午": "day",
            "中午": "noon",
            "下午": "afternoon",
            "傍晚": "dusk",
            "夜": "night",
            "深夜": "late_night",
            "黎明": "dawn",
        }
        for key, value in mapping.items():
            if key in text:
                return value
        lowered = text.lower()
        if "night" in lowered:
            return "night"
        if "morning" in lowered:
            return "morning"
        return None

    def _guess_mood(self, text: str) -> str | None:
        mapping = {
            "紧张": "tense",
            "愤怒": "angry",
            "开心": "warm",
            "微笑": "warm",
            "沉默": "quiet",
            "害怕": "fearful",
            "冷": "somber",
            "雨": "somber",
        }
        for key, value in mapping.items():
            if key in text:
                return value
        return "neutral"

    def _summarize(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned[:120]


class OpenAICompatibleLLMClient(LLMClient):
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_sec: int = 60,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.timeout_sec = timeout_sec
        if not self.api_key:
            raise LLMClientError("OPENAI_API_KEY is required for OpenAI-compatible mode.")

    def generate_json(self, prompt_name: str, prompt: str, payload: dict[str, Any]) -> Any:
        response_text = self._chat(prompt)
        try:
            return try_parse_json(response_text)
        except json.JSONDecodeError:
            repair_prompt = self._build_repair_prompt(response_text)
            repaired = self._chat(repair_prompt)
            try:
                return try_parse_json(repaired)
            except json.JSONDecodeError as exc:
                raise LLMClientError(f"Failed to parse JSON for prompt {prompt_name}") from exc

    def _build_repair_prompt(self, bad_response: str) -> str:
        return (
            "你将收到一段原始模型输出，它本应是 JSON，但格式不合法。"
            "请只返回修复后的合法 JSON，不要输出解释，不要使用 markdown 代码块。\n\n"
            f"原始输出：\n{bad_response}"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type((urllib.error.URLError, TimeoutError, LLMClientError)),
        reraise=True,
    )
    def _chat(self, prompt: str) -> str:
        try:
            return self._chat_once(prompt, include_response_format=True)
        except LLMClientError as exc:
            message = str(exc).lower()
            if "response_format" not in message:
                raise
            return self._chat_once(prompt, include_response_format=False)

    def _chat_once(self, prompt: str, include_response_format: bool) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a strict JSON generation engine. Return JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        if include_response_format:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise LLMClientError(f"HTTP {exc.code}: {details}") from exc

        data = json.loads(raw)
        choices = data.get("choices") or []
        if not choices:
            raise LLMClientError("No choices returned from API.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            text_parts = [item.get("text", "") for item in content if isinstance(item, dict)]
            content = "".join(text_parts)
        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("Empty content returned from API.")
        return content
