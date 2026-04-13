# novel2script

一个最小可用、可扩展的“小说转剧本”本地 Python Pipeline 项目。它支持从 `.txt` 小说文本导入、章节切分、场景抽取、角色抽取、分镜生成，到最终结构化 JSON 输出；同时支持 `mock` 模式和 `OpenAI-compatible` 模式。

## 项目目录结构

```text
pipeline_story/
├── README.md
├── requirements.txt
├── examples/
│   └── sample_novel.txt
├── novel2script/
│   ├── __init__.py
│   ├── cli.py
│   ├── extractors.py
│   ├── llm.py
│   ├── loader.py
│   ├── pipeline.py
│   ├── prompts.py
│   ├── schemas.py
│   ├── utils.py
│   └── validators.py
└── tests/
    ├── test_loader.py
    └── test_pipeline.py
```

## 设计说明

- 使用 `Pydantic v2` 定义强类型数据结构，所有中间对象都以模型实例在模块间传递。
- Pipeline 分为 `ingest`、`scenes`、`shots`、`finalize` 四个阶段，每一步都可以单独落盘。
- 默认优先用标准库，OpenAI-compatible 调用使用 `urllib` 实现，不依赖官方 SDK。
- `MockLLMClient` 可在无 API Key 条件下跑通整条链路，适合本地开发和测试。
- 所有输出同时生成紧凑版 JSON 和 pretty JSON，便于程序消费和人工查看。

## 安装方法

建议使用 Python 3.11+。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Mock 模式运行方法

```bash
python -m novel2script.cli run examples/sample_novel.txt --mock
python -m novel2script.cli run examples/sample_novel.txt --mock --step ingest
python -m novel2script.cli run examples/sample_novel.txt --mock --step scenes -o ./output_mock
```

## 真实模型模式运行方法

先配置环境变量：

```bash
export OPENAI_API_KEY="your_api_key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4o-mini"
```

然后运行：

```bash
python -m novel2script.cli run examples/sample_novel.txt
python -m novel2script.cli run examples/sample_novel.txt --model gpt-4o-mini --timeout-sec 90
python -m novel2script.cli run examples/sample_novel.txt --base-url https://your-compatible-endpoint/v1
```

## 校验输出

```bash
python -m novel2script.cli validate output/script_pretty.json
```

## 输出文件说明

默认输出目录为 `./output`，主要文件包括：

- `ingested.json` / `ingested_pretty.json`：导入结果和章节切分结果
- `scenes.json` / `scenes_pretty.json`：场景抽取结果
- `shots.json` / `shots_pretty.json`：分镜生成结果
- `script.json` / `script_pretty.json`：最终结构化剧本汇总
- `run_report.json` / `run_report_pretty.json`：运行报告、步骤状态、耗时和错误信息

## 日志示例

```text
[ingest] loaded file
[chapters] split into 2 chapters
[scenes] extracted 4 scenes
[shots] generated 12 shots
```

## 预期输出示例

`script_pretty.json` 结构示例：

```json
{
  "id": "story_xxx",
  "title": "雾城旧事",
  "description": "Imported from sample_novel.txt",
  "source_path": "/absolute/path/examples/sample_novel.txt",
  "chapters": [
    {
      "id": "chapter_xxx",
      "story_id": "story_xxx",
      "chapter_index": 1,
      "title": "第1章 雨夜来客",
      "raw_text": "...",
      "summary": "...",
      "scenes": [
        {
          "id": "scene_xxx",
          "scene_index": 1,
          "title": "第1章 雨夜来客-Scene 1",
          "location_name": "巷子",
          "time_of_day": "night",
          "summary": "...",
          "characters": [],
          "mood": "tense",
          "actions": [],
          "dialogues": [],
          "source_text": "...",
          "shots": [
            {
              "id": "shot_xxx",
              "shot_index": 1,
              "shot_type": "establishing",
              "content": "巷子",
              "dialogue": null,
              "narration": "...",
              "camera_direction": "slow pan",
              "emotion": "tense",
              "duration_sec": 3.0
            }
          ]
        }
      ]
    }
  ]
}
```

## 运行测试

```bash
python -m unittest discover -s tests
```

## 工程说明

- 如果输入小说没有明确章节标记，`loader.py` 会自动按段落和长度降级切分。
- 如果模型返回非法 JSON，`OpenAICompatibleLLMClient` 会自动进行一次修复重试。
- 后续如果要扩展数据库、任务队列、图片/视频生成，可以继续在 `pipeline.py` 上游和下游增加新的 step，而不需要推翻现有结构。
