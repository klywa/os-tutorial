# 万象棋战术手册

## 公网部署

双站更新脚本的执行方法见 [docs/depolyment.md](docs/depolyment.md)。网站地址为 `https://klywa.xyz/os-tutorial/`，登录入口为 `/os-tutorial/admin`；Pokilot 地址为 `/pokilot/`。

本地修改代码或笔记后，在项目根目录执行 `./publish-local.ps1` 上传 GitHub，再在服务器执行 `update-sites --os-tutorial` 发布。线上管理员确认的笔记会自动同步 GitHub；本地执行 `./pull-local.ps1` 拉取并按原运行状态重启服务。私有提案不上传 Git；本地编辑和调试不会自行提交。

顶栏可切换管理员和编写员身份；编写员的正文增改删仅暂存为淡红色提案，由管理员逐条确认。服务器安装脚本初始化 `test1 / aa2025` 为编写员，本地默认管理员，支持切换调试。

公网只提供笔记和看板，不创建采集运行时；现有服务器的更新命令见部署文档。本机启动方式见下方。

## 每次更新服务器

更新万象棋时，直接按下面三步操作。

1. 在 **Windows 本机 PowerShell** 发布代码和正式笔记：

   ```powershell
   Set-Location D:\GameProjects\os-tutorial
   powershell -NoProfile -ExecutionPolicy Bypass -File .\publish-local.ps1
   ```

   等到发布成功，再执行第 2 步；如果报错，先保留完整输出。

2. 在 **同一个 PowerShell 窗口** 登录服务器：

   ```powershell
   ssh root@klywa.xyz
   ```

   如果提示密码，输入服务器 root 密码并按回车；输入时不显示字符是正常的。

