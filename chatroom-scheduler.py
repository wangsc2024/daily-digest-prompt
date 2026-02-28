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
import time
import os
import logging
import urllib.request
import urllib.error

# 設定日誌
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_PROCESS_SCRIPT = os.path.join(PROJECT_DIR, "bot", "process_messages.ps1")
BOT_HEALTH_URL = "http://localhost:3001/api/health"
SCHEDULE_INTERVAL_MINUTES = 5
HEALTH_CHECK_TIMEOUT = 5
PROCESS_TIMEOUT_SECONDS = 300

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

    schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(trigger_process_messages)

    # 啟動時立即執行一次
    trigger_process_messages()

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    main()
