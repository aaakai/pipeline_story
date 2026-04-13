from __future__ import annotations

import json
from typing import Any


def render_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def chapter_to_scenes_prompt(chapter_payload: dict[str, Any]) -> str:
    return f"""
任务目标：
你要把一章小说文本拆解为多个结构化场景（scene）。

输入字段：
{render_json(chapter_payload)}

输出 schema：
{{
  "summary": "string or null",
  "scenes": [
    {{
      "title": "string",
      "location_name": "string or null",
      "time_of_day": "string or null",
      "summary": "string",
      "characters": [
        {{
          "name": "string",
          "alias": "string or null",
          "role_hint": "string or null"
        }}
      ],
      "mood": "string or null",
      "actions": [
        {{
          "actor": "string or null",
          "action": "string",
          "target": "string or null",
          "emotion": "string or null"
        }}
      ],
      "dialogues": [
        {{
          "speaker": "string or null",
          "content": "string",
          "emotion": "string or null"
        }}
      ],
      "source_text": "string"
    }}
  ]
}}

约束条件：
1. 必须只输出 JSON，不能输出 markdown 代码块，不能输出额外解释。
2. 一个章节可以拆成 1 到 5 个场景，优先按地点、时间、人物组合变化切分。
3. scenes 必须保持原文叙事顺序。
4. source_text 必须来自输入文本中的连续片段，不要凭空捏造。
5. 如果无法确定字段，使用 null、空数组或空字符串，不要胡编。
6. summary 要简洁稳定，长度建议 1 到 2 句。
7. dialogues 只保留明确像对白的内容；actions 只保留关键动作。
8. characters 中名称尽量统一，避免同一角色多种写法。

只返回 JSON。
""".strip()


def scene_characters_prompt(scene_payload: dict[str, Any]) -> str:
    return f"""
任务目标：
从单个场景文本中抽取人物引用信息，用于统一角色名和角色提示。

输入字段：
{render_json(scene_payload)}

输出 schema：
{{
  "characters": [
    {{
      "name": "string",
      "alias": "string or null",
      "role_hint": "string or null"
    }}
  ]
}}

约束条件：
1. 只返回 JSON。
2. 人物列表去重，按在场景中首次出现顺序输出。
3. 不确定时不要杜撰角色背景，role_hint 可以为 null。
4. 不要输出旁白、地点、时间作为人物。
5. 如果没有明显人物，返回空数组。

只返回 JSON。
""".strip()


def scene_to_shots_prompt(scene_payload: dict[str, Any]) -> str:
    return f"""
任务目标：
把一个结构化场景进一步拆成可执行的分镜（shot）列表。

输入字段：
{render_json(scene_payload)}

输出 schema：
{{
  "shots": [
    {{
      "shot_type": "string",
      "content": "string",
      "dialogue": "string or null",
      "narration": "string or null",
      "camera_direction": "string or null",
      "emotion": "string or null",
      "duration_sec": 1.0
    }}
  ]
}}

约束条件：
1. 只返回 JSON。
2. shots 必须按场景内时间顺序输出，建议 2 到 6 个分镜。
3. shot_type 使用稳定短语，例如：establishing、wide、medium、close_up、insert、tracking。
4. content 描述画面主体；dialogue 只放该镜头承载的对白；narration 只放必要旁白。
5. duration_sec 必须是正数，建议范围 1 到 8 秒。
6. 如果信息不足，保持简洁，不要发明复杂机位。
7. 分镜内容必须基于输入场景，不要添加新的剧情事实。

只返回 JSON。
""".strip()
