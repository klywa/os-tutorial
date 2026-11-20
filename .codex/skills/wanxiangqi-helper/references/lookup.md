# 查询万象棋知识

以包含 `knowledge/index.meta.json` 的目录为项目根。服务在 `http://127.0.0.1:8765`，使用 GET。

| 查询 | 入口 |
|---|---|
| 找笔记 | `/api/notes/search?q=...`，对中文关键词做 URL 编码。按空格分词且要求全部命中，整句没命中就用短词，读返回的笔记 ID。 |
| 读正文 | `/api/notes/{id}/reading` 读阅读正文，`/api/notes/{id}` 读结构化正文和公开证据。棋手分支核对标题和绑定身份。 |
| 查卡牌 | `/api/cards` 找候选 ID，`/api/cards/{id}` 查详情。按 ID、类别、别名、阵营、品阶和觉醒区分形态。 |

服务不可用时，只读有权访问的正式文件。用 `knowledge/index.meta.json` 或 `knowledge/cards/index.meta.json` 的 ID 和路径定位，正文读 JSON 的 nodes，身份和证据读同名 .meta.json。需要官方实体字段时查 `entities/` 对应类别。历史、备份、草稿和未审转写不能替代当前正文。问答期间不运行启动、恢复、采集、同步或写入命令。

常用笔记 ID 为 `game-basics`（基础知识）、`mechanics-rules`（游戏机制）、`game-decisions`（游戏决策逻辑）、`game-macro`（游戏大局观）、`game-common-sense`（游戏打法常识）和 `common-tips`（常用技巧）。发现缺项时说明待核实条目，留给维护技能处理。
