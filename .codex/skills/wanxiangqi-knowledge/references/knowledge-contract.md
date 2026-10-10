# 知识及实体数据契约

## 提交知识

将提交 JSON 放到 `raw/reports/`。脚本不负责猜阵容或语义改写：Codex 生成提交文件后运行 `commit`，文件格式为 `{"notes": [...]}`。

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

## 阵容 meta 与人工编辑契约（schema_version=2）

稳定 ID 与路径分离：`path` 为 `knowledge/类型目录/中文标题.md`，重名采用持久中文序号；关联条目保存 `path`。每套阵容在同目录生成同名 `.json`，内容与索引对应记录一致。路径一经分配保持稳定，标题改动不破坏链接。

阵容 `meta` 格式：

```json
{
  "required_factions": ["faction:dahe"],
  "players": ["player:34"],
  "core_heroes": ["card:1871"],
  "compositions": {
    "early": [{"hero":"card:1871","necessity":"optional","role":"作用","replaces":"","replacement_note":"替换说明"}],
    "middle": [],
    "late": []
  },
  "ban_conditions": [{"faction":"faction:sanfen","status":"unknown","reason":"待确认"}],
  "matchups": [{"target":"card:1871","condition":"适用情境","text":"经确认的针对策略"}]
}
```

示例只说明格式，不表示真实打法。禁用状态为 `playable`、`unplayable`、`unknown`；必须阵营被禁优先判不可玩。多个禁用条件须全部已确认可玩，否则待确认；任一不可玩则不可玩。无证据时保存空列表或 unknown，不根据出现英雄反推必须阵营。实体引用使用实体 ID，未知名称显式 `pending:名称`。针对目标可为英雄 ID 或阵容笔记 ID。

网页 PUT 笔记包含 `revision`、按名称映射的 `sections` 和可选 `meta/title/aliases`。旧 revision 返回冲突，不覆盖；章节修改以 origin=manual 结论替换，原结论与证据进入 history，不附假视频依据。manual_sections 保护人工章节，manual_meta 保护人工 meta；CLI 新输入冲突进入 conflicts。人工修订不经普通视频导入校验，但必须经网页统一入口校验保存，CLI 不接受伪造的人工证据。

索引是唯一知识源。所有保存通过共享操作系统写锁及 pending-save.json 恢复事务生成 Markdown/阵容存档/索引；禁止直接编辑生成物。

## 卡牌与文字稿存档

`knowledge/cards/index.json` 的 `cards` 为实体派生资料，包含稳定ID、类别、别名、效果、阵营（官方relationID及项目ID）、英雄品阶、觉醒状态、skills及强化节点、skills_source、按官网展示换算的stats、中文attributes、raw_attributes、来源、同步日期和版本。分类中文Markdown与目录一致，不编造视频证据。普通与觉醒ID分开；借用普通英雄技能必须声明来源。

`raw/BV编号_pN.md` 保存带时间戳的纠正版全文；`raw/index.json` 的sources记录来源ID、路径、raw_sha256、corrected_sha256和output_sha256。原始ASR不可改写，旧视频数值不可更新为现版本；人工全文修改保留并产生差异。全文不纳入攻略claims，实战操作不自动泛化。

阵容必须阵营由核心和中后期必需成员推导，包括关键辅助；前期过渡、可选与无阵营成员排除。成员的必要性先依据攻略确定，不能因全文出现或官方标签而擅自判定。完整阵容被禁与有条件替代路线分别说明；人工meta仍按原保护契约处理。

## 实体记录

结论分类 `kind` 必填：`mechanic`、`general_strategy`、`conditional_strategy` 可进入知识索引；`match_action` 仅保存在内部筛选报告，commit 拒绝。条件策略需在正文明确适用情境。混合段落由 Codex 按转写语义拆分，脚本不以关键词自动推断通用性。被移出项保存完整原结论、原因及原证据。

七类 JSON 数组：`players`、`heroes`、`equipment`、`talents`、`derivatives`、`effect-cards`、`player-skills`。每条包括：

`id`、`category`、`name`、`aliases`、`description`、`properties`、`relations`、`sources`、`version`、`status`、`retrieved_at`。

官网记录 ID 使用 `card:ID` / `player:ID`。仅视频发现的实体使用 `pending:类别:名称摘要`，`status=pending`，记录 BV 来源和时间段，不伪装官方 ID。确认官方对应项后统一迁移知识中的引用，合并别名，保留映射记录。

`properties` 保存官方原始字段，`description` 去除富文本标签但保留数值与单位；`history` 保存实际变更前内容。觉醒英雄作为独立卡牌记录，区分同名不同卡 ID；衍生物由卡牌类型与英雄 `actorType` 等官方字段判定，不凭名称猜。棋手牌通过其所属棋手记录关联。未知官方类型保留并在同步报告中说明待分类。

新增确认别名要记录依据到来源 `corrections.json`。写实体文件使用 `wxq.atomic_json` 保留恢复副本，校验同一 ID 不重复、类别与目标文件一致。
