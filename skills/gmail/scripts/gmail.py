#!/usr/bin/env python3
"""
Gmail CLI - 郵件查詢命令列工具
"""

import argparse
import json
import sys

from gmail_client import GmailClient


def main():
    parser = argparse.ArgumentParser(
        description="Gmail 郵件查詢工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python gmail.py unread                      # 查詢未讀郵件
  python gmail.py unread -n 5                 # 查詢 5 封未讀
  python gmail.py important                   # 查詢重要未讀郵件
  python gmail.py search "from:boss@co.com"   # 搜尋特定寄件者
  python gmail.py search "newer_than:1d"      # 最近一天的郵件
  python gmail.py from boss@company.com       # 特定寄件者未讀郵件
""",
    )
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # === unread 命令 ===
    unread_cmd = subparsers.add_parser("unread", help="查詢未讀郵件")
    unread_cmd.add_argument(
        "-n", "--max-results", type=int, default=10, help="最多筆數 (預設: 10)"
    )

    # === important 命令 ===
    important_cmd = subparsers.add_parser("important", help="查詢重要未讀郵件")
    important_cmd.add_argument(
        "-n", "--max-results", type=int, default=10, help="最多筆數 (預設: 10)"
    )

    # === from 命令 ===
    from_cmd = subparsers.add_parser("from", help="查詢特定寄件者未讀郵件")
    from_cmd.add_argument("sender", help="寄件者 email")
    from_cmd.add_argument(
        "-n", "--max-results", type=int, default=10, help="最多筆數 (預設: 10)"
    )

    # === search 命令 ===
    search_cmd = subparsers.add_parser("search", help="使用 Gmail 搜尋語法查詢")
    search_cmd.add_argument("query", help="Gmail 搜尋語法")
    search_cmd.add_argument(
        "-n", "--max-results", type=int, default=10, help="最多筆數 (預設: 10)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        client = GmailClient()
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Gmail 認證失敗: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.command == "unread":
            messages = client.get_unread_messages(max_results=args.max_results)
        elif args.command == "important":
            messages = client.get_important_messages(max_results=args.max_results)
        elif args.command == "from":
            messages = client.get_messages_from(
                sender=args.sender, max_results=args.max_results
            )
        elif args.command == "search":
            messages = client.get_messages(
                query=args.query, max_results=args.max_results
            )
        else:
            parser.print_help()
            return

        if args.json:
            print(json.dumps(messages, ensure_ascii=False, indent=2))
        else:
            print(GmailClient.format_messages(messages))

    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
