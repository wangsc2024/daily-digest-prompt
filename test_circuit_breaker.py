#!/usr/bin/env python3
"""
測試 Circuit Breaker 整合

驗證場景：
1. 初始狀態（所有 API 為 closed）
2. 連續 3 次失敗 → 轉為 open
3. cooldown 後轉為 half_open
4. 試探成功 → 轉為 closed
"""
import sys
import os
import json
from datetime import datetime, timedelta

# 設定路徑
sys.path.insert(0, "hooks")
from agent_guardian import CircuitBreaker, ErrorClassifier

def test_circuit_breaker():
    print("=== Circuit Breaker 整合測試 ===\n")

    # 清理舊狀態
    state_file = "state/api-health.json"
    if os.path.exists(state_file):
        os.remove(state_file)
        print("✓ 清理舊狀態檔案")

    # 1. 初始化
    breaker = CircuitBreaker(state_file)
    print("\n1. 初始化 Circuit Breaker")
    print(f"   狀態檔案: {state_file}")

    # 2. 測試成功案例
    print("\n2. 測試成功案例（todoist API）")
    breaker.record_result("todoist", success=True)
    state = breaker.check_health("todoist")
    print(f"   ✓ 狀態: {state} (預期: closed)")
    assert state == "closed", "初始狀態應為 closed"

    # 3. 測試連續失敗 → open
    print("\n3. 測試連續失敗（連續 3 次）")
    for i in range(3):
        breaker.record_result("todoist", success=False)
        state = breaker.check_health("todoist")
        print(f"   失敗 #{i+1}: 狀態={state}")

    assert state == "open", "連續 3 次失敗後應轉為 open"
    print("   ✓ 狀態正確轉為 open")

    # 4. 讀取狀態檔案驗證
    print("\n4. 驗證狀態檔案內容")
    with open(state_file, "r", encoding="utf-8") as f:
        saved_state = json.load(f)

    print(f"   狀態檔案內容:")
    print(f"   {json.dumps(saved_state, indent=2, ensure_ascii=False)}")

    todoist_state = saved_state.get("todoist", {})
    assert todoist_state.get("state") == "open", "狀態檔案中應為 open"
    assert todoist_state.get("failures") == 3, "失敗次數應為 3"
    assert todoist_state.get("cooldown") is not None, "應有 cooldown 時間"
    print("   ✓ 狀態檔案格式正確")

    # 5. 測試 cooldown 檢查（未過期）
    print("\n5. 測試 cooldown 檢查（未過期）")
    state = breaker.check_health("todoist")
    print(f"   ✓ 狀態: {state} (預期: open，因 cooldown 未過期)")
    assert state == "open", "cooldown 未過期應保持 open"

    # 6. 模擬 cooldown 過期 → half_open
    print("\n6. 模擬 cooldown 過期（手動修改狀態檔案）")
    with open(state_file, "r", encoding="utf-8") as f:
        saved_state = json.load(f)

    # 設定 cooldown 為過去時間
    past_time = (datetime.now() - timedelta(seconds=10)).isoformat()
    saved_state["todoist"]["cooldown"] = past_time

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(saved_state, f, ensure_ascii=False, indent=2)

    # 重新載入 breaker
    breaker = CircuitBreaker(state_file)
    state = breaker.check_health("todoist")
    print(f"   ✓ 狀態: {state} (預期: half_open)")
    assert state == "half_open", "cooldown 過期應轉為 half_open"

    # 7. 測試 half_open 試探成功 → closed
    print("\n7. 測試 half_open 試探成功")
    breaker.record_result("todoist", success=True)
    state = breaker.check_health("todoist")
    print(f"   ✓ 狀態: {state} (預期: closed)")
    assert state == "closed", "試探成功應轉為 closed"

    # 8. 驗證失敗計數已重置
    with open(state_file, "r", encoding="utf-8") as f:
        saved_state = json.load(f)

    failures = saved_state["todoist"]["failures"]
    print(f"   ✓ 失敗計數已重置: {failures} (預期: 0)")
    assert failures == 0, "試探成功後失敗計數應重置為 0"

    print("\n=== 所有測試通過 ✅ ===")

    # 9. 測試多個 API 來源
    print("\n9. 測試多個 API 來源")
    apis = ["pingtung-news", "hackernews", "gmail"]
    for api in apis:
        breaker.record_result(api, success=True)
        state = breaker.check_health(api)
        print(f"   ✓ {api}: {state}")
        assert state == "closed"

    print("\n10. 最終狀態檔案")
    with open(state_file, "r", encoding="utf-8") as f:
        final_state = json.load(f)

    print(json.dumps(final_state, indent=2, ensure_ascii=False))

    print("\n=== Circuit Breaker 整合測試完成 ===")
    return True

if __name__ == "__main__":
    try:
        test_circuit_breaker()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ 測試失敗: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 執行錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
