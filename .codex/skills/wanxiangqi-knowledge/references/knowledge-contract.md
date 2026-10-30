# 知识契约 schema6

阵容附件统一包含 `aliases: string[]`，一项一个完整别名，不新增 `alias` 字段。Top-50 当前有效人工匹配和组成唯一自动匹配，把网站名称去首尾空白后追加到对应棋手笔记，保留旧别名并去重。名称只用于检索，不用于自动匹配。每日同步和保存/恢复匹配复用共享知识锁、增量事务和库外版本历史；别名同步与榜单发布共用写锁，失败不报告同步成功。解除或改绑保留历史别名，正文、证据和人工保护不因此改变。

## 文件
正文为 knowledge/players/棋手.json、knowledge/lineups/阵容-棋手.json、knowledge/other/名称.json，同名 .meta.json 保存身份、证据、人工保护、历史、冲突和关联。棋手及阵容必须绑定有效 player_id，棋手笔记唯一，阵容按棋手独立。

index.meta.json 的 schema_version=6，notes 仅包含 id/type/title/path/player_id/revision，aliases 保存旧 note/branch 到新ID的映射，不复制全文。来源登记为source-registry.meta.json，本地文档为document-sources.meta.json；旧内部路径兼容读取，不生成旧文件。

## 正文节点
正文包含 schema_version=6、leading、nodes。nodes 按原顺序排列，均有稳定id：
- heading：level=1..6、title、space、separator；唯一一级标题与附件title一致。
- entry：key、show_key、value、separator，可有prefix和key_suffix保留原格式。

无标题段落固定key=正文、show_key=false，多段以不同ID区分。英雄整段一个条目，五个行动字段及有据的可选获得途径、其他作用保留于value。列表、表格、代码、链接等在对应value保留Markdown语法，不能把全文当唯一字符串。

棋手笔记的适用打法与适用技巧使用命名entry，具体格式见[player-notes](player-notes.md#适用打法与技巧的段落格式)。阵容九项“标题：内容”保存在value内，不加【】等装饰括号；每个阵容、每条技巧各占一段，不使用换行或子列表。

semantics保存组成、路线、禁用和替换条件等知识，重复文本用 {"$text":"节点ID"} 引用；supporting_nodes保存已审核但不重复显示的支撑知识；adaptations保存棋手适配知识。当前知识不在附件保留第二份可编辑文本。

json_document.parse(text)与markdown(body)无损往返；导出格式与剪贴板格式分开。整篇复制/导出包含标题；二/三级标题复制至下个同级或更高标题，仅一个普通文字段落且无子标题时折为“章节标题：正文”，否则保留层级。条目复制“key：value”，隐藏条目采用最近章节标题，无章节用笔记标题。所有复制key无加粗星号，value有效Markdown保留。显示标签不带装饰方括号，clean_labels在编辑和commit入口修复跨key/value拆分残留。

## 附件与事务
claim_annotations保留原结论ID、kind、section、condition、version、inference、evidence，以text_ref关联正文/支撑节点，附件不保存当前结论text。证据使用真实视频source/start/end/frame或document/source/paragraph_start/paragraph_end，沿用文件和来源校验。

人工编辑将旧文及旧证据保留history，不为新话术沿用旧来源。node_annotations记录人工节点，后续导入不能自动覆盖，冲突进入conflicts。

revision由正文与附件共同计算，body_sha256校验配对。raw/knowledge/pending-json-save.json先发布事务再写正文/附件/索引，恢复完成后移除。delta=true的增量事务仅包含变更笔记、完整轻量索引和版本快照；读者通过统一存储接口将变更覆盖到未变笔记上，不能把records数组当全库。旧完整事务仍兼容恢复。共享写锁和恢复文件都在raw。

## 接口

正文保存统一产生库外历史快照；历史快照和批注均在已忽略的 raw/knowledge 下，不生成知识 Markdown。GET notes/ID/versions 列出可恢复完整版本，GET notes/ID/versions/版本ID 读取完整正文与证据附件。GET annotations 支持 note_id、status 查询；POST annotations 新建，PUT annotations/ID 修改或重新打开，DELETE annotations/ID 软删除，POST annotations/ID/complete 校验并结项。批注使用独立 revision，正文仍使用原有 revision。
workspace.notes(root)提供兼容读视图及document；磁盘同名附件提供提交信息，兼容claims不是写入契约。GET notes/ID/reading返回document、markdown与含节点的sections，GET notes返回独立笔记。

PUT notes/ID接受revision、document及可选aliases；旧sections/claims在schema6拒绝，失败保留草稿。POST notes接受type/title/aliases/request_id，player/lineup必须传player_id，阵容自动补棋手后缀，重复请求幂等。

CLI commit文件为 {"notes":[{"body":正文对象,"metadata":附件对象}]}。已有记录必须带最新metadata.revision，保留历史、ID、人工保护及证据。人工节点变化进入conflicts，不静默覆盖。新增结论需有效证据，不将单局操作包装成通用知识。

新增或改义的非空条目必须由 claim_annotations.text_ref 直接关联该节点及有效来源，不能仅在其他支撑节点挂证据。既有原样保留的留缺结论可以没有证据；不能据此给新结论伪造来源。网页人工编辑由服务记录 origin=manual，导入不得伪造人工标记。删除条目时，旧正文和证据留在 history，退出当前阅读的结论进入 retired_claim_annotations 并记录对应历史位置。

## 迁移
旧schema1–5仅用migrate_json_knowledge.py读取，默认预演，--apply才写入。先恢复旧事务、核对外部修改、库外备份及逐文无损比较；编号/总览有独有有效结论时先归并。reviews/replays当前结论与正式知识对比，历史与报告移raw，不恢复已排除内容。

schema6 的sync-markdown仅返回说明。创建、提交、恢复、卡牌同步和启动不能生成知识Markdown、编号笔记、总览或replays。用户导出Markdown放knowledge之外。
