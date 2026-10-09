# 知识及实体数据契约

## 提交知识

将提交 JSON 放到 `knowledge/reports/`。脚本不负责猜阵容或语义改写：Codex 生成提交文件后运行 `commit`，文件格式为 `{"notes": [...]}`。

```json
{
  "notes": [{
    "id": "lineup-stable-topic-id",
    "type": "lineup",
    "title": "从视频确认的阵容名称",
    "entities": ["card:官方ID", "player:官方ID"],
    "core": ["card:核心英雄ID"],
    "topic": "从视频确认的主题",
    "claims": [{
      "section": "核心机制",
      "text": "经ASR及画面确认的结论",
      "version": null,
      "condition": "明确的适用条件；未说明时为空字符串",
      "inference": false,
      "kind": "general_strategy",
      "evidence": [{"source": "BV实际编号:p1", "start": 12.5, "end": 25.0,
                    "frame": "frames/18-0.jpg"}]
    }]
  }]
}
```

该示例是格式说明，不能作为真实知识导入。`frame` 仅在实际存在并核对过时填写。时间是视频秒数，不是游戏回合。ID 使用字母、数字、下划线或短横线，不包含路径或冒号。来源 ID 含冒号，落盘目录将冒号换成下划线。

- `type`：`lineup`、`player`、`other`，分别输出到 `lineups/`、`players/`、`other/`。
- 阵容固定字段：阵容组成、核心机制、前期运营及应变、中期运营及应变、后期运营及应变、成型后提升思路、第一轮拍卖、第二轮拍卖、第三轮拍卖、推荐天赋及原因、站位技巧、推荐装备、终局技巧、克制手段。
- 棋手固定字段：技能、使用技巧、适配阵容。其他默认“知识内容”，可追加自定义章节。
- 回合描述写在结论正文，例如“第5–7回合”；来源没说具体回合时只能写前期等原始阶段。
- 每条结论需要一个或多个来源时间段。版本与条件是结论级字段；相同文本但版本或条件不同不能合并。
- 推断须设 `inference=true`，正文说明推导依据；缺字段不主动搜索其他攻略补全。
- `evidence`、`version` 保留在内部索引，不渲染为逐条引用、版本前缀、视频链接或图片。将适用条件自然写入 `text`，必要时集中说明版本差异。其他知识仅输出有内容的主题章节。
- 改写已有攻略时替换索引中的原结论文本，并同步维护用于重放的导入数据，不以新增结论追加。原有证据与条件完整保留；技术识别问题放内部报告。
- 未知实体先录入实体库再引用；索引储存所有结构化结论，不能只改 Markdown 而不更新索引。已有手写笔记需要读后按证据迁移；不得覆盖未迁移内容。

## 实体记录

结论分类 `kind` 必填：`mechanic`、`general_strategy`、`conditional_strategy` 可进入知识索引；`match_action` 仅保存在内部筛选报告，commit 拒绝。条件策略需在正文明确适用情境。混合段落由 Codex 按转写语义拆分，脚本不以关键词自动推断通用性。被移出项保存完整原结论、原因及原证据。

七类 JSON 数组：`players`、`heroes`、`equipment`、`talents`、`derivatives`、`effect-cards`、`player-skills`。每条包括：

`id`、`category`、`name`、`aliases`、`description`、`properties`、`relations`、`sources`、`version`、`status`、`retrieved_at`。

官网记录 ID 使用 `card:ID` / `player:ID`。仅视频发现的实体使用 `pending:类别:名称摘要`，`status=pending`，记录 BV 来源和时间段，不伪装官方 ID。确认官方对应项后统一迁移知识中的引用，合并别名，保留映射记录。

`properties` 保存官方原始字段，`description` 去除富文本标签但保留数值与单位；`history` 保存实际变更前内容。觉醒英雄作为独立卡牌记录，区分同名不同卡 ID；衍生物由卡牌类型与英雄 `actorType` 等官方字段判定，不凭名称猜。棋手牌通过其所属棋手记录关联。未知官方类型保留并在同步报告中说明待分类。

新增确认别名要记录依据到来源 `corrections.json`。写实体文件使用 `wxq.atomic_json` 保留恢复副本，校验同一 ID 不重复、类别与目标文件一致。
