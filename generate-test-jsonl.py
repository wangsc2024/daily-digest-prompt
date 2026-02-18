#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
測試 JSONL 產生器
為 Circuit Breaker 測試產生不同場景的 JSONL 日誌
"""

import json
import sys
from datetime import datetime, timedelta, timezone

def generate_test_jsonl(output_path, scenario):
    """
    產生測試 JSONL 檔案

    scenario 選項:
    - single_error: 單次 API 錯誤
    - triple_failure: 連續 3 次失敗（觸發 open）
    - success_after_failure: 3 次失敗 + 1 次成功（測試 half_open → closed）
    - mixed: 混合場景（todoist 失敗，news 成功）
    """
    base_time = datetime.now(timezone(timedelta(hours=8)))  # +08:00
    entries = []

    if scenario == "single_error":
        entries.append({
            "ts": base_time.isoformat(),
            "sid": "test-001",
            "tool": "Bash",
            "event": "post",
            "summary": "curl -s -H \"Authorization: Bearer ***\" https://api.todoist.com/rest/v2/tasks",
            "output": "HTTP/1.1 401 Unauthorized\n{\"error\":\"Invalid token\"}",
            "has_error": True,
            "tags": ["api-call", "todoist", "error"]
        })

    elif scenario == "triple_failure":
        for i in range(3):
            entries.append({
                "ts": (base_time + timedelta(minutes=i)).isoformat(),
                "sid": "test-001",
                "tool": "Bash",
                "event": "post",
                "summary": f"curl todoist API (attempt {i+1}/3)",
                "output": "HTTP/1.1 401 Unauthorized\n{\"error\":\"Invalid token\"}",
                "has_error": True,
                "tags": ["api-call", "todoist", "error"]
            })

    elif scenario == "success_after_failure":
        # 3 次失敗（應該轉 open）
        for i in range(3):
            entries.append({
                "ts": (base_time + timedelta(minutes=i)).isoformat(),
                "sid": "test-001",
                "tool": "Bash",
                "event": "post",
                "summary": f"curl todoist API (failure {i+1}/3)",
                "output": "HTTP/1.1 401 Unauthorized\n{\"error\":\"Invalid token\"}",
                "has_error": True,
                "tags": ["api-call", "todoist", "error"]
            })

        # 等待 10 分鐘（模擬 cooldown 過期），然後試探成功
        entries.append({
            "ts": (base_time + timedelta(minutes=10)).isoformat(),
            "sid": "test-002",
            "tool": "Bash",
            "event": "post",
            "summary": "curl todoist API (trial after cooldown)",
            "output": '{"results":[{"id":"8217170753","content":"測試任務"}]}',
            "has_error": False,
            "tags": ["api-call", "todoist"]
        })

    elif scenario == "mixed":
        # todoist: 1 次成功 + 1 次失敗
        entries.append({
            "ts": base_time.isoformat(),
            "sid": "test-mixed-001",
            "tool": "Bash",
            "event": "post",
            "summary": "curl todoist API (success)",
            "output": '{"results":[{"id":"123"}]}',
            "has_error": False,
            "tags": ["api-call", "todoist"]
        })
        entries.append({
            "ts": (base_time + timedelta(seconds=30)).isoformat(),
            "sid": "test-mixed-001",
            "tool": "Bash",
            "event": "post",
            "summary": "curl todoist API (failure)",
            "output": "network_error: Connection timeout",
            "has_error": True,
            "tags": ["api-call", "todoist", "error"]
        })

        # pingtung-news: 1 次失敗
        entries.append({
            "ts": (base_time + timedelta(minutes=1)).isoformat(),
            "sid": "test-mixed-001",
            "tool": "Bash",
            "event": "post",
            "summary": "curl pingtung-news API",
            "output": "HTTP/1.1 500 Internal Server Error",
            "has_error": True,
            "tags": ["api-call", "pingtung-news", "error"]
        })

        # hackernews: 1 次成功
        entries.append({
            "ts": (base_time + timedelta(minutes=2)).isoformat(),
            "sid": "test-mixed-001",
            "tool": "Bash",
            "event": "post",
            "summary": "curl hackernews API",
            "output": '[{"id":42068123,"title":"AI News"}]',
            "has_error": False,
            "tags": ["api-call", "hackernews"]
        })

    else:
        print(f"錯誤：未知的場景 '{scenario}'")
        print("可用場景: single_error, triple_failure, success_after_failure, mixed")
        sys.exit(1)

    # 寫入 JSONL 檔案
    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"✅ 成功產生 {len(entries)} 筆測試記錄 → {output_path}")
    print(f"   場景: {scenario}")
    print(f"   時間範圍: {entries[0]['ts']} ~ {entries[-1]['ts']}")

def main():
    if len(sys.argv) < 3:
        print("用法: python generate-test-jsonl.py <scenario> <output_path>")
        print()
        print("場景選項:")
        print("  single_error           - 單次 API 錯誤")
        print("  triple_failure         - 連續 3 次失敗（觸發 open）")
        print("  success_after_failure  - 3 次失敗 + 1 次成功（測試恢復）")
        print("  mixed                  - 混合場景（多個 API，成功/失敗混合）")
        print()
        print("範例:")
        print("  python generate-test-jsonl.py single_error logs/structured/test-single.jsonl")
        sys.exit(1)

    scenario = sys.argv[1]
    output_path = sys.argv[2]

    generate_test_jsonl(output_path, scenario)

if __name__ == '__main__':
    main()
