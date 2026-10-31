# 双站部署步骤

## 1. 在 Windows 本机发布代码与网站资料

1. 关闭本机正在运行的万象棋服务。
2. 在 PowerShell 执行：

```powershell
Set-Location D:\GameProjects\os-tutorial
git status --short
git pull --ff-only origin master
# 如果提示本地改动阻止拉取，先在本机整理、提交这些改动，再重跑上一条。
.\.wxq-runtime\Scripts\python.exe frontend/website_data.py export
.\.wxq-runtime\Scripts\python.exe frontend/website_data.py validate
git add README.md .gitignore .codex/skills/wanxiangqi-knowledge frontend deploy docs website-data
git diff --cached --stat
git commit -m "feat: deploy public notes and dashboard"
git push origin master

Set-Location D:\GameProjects\pokilot
git status --short
git add README.md apps/web
git diff --cached --stat
git commit -m "feat: support pokilot deployment base path"
git push origin app
```

3. 打开两个仓库，确认刚才的提交已经出现：

- [os-tutorial](https://github.com/klywa/os-tutorial)
- [pokilot](https://github.com/klywa/pokilot)

## 2. 登录服务器，备份现站

1. 在 Windows PowerShell 设置服务器地址并登录：

```powershell
$ServerIp = Read-Host '输入阿里云服务器公网IP'
ssh root@$ServerIp
```

2. 以下 Bash 命令全部在服务器执行：

```bash
set -e
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP=/root/backups/dual-site-$STAMP
mkdir -p "$BACKUP"
chmod 700 "$BACKUP"
cp -a /etc/caddy/Caddyfile "$BACKUP/Caddyfile"
cp -a /etc/systemd/system/pokilot.service "$BACKUP/pokilot.service"
if [ -d /etc/systemd/system/pokilot.service.d ]; then
  cp -a /etc/systemd/system/pokilot.service.d "$BACKUP/pokilot.service.d"
fi
cp -a /etc/pokilot "$BACKUP/pokilot-config"
systemctl stop pokilot
cd /opt/pokilot
git status --short
git rev-parse HEAD > "$BACKUP/pokilot-head"
tar --exclude='./node_modules' --exclude='./apps/web/node_modules' --exclude='./apps/web/.next' \
  -czf "$BACKUP/pokilot.tgz" -C /opt/pokilot .
printf '%s\n' "$BACKUP" > /root/backups/dual-site-latest
systemctl start pokilot
```

## 3. 安装依赖，创建万象棋服务用户

```bash
apt update
apt install -y python3 python3-venv git curl sudo ca-certificates
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt install -y nodejs
command -v pnpm >/dev/null || npm install -g pnpm
python3 --version
node --version
pnpm --version
# 确认 Python 为3.12，Node为24。

id os-tutorial >/dev/null 2>&1 || useradd --system --create-home \
  --home-dir /var/lib/os-tutorial --shell /usr/sbin/nologin os-tutorial
install -d -o os-tutorial -g os-tutorial -m 750 /opt/os-tutorial /var/lib/os-tutorial
install -d -o os-tutorial -g os-tutorial -m 700 /var/lib/os-tutorial/.ssh /etc/os-tutorial
sudo -u os-tutorial -H git config --global user.name 'os-tutorial website'
sudo -u os-tutorial -H git config --global user.email 'website@klywa.xyz'
```

## 4. 为万象棋设置 GitHub 可写部署密钥

```bash
sudo -u os-tutorial -H ssh-keygen -t ed25519 -C os-tutorial-server \
  -f /var/lib/os-tutorial/.ssh/id_ed25519 -N ''
cat /var/lib/os-tutorial/.ssh/id_ed25519.pub
```

1. 打开 [os-tutorial 部署密钥设置](https://github.com/klywa/os-tutorial/settings/keys)。
2. 点击 **Add deploy key**。
3. Title 填 `os-tutorial-server`，Key 粘贴上一条命令的完整公钥。
4. 勾选 **Allow write access**，保存。
5. 在服务器执行下面命令；对照 [GitHub 公钥指纹](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints)确认指纹后输入 `yes`：

```bash
sudo -u os-tutorial -H ssh -T git@github.com || true
sudo -u os-tutorial -H git ls-remote git@github.com:klywa/os-tutorial.git refs/heads/master
```

6. 确认上一条命令输出 `refs/heads/master` 及提交哈希。

## 5. 配置万象棋管理员

```bash
umask 077
python3 - <<'PY'
import json,secrets
from pathlib import Path
path=Path('/etc/os-tutorial/admins.json')
if path.exists():
    raise SystemExit('配置已存在；请保留原文件，跳过本步骤。')
path.write_text(json.dumps({
    'sessionSecret':secrets.token_urlsafe(48),
    'sessionTtlHours':168,
    'users':[{'username':'klywa','password':'aa2025'}]
},ensure_ascii=False,indent=2)+'\n')
PY
chown os-tutorial:os-tutorial /etc/os-tutorial/admins.json
chmod 600 /etc/os-tutorial/admins.json
```

## 6. 安装万象棋服务和首次版本

```bash
sudo -u os-tutorial -H git clone --branch master \
  git@github.com:klywa/os-tutorial.git /opt/os-tutorial/bootstrap
cd /opt/os-tutorial/bootstrap
install -m 644 deploy/os-tutorial.service /etc/systemd/system/os-tutorial.service
install -m 644 deploy/os-tutorial-update.service /etc/systemd/system/os-tutorial-update.service
install -m 644 deploy/os-tutorial-update.timer /etc/systemd/system/os-tutorial-update.timer
visudo -cf deploy/os-tutorial.sudoers
install -m 440 deploy/os-tutorial.sudoers /etc/sudoers.d/os-tutorial
systemctl daemon-reload
sudo -u os-tutorial -H python3 /opt/os-tutorial/bootstrap/deploy/release.py \
  --base-dir /opt/os-tutorial --state-dir /var/lib/os-tutorial \
  --repo git@github.com:klywa/os-tutorial.git
systemctl enable os-tutorial.service
systemctl enable --now os-tutorial-update.timer
systemctl status os-tutorial.service --no-pager
systemctl list-timers os-tutorial-update.timer --no-pager
curl --fail http://127.0.0.1:8765/os-tutorial/api/health
curl --fail -H 'Host: klywa.xyz' http://127.0.0.1:8765/os-tutorial/api/auth/me
```

确认健康接口返回 `"ok": true`，身份接口返回 `"mode": "public"`、`"role": "guest"`。

## 7. 把 Pokilot 改到 /pokilot

```bash
systemctl stop pokilot
cd /opt/pokilot
git status --short
# 如果有本机改动，先备份并处理，直到能执行下一条。
git pull --ff-only origin app
pnpm install --frozen-lockfile
NEXT_PUBLIC_BASE_PATH=/pokilot pnpm build

mkdir -p /etc/systemd/system/pokilot.service.d
cat > /etc/systemd/system/pokilot.service.d/subpath.conf <<'EOF'
[Service]
Environment=NEXT_PUBLIC_BASE_PATH=/pokilot
ExecStart=
ExecStart=/usr/bin/node /opt/pokilot/apps/web/node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3000
EOF
systemctl daemon-reload
systemctl restart pokilot
systemctl status pokilot --no-pager
curl --fail http://127.0.0.1:3000/pokilot/db -o /dev/null
curl --fail http://127.0.0.1:3000/pokilot/api/auth/me
```

确认身份接口返回 `"mode":"on"`、`"role":"guest"`。

## 8. 配置两个网站共存

1. 打开 Caddy 配置：

```bash
nano /etc/caddy/Caddyfile
```

2. 将已有的 `klywa.xyz` 站点块替换为下列内容；保留文件中其他域名的站点块：

```caddyfile
klywa.xyz {
    @home path /
    redir @home /os-tutorial/ 302

    @os_bare path /os-tutorial
    redir @os_bare /os-tutorial/ 308

    handle /os-tutorial/* {
        reverse_proxy 127.0.0.1:8765
    }

    @pokilot path /pokilot /pokilot/*
    handle @pokilot {
        reverse_proxy 127.0.0.1:3000
    }

    handle {
        respond "Not Found" 404
    }
}
```

3. 保存退出，执行：

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
systemctl is-active caddy pokilot os-tutorial
ss -lntp | grep -E ':(3000|8765)\b'
ufw status
```

4. 确认 `3000`、`8765` 都只监听 `127.0.0.1`。
5. 阿里云安全组仅保留网站所需的 `80`、`443` 以及你的 SSH 端口；删除 `3000`、`8765` 的公网入站规则。

## 9. 验收两个网站

```bash
SITE=https://klywa.xyz
curl -I "$SITE/"
curl --fail "$SITE/os-tutorial/api/auth/me"
curl --fail "$SITE/os-tutorial/api/notes/catalog" -o /dev/null
curl --fail "$SITE/os-tutorial/api/dashboard?scope=usage_top50" -o /dev/null
curl --fail "$SITE/pokilot/api/auth/me"
curl --fail "$SITE/pokilot/db" -o /dev/null
curl -s -o /dev/null -w '%{http_code}\n' "$SITE/api/auth/me"
# 最后一条应为404。

curl -s -o /dev/null -w '%{http_code}\n' -X PUT \
  "$SITE/os-tutorial/api/notes/anonymous-probe" \
  -H "Origin: $SITE" -H 'Content-Type: application/json' -d '{}'
# 应为401。

curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  "$SITE/os-tutorial/api/crawler/creators/resume" \
  -H "Origin: $SITE" -H 'Content-Type: application/json' -d '{}'
# 应为404。

curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  "$SITE/pokilot/api/teams" -H "Origin: $SITE" \
  -H 'Content-Type: application/json' -d '{}'
# 应为401。
```

1. 用无痕窗口打开 `https://klywa.xyz/os-tutorial/`，确认只有笔记和看板，不能编辑。
2. 浏览笔记、搜索、打开卡牌详情、查看图片、复制和导出笔记。
3. 打开看板，依次切换全部、Top-10、Top-20、Top-50。
4. 打开 `https://klywa.xyz/os-tutorial/admin`，输入 `klywa` / `aa2025`。
5. 修改一条测试笔记并保存，确认同步提示成功，再去 GitHub 查看自动产生的笔记提交。
6. 修改一项看板匹配，刷新页面确认保留，并确认 GitHub 出现对应提交。
7. 退出登录，确认编辑及匹配管理入口消失。
8. 打开 `https://klywa.xyz/pokilot/admin`，使用原有 Pokilot 管理员配置登录，检查数据库、笔记、战斗页面，随后退出。
9. 分别刷新两个网站的子页面，确认图片、接口和登录状态正常。

## 10. 验收小时自动更新

1. 在 Windows 本机拉取线上笔记提交：

```powershell
Set-Location D:\GameProjects\os-tutorial
git pull --ff-only origin master
```

2. 在本机修改一条笔记并提交推送，或更新本机采集资料后执行：

```powershell
.\.wxq-runtime\Scripts\python.exe frontend/website_data.py export
.\.wxq-runtime\Scripts\python.exe frontend/website_data.py validate
git add knowledge website-data
git diff --cached --stat
git commit -m "content: update website notes and snapshots"
git push origin master
```

3. 在服务器手动触发一次同样的小时任务：

```bash
systemctl start os-tutorial-update.service
journalctl -u os-tutorial-update.service -n 80 --no-pager
readlink -f /opt/os-tutorial/current
sudo -u os-tutorial -H git -C /opt/os-tutorial/current log -1 --oneline
systemctl list-timers os-tutorial-update.timer --no-pager
```

4. 刷新网站，确认刚才的修改出现。
5. 不再改动，再执行一次 `systemctl start os-tutorial-update.service`，日志应显示 `unchanged`。
6. 后续每次在本机整理内容前，先停止本机服务并执行 `git pull --ff-only origin master`。若发生冲突，先合并完成，再打开本机工具。网站使用率由本机生成的最新快照提供。

## 11. 查看日志、重试同步、修改管理员

```bash
journalctl -u os-tutorial -n 80 --no-pager
journalctl -u os-tutorial-update.service -n 100 --no-pager
journalctl -u pokilot -n 80 --no-pager
journalctl -u caddy -n 50 --no-pager
sudo -u os-tutorial -H python3 /opt/os-tutorial/current/frontend/website_sync.py \
  --root /opt/os-tutorial/current --state-dir /var/lib/os-tutorial --status

# 修复网络、密钥或仓库写权限后，重试同步和发布。
systemctl start os-tutorial-update.service

# 修改万象棋账号、密码或会话有效期。
nano /etc/os-tutorial/admins.json
chown os-tutorial:os-tutorial /etc/os-tutorial/admins.json
chmod 600 /etc/os-tutorial/admins.json
```

## 12. 处理线上与 GitHub 冲突

1. 在服务器停止更新与编辑，并备份活动版本：

```bash
systemctl stop os-tutorial-update.timer
systemctl stop os-tutorial-update.service
systemctl stop os-tutorial.service
CURRENT=$(readlink -f /opt/os-tutorial/current)
STAMP=$(date +%Y%m%d-%H%M%S)
install -d -m 700 /root/backups
tar --exclude='./frontend/node_modules' --exclude='./frontend/dist' \
  -czf "/root/backups/os-tutorial-conflict-$STAMP.tgz" -C "$CURRENT" .
sudo -u os-tutorial -H git -C "$CURRENT" status --short
sudo -u os-tutorial -H git -C "$CURRENT" fetch origin master
sudo -u os-tutorial -H git -C "$CURRENT" merge --no-commit --no-ff origin/master || true
```

2. 若最后一条提示冲突，执行 `git -C "$CURRENT" diff --name-only --diff-filter=U`，逐个用 `sudo -u os-tutorial nano "$CURRENT/文件相对路径"` 处理冲突标记，保留需要的双方内容。
3. 若同步失败留下了尚未提交的笔记，先处理 `git status` 列出的笔记/索引/匹配文件，执行下面提交命令提交后，再执行上面的 fetch 和 merge。
4. 检查并提交完成的内容：

```bash
sudo -u os-tutorial -H python3 "$CURRENT/frontend/website_data.py" recover --root "$CURRENT"
sudo -u os-tutorial -H python3 "$CURRENT/frontend/website_data.py" prepare --root "$CURRENT"
sudo -u os-tutorial -H python3 "$CURRENT/frontend/website_data.py" validate --root "$CURRENT"
sudo -u os-tutorial -H git -C "$CURRENT" add -- knowledge website-data/usage-matches.json
sudo -u os-tutorial -H git -C "$CURRENT" diff --check --cached
sudo -u os-tutorial -H git -C "$CURRENT" diff --cached --stat
sudo -u os-tutorial -H git -C "$CURRENT" commit -m 'content: resolve website synchronization'
sudo -u os-tutorial -H git -C "$CURRENT" push origin HEAD:master
sudo -u os-tutorial -H python3 "$CURRENT/frontend/website_sync.py" \
  --root "$CURRENT" --state-dir /var/lib/os-tutorial
sudo -u os-tutorial -H python3 "$CURRENT/deploy/release.py" \
  --base-dir /opt/os-tutorial --state-dir /var/lib/os-tutorial --rebuild
systemctl enable --now os-tutorial-update.timer
systemctl is-active os-tutorial
```

5. 不执行 `git reset --hard`、强制推送或删除包含待同步编辑的版本目录。

## 13. 备份万象棋网站

```bash
systemctl stop os-tutorial-update.timer
systemctl stop os-tutorial-update.service
systemctl stop os-tutorial.service
STAMP=$(date +%Y%m%d-%H%M%S)
CURRENT=$(readlink -f /opt/os-tutorial/current)
install -d -m 700 /root/backups
tar --exclude='./frontend/node_modules' --exclude='./frontend/dist' \
  -czf "/root/backups/os-tutorial-$STAMP.tgz" -C "$CURRENT" .
tar -czf "/root/backups/os-tutorial-config-$STAMP.tgz" -C / \
  etc/os-tutorial var/lib/os-tutorial etc/caddy/Caddyfile
chmod 600 /root/backups/os-tutorial-*.tgz
systemctl start os-tutorial.service
systemctl start os-tutorial-update.timer
```

## 14. 回退万象棋版本

1. 先执行上一节备份。
2. 停止自动更新和服务，查看可用版本：

```bash
systemctl stop os-tutorial-update.timer
systemctl stop os-tutorial-update.service
systemctl stop os-tutorial.service
find /opt/os-tutorial/releases -mindepth 1 -maxdepth 1 -type d | sort
readlink -f /opt/os-tutorial/current
```

3. 输入要回退到的完整版本目录：

```bash
read -r -p '输入上一成功版本的绝对目录：' PREVIOUS
test -f "$PREVIOUS/frontend/dist/index.html"
sudo -u os-tutorial -H python3 - "$PREVIOUS" <<'PY'
import os,sys
from pathlib import Path
base=Path('/opt/os-tutorial')
target=Path(sys.argv[1]).resolve()
if target.parent != (base/'releases').resolve():
    raise SystemExit('目录不在 releases 中，停止回退')
temporary=base/'.rollback-current'
temporary.unlink(missing_ok=True)
temporary.symlink_to(target,target_is_directory=True)
os.replace(temporary,base/'current')
PY
systemctl start os-tutorial
curl --fail http://127.0.0.1:8765/os-tutorial/api/health
```

4. 保留自动更新为停止状态；修复 GitHub 中的问题后，执行 `systemctl start os-tutorial-update.service`，验收通过再执行 `systemctl start os-tutorial-update.timer`。

## 15. 恢复迁移前的 Pokilot 根站点

```bash
BACKUP=$(cat /root/backups/dual-site-latest)
systemctl stop os-tutorial-update.timer
systemctl stop pokilot
STAMP=$(date +%Y%m%d-%H%M%S)
mv /opt/pokilot "/opt/pokilot-before-rollback-$STAMP"
mkdir /opt/pokilot
tar -xzf "$BACKUP/pokilot.tgz" -C /opt/pokilot
cp -a "$BACKUP/pokilot.service" /etc/systemd/system/pokilot.service
if [ -f /etc/systemd/system/pokilot.service.d/subpath.conf ]; then
  mv /etc/systemd/system/pokilot.service.d/subpath.conf "$BACKUP/subpath.conf.disabled-$STAMP"
fi
if [ -d "$BACKUP/pokilot.service.d" ]; then
  cp -a "$BACKUP/pokilot.service.d/." /etc/systemd/system/pokilot.service.d/
fi
cd /opt/pokilot
pnpm install --frozen-lockfile
NEXT_PUBLIC_BASE_PATH= pnpm build
systemctl daemon-reload
systemctl start pokilot
cp -a "$BACKUP/Caddyfile" /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
curl --fail https://klywa.xyz/db -o /dev/null
```
