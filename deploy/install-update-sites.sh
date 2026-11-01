#!/usr/bin/env bash
# Install once from the repository or a copy uploaded to /tmp, in a root SSH shell.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo '请在服务器用 sudo bash /tmp/install-update-sites.sh 执行' >&2
  exit 1
fi
# Bootstrap through the existing safe publisher; old current may lack this installer.
install -d -m 755 /run/lock
exec 9>/run/lock/update-sites.lock
flock -n 9 || { echo '另一条 update-sites 正在运行，请等待完成' >&2; exit 1; }
echo '先通过现有发布服务更新万象棋；正在运行的发布会等待完成。'
systemctl start os-tutorial-update.service
SOURCE=/opt/os-tutorial/current/deploy
for name in update_sites.py configure_roles.py; do
  test -f "$SOURCE/$name" || { echo "缺少 $SOURCE/$name；请先发布包含更新器的版本" >&2; exit 1; }
done
# Wrapper always loads the current release; later releases update the command itself.
install -d -m 755 /usr/local/bin
TEMP=$(mktemp /usr/local/bin/.update-sites.XXXXXXXX)
trap 'rm -f "$TEMP"' EXIT
cat > "$TEMP" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/python3 /opt/os-tutorial/current/deploy/update_sites.py "$@"
WRAPPER
chmod 755 "$TEMP"
chown root:root "$TEMP"
mv -f "$TEMP" /usr/local/bin/update-sites
trap - EXIT
flock -u 9
exec 9>&-
echo 'update-sites 已安装。现在检查新版服务并安全迁移账号。'
/usr/local/bin/update-sites --os-tutorial
echo '安装完成。以后在服务器运行 update-sites；只更新单站可加 --os-tutorial 或 --pokilot。'
