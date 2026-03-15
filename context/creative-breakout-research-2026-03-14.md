# 創意打磚塊研究報告：Prism Pulse Breakout

- 日期：2026-03-14
- 任務類型：game_research
- 產出：`output/creative-breakout/index.html`

## 研究主題
將經典 Breakout 轉化為具有現代感與明確創意機制的 HTML5 Canvas 遊戲，兼顧：
1. 經典可理解性
2. 高回饋手感
3. 視覺辨識與可及性
4. 可單檔部署

## 查詢策略
- breakout game design juice it or lose it game feel
- MDN 2D breakout tutorial requestAnimationFrame canvas
- breakout powerups game design article

## 來源摘要

[MDN 2D breakout game using pure JavaScript](https://developer.mozilla.org/en-US/docs/Games/Tutorials/2D_Breakout_game_pure_JavaScript) — 品質等級 A | 持續維護
MDN 的 Breakout 教學提供經典結構：球、球拍、磚塊、碰撞與 `requestAnimationFrame` 遊戲迴圈，適合作為穩定基底。對本實作的主要啟發是以單純核心規則搭配額外效果，而不是先把系統做得過度複雜。

[Juice it or lose it — a game feel study](https://www.gdcvault.com/play/1016487/Juice-It-or-Lose) — 品質等級 B | 經典演講
此演講強調粒子、震動、音畫回饋、動態縮放等「果汁感」能大幅提升同樣規則的爽感。對本作的啟發是加入粒子尾焰、畫面震動、分數浮字與脈衝爆發，而非只停留在靜態打磚塊。

[Cornell Game Design Initiative — Breakout Powerups](https://www.cs.cornell.edu/courses/cs3152/2024sp/labs/program3/) — 品質等級 B | 2024
Cornell 的教材展示打磚塊可以透過能力道具擴充策略深度，例如球拍變寬、球速變化與特殊效果。對本作的啟發是將能力設計為「充能後主動施放」的重力脈衝，而不是只做隨機掉落。

[Breakout (video game)](https://en.wikipedia.org/wiki/Breakout_(video_game)) — 品質等級 C | 歷史整理
Breakout 的核心魅力在於極低規則門檻與即時手眼協調。這支持本作保留「接球、切角、清牆」三大核心，創意只疊加在節奏與回饋層。

## 設計結論
- 核心規則維持經典 Breakout，降低學習成本。
- 創新點放在「連擊充能 → 主動施放重力脈衝」，讓玩家有戰術決策。
- 用圖示與紋理區分磚塊，不只依賴顏色，提高辨識度。
- 以 `requestAnimationFrame`、粒子效果、震動與浮字建立現代手感。
- 成品採單一 HTML 檔，方便快速分享與部署。

## 品質自評 JSON
```json
{
  "research_topic": "創意打磚塊遊戲設計",
  "queries_used": [
    "breakout game design juice it or lose it game feel",
    "MDN 2D breakout tutorial requestAnimationFrame canvas",
    "breakout powerups game design article"
  ],
  "sources_count": 4,
  "grade_distribution": {"A": 1, "B": 2, "C": 1, "D": 0},
  "cross_verified_facts": 3,
  "unverified_claims": 0,
  "research_depth": "adequate",
  "confidence_level": "high"
}
```
