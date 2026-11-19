"""Read formal template feedback from the project's local API."""
import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    comments = commands.add_parser("comments", help="读取正式组及话术批注")
    comments.add_argument("--status", choices=["open", "closed", "all"], default="open")
    comments.add_argument("--group-id")
    history = commands.add_parser("history", help="查看单组改动或各组最近操作")
    source = history.add_mutually_exclusive_group(required=True)
    source.add_argument("--group-id", help="查看该组管理员操作及前后内容")
    source.add_argument("--latest", action="store_true", help="只列各组最近操作摘要")
    args = parser.parse_args()
    filters = {"group_id": args.group_id} if args.group_id else {}
    if args.command == "comments":
        filters["status"] = args.status
    elif args.latest:
        filters["latest"] = "1"
    url = "http://127.0.0.1:8765/api/templates/" + args.command + "?" + urlencode(filters)
    try:
        with urlopen(url, timeout=45) as response:
            result = json.load(response)
    except HTTPError as error:
        parser.exit(1, f"反馈接口 HTTP {error.code}：{error.reason}\n")
    except URLError as error:
        parser.exit(1, f"无法读取本地反馈：{error.reason}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()