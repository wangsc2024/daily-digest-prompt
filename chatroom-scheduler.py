#!/usr/bin/env python3
"""
chatroom-scheduler.py — 聊天室任務排程器
每 5 分鐘觸發一次 bot/process_messages.ps1（若存在），
並確認 bot.js 健康狀態。

修復：
- I2: subprocess TimeoutExpired 後正確 kill 子進程
- M2: 防重入鎖，避免並行觸發
"""

import schedule
import subprocess
import sys
import time
import os
import logging
import urllib.request
import urllib.error

# 設定日誌（寫入 bot/logs/ 目錄）
# Windows 上 Start-Process -WindowStyle Hidden 啟動的進程沒有 console，
# StreamHandler 寫入 sys.stderr 會觸發異常導致進程崩潰，故僅在 stderr 可用時才加。
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot", "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "chatroom-scheduler.log")

_handlers: list[logging.Handler] = [
    logging.FileHandler(_log_file, encoding="utf-8"),
]
if sys.stderr is not None and hasattr(sys.stderr, "write"):
    try:
        sys.stderr.write("")
        _handlers.append(logging.StreamHandler())
    except (OSError, ValueError):
        pass

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=_handlers)
logger = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_PROCESS_SCRIPT = os.path.join(PROJECT_DIR, "bot", "process_messages.ps1")
BOT_HEALTH_URL = "http://localhost:3001/api/health"
SCHEDULE_INTERVAL_MINUTES = 5
HEALTH_CHECK_TIMEOUT = 5
PROCESS_TIMEOUT_SECONDS = 1800  # 30 min：研究型任務含 kb-strategist + claude -p 實測需 11-17 min

# M2 修復：防重入 flag
_is_running = False


def check_bot_health() -> bool:
    """檢查 bot.js 是否運行中。"""
    try:
        req = urllib.request.Request(BOT_HEALTH_URL)
        with urllib.request.urlopen(req, timeout=HEALTH_CHECK_TIMEOUT) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def trigger_process_messages():
    """觸發 bot/process_messages.ps1 處理聊天室任務。"""
    global _is_running

    # M2 修復：防重入保護
    if _is_running:
        logger.info("上輪仍在執行，跳過本輪觸發")
        return

    if not os.path.exists(BOT_PROCESS_SCRIPT):
        logger.debug("bot/process_messages.ps1 不存在，跳過")
        return

    if not check_bot_health():
        logger.info("bot.js 未啟動，跳過本輪處理")
        return

    logger.info("觸發 process_messages.ps1")
    _is_running = True
    try:
        # I2 修復：改用 Popen + communicate 以便 TimeoutExpired 後正確 kill
        proc = subprocess.Popen(
            ["pwsh", "-ExecutionPolicy", "Bypass", "-File", BOT_PROCESS_SCRIPT],
            cwd=PROJECT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            _stdout, stderr = proc.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
            if proc.returncode == 0:
                logger.info("process_messages.ps1 完成")
            else:
                stderr_snippet = (stderr or "")[:300]
                logger.error(f"process_messages.ps1 失敗（code={proc.returncode}）: {stderr_snippet}")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()  # 清空 pipe 避免 deadlock
            logger.error(f"process_messages.ps1 超時（{PROCESS_TIMEOUT_SECONDS}s），已強制終止")
    except Exception as exc:
        logger.error(f"process_messages.ps1 例外: {exc}")
    finally:
        _is_running = False


def main():
    logger.info(f"Chatroom scheduler 啟動（每 {SCHEDULE_INTERVAL_MINUTES} 分鐘執行）")
    logger.info(f"專案目錄: {PROJECT_DIR}")
    logger.info(f"Python: {sys.executable}, PID: {os.getpid()}")

    schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(trigger_process_messages)

    trigger_process_messages()

    logger.info("進入主迴圈")
    loop_count = 0
    while True:
        schedule.run_pending()
        time.sleep(10)
        loop_count += 1
        if loop_count % 30 == 0:  # ~5 min
            logger.info(f"心跳: 迴圈 #{loop_count}, PID {os.getpid()}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("chatroom-scheduler 異常退出")
        raise
    except KeyboardInterrupt:
        logger.info("chatroom-scheduler 收到中斷信號，正常退出")
    finally:
        logger.info(f"chatroom-scheduler 結束 (PID {os.getpid()})")
