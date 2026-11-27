---
name: initialize-template
description: 使用 initialize_template 从王者万象棋知识笔记 JSON、Markdown 笔记或 XLSX 阵容定义表初始化空话术模板库。用户要求初始化阵容模板、生成空组或为 template_generate 准备已有库时使用。
---

# 初始化万象棋模板库

从用户指定的阵容资料生成 v0.5 模板库。先确定事件和额外信息键，再写阵容条件。所有组的 `utterances` 为 `[]`。随后用 `template_generate` 读取初始库和用户指定的笔记生成话术。

## 初始化

在仓库根目录执行。

```powershell
& .wxq-runtime/Scripts/python.exe -m workflow.template_generation.initialize `
  'knowledge/lineups/开备韩信-姜导.json' `
  --output 'personal/template/initial/开备韩信-姜导.json'
```

- 知识 JSON 直接解析结构化阵容组成、核心英雄和章节条目。Markdown 使用知识笔记解析器识别阵容组成、装备、天赋和效果牌。阵容表读取「阵容英雄配置」和「CP天赋打法」，多阵容表用 `--lineup` 指定打法名。
- 程序用本地卡牌资料核实正式名称和品阶。跨赛季品阶有差异时，用 `--season S1` 或 `--season S2` 指定有依据的赛季。
- 跟进命令输出中的待确认项。装备适用英雄写在自然语言中时，核对装备分配、替代关系与实际穿戴者。需要补充已确认的归属时，传入 `--equipment-review`，JSON 为记录列表，每条包含 `equipment`、`hero` 和来自同一份笔记的逐字 `quote`。仍无法确认的条目随结果列出。
- 复核所有空组的事件、额外信息键和具名 `instruction`。购买和选择覆盖每位明确列入阵容的成员，2 至 3 阶另有首拍，4 至 5 阶另有二拍。装备按每个可核实的装备与适配英雄组合生成铸造、穿戴、转移三组。天赋只有选择，效果牌覆盖购买和选择。条件统一为 `我方.阵容名称 == "正式阵容名"`，已经写入具体键的名称不要在条件里再比较。
- 拍卖类事件的 `instruction` 须包含「若有充足信息，应补充拍卖预算」。有依据的预算用建议预期表达，避免给出硬性出价。

输出检查通过后，报告初始库路径、组数和仍待确认的条目。需要生成成品时，向 `template_generate` 传入 `--base-library` 和用户指定的笔记。
