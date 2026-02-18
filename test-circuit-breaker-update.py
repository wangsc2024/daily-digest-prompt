#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Circuit Breaker 更新腳本（測試用）
從 JSONL 日誌讀取 API 呼叫結果，更新 Circuit Breaker 狀態
"""

import json
import sys
import os
from datetime import datetime

# 添加 hooks 目錄到路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'hooks'))
from agent_guardian import CircuitBreaker

def main():
    # 讀取測試 JSONL
    jsonl_path = sys.argv[1] if len(sys.argv) > 1 else "logs/structured/test-circuit-breaker.jsonl"

    if not os.path.exists(jsonl_path):
        print(f"錯誤：找不到 JSONL 檔案 {jsonl_path}")
        sys.exit(1)

    # 統計各 API 呼叫結果
    api_results = {}
    line_count = 0

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
                line_count += 1

                # 只處理 API 呼叫
                if 'api-call' in entry.get('tags', []):
                    # 識別 API 來源
                    for tag in entry['tags']:
                        if tag in ['todoist', 'pingtung-news', 'hackernews', 'gmail']:
                            success = not entry.get('has_error', False)
                            api_results.setdefault(tag, []).append(success)
                            print(f"[{entry.get('ts', 'N/A')}] {tag}: {'成功' if success else '失敗'}")
            except json.JSONDecodeError as e:
                print(f"警告：第 {line_count} 行 JSON 解析失敗：{e}")
                continue

    print(f"\n讀取了 {line_count} 筆日誌記錄")
    print(f"識別出 {sum(len(v) for v in api_results.values())} 筆 API 呼叫\n")

    if not api_results:
        print("警告：未找到任何 API 呼叫記錄")
        return

    # 更新 Circuit Breaker
    breaker = CircuitBreaker("state/api-health.json")

    for api_source, results in api_results.items():
        # 依時間順序記錄每次呼叫
        for success in results:
            breaker.record_result(api_source, success=success)

        print(f"更新 {api_source}: {len(results)} 次呼叫，最後結果={'成功' if results[-1] else '失敗'}")

    # 顯示最終狀態
    print("\n" + "="*60)
    print("[最終 Circuit Breaker 狀態]")
    print("="*60)

    for api in ['todoist', 'pingtung-news', 'hackernews', 'gmail']:
        state = breaker.check_health(api)
        api_state_data = breaker._load_state()
        api_data = api_state_data.get(api, {})

        print(f"\n{api}:")
        print(f"  狀態: {state}")
        print(f"  失敗次數: {api_data.get('failures', 0)}")

        if api_data.get('cooldown'):
            print(f"  冷卻至: {api_data['cooldown']}")

if __name__ == '__main__':
    main()
