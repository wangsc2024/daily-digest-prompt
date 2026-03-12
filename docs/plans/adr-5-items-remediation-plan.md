# 5 項 ADR 修復方案（2026-03-12）

| ADR | 主題 | 決策 | 實作項目 | 狀態 |
|-----|------|------|----------|------|
| ADR-012 | YAML 注釋密度 20% | immediate_fix | cache-policy / scoring / notification 頂層欄位注釋 | ✅ done |
| ADR-010 | 依賴漏洞掃描 | Accepted | pyproject.toml 新增 pip-audit；check-health.ps1 新增 [依賴安全掃描] | ✅ partial（缺 CVSS 告警與核心依賴 == 鎖定） |
| ADR-011 | 行覆蓋率提升 | 分階段 | .coveragerc + pytest-cov 配置（Phase 1 基礎） | ✅ partial（基礎建設完成，待補測試案例） |
| ADR-013 | GitHub Actions CI | Accepted | .github/workflows/ci.yml 最小 CI（pytest tests/hooks/ + pip-audit） | ✅ partial（workflow 已建立，待 push 驗證） |
| ADR-015 | PS1 timeout 外部化 | Accepted | run-todoist-agent-team.ps1 從 timeouts.yaml 讀取 Phase1/Phase3/Phase2_by_task | ✅ partial（todoist-team 完成，run-agent-team.ps1 未改） |

實施順序：012 → 010 → 011 → 013 → 015（由低風險到涉及核心腳本）。  
adr-registry 已更新對應 implementation_status。
