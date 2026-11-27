# 万象棋模板生成工作流

在项目根目录运行下面的 PowerShell 命令。输入文件使用 UTF-8 编码，可以是 Markdown 或其他纯文本。工作流默认自动跑完，旧 `wanxiangqi-template` skill 可以继续独立使用。

```powershell
$python = '.wxq-runtime/Scripts/python.exe'
& $python -m workflow.template_generation.run start .\攻略.md --run-dir .\raw\template-runs\第一稿 --output .\exports\打法模板.json --provider codex --model default
```

运行目录保存完整模型调用、校验、修订和恢复记录。输出目录会得到 `打法模板.json` 和新版 `打法模板-detail.json`。前者是主库，后者按组和句 ID 指向五阶段审阅内容及实际输入 prompt。

## 补全已有库并生成新组

`--base-library` 读取已有 v0.4 或 v0.5 文件并保存输入快照。v0.4 规则在输出时迁移为 v0.5。每个 `utterances: []` 的组需要非空 `instruction`。工作流逐组准备知识、扩充证据、补充解释角度并生成话术。补全已有组时沿用事件、额外信息键和迁移后的条件。新组分别生成键和表达式，发布前执行 v0.5 校验。带话术的已有组可省略 `instruction`。

同次运行也从指定笔记发现新组。事件、额外信息键和有效条件相同的组保留已有版本，其他新组通过整库校验后追加。每个输入空组补齐后才发布。空组的分支 ID 可从 `nodes/split.json` 查到，后续支持 `revise` 和 `resume`。初始化空库使用 [initialize-template](../../.codex/skills/initialize-template/SKILL.md)。

带已有库的运行按段登记发现结果。`identify` 的 `coverage` 数组逐段记录 `segment_id`、对应的 `point_ids` 及 `reason`。段落没有新增知识点时说明复用或跳过原因。溯源文件的 `coverage` 可从段落查到知识点、事件和成品组，也会列出被排除的入口和未通过筛选的条件。

已有基础解释时，细分条件可以用 `base_group_id` 引用同事件同键的基础组，细分优先级须更高。用 `fallback: true` 标记动作相同、额外局势事实不成立或缺失的用例。合库校验确保正例播细分组，回退例仍能播基础组。

```powershell
& $python -m workflow.template_generation.run start .\攻略.md `
  --base-library .\初始模板.json --run-dir .\raw\template-runs\补全 `
  --output .\exports\打法模板.json --provider codex --model default
```

## 人工话术样例

直接在工作流自己的 [event-examples.json](references/event-examples.json) 按正式事件增删样例。每条只填写 `condition` 和 `utterance`。`condition` 用自然语言交代动作和必要前提，`utterance` 保留人工原句。首拍、二拍和第三次拍卖分别使用各自的正式事件名。拍卖样例的原句须写明有依据的建议预算。

```powershell
& $python -m workflow.template_generation.event_examples --check
```

话术节点按本次实际生成的正式事件加载样例。普通生成与初始库补全共用该数据。原始 prompt 溯源会显示本次加载的样例。暂无样例的事件继续使用原有写作策略和骨架。

## 模型配置

`--provider` 和 `--model` 设置默认通道。用 `--node-config <JSON 文件>` 可为指定的模型节点覆盖通道和模型，并为 Chat Completions 兼容服务单独指定地址和密钥环境变量名。恢复运行时沿用 `run.json` 中的节点配置。所选服务会收到该节点实际使用的文字稿、卡面与规则。配置示例见[项目 README](../../README.md#按节点接入自部署模型)。

- `--provider codex --model default` 使用 Codex CLI 和已登录的默认模型，也可提供本机账户支持的 GPT 模型名。可用 `codex login status` 检查登录状态。脚本在临时空目录中发送固定 prompt，使用只读沙箱、关闭 shell、应用与插件。
- `--provider gemini --model gemini-flash-latest` 优先使用环境变量 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`。没有环境变量时，调用本机已配置的 `gemini-api` CLI。
- `--provider openai --model <模型名>` 使用 Chat Completions 兼容接口。配置 `OPENAI_BASE_URL`（包含供应商要求的路径，如 `/v1`）和 `OPENAI_API_KEY`。本地回环模型服务可使用 HTTP。长稿和事件规则需要模型具备足够的上下文，且能按节点约定输出 JSON。
- `--provider local --model editorial --local-replies <JSON>` 从本地文件读取已审编的节点回复。文件是按 `identify`、`enrich:<point_id>`、`events:<point_id>`、`conditions:<point_id>`、`phrases:<point_id>` 索引的 JSON 对象，值使用对应节点的回复格式。话术节点直接提交 6 条审读后的候选。该模式在本地记录并校验各阶段结果，不调用模型服务。

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

事件框架先声明独立成立的基础收益及其最小字段。条件节点须为这类事件交付基础组，另有细分收益时由较高优先级的细分组播报。无法建组的事件记录可核对的排除依据。模型提交表达式和用例后，由本地程序求值。基础覆盖校验失败时，该分支会带着错误反馈重试一次。

### 审查每个模型节点

打开下面链接可查看预先维护的 prompt 与该节点的 JSON 输出格式。运行目录中另存每次实际发送的 prompt，包含当时装入的原文、卡面或事件标准。

1. **[知识点识别](prompts/identify.md)** 从整篇文档生成 `points`。同段原文涉及多个独立问题时，按[正式知识类型](references/knowledge-types.json)拆为多个 ID，各保留类型、前提和相关原文。需要时用 `related_ids` 建立关联。
2. **代码分流**输出分支清单，逐项记录知识点、原文引用和识别版本。每个分支在汇总前独立处理；后续需要其他知识时按 `related_ids` 引用。
3. **[知识补充](prompts/enrich.md)** 程序沿用识别阶段的类型，只注入该类型的补充边界。正文围绕当前问题写结论、机制、收益和必要前提，并将原类型一路传给事件和溯源。卡面引文按赛季和卡牌 ID 验证，证据不足记入 `gaps`。
4. **[事件框架生成](prompts/events.md)** 保留完整知识，添加所有相关正式事件及各事件预期说的内容。[事件资料](references/events.json)保存当前工作簿 D/E 列、骨架与策略。
5. **[条件生成](prompts/conditions.md)** 保留知识和事件，添加按事件排列的生效条件、必要性、限定范围、预期内容和措辞要求。运行记录保存求值用例及排除依据。
6. **[话术生成](prompts/phrases.md)** 保留补充知识、事件和条件，添加写作依据和最终六条合格话术。候选不足时重试一次，仍不足的组留在运行记录待审。
7. **代码汇总**重新校验各分支的条件和入选话术，检查实际可播性，建立组 ID、句 ID、知识点、事件、条件与采用版本的索引。主库和 detail 配对发布；已有不同内容的同名文件会报告冲突，可为新运行指定另一输出文件名。

## 在前端查看溯源

进入「模板库」，将内容来源切到「文件」，授权主库所在目录并选择主库。打开模板组的「溯源」时，页面自动读取同目录的同名 `-detail.json`。可切换话术查看五个阶段，输入 prompt 默认折叠。溯源文件采用 `schema_version: 2`。
