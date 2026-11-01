#!/usr/bin/env bash
# Uploaded with os-tutorial-release.py to the same directory; no active code edits.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo '请在服务器 root SSH 窗口执行，或使用 sudo bash。' >&2
  exit 1
fi
PUBLISHER="$(cd -- "$(dirname -- "$0")" && pwd)/os-tutorial-release.py"
if [ ! -f "$PUBLISHER" ]; then
  echo '缺少同目录的 os-tutorial-release.py，请先按部署文档上传两个文件。' >&2
  exit 1
fi
install -d -m 755 /run/lock
exec 9>/run/lock/update-sites.lock
flock -n 9 || { echo '另一条更新命令正在运行，请等待完成。' >&2; exit 1; }
ACTIVE=$(systemctl show os-tutorial-update.service --property=ActiveState --value)
case "$ACTIVE" in
  inactive|failed) ;;
  *) echo '发布服务仍在运行，请等它结束后再执行恢复脚本；未停止原任务。' >&2; exit 1 ;;
esac
echo '开始恢复万象棋更新；下载和构建完成前，旧网站继续提供访问。'
runuser -u os-tutorial -- /usr/bin/python3 -u - "$PUBLISHER" <<'PY'
import runpy
import sys

# Use serving-version helpers, but execute the uploaded fixed publisher.
# Do not overwrite tracked files or change the active checkout.
sys.path[:0]=['/opt/os-tutorial/current/frontend','/opt/os-tutorial/current/deploy']
sys.argv=[sys.argv[1]]
runpy.run_path(sys.argv[0],run_name='__main__')
PY
echo '恢复完成。以后继续使用 update-sites --os-tutorial。'
