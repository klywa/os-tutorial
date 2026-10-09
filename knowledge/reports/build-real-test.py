"""Replay maintained acceptance knowledge without resetting editorial text."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
from wxq import commit_notes, read_json
if __name__ == '__main__':
    print(commit_notes(ROOT, read_json(ROOT / 'knowledge/reports/real-video-import.json')['notes']))
