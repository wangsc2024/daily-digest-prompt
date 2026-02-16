# 系統審查報告

## 基本資訊

| 項目 | 值 |
|------|---|
| 目標系統 | {system_name} |
| 系統路徑 | {system_path} |
| 審查日期 | {audit_date} |
| 權重模型 | {weight_profile} |
| 審查者 | Claude Code (system-audit skill v1.0.0) |

---

## 總覽

| 維度 | 權重 | 得分 | 等級 | 關鍵發現 |
|------|------|------|------|---------|
| 資訊安全 | {sec_weight}% | {sec_score}/100 | {sec_grade} | {sec_finding} |
| 系統架構 | {arch_weight}% | {arch_score}/100 | {arch_grade} | {arch_finding} |
| 系統品質 | {qual_weight}% | {qual_score}/100 | {qual_grade} | {qual_finding} |
| 系統工作流 | {wf_weight}% | {wf_score}/100 | {wf_grade} | {wf_finding} |
| 技術棧 | {tech_weight}% | {tech_score}/100 | {tech_grade} | {tech_finding} |
| 系統文件 | {doc_weight}% | {doc_score}/100 | {doc_grade} | {doc_finding} |
| 系統完成度 | {comp_weight}% | {comp_score}/100 | {comp_grade} | {comp_finding} |
| **加權總分** | **100%** | **{total_score}/100** | **{total_grade}** | |

> 校準說明：{calibration_note}

---

## 1. 資訊安全（{sec_score}/100）{sec_grade}

| 子項 | 分數 | 證據摘要 |
|------|------|---------|
| 1.1 機密管理 | {s11} | {e11} |
| 1.2 輸入驗證 | {s12} | {e12} |
| 1.3 存取控制 | {s13} | {e13} |
| 1.4 依賴安全 | {s14} | {e14} |
| 1.5 傳輸安全 | {s15} | {e15} |
| 1.6 日誌安全 | {s16} | {e16} |

**維度分數**：{sec_score}（子項平均）

**優勢**：
- {sec_strength_1}
- {sec_strength_2}

**風險**：
- {sec_risk_1}
- {sec_risk_2}

**改善建議**：
1. {sec_rec_1}
2. {sec_rec_2}

---

## 2. 系統架構（{arch_score}/100）{arch_grade}

| 子項 | 分數 | 證據摘要 |
|------|------|---------|
| 2.1 關注點分離 | {s21} | {e21} |
| 2.2 配置外部化 | {s22} | {e22} |
| 2.3 耦合度 | {s23} | {e23} |
| 2.4 可擴展性 | {s24} | {e24} |
| 2.5 容錯設計 | {s25} | {e25} |
| 2.6 單一定義處 | {s26} | {e26} |

**維度分數**：{arch_score}（子項平均）

**優勢**：
- {arch_strength_1}
- {arch_strength_2}

**風險**：
- {arch_risk_1}
- {arch_risk_2}

**改善建議**：
1. {arch_rec_1}
2. {arch_rec_2}

---

## 3. 系統品質（{qual_score}/100）{qual_grade}

| 子項 | 分數 | 證據摘要 |
|------|------|---------|
| 3.1 測試覆蓋率 | {s31} | {e31} |
| 3.2 程式碼品質 | {s32} | {e32} |
| 3.3 錯誤處理 | {s33} | {e33} |
| 3.4 品質驗證機制 | {s34} | {e34} |
| 3.5 監控與可觀測性 | {s35} | {e35} |
| 3.6 效能基準 | {s36} | {e36} |

**維度分數**：{qual_score}（子項平均）

**優勢**：
- {qual_strength_1}
- {qual_strength_2}

**風險**：
- {qual_risk_1}
- {qual_risk_2}

**改善建議**：
1. {qual_rec_1}
2. {qual_rec_2}

---

## 4. 系統工作流（{wf_score}/100）{wf_grade}

| 子項 | 分數 | 證據摘要 |
|------|------|---------|
| 4.1 自動化程度 | {s41} | {e41} |
| 4.2 並行效率 | {s42} | {e42} |
| 4.3 失敗恢復 | {s43} | {e43} |
| 4.4 狀態追蹤 | {s44} | {e44} |
| 4.5 排程管理 | {s45} | {e45} |

**維度分數**：{wf_score}（子項平均）

