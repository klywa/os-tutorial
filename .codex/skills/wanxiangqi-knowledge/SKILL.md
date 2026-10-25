---
name: wanxiangqi-knowledge
description: 将王者万象棋攻略复用文字稿或按需ASR及关键帧核对整理入库，维护纯JSON知识、棋手阵容笔记与实体；支持读取前端批注并按要求修改笔记。适用于导入攻略、更新知识、处理批注、逐英雄教学及按需导出阅读版；普通视频摘要或无关网页制作不使用此技能。
---

# 王者万象棋知识整理

## 批注修改模式
用户要求处理批注、按前端批注修订时，先读[批注修改流程](references/annotation-review.md)。默认查询全库未处理批注，读取最新正文与附件，按批注直接修改并保存；证据不足或有歧义的保留待处理并说明原因。只授权批注涉及的人工保护范围，不能绕过其他人工保护。保存读回、校验成功后才标记已处理。

## schema6：纯 JSON 知识
先读[知识契约](references/knowledge-contract.md)。knowledge/ 仅保存 JSON：名称.json 是正文唯一事实源，同名 .meta.json 保存身份、来源、证据、历史、人工保护、冲突与迁移映射。index.meta.json 只登记身份和路径，不复制全文。

棋手笔记按官方 player_id 唯一绑定；阵容独立保存为“阵容名-棋手”，共通知识完整归入各适用分支。常小娥使用“常小娥灵活变阵-常小娥”。不生成编号副本、阵容总览、知识 Markdown、reviews 或 replays。

正文使用有序章节与 key-value 节点，保存必要格式以完整导出 Markdown。英雄整段一个条目，行动字段及有据的获得途径、其他作用保留在 value；无标题段落固定 key=正文、show_key=false，以稳定节点ID区分。条目复制为“key：value”，无标题条目用最近所属章节标题，无章节则用笔记标题；单段纯文字章节复制为“章节标题：正文”，复杂章节保留层级。所有复制的key不带加粗星号；正文有效Markdown及下载格式保留。清除标签装饰方括号，修复key开括号、value闭括号的拆分残留，不删除链接或代码语法。

组成、运营路线、禁用条件、作用和替换条件本身也是知识，保存在正文 semantics；相同文本用 $text 引用节点，不在附件再存独立可编辑副本。supporting_nodes 保存已审核但不重复显示的支撑知识，claim_annotations 在附件中按 text_ref 保留原结论ID和证据。人工历史不作为当前知识自动重放。

## 路径与统一写入
技能所在 .codex/skills 的项目为默认根目录，可显式 --root；不写个人全局知识库。raw、entities、knowledge 与 .codex 同级。原始资料、全文文字稿和报告在 raw；备份在 raw/backups/knowledge，锁与事务在 raw/knowledge，不能放在 knowledge。

先通过 workspace.notes(root) 读取最新 document、revision，并读取同名附件。相关新旧知识在同一次 commit 中提交，不能分别手改正式正文和附件。当前文件契约为 {"notes":[{"body":正文对象,"metadata":附件对象}]}，已有记录必须带最新 revision。旧 claims 字符串和 Markdown 同步不能作为 schema6 写入入口。

原笔记ID、结论ID和证据保持稳定。人工修改保留旧文本与旧证据到 history，新话术不能冒用旧来源，冲突保留待裁决。旧schema仅用 migrate_json_knowledge.py 显式迁移，先预演、备份和逐文比较，再 --apply。sync-markdown 在 schema6 只返回格式迁移说明；Markdown仅用于即时阅读、复制和用户要求的库外导出。

项目根目录命令：
- .wxq-runtime/Scripts/python.exe .codex/skills/wanxiangqi-knowledge/scripts/wxq.py related --topic 阵容名
- .wxq-runtime/Scripts/python.exe .codex/skills/wanxiangqi-knowledge/scripts/wxq.py commit raw/reports/提交.json
- .wxq-runtime/Scripts/python.exe .codex/skills/wanxiangqi-knowledge/scripts/wxq.py validate

## 来源与证据
导入前读[流程](references/workflow.md)、[内容标准](references/editorial-standards.md)。参考中的旧schema写入、Markdown同步和重放字段仅适用于迁移历史；教学、采集和证据规则继续适用，当前写入以知识契约为准。

