#!/usr/bin/env python3
"""Migrate accounts only after the running server advertises role support."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import urllib.request
import uuid


def capability(url='http://127.0.0.1:8765/os-tutorial/api/auth/me'):
    request = urllib.request.Request(url, headers={'Host': 'klywa.xyz'})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def migrate(path, server_capability):
    if not isinstance(server_capability, dict) or not any(k in server_capability for k in ('account_role', 'allowed_roles')):
        raise ValueError('正在运行的服务尚未支持角色；先发布新版服务，再迁移账号')
    path = Path(path)
    if path.is_symlink():
        raise ValueError('账号配置不能是符号链接')
    original = json.loads(path.read_text(encoding='utf-8'))
    if original.get('schema_version') == 2:
        accounts = [dict(account) for account in original['accounts']]
    elif 'schema_version' not in original and isinstance(original.get('users'), list):
        accounts = [{**account, 'role':'admin'} for account in original['users']]
    else:
        raise ValueError('不支持的账号配置格式')
    if not isinstance(original.get('sessionSecret'), str) or not original['sessionSecret']:
        raise ValueError('账号配置缺少 sessionSecret')
    seen = set()
    for account in accounts:
        if (set(account) != {'username', 'password', 'role'} or
                not all(isinstance(account[key], str) and account[key] for key in account) or
                account['role'] not in ('admin', 'annotator', 'viewer') or account['username'] in seen):
            raise ValueError('账号配置无效或用户名重复')
        seen.add(account['username'])
        if account['username'] == 'test1' and account['role'] != 'annotator':
            raise ValueError('test1 已存在且不是 annotator；请管理员明确处理，未改写任何账号')
    if 'test1' not in seen:
        accounts.append({'username':'test1', 'password':'aa2025', 'role':'annotator'})
    updated = {'schema_version':2, 'sessionSecret':original['sessionSecret'],
               'sessionTtlHours':original.get('sessionTtlHours', 168), 'accounts':accounts}
    if updated == original:
        return False
    stat = path.stat()
    suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    backup = path.with_name(path.name + '.backup-' + suffix)
    with path.open('rb') as source:
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            shutil.copyfileobj(source, handle)
            handle.flush()
            os.fsync(handle.fileno())
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    try:
        # Backups and replacement retain the original owner; credentials are private.
        for target in (backup, temporary):
            if target == temporary:
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                    json.dump(updated, handle, ensure_ascii=False, indent=2)
                    handle.write('\n')
                    handle.flush()
                    os.fsync(handle.fileno())
            os.chmod(target, 0o600)
            if hasattr(os, 'chown'):
                os.chown(target, stat.st_uid, stat.st_gid)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/os-tutorial/admins.json'))
    args = parser.parse_args()
    try:
        changed = migrate(args.config, capability())
        print('账号配置已安全迁移，请重启 os-tutorial' if changed else '账号配置无需修改')
        return 0
    except Exception as exc:
        print(str(exc))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
