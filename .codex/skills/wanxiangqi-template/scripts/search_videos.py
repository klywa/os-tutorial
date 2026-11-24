"""Search one Bilibili results page with the project's existing discovery adapter."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "frontend"), str(ROOT / ".codex/skills/wanxiangqi-knowledge/scripts")]

from bilibili import Bilibili


def main():
    parser = argparse.ArgumentParser(description="按主题查找 B 站视频，供核对 BV、作者和分 P 后转写。")
    parser.add_argument("keyword", help="搜索主题")
    parser.add_argument("--page", type=int, default=1)
    args = parser.parse_args()
    if not args.keyword.strip() or args.page < 1:
        parser.error("请输入非空主题，页码从 1 开始")
    videos, more = Bilibili(root=ROOT).search_page(args.keyword.strip(), args.page, "totalrank")
    print(json.dumps({"videos": videos, "has_more": more}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
