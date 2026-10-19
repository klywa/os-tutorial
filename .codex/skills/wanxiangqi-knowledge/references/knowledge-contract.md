# 知识及实体数据契约

## 当前扩展：schema5

阵容—棋手阅读采用语义布局版本2（完整目录见[player-branches.md](player-branches.md)）。顶层`reading_layout.version=2`及`claim_locations`明确结论位置；`coverage`按分支保存教学字段状态及审核引用。阅读API保留`sections/section_aliases`，增加`opening/layout_version/coverage`；网页、Markdown、概览及导出使用相同棋手投影。`explicit_relationships`启用明确关系，`guide_related`保存目标note/player、关系及href，不按实体交集推导相关性。旧版布局继续兼容。

有棋手分支的记录使用schema5，旧schema4无分支记录保持兼容。完整规则见[player-branches.md](player-branches.md)。新增`meta.common_claim_refs/player_branches/assessment`；分支通过明确ID关联棋手与结论、路线、组合和主要变阵。原稳定笔记ID、结论ID、证据和人工历史保留。成员按阶段完整替换；统计比例须同时具备样本量、口径、时间范围与来源。网页、skill和固定格式Markdown都通过共享事务同步；不能只更新正文或只更新结构化信息。

## 提交知识

网页可用`POST /api/notes`直接创建空笔记：`type/title/aliases/request_id`；类型为lineup/player/other，标题按现有中文文件名规则校验。`workspace.create_note`经过共享写锁、事务恢复和统一生成保存，不写入虚构结论或证据。同类型同名报冲突，不自动合并；相同请求标识和内容重试返回同一笔记（即使后来人工改名），标识复用于不同内容报冲突。正文及棋手分支继续通过既有统一编辑或skill提交补充。已有笔记ID与文件路径不因目录改版而迁移；旧阵容名单与采集标签保留兼容。

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
- 旧版阵容字段：阵容组成、禁用阵营适用情况、核心机制、前期运营及应变、中期运营及应变、后期运营及应变、成型后提升思路、第一轮拍卖、第二轮拍卖、第三轮拍卖、推荐天赋及原因、站位技巧、推荐装备、终局技巧、克制手段。无分支记录保持兼容；schema5分支按版本2语义目录投影，旧“克制手段”必须逐段分辨制敌和被克制方向。
- 阵容整理还需按 [教学主题覆盖检查](teaching-coverage.md) 扫描关键牌判断、经济与竞价取舍、关键操作顺序、新手步骤、战后诊断及操作时间不足。主题可由既有章节或 meta 中的明确策略覆盖，不要求模板与章节一一对应。有独立可靠内容时，可用现有 `claim.section` 追加“关键牌判断”“战后复盘”“操作时间不足”等自定义章节；无证据时不新增空结论、不迁移固定字段或扩展 meta schema。
- 棋手正文顺序：技能、前期思路、适用打法与选择、适用技巧、关联知识。旧“使用技巧”“适配阵容”兼容映射至新章节，不保留重复标题。阶段强度按[player-notes.md](player-notes.md)在阵容分支保存并投影，旧schema5缺字段兼容；其他知识默认“知识内容”，可追加自定义章节。
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

索引保存结构化知识。所有保存通过共享操作系统写锁及 pending-save.json 恢复事务同步 Markdown/阵容存档/索引。schema5固定格式棋手Markdown允许直接编辑，必须经sync-markdown或本地服务读回后再提交；其他生成物不单独手改。

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


## 灵活阵容扩展（schema_version=3）

新写入使用下述schema4，并保留本节全部字段与含义。

保留 v2 的全部 meta 字段，新增可选 `operation_routes` 与 `late_variants`。缺失字段按空列表读取，不将旧阵容自动拆成多套组合。索引迁移为阵容 claims 增加稳定 `id`；未指定 ID 时按结论语义生成，来源证据不参与 ID。路径、笔记 ID 与人工内容保持稳定。

`operation_routes` 每项包含 `id/name/condition/advantages/risks/transition`、`phases: {early:结论ID列表,middle:结论ID列表,late:结论ID列表}`、`claim_refs:结论ID列表`、`variant_ids:已确认适配的组合ID列表`。

`late_variants` 每项包含 `id/name/condition/members/core_heroes/required_factions/ban_conditions/ban_combinations/claim_refs`。`members` 使用既有 Member 格式；`ban_combinations` 为 `{factions:同时禁用阵营ID列表,status:playable|unplayable|unknown,reason:说明}` 列表。名称、描述、成员必要性和适配关系都必须有 `claim_refs` 所指结论的证据支持，网页人工编辑沿用 manual_meta 保护，不冒充视频确认。

全局核心、全局中后期必需成员只表达所有路线共同依赖，不将所有组合合并进 compositions.late。组合依赖独立由其核心及必需成员推导。共同必需阵营被禁时整篇不可玩；组合必需阵营被禁只排除该组合。至少一套完整组合在当前全部禁用条件下已确认可玩，整篇才为可玩；全不可玩为不可玩；其他为待确认。多个禁用阵营必须有匹配全部禁用集合的联合条件，不能由单个阵营的可玩记录推导。

沿用 GET/PUT notes、commit、persist 事务和 revision。删除组合同步移除节奏适配引用；修改或清空章节时将相关引用指向新人工结论或移除，并保护相应 meta。导入拒绝重复 ID、悬空结论/组合/实体引用。Markdown 导出运营节奏及推荐组合，省略内部 ID 与来源证据。

既有显式结论ID允许同一已引用来源的文案核对修正，旧文案与证据存入history；不同版本、条件、推断标志或仅有新来源的策略不能复用旧ID覆盖，须另建结论。人工章节与meta仍优先保护。

灵活阵容记录一旦存在，必须填写契约字段：节奏包含 condition/advantages/risks/transition/phases/claim_refs/variant_ids，组合包含 condition/members/core_heroes/required_factions/ban_conditions/ban_combinations/claim_refs；未知说明可为空、无引用可为 []，不可省略导致前端数据形状不完整。旧阵容可继续省略两类记录。

## 主要变阵扩展（schema_version=4）

旧数据缺少`meta.major_variants`按空列表读取。每项固定字段：`id/name/condition_refs/baseline_refs/claim_refs/late_variant_ids/operation_route_ids/differences`。前三个refs对应采用条件与转入限制、共同主干和变阵依据，引用稳定结论ID。`differences`包含`heroes/mechanism/tempo/equipment/talents/skills`，各项固定`status: different|same|unknown`与`claim_refs: []`；有差异和沿用主干均须有效依据。已确认条目需有条件、主干、变阵依据及至少一项有据差异；缺失时显示待确认。

后两个ID列表引用现有组合／路线，不复制英雄名单、不创建额外适配。禁止重复ID及悬空引用，删除被引用对象前先解除关联。嵌套结论参与重映射、合并校验、人工保护和依赖扫描；旧导入不传新字段时保留已有值，显式空列表才清空。统一事务写schema4并同步生成物。分类与编辑规则见[major-variants.md](major-variants.md)。
