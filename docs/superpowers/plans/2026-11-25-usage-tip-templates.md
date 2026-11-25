# 万象大赛技巧话术 Implementation Plan

> Use superpowers:executing-plans to verify each task. The scope contract is shared by the Python and TypeScript implementations.

**目标** 将两季使用技巧转成可按赛季和模式筛选的 v0.4 模板包。

**设计** [万象大赛技巧话术生成方案](https://chatgpt.com/space/page_fde86650678481918515219fe562e641)。新组以 `version: ["S1", "S2"]` 和 `mode: ["万象大赛"]` 表示范围，兼容已有字符串与缺省值。

## 范围兼容

- [ ] 在 Python 模板 schema、编审身份、实体快照及发布选择中校验范围。以双季共享组、两条范围互斥的同条件组、旧字符串和其他模式为回归用例。
- [ ] 在 TypeScript 模板文件、编辑器和列表中支持范围数组。用同一组 ID 经过两季过滤、本地文件往返和旧字符串筛选来验证。
- [ ] 让本地构建去重及场景候选池感知范围。显式模式请求使用独立发布投影，验证它不改写默认快照。

## 技巧生成

- [ ] 逐行登记来源，按赛季校对机制与可发生入口。为每个决策确定共享或单季范围，逐项复核条件最小化，并记录缺口。
- [ ] 用一组跑通 Gemini 构思、独立 16 条请求和实际求值，再按组分批生成。每组留至多 6 条候选原句和两轮复核记录。
- [ ] 使用正式编审解析和场景求值核验后写出 `personal/template/技巧话术.json`。复核各赛季与模式、举一反三覆盖、正例、单项反例和缺值。
- [ ] 执行 `.wxq-runtime/Scripts/python.exe deploy/ensure_local.py --build --restart-backend`，在另一次调用验证两个端口及相关 API。用浏览器打开交付文件检查筛选。
