# 两站日常更新：执行脚本

以下适用于已经部署好的网站。本地双向同步脚本只操作万象棋；服务器 `update-sites` 可以更新万象棋和 Pokilot。Pokilot 沿用服务器当前部署分支（例如 `master`），更新前需将代码上传到 GitHub 的同名分支；脚本不会切换分支。

## 首次安装服务器命令（只做一次）

先在 **Windows 本机 PowerShell** 上传本次代码，再上传安装脚本：

```powershell
Set-Location D:\GameProjects\os-tutorial
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish-local.ps1
scp .\deploy\install-update-sites.sh root@klywa.xyz:/tmp/install-update-sites.sh
```

然后在 **服务器 SSH 窗口** 执行：

```bash
sudo bash /tmp/install-update-sites.sh
```

等显示“安装完成”，以后直接使用下面的日常命令。

首次升级若报 `Address already in use`：在本机重新执行本节的发布、上传安装脚本两步。确认成功后，在服务器执行下面这一条命令。万象棋会暂停访问直到安装完成，Pokilot 不受影响；安装失败会尝试恢复网站服务并保留失败提示。

```bash
bash /tmp/install-update-sites.sh --recover-port
```

## 如果更新报“clone 超过 180 秒”（恢复一次即可）

先在 **Windows 本机 PowerShell** 逐行执行。第一条发布命令成功后，再执行两条上传命令；上传时提示输入密码，填写服务器 root 的 SSH 密码：

```powershell
Set-Location D:\GameProjects\os-tutorial
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish-local.ps1
scp .\deploy\release.py root@klywa.xyz:/tmp/os-tutorial-release.py
scp .\deploy\recover-os-tutorial-update.sh root@klywa.xyz:/tmp/recover-os-tutorial-update.sh
```

然后在 **服务器 root SSH 窗口** 执行：

```bash
bash /tmp/recover-os-tutorial-update.sh
```

保持窗口打开，等到显示“恢复完成”，再刷新网站。下载与构建期间旧网站继续运行。脚本若提示更新正在运行，等待原任务结束后再执行同一命令。若报 Git 连接错误或再次超时，保留完整输出。

恢复成功后，以后仍执行 `update-sites --os-tutorial`，不需要再次上传恢复脚本。

## 1. 本地代码、正式笔记 → GitHub

在 **Windows 本机 PowerShell** 执行：

```powershell
Set-Location D:\GameProjects\os-tutorial
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish-local.ps1
```

完成后再更新服务器。本机原来运行的服务会按需自动停止并恢复；原来没运行则保持关闭。

发布成功或失败后都会恢复原来运行的服务；恢复后检查 API、首页及前端 JS/CSS，连续稳定 5 秒才报告完成。每次启动最长等待 120 秒，进程退出时最多自动重试 3 次；仍在启动的进程不会重复启动。后台服务独立于发布窗口，关闭发布窗口后仍可访问 `http://127.0.0.1:8765/`。若恢复失败，输出会分别保留发布错误与恢复错误，并显示进程信息和日志路径。

## 2. GitHub → 线上网站

在 **服务器 root SSH 窗口** 更新两站：

```bash
update-sites
```

只更新万象棋：

```bash
update-sites --os-tutorial
```

只更新 Pokilot：

```bash
update-sites --pokilot
```

若旧版报“Pokilot 分支必须是 app”，先在本机运行发布脚本上传修复，再在服务器依次执行：

```bash
update-sites --os-tutorial
update-sites --pokilot
```

普通 sudo 用户在命令前加 `sudo`。失败时停止后续更新，并显示日志路径；先保留日志处理错误，再重试。

## 3. 线上正式笔记 → 本地

线上管理员确认的正式笔记同步到 GitHub 后，在 **Windows 本机 PowerShell** 执行：

```powershell
Set-Location D:\GameProjects\os-tutorial
powershell -NoProfile -ExecutionPolicy Bypass -File .\pull-local.ps1
```

本机有未提交改动时先用发布脚本处理。无更新不会重启；有更新时按需构建，并恢复原来运行的本地服务。

默认本地端口为 `8765`。如果启动时使用其他端口，传相同端口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish-local.ps1 -Port 8877
powershell -NoProfile -ExecutionPolicy Bypass -File .\pull-local.ps1 -Port 8877
```

首次升级遇到“不支持安全停止”时，在原服务窗口按一次 `Ctrl+C`，再运行脚本；升级完成后可用原 `start.ps1` 启动。脚本不会结束其他项目或不明 Python 进程。本地同步与后台服务日志位于 `raw/local-sync/`。

点击右上角“登录”，在弹窗中输入账号密码。管理员可在右上角切换身份；`test1 / aa2025` 仅为编写员，提交提案供管理员审核，访客只看正式内容。本地调试不会自动上传，上传需明确运行发布脚本。

脚本显示更新成功后，刷新 https://klywa.xyz/os-tutorial/ 和 https://klywa.xyz/pokilot/ 检查网站。
