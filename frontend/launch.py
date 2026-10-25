"""Prepare dependencies, build the UI, and run the API and background workers."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / 'frontend'


def run(command, cwd=ROOT):
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--skip-topic-model', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be 1..65535')
    if not (3, 11) <= sys.version_info[:2] <= (3, 12):
        raise RuntimeError('Please use Python 3.11 or 3.12 (recommended: 3.12).')
    node = shutil.which('node')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not node or not npm:
        raise RuntimeError('Install Node.js 24 including npm first.')
    run([node, '-e', 'const [a,b]=process.versions.node.split(".").map(Number); if(!((a===20&&b>=19)||(a===22&&b>=12)||a>=23)) process.exit(1)'])
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', args.port))
        except OSError as exc:
            raise RuntimeError(f'Port {args.port} is occupied. Stop the old service or select another port.') from exc
    runtime = ROOT / '.wxq-runtime'
    python = runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        if (runtime / 'pyvenv.cfg').exists():
            raise RuntimeError('Copied virtual environment is incompatible. Move .wxq-runtime aside and rerun; do not copy virtual environments between computers.')
        run([sys.executable, '-m', 'venv', runtime])
    run([python, '-c', 'import sys; assert (3,11)<=sys.version_info[:2]<=(3,12), "Recreate the virtual environment with Python 3.12"'])
    requirements = ROOT / '.codex/skills/wanxiangqi-knowledge/scripts/requirements.txt'
    stamp = runtime / 'launcher-requirements.sha256'
    signature = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text().strip() != signature:
        run([python, '-m', 'pip', 'install', '-r', requirements])
        stamp.write_text(signature, encoding='utf-8')
    if not args.skip_topic_model:
        run([python, FRONTEND / 'install_topic_model.py'])
    lock = FRONTEND / 'package-lock.json'
    npm_stamp = FRONTEND / 'node_modules/.launcher-lock.sha256'
    platform_key = subprocess.check_output([node, '-p', 'process.platform+"/"+process.arch+"/"+process.versions.node'], text=True).strip()
    npm_signature = hashlib.sha256(lock.read_bytes() + platform_key.encode()).hexdigest()
    if not npm_stamp.exists() or npm_stamp.read_text().strip() != npm_signature:
        run([npm, 'ci'], FRONTEND)
        npm_stamp.write_text(npm_signature, encoding='utf-8')
    run([npm, 'run', 'build'], FRONTEND)
    command = [python, FRONTEND / 'server.py', '--port', args.port]
    if not args.no_browser:
        command.append('--open-browser')
    print(f'Frontend + API + background jobs: http://127.0.0.1:{args.port} (Ctrl+C to stop)', flush=True)
    if os.name != 'nt':
        os.execv(str(python), [str(item) for item in command])
    run(command)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Start failed: {exc}', file=sys.stderr)
        sys.exit(1)
