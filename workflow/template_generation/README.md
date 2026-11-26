# 万象棋模板生成工作流

在项目根目录运行下面的 PowerShell 命令。输入文件使用 UTF-8 编码，可以是 Markdown 或其他纯文本。工作流默认自动跑完，旧 `wanxiangqi-template` skill 可以继续独立使用。

```powershell
$python = '.wxq-runtime/Scripts/python.exe'
& $python -m workflow.template_generation.run start .\攻略.md --run-dir .\raw\template-runs\第一稿 --output .\exports\打法模板.json --provider codex --model default
```

运行目录保存过程记录。输出目录会得到 `打法模板.json` 和 `打法模板-detail.json`。前者可在模板库中打开，后者保存审查所需的原文、卡面依据、各节点输入输出、实际 prompt 和修订记录。

## 模型配置

每次运行只调用启动时选定的模型通道。所选服务会收到该节点实际使用的文字稿、卡面与规则；不会自动切换到其他服务。只在本机处理资料时，可把兼容接口指向本地模型。

- `--provider codex --model default` 使用 Codex CLI 和已登录的默认模型，也可提供本机账户支持的 GPT 模型名。可用 `codex login status` 检查登录状态。脚本在临时空目录中发送固定 prompt，使用只读沙箱、关闭 shell、应用与插件。
- `--provider gemini --model gemini-flash-latest` 优先使用环境变量 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`。没有环境变量时，调用本机已配置的 `gemini-api` CLI。
- `--provider openai --model <模型名>` 使用 Chat Completions 兼容接口。配置 `OPENAI_BASE_URL`（包含供应商要求的路径，如 `/v1`）和 `OPENAI_API_KEY`。本地回环模型服务可使用 HTTP。长稿和事件规则需要模型具备足够的上下文，且能按节点约定输出 JSON。

## 暂停、修订与恢复

例如，希望先审查知识补充结果，可以在启动命令最后添加 `--pause-after enrich`。打开运行目录查看各知识点的节点结果，复制要修改的 JSON 作为修订文件。用识别结果中的知识点 ID 提交修订：

```powershell
& $python -m workflow.template_generation.run revise --run-dir .\raw\template-runs\第一稿 --stage enrich --point P1 --file .\修订.json
& $python -m workflow.template_generation.run resume --run-dir .\raw\template-runs\第一稿
```

人工修订应保留节点 JSON 结构。原始模型回复随调用保存，后续节点引用实际采用的版本。失败时先查看失败节点和校验原因，再恢复同次运行。

## 节点与交接

| 节点 | 输入和职责 | 输出与审查重点 |
| --- | --- | --- |
| identify · 知识点识别 | 读取原文，找出知识类型、打法原则、相关知识、适用范围 | 知识点列表，核对原文引文和棋手、阵容、局面前提 |
| split · 代码分流 | 按知识点建立独立分支 | 知识点、原文与分支之间的对应关系 |
| enrich · 知识补充 | 回查原文与卡牌资料，解释知识为什么成立 | 单独保存补充后的知识、依据、必要条件和证据缺口 |
| events · 事件框架 | 按七类映射和工作簿「事件」D/E 列选择决策入口 | 正式事件、解释对象、采用或排除理由 |
| conditions · 条件生成 | 按事件载入骨架，从通用到具体审查局面 | 条件表达式，逐项检查正例、反例、缺值 |
| phrases · 话术生成 | 按条件与事件策略编写、筛选候选话术 | 句子必须解释该动作对当前局面的实际收益 |
| assemble · 代码汇总 | 校验模板格式并连接各分支记录 | 主库及同名 detail，可从组或句查回各阶段 |

### 审查每个模型节点

打开下面链接可查看预先维护的 prompt 与该节点的 JSON 输出格式。运行目录中另存每次实际发送的 prompt，包含当时装入的原文、卡面或事件标准。

1. **[知识点识别](prompts/identify.md)** 从整篇文档生成 `points`。每项记录做法、类型、整体打法、核心原则、适用范围、前提、关联知识点和原文出处。审查时检查引文能否定位到原文，以及仅在某套打法成立的结论是否写明了范围。
2. **代码分流**输出分支清单，逐项记录知识点、原文引用和识别版本。每个分支在汇总前独立处理；后续需要其他知识时按 `related_ids` 引用。
3. **[知识补充](prompts/enrich.md)** 输入完整原文、分流知识、关联知识和卡牌资料，另存 `knowledge`、`cause`、`benefit`、`prerequisites` 及证据。核对收益依赖的是阵容方向、场上英雄、手牌英雄、棋手、天赋、装备、对手、时机还是多项事实。卡面引文按赛季和卡牌 ID 验证，证据不足记入 `gaps`。
4. **[事件框架生成](prompts/events.md)** 把补充后的知识映射为正式事件，输出 `events` 与 `excluded`。七类映射分别覆盖英雄、天赋、装备、效果牌、棋手技能、运营节奏和技巧对策。[事件资料](references/events.json)按正式事件保存当前工作簿 D/E 列、骨架与策略。
5. **[条件生成](prompts/conditions.md)** 输入知识与事件组，输出 `conditions`、求值用例与排除原因。沿当前事件骨架从通用到具体遍历，移除不影响选择的限制。对于“场上已有搭档且手里有后续英雄”的理由，分别撤掉场上搭档或手牌英雄应使该理由失效。
6. **[话术生成](prompts/phrases.md)** 输入知识、事件、经校验的条件，输出每组候选句、逐句审读和选用 ID。按事件载入规则，并遵循[话术策略](references/writing-strategy.md)。每种可命中的局面都要能支持该句话提到的对象、时机与收益。
7. **代码汇总**重新校验各分支的条件和入选话术，检查实际可播性，建立组 ID、句 ID、知识点、事件、条件与采用版本的索引。主库和 detail 配对发布；已有不同内容的同名文件会报告冲突，可为新运行指定另一输出文件名。

## 在前端查看溯源

进入「模板库」，将内容来源切到「文件」，在打开文件时同时选择主库和同名 detail。打开模板组的「溯源」后可切换话术，逐个展开节点。模型 prompt 默认折叠。已单独打开主库时也可以在浮窗里补选 detail。
