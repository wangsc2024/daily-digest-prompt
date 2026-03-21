"""Generate the long-term memory optimization manual PDF."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUTPUT = Path("docs/Long_Term_Memory_Optimization_Manual.pdf")

CONTENT = [
    "長期記憶優化手冊",
    "",
    "一、設計決策",
    "- 採用 daily / weekly / monthly 三層摘要。",
    "- 預設以本機 deterministic embedding 供離線與測試使用，正式環境可切換 OpenAI、Sentence-Transformers 或 Qdrant 後端。",
    "- 過期前先備份到 JSONL，再執行刪除。",
    "",
    "二、部署步驟",
    "1. 啟動 knowledge-base-search 或 docker compose 測試環境。",
    "2. 設定 config/long_term_memory.yaml。",
    "3. 執行 demo_long_term_memory.py 驗證摘要、儲存與檢索流程。",
    "4. 將 digest_scheduler.py 併入排程器或 Windows Task Scheduler。",
    "",
    "三、環境變數",
    "- MISTRAL_API_KEY：知識庫服務既有向量檢索用。",
    "- KB_STORE_PATH：knowledge-base-search 本機儲存路徑。",
    "- 若切到外部 embedding provider，應額外提供對應 API Key。",
    "",
    "四、常見問題",
    "- Q: 為何 score 過低？",
    "  A: 先檢查查詢詞是否包含 topic / decisions / open questions 的核心詞。",
    "- Q: 為何 daily 資料被刪除？",
    "  A: 已超過 30 天 TTL，刪除前資料會先寫入 backups/long_term_memory_expired.jsonl。",
    "",
    "五、排錯指南",
    "- 確認 prompt_templates/daily_digest_prompt.txt 存在。",
    "- 確認 storage_path 可寫入。",
    "- 若改用外部向量庫，先驗證 API key、index schema 與 metadata filter。",
]


def main() -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    pdf.add_font("NotoSansTC", "", r"C:\Windows\Fonts\NotoSansTC-VF.ttf")
    pdf.set_font("NotoSansTC", size=11)
    for line in CONTENT:
        pdf.multi_cell(180, 8, line if line else " ")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT))
    print(str(OUTPUT))


if __name__ == "__main__":
    main()