1. 使用 workspace.register_source 登记规范化链接，保留人工标题、标签和备注；登记不等于沉淀。先恢复事务再读取知识，避免旧快照覆盖人工修改。
2. 查 raw/index.json 及实际全文，已有完整且身份对应的文字稿直接复用，不重复下载或ASR；缺画面只补帧。无有效全文才 prepare，优先中文字幕，不可用才回退 large-v3，不悄悄换小模型。环境缺失才 setup。
3. 逐段读全文，按需核对音频、画面和实体。原始ASR不修改，纠错记录原词、标准词、实体、时间与依据；歧义留候选，不写全局别名。官网新数值与旧视频差异只在附件与raw保留，不冒充纠错。
4. 本地文档按[文档融合](references/local-documents.md)登记文件与段落快照，使用 document 证据，不伪造视频秒数。
5. 写前按实体、核心及主题扫描关联知识，读取候选正文和附件。复用同主题笔记，有证据影响的旧知识与新增知识同批提交；仅加链接不能代替融合。
6. 支撑结论只接受 mechanic、general_strategy、conditional_strategy；单局操作留内部报告。条件和版本分别保留，冲突不强行合并；不编造预算、回合或投入阈值。推导明确 inference 并保存依据。
策略出现冲突时，先核对是否适用于不同的来牌、觉醒进度、资源、血量、对手或成长分配。能够成立的条件方案分别保留，在同一主题下说明“何时选谁、先做什么、收益与代价、何时转向”，同步阵容与棋手摘要；不要只写“两种都可”，也不要拼成一条固定流程。条件须有直接证据或明确标记的有据推导，缺少判断边界就留缺，不能为消解冲突编造条件。策略优先级或运营路线的教学分歧，有可靠适用条件时按条件保留两种方案；没有可靠条件时采用发布时间较新的合格来源方案，替换当前旧推荐，旧文及旧证据保留在历史和审计中，不继续作为当前推荐。日期未确认的来源不据此覆盖，不能为消解冲突编造条件；若较新来源本身身份、含义或适用性不明，明确留缺。用户已裁决的依其裁决落地，不重复索要同一授权。卡牌数值或效果机制的版本冲突按下一段自动查询官网，不能只按视频新旧判断。正文只展示可执行方案；双方原文、证据、条件依据及裁决保存在附件与raw，保留稳定ID和历史，不以supporting_nodes隐藏未裁决的旧结论。

卡牌数值或效果出现版本冲突时，自动查询官网当前对应卡牌与关联效果，核对身份、形态及适用条件，保存实际查询时间、来源地址与原文快照，按文档融合规则登记直接证据。官网能明确解决的，以当前官方机制修订正文并保留旧文与证据历史，无需为同一数值冲突反复询问用户。官网未写明、查询失败或官方资料自身冲突时，明确留缺并记录未解决分歧，不用旧缓存冒充本次查询，不以缺失字段或商店购买费用推断技能实际消耗。

7. 提交后检查正文、证据及引用。仅新增或实际修改转写时才 export-transcripts，保护人工全文。审核、已提交知识和来源阶段均满足后才 finish；文字稿存在不等于沉淀。

网页与CLI保留共享BV处理锁、持久队列、字幕优先、large-v3回退及失败恢复。采集成功只代表待核对，不自动 commit/finish。来源、字幕、ASR、纠错与关键帧存 raw。

## 教学、实体与验收
新建或提质先读[教学表达v4](references/teaching-v4.md)、[内容标准](references/editorial-standards.md)，按需读[覆盖检查](references/teaching-coverage.md)、[主要变阵](references/major-variants.md)。沿用其教学质量要求，旧字段位置按schema6转换。

说明“什么情况下，对哪个单位，做什么，为什么”。核心原理先讲胜利手段；英雄逐名解释职责、机制及因果，涵盖觉醒需求、等级投入、购买策略、上阵时机、出售时机，缺证据留缺。特殊获得渠道与跨阵容供牌按[特殊获取](references/acquisition.md)核查：统一“获得途径”，具体到英雄和卡牌；不纳入梦奇获取渠道（含经兑换券的间接链），兑换券独立渠道保留；无已确认渠道省略字段，供牌英雄用“其他作用”说明目标卡与触发条件。操作说明前置条件、目标与顺序，区分英雄品阶、英雄等级、棋手等级和人口。

棋手通用思路与阵容运营分开，保持章节层级，关联定位独立分支。棋手写作读[player-notes](references/player-notes.md)，旧分支迁移读[player-branches](references/player-branches.md)。不按全文提及猜归属，不默认未分类为共通。正文只写确认的当前机制与适用条件；新内容覆盖旧内容，不显示版本号、补丁过程、旧值对照及版本差异章节，旧文、裁决和冲突保留附件与raw。措辞修订替换同一节点，不追加重复改写。

官网实体保留原始属性、来源和历史，部分失败保留旧值，缺失不猜。schema6 的 sync-entities 输出卡牌正文JSON、附件及轻量索引，不产Markdown。必须阵营按核心及中后期必需成员推导，联合禁用的可玩判断需联合依据。

修改技能或系统时读[验收规范](references/acceptance.md)。检查无损往返、三种复制、结构化编辑、棋手目录、ID/证据/人工历史、并发恢复及创建/导入/同步不再产Markdown。运行Python回归、前端测试与构建、skill-creator quick_validate及wxq validate，检查双入口桌面与窄屏。区分模拟测试与真实来源核对，不虚构ASR或画面验收。

交付正文JSON链接、范围、验证结果及待核实项，迁移报告和恢复备份留raw。