3. 登录成功后，在 **当前服务器 root SSH 窗口** 执行：

   ```bash
   update-sites --os-tutorial
   ```

   保持窗口打开，等显示“更新结束”且没有报错，再刷新 [万象棋网站](https://klywa.xyz/os-tutorial/)。

每次更新都执行以上三步，无需重新安装更新命令或上传恢复脚本。首次安装及克隆超时的恢复步骤见 [部署文档](docs/depolyment.md)。

## 增加管理员或编写员账号

1. 首次使用新增账号脚本前，先执行上方“每次更新服务器”的三步，将此脚本发布到服务器。

2. 在 **服务器 root SSH 窗口** 执行对应命令。每条命令最后三个参数依次是：角色、用户名、密码。

   新增管理员（将 `admin2` 和 `换成你的密码` 改为需要的用户名、密码）：

   ```bash
   python3 /opt/os-tutorial/current/deploy/add_account.py admin admin2 '换成你的密码'
   ```

   新增编写员（将 `writer2` 和 `换成你的密码` 改为需要的用户名、密码）：

   ```bash
   python3 /opt/os-tutorial/current/deploy/add_account.py annotator writer2 '换成你的密码'
   ```

3. 显示“账号已新增”后，直接在网站右上角点击“登录”，使用新账号登录；无需重启服务或再次更新网站。

管理员可以直接保存和审核提案；编写员的修改需要管理员确认。新增只读浏览者使用同一脚本，将角色设为 `viewer`；浏览者可阅读、搜索、复制及导出 Markdown/JSON，不能修改或提交提案。公网所有内容均须登录，本地继续免登录。脚本自动备份服务器账号配置、保留已有账号；用户名重复会拒绝新增，不覆盖原密码和角色。密码用英文单引号包住；若密码包含单引号，将该字符写成 `'"'"'`。账号保存在服务器 `/etc/os-tutorial/admins.json`，不上传 Git。本地调试继续使用网页中的身份切换。

## UP 主监听自动重试

本地服务保持运行即可；临时故障会自动重试，无需反复点击。重启服务后会接着处理，保留重试次数、冷却时间、下载分片和转写检查点。

- 资料正在保存或临时文件占用：5、15、30、60 秒重试，之后每 60 秒重试。
- 网络中断、页面解析失败、暂时缺少格式：1、5、15、30 分钟重试，之后每 30 分钟重试。
- 工作进程异常退出：1、5、15 分钟重试，之后每 60 分钟重试。
- B站访问限制：按共享冷却时间重试；“立即重试”也不会绕过风控冷却。

监听卡片和视频任务显示“等待自动重试”、次数及下次时间。单个视频失败不影响其他任务。暂停、停用或删除后不会由自动重试恢复；共享视频仍有其他有效处理需求时继续处理。

需要手动处理时，页面会说明原因：登录失效请在“B站连接设置”更新 cookies；视频删除、目录权限不足或材料校验失败请先处理对应问题，再点击重试。程序不会自行升级依赖或改写你提供的 cookies 文件。

查看失败任务的“技术详情”；每次视频处理的独立日志和诊断保存在 `raw/crawler/attempts/视频BV号/`，最新日志仍可在 `raw/crawler/视频BV号.log` 查看。诊断包含阶段、设备、版本和退出码，不包含 cookies 内容。若确认是 GPU 转写崩溃，下一次使用相同 `large-v3` 模型的 CPU 保守配置恢复，不降低模型。

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

## 本地开发服务与恢复

完成首次安装后，在项目根目录执行以下命令，启动或恢复后端与开发前端：

```powershell
.\.wxq-runtime\Scripts\python.exe deploy/ensure_local.py
```

后端入口为 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)，开发前端为 [http://127.0.0.1:5173/](http://127.0.0.1:5173/)。管理器独立于启动终端持续运行，不安装系统服务，也不设置开机启动。它先核对项目身份，遇到其他程序占用端口时报告错误，不结束该程序。

前端修改后加 `--build` 更新 8765 使用的静态页面；后端修改后加 `--restart-backend` 安全重启。完整交付命令为：

```powershell
.\.wxq-runtime\Scripts\python.exe deploy/ensure_local.py --build --restart-backend
```

查看状态使用 `--status`；明确停止两个服务使用 `--stop`。停止后保持暂停，再次执行恢复命令才会启动。正常发布流程暂停后端，完成后按原状态恢复，保留后台任务与检查点。

管理器对意外退出按 1、5、15、60 秒退避恢复，之后每 60 秒重试；稳定运行一分钟后重置退避。`raw/local-services/manager.log` 记录停启原因，`status.json` 保存 PID、最近退出时间、退出码及十六进制退出码，`backend.stdout.log`、`backend.stderr.log`、`frontend.stdout.log`、`frontend.stderr.log` 保存服务输出。接管已有服务时无法追溯其真实退出码，会明确记录为空。`control.json` 是本机控制凭据，不应分享。

模板库顶栏的【帮助】提供当前 JSON 协议和可复制、下载的示例；仓库文档见 [模板库 JSON 协议](docs/template-library.md)。

## 管线生成

在项目根目录用 PowerShell 执行。流程分两步，先从阵容资料初始化 v0.5 空模板库，再把初始库和阵容笔记交给 `template_generate` 工作流补全话术。

### 1. 初始化模板库

| 手头资料 | 初始化输入 | 生成阶段的笔记输入 |
| --- | --- | --- |
| Markdown | UTF-8 阵容笔记 `.md` | 同一份 Markdown 笔记 |
| JSON | 项目的结构化知识笔记 `.json` | 同一份 UTF-8 JSON 笔记会按文本读取，也可使用从知识页导出的 Markdown |
| Excel | 阵容定义表 `.xlsx`，必需的工作表是「阵容英雄配置」，其中需有「打法名称」和「英雄名称」列 | 准备同一打法的 UTF-8 Markdown，保留表中的阵容配置、装备分配、天赋及打法理由。有现成的同阵容笔记也可直接使用 |

「CP天赋打法」工作表仅用于补充特殊打法的天赋。所选打法列在「完全匹配打法」或「新增打法支持」中时，才会补入对应的 CP 天赋。普通阵容只准备「阵容英雄配置」即可，常规天赋直接从该表的天赋列读取。

下面以仓库中的「开备韩信-姜导」JSON 笔记为例。使用 Markdown 时将 `$source` 换为对应的 `.md`。使用 Excel 时，将其换为 `.xlsx`，多阵容表需在初始化命令末尾加 `--lineup '表中的打法名称'`。

```powershell
$python = '.\.wxq-runtime\Scripts\python.exe'
$source = '.\knowledge\lineups\开备韩信-姜导.json'
$initial = '.\personal\template\initial\开备韩信-姜导.json'

& $python -m workflow.template_generation.initialize $source --output $initial
```

命令输出初始库路径、组数及待确认项。检查各组的事件、额外信息键和 `instruction`，此时 `utterances` 均为空。跨赛季卡牌品阶有差异时，可按依据追加 `--season S1` 或 `--season S2`。Markdown 或 JSON 笔记里的装备归属可通过 `--equipment-review '.\装备归属.json'` 补充。该文件是记录数组，每条填写 `equipment`、`hero` 和笔记中的逐字引文 `quote`。重新初始化且内容有变化时，为 `--output` 指定新文件名。

### 2. 配置模型并生成话术

每次运行通过 `--provider` 选择调用方式，通过 `--model` 指定服务实际接受的模型 ID。要固定版本，填写供应商给出的具体版本或快照 ID。API 地址和密钥在启动工作流的终端中通过环境变量设置。

| 调用方式 | 参数 | URL 和凭据 |
| --- | --- | --- |
| OpenAI Chat Completions 或兼容 API | `--provider openai --model '供应商模型ID'` | 用 `OPENAI_BASE_URL` 指定基础 URL，保留供应商要求的路径（例如 `/v1`）。程序自动追加 `/chat/completions`。默认使用 `https://api.openai.com/v1`，远程地址要求 HTTPS，本机回环地址可用 HTTP。服务需要鉴权时设置 `OPENAI_API_KEY`，请求使用 Bearer Token |
| Gemini 原生 API | `--provider gemini --model '供应商模型ID'` | 使用 Google 固定地址的 `v1beta :generateContent`。优先读取 `GEMINI_API_KEY`，其次是 `GOOGLE_API_KEY`。两者均未设置时使用本机已配置的 `gemini-api` CLI |
| Codex CLI | `--provider codex --model default` | 使用 PATH 中已登录的 `codex` CLI。可运行 `codex login status` 检查登录，或将 `default` 换成本机账号支持的模型 ID |
| 本地审编回复 | `--provider local --model editorial --local-replies '.\节点回复.json'` | 从文件读取各节点的已审编 JSON 回复，无需模型 URL 或密钥。回复格式见下方工作流文档 |

OpenAI Responses (`/v1/responses`) 和 Anthropic Messages (`/v1/messages`) 暂未接入。供应商如果同时提供 Chat Completions 兼容入口，可以通过 `--provider openai` 接入。

下面以兼容 API 为例。把基础 URL 和模型 ID 换成供应商提供的值，在当前 PowerShell 窗口设置密钥。接入 Gemini 时，在同一窗口设置 `GEMINI_API_KEY`，将启动参数改为 `--provider gemini --model '供应商模型ID'`。所选服务会收到模型节点使用的笔记和相关参考资料。

```powershell
$env:OPENAI_BASE_URL = 'https://api.openai.com/v1'
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'API Key' -AsSecureString)).Password
$model = '供应商提供的模型ID或版本ID'
$note = $source  # 如果初始化用了 Excel，换成 UTF-8 笔记路径
$runDir = '.\raw\template-runs\开备韩信-姜导-01'

& $python -m workflow.template_generation.run start $note `
  --base-library $initial --run-dir $runDir `
  --output '.\exports\开备韩信-姜导.json' `
  --provider openai --model $model
```

`--base-library` 指向第 1 步的初始库。工作流保留已有组的事件、额外信息键和条件，为空组生成话术，并追加从笔记发现且通过校验的新组。每次 `start` 使用新的空运行目录和新的主库输出路径。可加 `--jobs 1` 降低模型调用并发（默认 4），或加 `--pause-after enrich` 在知识补充后停下来审查。

完成后输出 `"status": "complete"`，并写出 `exports/开备韩信-姜导.json` 主库和 `exports/开备韩信-姜导-detail.json` 溯源文件。在模板库页面将内容来源切到「文件」，授权输出目录并选择主库，打开模板组的「溯源」即可读取同目录的配套文件。

运行记录保存在 `$runDir`。暂停或失败后，查看 `run.json` 和 `nodes/`，处理原因并保留原服务的 URL 与凭据配置，再执行 `& $python -m workflow.template_generation.run resume --run-dir $runDir`。恢复沿用原运行记录中的 provider 和 model。

节点回复格式、暂停修订和溯源字段见 [模板生成工作流](workflow/template_generation/README.md)。

## 使用

Git 只管理代码与正式知识。外部采集、官网同步、运行状态及来源标题、标签和备注均保存在被忽略的本地资料中。请额外备份 `raw/`、`entities/`、`knowledge/cards/`、`personal/` 及 `knowledge/source-registry.meta.json`、`knowledge/document-sources.meta.json`；只克隆 Git 仓库无法恢复这些数据。

启动、后台任务和网页官网检查不会自动改写正式笔记。需要把官网资料应用到棋手笔记时，明确执行 `.wxq-runtime/Scripts/python.exe .codex/skills/wanxiangqi-knowledge/scripts/wxq.py sync-entities --apply-notes`（macOS 使用虚拟环境中的 `bin/python`）。默认 `sync-entities` 只更新本地缓存。外网阵容名称留在本地快照中，正式搜索别名通过笔记编辑保存。

使用上述 `start.ps1` / `start.zsh` 安装入口时，浏览器自动打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)，后端同时提供构建后的前端、API、采集与定时任务。该前台入口需保持终端打开，按 `Ctrl+C` 停止。需要脱离终端持续运行并同时提供 5173 开发前端时，安装完成后使用前文的 `deploy/ensure_local.py`；由 `--stop` 安全停止，关闭网页不会停止后台。

首次安装需联网，主题模型约 2GB；语音转写首次使用时还会下载 large-v3 模型。Mac 转写使用 CPU，耗时取决于硬件。后续启动复用依赖，仍会构建前端。

可选参数：

| 用途 | PowerShell | zsh |
| --- | --- | --- |
| 更换端口 | `-Port 8766` | `--port 8766` |
| 不自动打开浏览器 | `-NoBrowser` | `--no-browser` |
| 暂不安装主题模型 | `-SkipTopicModel` | `--skip-topic-model` |

跳过主题模型不影响阅读、编辑、采集和转写，但自动主题识别需安装模型后才能使用。端口被占用时，关闭旧服务或更换端口。首次依赖下载失败可直接重跑脚本。

macOS 的安装命令依据 [Python](https://formulae.brew.sh/formula/python@3.12)、[Node.js](https://formulae.brew.sh/formula/node@24) 和 [llama.cpp](https://formulae.brew.sh/formula/llama.cpp) 的 Homebrew 配方。macOS 启动入口已补齐，尚未在真实 Mac 上验收。
