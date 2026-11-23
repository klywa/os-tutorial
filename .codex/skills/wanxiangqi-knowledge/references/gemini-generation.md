# 用 Gemini 撰写待审正文

每篇笔记或每组模板单独使用一个请求文件和状态文件，放在 Git 忽略的 `raw/reports/`。先完成本技能的事实核验、证据选择和条件推导。只提供撰写该篇内容所需的事实、限定条件、可复查的来源定位与摘录、需保留的原文及写作要求。按主题或条目组织它们，不传入整个仓库、账号信息或凭据。

请求由 `context` 对象和 `fields` 对象组成。`context` 组织材料，`fields` 为每项待撰写的内容取一个稳定键。`text` 表示一段文字，`lines` 表示一组独立句子。笔记优先用目标节点 ID 作字段键，新节点在本地分配稳定 ID。模板使用 `utterances`（`lines`）及本次需要撰写的说明字段（`text`）。

```json
{
  "context": {
    "任务": "写出这个决策适用的条件和当下收益",
    "已核实事实": ["此效果限前排"],
    "来源定位": ["官方说明的触发段"],
    "须保留": ["仅适用前排"]
  },
  "fields": {"段落节点ID": "text"}
}
```

在项目根目录运行，其他环境可使用自己的 Python 3。

```powershell
.wxq-runtime/Scripts/python.exe .codex/skills/wanxiangqi-knowledge/scripts/gemini_generate.py raw/reports/本次请求.json --state raw/reports/本次生成状态.json
```

`status=ok` 时从 `content` 读取待审稿。保留请求和状态文件，用本技能的原有清单核对证据、结构和表达。发现问题时，把具体审核意见写入 UTF-8 文件，用原命令加 `--review-feedback raw/reports/本次审核意见.txt`。助手脚本会把审核意见和上一稿一起送回 Gemini，并把这次退回计入同一个三次失败上限。调用错误、超时和无效输出也计入该上限。返回 `status=fallback` 后由默认模型完成待写部分并照常审核。缺少 CLI 会直接回退，现有 CLI 认证沿用运行环境配置。

模板的 Gemini 请求只包含话术、前置思考、来源及本次确需改写的旧版说明。实际复核和求值由默认模型完成，再由默认模型根据真实结果撰写 `explanation_after`，逐项标明通过或待验证。生成脚本只输出待审文字，由技能按现有授权流程组装和提交。明确要求全批由 Gemini 生成时，遇到回退结果就保留已完成稿和失败记录，暂缓提交整批。
