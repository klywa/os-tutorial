# 万象棋战术手册

在项目根目录运行：

```powershell
powershell -NoProfile -File frontend/start.ps1
```

脚本安装锁定依赖、构建前端，并在 http://127.0.0.1:8765 启动本地服务。首次需可用 Node.js/npm 及项目 `.wxq-runtime`。终端 Ctrl+C 停止服务。`-NoBrowser` 不打开浏览器；`-Port 8766` 更改端口。

开发：先运行 `..\.wxq-runtime\Scripts\python.exe server.py`，另开终端在此目录运行 `npm run dev`。生产使用同源页面，开发端口 5173 通过 Vite 代理 API。

笔记编辑会同步索引、中文 Markdown 和阵容 JSON。人工修订保留，技能导入冲突显示待核对。meta 缺失是待确认，禁用条件缺失不会被当作可玩。来源登记不启动下载或 ASR，继续通过技能整理。

验证：`npm test`、`npm run build`；项目根目录运行 `.wxq-runtime\Scripts\python.exe -m unittest discover -s .codex/skills/wanxiangqi-knowledge/tests` 与 `wxq.py validate`。
