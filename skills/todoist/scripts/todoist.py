#!/usr/bin/env python3
"""
Todoist CLI - 完整的 Todoist 命令列工具
"""

import os
import sys
import json
import requests
import argparse
from datetime import datetime
from typing import Optional, List, Dict, Any


class TodoistAPI:
    """Todoist REST API v2 客戶端"""
    
    BASE_URL = "https://api.todoist.com/rest/v2"
    
    PRIORITY_EMOJI = {4: "🔴", 3: "🟡", 2: "🔵", 1: "⚪"}
    PRIORITY_NAMES = {4: "p1", 3: "p2", 2: "p3", 1: "p4"}
    
    def __init__(self, api_token: str = None):
        self.api_token = api_token or os.environ.get("TODOIST_API_TOKEN", "")
        if not self.api_token:
            raise ValueError("TODOIST_API_TOKEN 未設定")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
    
    def _request(
        self, 
        method: str, 
        endpoint: str, 
        params: Dict = None,
        data: Dict = None
    ) -> Optional[Any]:
        """發送 API 請求"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                json=data,
                timeout=15
            )
            response.raise_for_status()
            
            if response.text:
                return response.json()
            return True  # 成功但無內容
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}"
            try:
                error_detail = e.response.json()
                error_msg += f": {error_detail}"
            except:
                error_msg += f": {e.response.text}"
            print(f"❌ API 錯誤: {error_msg}", file=sys.stderr)
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 網路錯誤: {e}", file=sys.stderr)
            return None
    
    # ==================== 任務操作 ====================
    
    def get_tasks(
        self, 
        filter_query: str = None,
        project_id: str = None,
        section_id: str = None,
        label: str = None
    ) -> List[Dict]:
        """取得任務列表
        
        Args:
            filter_query: 過濾條件，如 "today | overdue"
            project_id: 專案 ID
            section_id: 區段 ID
            label: 標籤名稱
        """
        params = {}
        if filter_query:
            params["filter"] = filter_query
        if project_id:
            params["project_id"] = project_id
        if section_id:
            params["section_id"] = section_id
        if label:
            params["label"] = label
        
        return self._request("GET", "tasks", params=params) or []
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """取得單一任務"""
        return self._request("GET", f"tasks/{task_id}")
    
    def create_task(
        self,
        content: str,
        description: str = None,
        project_id: str = None,
        section_id: str = None,
        parent_id: str = None,
        due_string: str = None,
        due_date: str = None,
        due_datetime: str = None,
        priority: int = 1,
        labels: List[str] = None,
        assignee_id: str = None
    ) -> Optional[Dict]:
        """建立新任務
        
        Args:
            content: 任務內容（必填）
            description: 任務描述
            project_id: 專案 ID
            section_id: 區段 ID
            parent_id: 父任務 ID（子任務）
            due_string: 自然語言日期，如 "tomorrow", "every monday"
            due_date: 日期格式，如 "2025-01-30"
            due_datetime: 日期時間，如 "2025-01-30T12:00:00Z"
            priority: 優先級 1-4（4=p1 最高）
            labels: 標籤列表
            assignee_id: 指派對象 ID
        """
        data = {"content": content}
        
        if description:
            data["description"] = description
        if project_id:
            data["project_id"] = project_id
        if section_id:
            data["section_id"] = section_id
        if parent_id:
            data["parent_id"] = parent_id
        if due_string:
            data["due_string"] = due_string
        if due_date:
            data["due_date"] = due_date
        if due_datetime:
            data["due_datetime"] = due_datetime
        if priority:
            data["priority"] = priority
        if labels:
            data["labels"] = labels
        if assignee_id:
            data["assignee_id"] = assignee_id
        
        return self._request("POST", "tasks", data=data)
    
    def update_task(
        self,
        task_id: str,
        content: str = None,
        description: str = None,
        due_string: str = None,
        priority: int = None,
        labels: List[str] = None
    ) -> Optional[Dict]:
        """更新任務"""
        data = {}
        if content:
            data["content"] = content
        if description is not None:
            data["description"] = description
        if due_string:
            data["due_string"] = due_string
        if priority:
            data["priority"] = priority
        if labels is not None:
            data["labels"] = labels
        
        return self._request("POST", f"tasks/{task_id}", data=data)
    
    def complete_task(self, task_id: str) -> bool:
        """完成任務"""
        result = self._request("POST", f"tasks/{task_id}/close")
        return result is not None
    
    def reopen_task(self, task_id: str) -> bool:
        """重新開啟任務"""
        result = self._request("POST", f"tasks/{task_id}/reopen")
        return result is not None
    
    def delete_task(self, task_id: str) -> bool:
        """刪除任務"""
        result = self._request("DELETE", f"tasks/{task_id}")
        return result is not None
    
    # ==================== 專案操作 ====================
    
    def get_projects(self) -> List[Dict]:
        """取得所有專案"""
        return self._request("GET", "projects") or []
    
    def get_project(self, project_id: str) -> Optional[Dict]:
        """取得單一專案"""
        return self._request("GET", f"projects/{project_id}")
    
    def create_project(
        self,
        name: str,
        parent_id: str = None,
        color: str = None,
        is_favorite: bool = False
    ) -> Optional[Dict]:
        """建立專案"""
        data = {"name": name}
        if parent_id:
            data["parent_id"] = parent_id
        if color:
            data["color"] = color
        if is_favorite:
            data["is_favorite"] = is_favorite
        
        return self._request("POST", "projects", data=data)
    
    # ==================== 標籤操作 ====================
    
    def get_labels(self) -> List[Dict]:
        """取得所有標籤"""
        return self._request("GET", "labels") or []
    
    def create_label(self, name: str, color: str = None) -> Optional[Dict]:
        """建立標籤"""
        data = {"name": name}
        if color:
            data["color"] = color
        return self._request("POST", "labels", data=data)
    
    # ==================== 格式化輸出 ====================
    
    def format_task(self, task: Dict, show_id: bool = False) -> str:
        """格式化單一任務"""
        priority = task.get("priority", 1)
        emoji = self.PRIORITY_EMOJI.get(priority, "⚪")
        content = task.get("content", "")
        
        # 截止日期
        due_info = ""
        due = task.get("due")
        if due:
            due_date_str = due.get("date", "")[:10]
            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                    today = datetime.now().date()
                    
                    if due_date < today:
                        due_info = " ⏰(過期!)"
                    elif due_date == today:
                        due_info = " 📅(今日)"
                    else:
                        due_info = f" 📅({due_date_str})"
                except ValueError:
                    pass
        
        # 標籤
        labels = task.get("labels", [])
        labels_str = ""
        if labels:
            labels_str = " " + " ".join([f"@{l}" for l in labels])
        
        # ID
        id_str = ""
        if show_id:
            id_str = f" [ID:{task.get('id')}]"
        
        return f"{emoji} {content}{due_info}{labels_str}{id_str}"
    
    def format_tasks(
        self, 
        tasks: List[Dict], 
        show_id: bool = False,
        sort_by_priority: bool = True
    ) -> str:
        """格式化任務列表"""
        if not tasks:
            return "✅ 無任務"
        
        if sort_by_priority:
            tasks = sorted(tasks, key=lambda x: x.get("priority", 1), reverse=True)
        
        lines = []
        for task in tasks:
            lines.append(self.format_task(task, show_id))
        
        return "\n".join(lines)
    
    def format_tasks_grouped(self, tasks: List[Dict]) -> str:
        """按優先級分組格式化"""
        if not tasks:
            return "✅ 無任務"
        
        groups = {4: [], 3: [], 2: [], 1: []}
        for task in tasks:
            p = task.get("priority", 1)
            groups[p].append(task)
        
        lines = []
        for p in [4, 3, 2, 1]:
            if groups[p]:
                emoji = self.PRIORITY_EMOJI[p]
                name = self.PRIORITY_NAMES[p]
                lines.append(f"\n{emoji} {name.upper()} ({len(groups[p])} 項)")
                for task in groups[p]:
                    lines.append(f"  • {task.get('content')}")
        
        return "\n".join(lines)


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(
        description="Todoist CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--token", help="API Token（或設定 TODOIST_API_TOKEN）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # === list 命令 ===
    list_cmd = subparsers.add_parser("list", help="列出任務")
    list_cmd.add_argument("-f", "--filter", default="today | overdue", 
                          help="過濾條件 (預設: 'today | overdue')")
    list_cmd.add_argument("-p", "--project", help="專案 ID")
    list_cmd.add_argument("--show-id", action="store_true", help="顯示任務 ID")
    list_cmd.add_argument("--group", action="store_true", help="按優先級分組")
    
    # === add 命令 ===
    add_cmd = subparsers.add_parser("add", help="新增任務")
    add_cmd.add_argument("content", help="任務內容")
    add_cmd.add_argument("-d", "--due", help="截止日期 (如: today, tomorrow, 2025-01-30)")
    add_cmd.add_argument("-p", "--priority", type=int, choices=[1,2,3,4], default=1,
                         help="優先級 (1=p4最低, 4=p1最高)")
    add_cmd.add_argument("-l", "--labels", nargs="+", help="標籤")
    add_cmd.add_argument("--project", help="專案 ID")
    add_cmd.add_argument("--desc", help="任務描述")
    
    # === complete 命令 ===
    complete_cmd = subparsers.add_parser("complete", help="完成任務")
    complete_cmd.add_argument("task_id", help="任務 ID")
    
    # === reopen 命令 ===
    reopen_cmd = subparsers.add_parser("reopen", help="重新開啟任務")
    reopen_cmd.add_argument("task_id", help="任務 ID")
    
    # === delete 命令 ===
    delete_cmd = subparsers.add_parser("delete", help="刪除任務")
    delete_cmd.add_argument("task_id", help="任務 ID")
    
    # === get 命令 ===
    get_cmd = subparsers.add_parser("get", help="取得單一任務詳情")
    get_cmd.add_argument("task_id", help="任務 ID")
    
    # === projects 命令 ===
    subparsers.add_parser("projects", help="列出所有專案")
    
    # === labels 命令 ===
    subparsers.add_parser("labels", help="列出所有標籤")
    
    # === search 命令（方便搜尋） ===
    search_cmd = subparsers.add_parser("search", help="搜尋任務（使用過濾器）")
    search_cmd.add_argument("query", help="搜尋條件")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 初始化 API
    try:
        api = TodoistAPI(args.token)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        print("請設定 TODOIST_API_TOKEN 環境變數或使用 --token 參數")
        sys.exit(1)
    
    # 執行命令
    if args.command == "list":
        tasks = api.get_tasks(
            filter_query=args.filter,
            project_id=args.project
        )
        if args.json:
            print(json.dumps(tasks, ensure_ascii=False, indent=2))
        elif args.group:
            print(f"📋 任務列表 (filter: {args.filter})")
            print(api.format_tasks_grouped(tasks))
        else:
            print(f"📋 任務列表 (filter: {args.filter})\n")
            print(api.format_tasks(tasks, show_id=args.show_id))
    
    elif args.command == "search":
        tasks = api.get_tasks(filter_query=args.query)
        if args.json:
            print(json.dumps(tasks, ensure_ascii=False, indent=2))
        else:
            print(f"🔍 搜尋結果: {args.query}\n")
            print(api.format_tasks(tasks, show_id=True))
    
    elif args.command == "add":
        task = api.create_task(
            content=args.content,
            description=args.desc,
            due_string=args.due,
            priority=args.priority,
            labels=args.labels,
            project_id=args.project
        )
        if task:
            if args.json:
                print(json.dumps(task, ensure_ascii=False, indent=2))
            else:
                print(f"✅ 已建立任務: {task.get('content')}")
                print(f"   ID: {task.get('id')}")
                if task.get("due"):
                    print(f"   截止: {task['due'].get('string')}")
        else:
            sys.exit(1)
    
    elif args.command == "complete":
        if api.complete_task(args.task_id):
            print(f"✅ 已完成任務 {args.task_id}")
        else:
            sys.exit(1)
    
    elif args.command == "reopen":
        if api.reopen_task(args.task_id):
            print(f"🔄 已重新開啟任務 {args.task_id}")
        else:
            sys.exit(1)
    
    elif args.command == "delete":
        if api.delete_task(args.task_id):
            print(f"🗑️  已刪除任務 {args.task_id}")
        else:
            sys.exit(1)
    
    elif args.command == "get":
        task = api.get_task(args.task_id)
        if task:
            if args.json:
                print(json.dumps(task, ensure_ascii=False, indent=2))
            else:
                print(f"📋 任務詳情\n")
                print(f"ID: {task.get('id')}")
                print(f"內容: {task.get('content')}")
                print(f"描述: {task.get('description') or '無'}")
                print(f"優先級: {api.PRIORITY_NAMES.get(task.get('priority', 1))}")
                print(f"標籤: {', '.join(task.get('labels', [])) or '無'}")
                if task.get("due"):
                    print(f"截止: {task['due'].get('string')} ({task['due'].get('date')})")
                print(f"URL: {task.get('url')}")
        else:
            sys.exit(1)
    
    elif args.command == "projects":
        projects = api.get_projects()
        if args.json:
            print(json.dumps(projects, ensure_ascii=False, indent=2))
        else:
            print("📁 專案列表\n")
            for p in projects:
                indent = "  " if p.get("parent_id") else ""
                star = "⭐ " if p.get("is_favorite") else ""
                print(f"{indent}• {star}{p.get('name')} (ID: {p.get('id')})")
    
    elif args.command == "labels":
        labels = api.get_labels()
        if args.json:
            print(json.dumps(labels, ensure_ascii=False, indent=2))
        else:
            print("🏷️  標籤列表\n")
            for l in labels:
                print(f"• @{l.get('name')} (ID: {l.get('id')})")


if __name__ == "__main__":
    main()