**優勢**：
- {wf_strength_1}
- {wf_strength_2}

**風險**：
- {wf_risk_1}
- {wf_risk_2}

**改善建議**：
1. {wf_rec_1}
2. {wf_rec_2}

---

## 5. 技術棧（{tech_score}/100）{tech_grade}

| 子項 | 分數 | 證據摘要 |
|------|------|---------|
| 5.1 技術成熟度 | {s51} | {e51} |
| 5.2 版本管理 | {s52} | {e52} |
| 5.3 工具鏈完整性 | {s53} | {e53} |
| 5.4 跨平台相容性 | {s54} | {e54} |
| 5.5 技術債務 | {s55} | {e55} |

**維度分數**：{tech_score}（子項平均）

**優勢**：
- {tech_strength_1}
- {tech_strength_2}

**風險**：
- {tech_risk_1}
- {tech_risk_2}

**改善建議**：
1. {tech_rec_1}
2. {tech_rec_2}

---

## 6. 系統文件（{doc_score}/100）{doc_grade}

| 子項 | 分數 | 證據摘要 |
|------|------|---------|
| 6.1 架構文件 | {s61} | {e61} |
| 6.2 操作手冊 | {s62} | {e62} |
| 6.3 API / 介面文件 | {s63} | {e63} |
| 6.4 配置說明 | {s64} | {e64} |
| 6.5 變更記錄 | {s65} | {e65} |

**維度分數**：{doc_score}（子項平均）

**優勢**：
- {doc_strength_1}
- {doc_strength_2}

**風險**：
- {doc_risk_1}
- {doc_risk_2}

**改善建議**：
1. {doc_rec_1}
2. {doc_rec_2}

---

## 7. 系統完成度（{comp_score}/100）{comp_grade}

| 子項 | 分數 | 證據摘要 |
|------|------|---------|
| 7.1 功能完成度 | {s71} | {e71} |
| 7.2 邊界處理 | {s72} | {e72} |
| 7.3 部署就緒 | {s73} | {e73} |
| 7.4 整合完整性 | {s74} | {e74} |
| 7.5 生產穩定性 | {s75} | {e75} |

**維度分數**：{comp_score}（子項平均）

**優勢**：
- {comp_strength_1}
- {comp_strength_2}

**風險**：
- {comp_risk_1}
- {comp_risk_2}

**改善建議**：
1. {comp_rec_1}
2. {comp_rec_2}

---

## TOP 5 改善建議

| 優先級 | 建議 | 影響維度 | 預期分數提升 | 實作難度 |
|--------|------|---------|-------------|---------|
| 1 | {top1_desc} | {top1_dim} | +{top1_gain} 分 | {top1_effort} |
| 2 | {top2_desc} | {top2_dim} | +{top2_gain} 分 | {top2_effort} |
| 3 | {top3_desc} | {top3_dim} | +{top3_gain} 分 | {top3_effort} |
| 4 | {top4_desc} | {top4_dim} | +{top4_gain} 分 | {top4_effort} |
| 5 | {top5_desc} | {top5_dim} | +{top5_gain} 分 | {top5_effort} |

---

## 審查方法論

- **評分配置**：`config/audit-scoring.yaml` v1
- **權重模型**：{weight_profile}
- **校準規則**：{calibration_rules_applied}
- **N/A 項目**：{na_count} 個（已按比例重分配權重）
- **審查工具**：Glob、Grep、Read、Bash（lint/test/audit 指令）
- **評分公式**：加權總分 = Σ (維度分數 x 維度權重 / 100)

---

## 附錄 A：校準規則觸發紀錄

| 規則 | 是否觸發 | 影響 |
|------|---------|------|
| 無自動化測試 → 品質上限 50 | {cap1} | {cap1_effect} |
| 無安全掃描/Hook → 安全上限 60 | {cap2} | {cap2_effect} |
| 無架構文件 → 文件上限 40 | {cap3} | {cap3_effect} |
| TODO/FIXME > 20 → 完成度上限 50 | {cap4} | {cap4_effect} |
| 無重試/降級 → 工作流上限 55 | {cap5} | {cap5_effect} |
| 硬編碼密碼 → 安全上限 30 | {cap6} | {cap6_effect} |

## 附錄 B：N/A 項目說明

| 子項 | 標記為 N/A 的原因 |
|------|-----------------|
| {na_items} | {na_reasons} |
