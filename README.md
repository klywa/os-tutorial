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

管理员可以直接保存和审核提案；编写员的修改需要管理员确认。脚本自动备份服务器账号配置、保留已有账号；用户名重复会拒绝新增，不覆盖原密码和角色。密码用英文单引号包住；若密码包含单引号，将该字符写成 `'"'"'`。账号保存在服务器 `/etc/os-tutorial/admins.json`，不上传 Git。本地调试继续使用网页中的身份切换。

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
