"""Export a clean, standalone LAN edition from the tracked working tree."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
EDITION = ROOT / 'deploy/internal-export'
TARGET = ROOT.with_name('os-tutorial-internal')
PATCH = EDITION / 'internal.patch'
INDEX = 'knowledge/index.meta.json'
TEMPLATE_META = 'templates/library.meta.json'
EXCLUDED_TREES = (
    '.github/', '.planning/', 'deploy/', 'docs/superpowers/', 'docs/reports/',
    '.codex/skills/wanxiangqi-knowledge/tests/', 'frontend/browser_',
    'knowledge-history/', 'knowledge-sync/', 'templates/conflicts/',
    'templates/resolutions/', 'templates/history/', 'raw/', 'personal/',
)
PRIVATE_FIELDS = {
    'history', 'history_head', 'history_count', 'conflicts', 'review_receipts',
    'retired_claim_annotations', 'acquisition_evidence', 'batch77_raw_archives',
    'cookie', 'cookies', 'credential', 'credentials', 'password', 'access_token',
    'refresh_token', 'session_token', 'session_secret', 'api_key', 'secret_key',
    'absolute_path', 'local_path', 'file_path', 'raw_path', 'transcript_path',
}
ABS_PATH = re.compile(r'^(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|root|opt|mnt)/)', re.I)


def git(root, *args, data=None, allowed=(0,), env=None):
    result = subprocess.run(
        ['git', '-c', 'core.autocrlf=false', '-c', 'core.quotePath=false', *args],
        cwd=root, env=env, input=data, capture_output=True,
    )
    if result.returncode not in allowed:
        detail = result.stderr.decode('utf-8', 'replace').strip()
        raise ValueError(detail or f'Git 命令失败（{args[0]}）')
    return result.stdout


def names(output):
    return [part.decode('utf-8') for part in output.split(b'\0') if part]


def ignored(root, paths):
    if not paths:
        return set()
    return set(names(git(
        root, 'check-ignore', '--no-index', '--stdin', '-z',
        data=('\0'.join(paths) + '\0').encode(), allowed=(0, 1),
    )))


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def is_link(path):
    if path.is_symlink():
        return True
    return path.exists() and bool(
        getattr(path.lstat(), 'st_file_attributes', 0)
        & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
    )


def excluded(path, policy):
    return (
        path in policy['excluded_paths']
        or path.rsplit('/', 1)[-1] in {'AGENTS.md', 'CLAUDE.md', 'task_plan.md', 'findings.md', 'progress.md'}
        or (path.startswith(EXCLUDED_TREES) and path != 'deploy/add_account.py')
        or any(part in {'.git', '.agents', '.aws'} for part in path.split('/'))
    )


def copy_sources(stage, policy):
    tracked = sorted(set(names(git(ROOT, 'ls-files', '-z'))))
    paths = [path for path in tracked if not excluded(path, policy)]
    skip = ignored(ROOT, paths)
    safe_folders = {ROOT}
    for relative in paths:
        if relative in skip:
            continue
        source = ROOT / relative
        if not source.exists() and not source.is_symlink():
            continue  # An unstaged deletion is part of the working copy.
        for parent in source.parents:
            if parent in safe_folders:
                break
            if is_link(parent):
                raise ValueError(f'源文件位于链接目录：{relative}')
            safe_folders.add(parent)
        if is_link(source) or not source.is_file():
            raise ValueError(f'源路径不是普通文件：{relative}')
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    # Only canonical notes belong in the snapshot. Additional JSON under
    # these folders can be old source records even when tracked.
    index = read(stage / INDEX)
    live = {row['path'] for row in index['notes']}
    live.update(str(Path(path).with_suffix('.meta.json').as_posix()) for path in list(live))
    for area in ('lineups', 'players', 'other'):
        for file in (stage / 'knowledge' / area).rglob('*.json'):
            if file.relative_to(stage).as_posix() not in live:
                file.unlink()


def apply_edition(stage, policy):
    git(stage, 'init', '-q')
    git(stage, 'index-pack', '--stdin', data=(EDITION / 'ancestors.pack').read_bytes())
    current = [path for path in policy['patch_paths'] if (stage / path).is_file()]
    for relative in current:
        path = stage / relative
        content = path.read_bytes()
        if b'\r\n' in content and b'\0' not in content:
            path.write_bytes(content.replace(b'\r\n', b'\n'))
    if current:
        git(stage, 'add', '-f', '--', *current)
    git(stage, 'apply', '--cached', '--3way', str(PATCH))
    git(stage, 'checkout-index', '-a', '-f')
    for path in ignored(stage, [p.relative_to(stage).as_posix() for p in files(stage)]):
        (stage / path).unlink()
    remove_tree(stage / '.git')


def remove_tree(path):
    def retry(operation, name, error):
        if not isinstance(error, PermissionError) or is_link(Path(name)):
            raise error
        os.chmod(name, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        operation(name)

    shutil.rmtree(path, onexc=retry)


def files(root):
    return (path for path in root.rglob('*') if path.is_file() and '.git' not in path.relative_to(root).parts)


def scrubber(policy):
    # Historical author identifiers and configured local identities stay in
    # the source repository. The export only receives these replacements.
    authored = git(ROOT, 'log', '--all', '--format=%an%n%ae').decode('utf-8', 'replace').splitlines()
    aliases = set(policy['private_identifiers'])
    aliases.update(a.strip() for a in authored if len(a.strip()) >= 4 and a.strip().isascii())
    replacements = {name: 'internal' for name in aliases if len(name) >= 4}
    replacements.update(policy['private_replacements'])
    pattern = re.compile('|'.join(re.escape(k) for k in sorted(replacements, key=len, reverse=True)), re.I)
    lowered = {k.lower(): v for k, v in replacements.items()}

    def redact(text):
        return pattern.sub(lambda match: lowered[match.group().lower()], text)

    return redact


def clean_json(value, redact):
    if isinstance(value, dict):
        return {
            redact(key): clean_json(item, redact)
            for key, item in value.items()
            if key.casefold() not in PRIVATE_FIELDS
        }
    if isinstance(value, list):
        return [clean_json(item, redact) for item in value]
    if isinstance(value, str):
        return '' if ABS_PATH.match(value) else redact(value)
    return value


def scrub(stage, policy):
    redact = scrubber(policy)
    for path in files(stage):
        relative = path.relative_to(stage).as_posix()
        if relative in {'website-data/manifest.json', TEMPLATE_META}:
            continue
        if relative.startswith('website-data/images/'):
            continue  # Content-addressed official image bytes.
        raw = path.read_bytes()
        try:
            original = raw.decode('utf-8')
        except UnicodeDecodeError:
            continue  # Application and official card assets are binary.
        if path.suffix == '.json' and relative.startswith(('knowledge/', 'templates/', 'website-data/')):
            value = json.loads(original.lstrip('\ufeff'))
            clean = clean_json(value, redact)
            if clean != value:
                write(path, clean)
        else:
            clean = redact(original)
            if clean != original:
                path.write_bytes(clean.encode('utf-8'))


def rebuild_notes(stage):
    from json_store import digest, meta_path

    path = stage / INDEX
    index = read(path)
    for row in index['notes']:
        body = read(stage / row['path'])
        metadata_path = stage / meta_path(row['path'])
        metadata = read(metadata_path)
        metadata['body_sha256'] = digest(body)
        metadata.pop('revision', None)
        metadata['revision'] = digest({'body': body, 'metadata': metadata})[:20]
        write(metadata_path, metadata)
        row['revision'] = metadata['revision']
    write(path, index)


def rebuild_templates(stage, policy):
    import templates_store

    public, previous = templates_store._load(stage)
    current = templates_store._meta()
    current['entity_bindings'] = previous['entity_bindings']
    # Suppress retired built-ins without carrying their original edit records.
    current['tombstones'] = {
        kind: {uid: {'actor': '事件目录迁移' if record.get('actor') == '事件目录迁移' else 'internal'}
               for uid, record in entries.items()}
        for kind, entries in previous['tombstones'].items()
    }
    catalog, _ = templates_store._catalog(stage)
    templates_store._baseline(current, {'events': [], 'groups': []}, public, catalog)
    write(stage / TEMPLATE_META, clean_json(current, scrubber(policy)))


def rebuild_manifest(stage):
    folder = stage / 'website-data'
    path = folder / 'manifest.json'
    excluded_names = {path.name, 'usage-matches.json'}
    hashes = {
        name.relative_to(folder).as_posix(): hashlib.sha256(name.read_bytes()).hexdigest()
        for name in sorted(files(folder))
        if name.name not in excluded_names
    }
    write(path, {'schema_version': 1, 'files': hashes})


def build(stage):
    policy = read(EDITION / 'paths.json')
    copy_sources(stage, policy)
    apply_edition(stage, policy)
    scrub(stage, policy)
    # Import the export's current schemas. Avoid bytecode in the deliverable.
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(stage / 'frontend'), str(stage / '.codex/skills/wanxiangqi-knowledge/scripts')]
    rebuild_notes(stage)
    rebuild_templates(stage, policy)
    rebuild_manifest(stage)


def replace_output(stage, target, previous):
    if is_link(target) or (target.exists() and not target.is_dir()) or (target / '.git').exists():
        raise ValueError(f'目标必须是普通内网导出目录：{target}')
    if target.exists():
        target.rename(previous)
    try:
        stage.rename(target)
    except OSError:
        if previous.exists():
            previous.rename(target)
        raise


def main():
    try:
        # The lock prevents two exporters from moving the same destination.
        lock = TARGET.with_name('.os-tutorial-internal-export.lock')
        lock.mkdir()
        try:
            previous = TARGET.with_name('.os-tutorial-internal-previous')
            if previous.exists() or is_link(previous):
                raise ValueError(f'上一次导出的旧目录仍在：{previous}，请先恢复或移走该目录')
            with tempfile.TemporaryDirectory(prefix='.os-tutorial-internal-', dir=TARGET.parent) as temp:
                workspace = Path(temp)
                stage = workspace / 'stage'
                stage.mkdir()
                build(stage)
                sizes = [path.stat().st_size for path in files(stage)]
                print(f'预计导出 {len(sizes)} 个文件，{sum(sizes) / 1024**2:.2f} MiB', flush=True)
                replace_output(stage, TARGET, previous)
                if previous.exists():
                    if is_link(previous) or previous.resolve() != previous:
                        raise ValueError(f'新版本已导出，旧目录路径无法安全清理：{previous}')
                    remove_tree(previous)
        finally:
            lock.rmdir()
    except (OSError, ValueError, KeyError) as error:
        print(f'内网版导出失败：{error}', file=sys.stderr)
        return 1
    print(f'已导出内网版：{TARGET}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
