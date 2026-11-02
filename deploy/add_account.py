#!/usr/bin/env python3
"""新增公网账号：add_account.py admin|annotator 用户名 密码。"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'frontend'))
from website_auth import Auth

CONFIG = Path('/etc/os-tutorial/admins.json')


@contextmanager
def account_lock(path):
    # A separate persistent inode keeps concurrent script invocations serialized
    # even when the JSON file is atomically replaced.
    descriptor = os.open(path.with_name(path.name + '.accounts.lock'),
                         os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, 'r+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError('另一个账号操作正在运行，请稍后重试') from None
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('另一个账号操作正在运行，请稍后重试') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def add_account(path, role, username, password):
    if role not in ('admin', 'annotator'):
        raise ValueError('角色必须是 admin 或 annotator')
    if not username or not username.strip() or not password:
        raise ValueError('用户名和密码不能为空')
    path = Path(path)
    if path.is_symlink():
        raise ValueError('账号配置不能是符号链接')
    with account_lock(path):
        original = path.read_bytes()
        value = json.loads(original.decode('utf-8'))
        if value.get('schema_version') != 2:
            raise ValueError('请先通过现有部署流程升级账号配置到版本 2')
        _, accounts, _ = Auth(path, '/os-tutorial').config()
        if username in accounts:
            raise ValueError('用户名已存在，未修改已有账号')
        value['accounts'].append({'username': username, 'password': password, 'role': role})
        metadata = path.stat()
        suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        backup = path.with_name(path.name + '.backup-' + suffix)
        temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex + '.tmp')
        try:
            for target, data in ((backup, original), (temporary, (
                    json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))):
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'wb') as handle:
                    if hasattr(os, 'fchown'):
                        os.fchown(handle.fileno(), metadata.st_uid, metadata.st_gid)
                    os.chmod(target, 0o600)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            Auth(temporary, '/os-tutorial').config()
            os.replace(temporary, path)
            if os.name != 'nt':
                descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
        return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=('admin', 'annotator'), help='账号角色')
    parser.add_argument('username', help='新账号用户名')
    parser.add_argument('password', help='新账号密码')
    args = parser.parse_args(argv)
    try:
        backup = add_account(CONFIG, args.role, args.username, args.password)
    except (OSError, ValueError, TypeError, KeyError):
        # Do not include exception details: JSON/parser errors can contain credentials.
        print('新增失败：请检查配置有效、角色正确、用户名未重复且非空、密码非空，'
              '并在服务器 root 窗口执行；如有其他账号操作，请等待后重试。', file=sys.stderr)
        return 1
    print(f'账号已新增（{args.role}），立即生效，无需重启。原配置备份：{backup}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
