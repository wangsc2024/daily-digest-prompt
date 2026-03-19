---
name: game-workflow-design
version: "1.2.0"
description: |
  以分階段工作流設計與實作 Flutter + Flame 2D 遊戲：概念規劃→專案初始化→素材管線→核心迭代→效能→測試發布；
  整合 OpenMoji（CC BY-SA 4.0）、ZapSplat 音效與延伸免費素材來源。依據 KB 筆記 4b7bf8f5（完整 Workflow 研究）。
  **產出遊戲必須可部署於 Cloudflare Pages**（flutter build web → 靜態站點）。
  Use when: 工作流設計遊戲、Flame Engine、Flutter 遊戲、遊戲開發流程、OpenMoji、ZapSplat、跨平台 2D 遊戲、素材管線、Bonfire RPG、Cloudflare Pages。
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
cache-ttl: 0min
depends-on:
  - knowledge-query
triggers:
  - "工作流設計遊戲"
  - "以工作流設計遊戲"
  - "Flame Engine"
  - "Flutter 遊戲"
  - "flame"
  - "遊戲開發流程"
  - "遊戲工作流"
  - "OpenMoji"
  - "ZapSplat"
  - "素材管線"
  - "Bonfire"
  - "flame_svg"
  - "flame_audio"
  - "Cloudflare Pages"
---

# 以工作流設計遊戲（Flutter + Flame）

> **部署要求**：產出遊戲**必須可部署於 Cloudflare Pages**（Web 為必選目標平台）。

## 專案目錄慣例

