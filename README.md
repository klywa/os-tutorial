# 万象棋战术手册

## 公网部署

双站部署、管理员配置、每小时自动更新及恢复步骤见 [docs/depolyment.md](docs/depolyment.md)。网站地址为 `https://klywa.xyz/os-tutorial/`，管理员入口为 `/os-tutorial/admin`；Pokilot 地址为 `/pokilot/`。

本机停止服务并拉取最新笔记后，运行 `.wxq-runtime/Scripts/python.exe frontend/website_data.py export` 导出公开实体、卡牌、图片和看板快照，再执行同脚本的 `validate`，提交 `website-data/` 与正式笔记。发布不会爬取内容；已发布的人工匹配不会被导出覆盖，后续本机和网站共用 Git 管理的匹配文件。

公网启动使用 `python3 frontend/server.py --public`，前置准备步骤见部署文档；只提供笔记和看板，不创建采集运行时。本机原有启动方式保持不变。

## 在另一台电脑准备项目

复制整个项目，**包含隐藏目录 `.codex`，以及 `knowledge/`、`entities/`、`raw/`**。其中部分数据被 Git 忽略，只克隆仓库不能带走完整资料。迁移前先停止旧电脑上的服务，避免复制到写入一半的数据库。

不要复制 `.wxq-runtime/`、`frontend/node_modules/` 和 `frontend/dist/`；脚本会在新电脑重建。若已复制虚拟环境，先将 `.wxq-runtime` 移到项目目录之外再启动。原电脑的 cookies 路径等本机设置需在新电脑重新配置。

## macOS

先安装 [Homebrew](https://brew.sh/)，然后在项目根目录的终端运行：

```zsh
zsh ./start.zsh
```

脚本通过 Homebrew 补装 Python 3.12、Node.js 24（未安装 Node 时）及 llama.cpp，再自动创建 Python 虚拟环境、安装依赖、下载主题模型、构建页面并启动整个项目。已有过旧 Node.js 时请先执行 `brew install node@24`，再重试脚本。

## Windows

先安装 [Python 3.12](https://www.python.org/downloads/)（勾选加入 PATH）和 [Node.js 24](https://nodejs.org/)，然后在项目根目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

脚本自动创建 `.wxq-runtime`、安装 Python 和前端依赖、下载主题模型、构建并启动。无需手动激活 Python 环境。

## 使用

Git 只管理代码与正式知识。外部采集、官网同步、运行状态及来源标题、标签和备注均保存在被忽略的本地资料中。请额外备份 `raw/`、`entities/`、`knowledge/cards/`、`personal/` 及 `knowledge/source-registry.meta.json`、`knowledge/document-sources.meta.json`；只克隆 Git 仓库无法恢复这些数据。

启动、后台任务和网页官网检查不会自动改写正式笔记。需要把官网资料应用到棋手笔记时，明确执行 `.wxq-runtime/Scripts/python.exe .codex/skills/wanxiangqi-knowledge/scripts/wxq.py sync-entities --apply-notes`（macOS 使用虚拟环境中的 `bin/python`）。默认 `sync-entities` 只更新本地缓存。外网阵容名称留在本地快照中，正式搜索别名通过笔记编辑保存。

浏览器自动打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。**一个服务同时提供前端、后台 API、采集与定时任务**，不需要另开 `npm run dev` 或后台进程。保持终端打开，按 `Ctrl+C` 停止；关闭网页不会停止后台。

首次安装需联网，主题模型约 2GB；语音转写首次使用时还会下载 large-v3 模型。Mac 转写使用 CPU，耗时取决于硬件。后续启动复用依赖，仍会构建前端。

可选参数：

| 用途 | PowerShell | zsh |
| --- | --- | --- |
| 更换端口 | `-Port 8766` | `--port 8766` |
| 不自动打开浏览器 | `-NoBrowser` | `--no-browser` |
| 暂不安装主题模型 | `-SkipTopicModel` | `--skip-topic-model` |

跳过主题模型不影响阅读、编辑、采集和转写，但自动主题识别需安装模型后才能使用。端口被占用时，关闭旧服务或更换端口。首次依赖下载失败可直接重跑脚本。

macOS 的安装命令依据 [Python](https://formulae.brew.sh/formula/python@3.12)、[Node.js](https://formulae.brew.sh/formula/node@24) 和 [llama.cpp](https://formulae.brew.sh/formula/llama.cpp) 的 Homebrew 配方。macOS 启动入口已补齐，尚未在真实 Mac 上验收。
