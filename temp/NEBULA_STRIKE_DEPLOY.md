# 星雲殲擊 Nebula Strike — 部署指南

## 遊戲檔案位置

遊戲已建立於 **daily-digest-prompt** 專案內：

```
temp/nebula-strike/
├── index.html   # 遊戲頁面
└── game.js     # 遊戲邏輯（requestAnimationFrame、Web Audio、粒子特效）
```

## 部署步驟（請手動執行）

### 1. 複製遊戲到 game_web

在 PowerShell 中執行：

```powershell
$src = "D:\Source\daily-digest-prompt\temp\nebula-strike"
$dst = "D:\Source\game_web\games\nebula-strike"
New-Item -ItemType Directory -Force -Path $dst
Copy-Item "$src\*" -Destination $dst -Force
```

### 2. 註冊遊戲至 gameMetadata.js

開啟 `D:\Source\game_web\js\gameMetadata.js`，在 `games` 陣列中**任一分號後**新增以下區塊（建議插在 `space-invaders` 之後）：

```javascript
  {
    id: 'nebula-strike',
    title: '星雲殲擊',
    subtitle: 'Nebula Strike',
    icon: '☄',
    description: '創意太空射擊。波次敵人、Boss 關、升級道具、連擊系統。多種敵方 AI、星雲粒子背景。',
    tags: ['射擊', '創意', '波次'],
    category: '創意',
    path: 'games/nebula-strike/',
    featured: true,
    difficulty: '中等',
    playtime: '自由遊玩'
  },
```

### 3. 建立分類（若無「創意」類別）

若 `getAllCategories()` 會自動從現有遊戲產生分類，新增此遊戲後應會出現「創意」。若希望沿用現有分類，可將 `category` 改為 `'經典'`。

### 4. Build 與部署

```powershell
cd D:\Source\game_web
npm run build
git add games/nebula-strike/ js/gameMetadata.js
git commit -m "feat: 新增星雲殲擊 Nebula Strike 創意太空射擊遊戲"
git push origin main
```

Cloudflare Pages 會自動從 GitHub 部署。

## 遊戲特色

- **敵人類型**：掃蕩者（橫移）、環繞者（左右擺動）、衝鋒者（直衝）、Boss（每 5 波）
- **道具**：散彈、速射、護盾
- **連擊系統**：連續擊殺有倍率加分
- **操作**：←→ 或 A/D 移動，空格或 ↑ 射擊，Esc 暫停
- **觸控**：支援行動裝置觸控按鈕

## 測試

```powershell
cd D:\Source\game_web
npm run build
npx serve dist
# 開啟 http://localhost:3000/games/nebula-strike/
```