| 情境 | 路徑 | 說明 |
|------|------|------|
| 新建 Flutter 遊戲 | `D:\Source\game\<game-name>\` 或獨立 repo | 與 `D:\Source\game` 下 HTML5 遊戲並存，以 `pubspec.yaml` 區分 |
| 既有專案 | 依任務指定 | 執行前用 `ls` 確認目錄存在 |

## 權威來源（KB）

| 項目 | 值 |
|------|-----|
| 筆記 ID | `4b7bf8f5-757b-4501-9e7c-be14fc49898e` |
| 標題關鍵字 | `Flutter + Flame Engine 遊戲開發完整 Workflow` |
| 取得方式 | `GET {knowledge_query.base_url}/api/notes/4b7bf8f5-757b-4501-9e7c-be14fc49898e` 或依 `knowledge-query` Skill 混合搜尋 |

執行複雜任務前，若本機知識庫可用，**先拉取該筆記的 `contentText`**，再依下方階段核對；細節表格、完整程式碼與連結以 KB 為準。

---

## Flame 核心速查（設計遊戲時必用）

| 概念 | 用途 |
|------|------|
| `FlameGame` | Game Loop、`onLoad` / `update(dt)` / `render` |
| FCS（Component） | 遊戲物件皆為 Component，模組化組合 |
| `World` + `CameraComponent` | 場景與視角 |
| `SpriteComponent` / `SvgComponent` | 2D 圖像（向量用 `flame_svg`） |
| Input Mixins | `TapCallbacks`、`DragCallbacks`、`KeyboardHandler` 等 |
| Hitbox + `CollisionCallbacks` | `CircleHitbox`、`RectangleHitbox`、`PolygonHitbox` |
| 延伸 | `flame_audio`、`flame_tiled`、`flame_forge2d`、`flame_bloc`、`flame_rive`、`flame_texturepacker`、`flame_network_assets` |

---

## 授權與署名（實作時不可省略）

- **OpenMoji**：CC BY-SA 4.0 — 商用可，需**署名**並注意相同方式分享；建議在「關於／致謝」放置官方署名文案（見 KB）。
- **ZapSplat**：免費會員需**署名**；Premium 免署名 — 下載頁遵守其條款。
- 其他來源（Kenney CC0、OpenGameArt、Freesound 等）逐檔確認授權欄位。

---

## Phase 0 — 概念與規劃（閘門：未完成不得進 Phase 1）

產出並寫入設計摘要（可放 repo `docs/` 或任務附檔）：

1. **類型**：平台、射擊、RPG、解謎等。
2. **核心機制**：操作方式、勝負條件、循環（core loop）。
3. **目標平台**：**Web 為必選**（Cloudflare Pages 部署）；可額外支援 iOS / Android / Desktop。
4. **素材需求清單**：視覺（角色、場景、UI、特效）、音效（動作、環境、UI）、音樂（BGM、勝利/失敗）。

---

## Phase 1 — 專案初始化

1. `flutter create --template=app <project>`，進入目錄。
2. `flutter pub add flame flame_audio`；若用 OpenMoji 向量則加 `flame_svg`；地圖／物理按需加 `flame_tiled`、`flame_forge2d`。
3. 建立資產目錄並在 `pubspec.yaml` 註冊，例如：
   - `assets/images/sprites`、`ui`、`emoji`（OpenMoji）
   - `assets/audio/sfx`、`bgm`（ZapSplat）
   - `assets/tiles`（Tiled）
4. `flutter pub get`。

---

## Phase 2 — 素材準備（Asset Pipeline）

1. **蒐集**：OpenMoji（SVG/PNG）、ZapSplat（WAV/MP3）、Kenney 等（見 KB 對照表）。
2. **處理**：TexturePacker 圖集、SVG 畫布統一、SFX 偏好 WAV / BGM 偏好 MP3、循環音樂檢查無縫 loop。
3. **匯入**：檔案放入對應 `assets/`，更新 `pubspec.yaml`，再 `flutter pub get`。

---

## Phase 3 — 核心開發（迭代循環）

依序實作並每輪可玩測試：

1. **主遊戲類**：`FlameGame`、`onLoad()` 預載、`World` + `Camera`；開發期 `debugMode = true`。
2. **元件**：Player（動畫 + 輸入 Mixin）、Enemy（行為/狀態機）、Collectible（碰撞 + `FlameAudio.play`）、HUD（Flutter Overlay）。
3. **碰撞**：Hitbox + callbacks；需完整物理時評估 `flame_forge2d`。
4. **音訊**：`FlameAudio.audioCache.loadAll` 預載；一次性 SFX vs `FlameAudio.bgm`；保留音量/靜音設定點。
5. **驗證**：Hot Reload、Hitbox 可視化、`dt` 乘上所有位移（裝置無關速度）、監看 FPS。

---

## Phase 4 — 效能優化

對照 KB 檢查：**Sprite Batching**、**Texture Atlas**、**Object Pooling**、**Viewport Culling**、**Delta Time**、**Asset Preloading（onLoad 一次載入）**。

## 品質檢查清單（發布前必過）

| 項目 | 檢查方式 |
|------|----------|
| Web 可執行 | `flutter run -d chrome` 無錯誤 |
| 60 FPS 維持 | 開發者工具 Performance 或 debug 模式 FPS 顯示 |
| 觸控支援 | 行動裝置或 Chrome 裝置模擬測試 |
| 音效可播 | SFX / BGM 正常觸發、無延遲 |
| 授權署名 | OpenMoji / ZapSplat 等已於關於頁標註 |

---

## Phase 5 — 測試與發布

1. **Web 煙霧測試**（必做）：`flutter run -d chrome` 或 `flutter run -d web-server` 驗證。
2. **Web 建置**（優化載入）：
   ```bash
   # --web-renderer html：較小 bundle、較快首載（CanvasKit 畫質佳但體積大）
   flutter build web --web-renderer html
   # 若部署於子路徑（如 /games/xxx/）：加 --base-href "/games/xxx/"
   ```
3. **Cloudflare Pages 部署**（必做）：
   ```bash
   # 方式 A：wrangler 直接部署
   npx wrangler pages deploy build/web --project-name=<project-name>

   # 方式 B：推 build/web/ 至 GitHub，由 Cloudflare Pages 連線 repo 自動部署
   ```
4. 若商業化：評估 Flutter Casual Games Toolkit（廣告、IAP、成就、分析等，見 KB）。
5. 其他平台（選做）：`flutter build appbundle` / `ios` / `windows` 等。

---

## 進階：Top-down RPG

優先評估 **Bonfire**（基於 Flame）：Tiled、跟隨攝影機、敵方 AI、光影、虛擬搖桿 — 適合原型與垂直切片。

---

## 學習路徑（與 KB 一致）

1. Codelab Brick Breaker → 2. Space Shooter → 3. Platformer → 4. Bonfire RPG → 5. 自訂擴展／多人

---

## 外部參考（速鏈）

- [Flame 文件](https://docs.flame-engine.org/)
- [Flame GitHub](https://github.com/flame-engine/flame)
- [OpenMoji](https://openmoji.org/) · [ZapSplat](https://www.zapsplat.com/)
- [Cloudflare Pages](https://developers.cloudflare.com/pages/)（部署目標）
- [Brick Breaker Codelab](https://codelabs.developers.google.com/codelabs/flutter-flame-brick-breaker)
- [awesome-flame](https://github.com/flame-engine/awesome-flame)

---

## 完成後建議

1. **驗證部署**：確認 Cloudflare Pages URL 可正常載入遊戲。
2. **知識庫回寫**：將工作流調整、套件版本與踩坑寫回知識庫（依 `knowledge-query` 匯入流程），系列標籤沿用 `flutter-flame-gamedev`。
