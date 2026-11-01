#!/usr/bin/env bash
# Install once from the repository or a copy uploaded to /tmp, in a root SSH shell.
set -euo pipefail
RECOVER_PORT=0
if [ "$#" -gt 0 ]; then
  if [ "$#" -eq 1 ] && [ "$1" = '--recover-port' ]; then
    RECOVER_PORT=1
  else
    echo '用法：bash install-update-sites.sh [--recover-port]' >&2
    exit 2
  fi
fi
if [ "$(id -u)" -ne 0 ]; then
  echo '请在服务器用 sudo bash /tmp/install-update-sites.sh 执行' >&2
  exit 1
fi
# Bootstrap through the existing safe publisher; old current may lack this installer.
install -d -m 755 /run/lock
exec 9>/run/lock/update-sites.lock
flock -n 9 || { echo '另一条 update-sites 正在运行，请等待完成' >&2; exit 1; }
WRAPPER_TEMP=''
RESTORE_WEBSITE=0
cleanup() {
  local result=$?
  if [ -n "$WRAPPER_TEMP" ]; then rm -f -- "$WRAPPER_TEMP" || true; fi
  if [ "$RESTORE_WEBSITE" -eq 1 ] && [ "$result" -ne 0 ]; then
    echo '安装未完成，正在尝试恢复网站服务…' >&2
    systemctl start os-tutorial.service || echo '网站服务恢复失败，请查看 journalctl -u os-tutorial.service' >&2
  fi
  exit "$result"
}
trap cleanup EXIT
if [ "$RECOVER_PORT" -eq 1 ]; then
  RESTORE_WEBSITE=1
  echo '首次端口恢复：停止万象棋并等待 70 秒；安装期间网站暂停访问。'
  systemctl stop os-tutorial.service
  sleep 70
fi
echo '先通过现有发布服务更新万象棋；正在运行的发布会等待完成。'
systemctl start os-tutorial-update.service
if [ "$RECOVER_PORT" -eq 1 ]; then systemctl start os-tutorial.service; fi
SOURCE=/opt/os-tutorial/current/deploy
for name in update_sites.py configure_roles.py; do
  test -f "$SOURCE/$name" || { echo "缺少 $SOURCE/$name；请先发布包含更新器的版本" >&2; exit 1; }
done
# Wrapper always loads the current release; later releases update the command itself.
install -d -m 755 /usr/local/bin
WRAPPER_TEMP=$(mktemp /usr/local/bin/.update-sites.XXXXXXXX)
cat > "$WRAPPER_TEMP" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/python3 /opt/os-tutorial/current/deploy/update_sites.py "$@"
WRAPPER
chmod 755 "$WRAPPER_TEMP"
chown root:root "$WRAPPER_TEMP"
mv -f "$WRAPPER_TEMP" /usr/local/bin/update-sites
WRAPPER_TEMP=''
flock -u 9
exec 9>&-
echo 'update-sites 已安装。现在检查新版服务并安全迁移账号。'
/usr/local/bin/update-sites --os-tutorial
echo '安装完成。以后在服务器运行 update-sites；只更新单站可加 --os-tutorial 或 --pokilot。'
