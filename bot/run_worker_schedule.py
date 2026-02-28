#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker 排程啟動腳本（Python）

定期執行 process_messages.ps1，等同於用 Windows 工作排程器每 N 分鐘跑一次 Worker。
僅使用 Python 標準庫，無需 pip install。

使用方式：
  python run_worker_schedule.py              # 預設每 10 分鐘執行一次
  python run_worker_schedule.py --min 5      # 每 5 分鐘
  python run_worker_schedule.py --once       # 只執行一次後結束（不排程）
"""
import argparse
import os
import subprocess
import sys
import time

# 專案根目錄 = 本腳本所在目錄
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKER_PS1 = os.path.join(SCRIPT_DIR, "process_messages.ps1")


def run_worker():
    """執行一次 Worker (process_messages.ps1)。"""
    if not os.path.isfile(WORKER_PS1):
        print(f"[錯誤] 找不到 Worker 腳本: {WORKER_PS1}", file=sys.stderr)
        return False
    # Windows: 用 powershell 執行 .ps1；若在非 Windows 環境可改為呼叫其他腳本
    if sys.platform == "win32":
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", WORKER_PS1]
    else:
        # 非 Windows 時若有 pwsh 可改用: ["pwsh", "-File", WORKER_PS1]
        print("[錯誤] 目前僅支援 Windows（PowerShell）。請在 Windows 上執行此排程腳本。", file=sys.stderr)
        return False
    try:
        result = subprocess.run(cmd, cwd=SCRIPT_DIR)
        return result.returncode == 0
    except Exception as e:
        print(f"[錯誤] 執行 Worker 失敗: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="定期執行 Worker (process_messages.ps1)")
    parser.add_argument(
        "--min", "-m",
        type=int,
        default=10,
        help="每隔幾分鐘執行一次（預設 10）",
    )
    parser.add_argument(
        "--once", "-o",
        action="store_true",
        help="只執行一次後結束，不排程",
    )
    args = parser.parse_args()

    interval_sec = max(1, args.min * 60)

    if args.once:
        print("[run_worker_schedule] 單次執行 Worker...")
        ok = run_worker()
        sys.exit(0 if ok else 1)

    print(f"[run_worker_schedule] 每 {args.min} 分鐘執行一次 Worker，按 Ctrl+C 結束")
    while True:
        run_worker()
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
