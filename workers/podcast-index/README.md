# Podcast 列表 Worker（podcast.pdoont.us.kg）

- 從 R2 讀取節目列表，渲染首頁與內嵌播放器。
- 播放次數存在 **Cloudflare KV**（binding: `KNOWLEDGE_VIEWS`），key 格式：`podcast:{R2 物件 key}`。
- 程式**不會**主動刪除或寫入 0，也**未**使用 `expirationTtl`，KV 不會自動過期。

## 為什麼點播次數會變成 0？

程式本身不會清零，常見原因如下：

| 原因 | 說明 | 建議 |
|------|------|------|
| **Worker 未綁定 KV** | 部署時 `wrangler.toml` 沒有 `[[kv_namespaces]]` 或部署來源不同 | 確認從本目錄部署，且 `wrangler.toml` 含 `KNOWLEDGE_VIEWS` |
| **KV namespace 不同** | 使用了不同的 `id`（例如新開一個 namespace） | 綁定必須是**同一個** namespace id：`4d12aabfac364c32b94e7ce6978641b0` |
| **Namespace 被刪除/重建** | 在 Cloudflare Dashboard 刪除或重建該 KV namespace | 重建後會是空的，計數從 0 開始；勿刪除既有 namespace |
| **自訂網域指向別個 Worker** | podcast.pdoont.us.kg 指到沒有 KV 或不同 KV 的 Worker | 在 Dashboard 確認該網域綁定的是本 Worker |

**如何檢查：**

1. Cloudflare Dashboard → Workers & Pages → 選 `podcast-index` → Settings → Variables → 確認 **KV Namespace Bindings** 有 `KNOWLEDGE_VIEWS`，且對應的 namespace id 為上述 id。
2. 若曾用 `tools/podcast-worker` 部署且當時有計數，兩邊需用**同一個** KV namespace id 才會看到同一份數字。

## 部署（重要：必須從本目錄執行）

**專案根目錄有另一個 `wrangler.jsonc`（Worker 名稱：daily-digest-prompt）。**  
若在根目錄執行 `npx wrangler deploy`，會部署到 **daily-digest-prompt**，不會更新 **podcast.pdoont.us.kg**。

請**一定要**在 **workers/podcast-index** 目錄下執行：

```bash
cd workers/podcast-index
npx wrangler deploy
```

或從專案根目錄用腳本（見專案根目錄 `deploy-podcast-worker.ps1`）：

```powershell
.\deploy-podcast-worker.ps1
```

部署成功後，輸出會顯示 `podcast-index` 的 URL（例如 `https://podcast-index.xxx.workers.dev`）。Custom domain `podcast.pdoont.us.kg` 需在 Dashboard 手動綁定到此 Worker。
