# Afu Brain → manufacturing-agent-system 對映分析

> 研究日期：2026-05-14
> 參考版本：`afu-brain` main (MASL 2026.05.07)
> 本專案狀態：P14 全部完成，HEAD `351cc00`

## A. Afu Brain 核心架構摘要

Afu Brain 是一個 **MASL (Model-Agnostic Safety Layer)** 參考實作，核心哲學是：
1. **LLM 不做不可逆決定**：模型只能「提議」(propose) 意圖與風險。
2. **Safety Gate 是確定性的**：閘道器根據策略檔 (`masl_policy.json`) 輸出 `allow` / `ask` / `block`。
3. **執行與準備分離**：即使是 `ask` (需審批)，也允許 `allowed_preparation: true` (例如：分析合約、草擬郵件)，但明確阻擋 `blocked_final_action` (例如：`external_send`)。
4. **可解釋性**：每個決定都附帶明確的 `reason`、`risk`、以及 `meaning_trace` (為什麼這樣判斷)。

---

## B. 四大面向對映分析

### 1. Decision Contract (決定合約)
| Afu Brain | 本專案現況 | 採用建議 |
|---|---|---|
| `intent` -> `risk` -> `decision` 明確三段論 | 分散在 rollout gating, guardrails, automation policy | **高價值**。目前我們的 `/run` 路由直接跳到 `skill`，缺少一個「前置決定層」統一評估 `risk` 與 `permission`。 |
| `can_execute` / `allowed_preparation` / `blocked_final_action` | 目前僅有 `approval_required` 和 `rollout_gated` | **強烈建議採用**。將「允許做準備」與「阻擋最終動作」解耦，大幅改善 Operator UX。 |
| `source_policy_version` | `config.py` 無明確版本追蹤 | 可在 `config.json` 加入 `policy_version` 欄位，方便審計。 |

### 2. Risk & Approval Ontology (風險與審批本體)
| Afu Brain | 本專案現況 | 採用建議 |
|---|---|---|
| `risk`: none / low / medium / high / critical | `risk_level` 類似，但缺乏語意連貫性 | 目前各 skill 自訂風險。建議統一抽離到 `policies/risk_ontology.json`。 |
| `decision`: allow / ask / block | 分散在 `guardrails.py` (allow/deny) 與 `rollout_profile.py` | 統一為三態輸出，可大幅簡化 `guardrails.py` 與 Dashboard 的渲染邏輯。 |
| `default-deny on ambiguity` | 預設允許 (除非被 guardrail 攔截) | 對高風險操作應改為 `default-deny`。 |

### 3. Explainability Layer (可解釋層)
| Afu Brain | 本專案現況 | 採用建議 |
|---|---|---|
| `reason`: "Contract review is legal/high-impact..." | 僅回傳 `guardrail_denied` 或 `rollout_gated` 錯誤碼 | **最高優先級**。Operator 需要知道「為什麼被 block」，而非只看 403。 |
| `meaning_trace` / `synapse_updates` | 無 | 可先實作輕量版 `decision_trace` (包含 matched rule, risk rationale)。 |
| `publication_gate` / `cost_model` | 無 | 目前不適用，屬個人助理領域。 |

### 4. P15 Candidate Mapping (P15 候選對映)
| 分類 | 項目 | 原因 |
|---|---|---|
| **立即可採用** | `Decision Contract` 前端渲染 (Dashboard 顯示 `reason` 與 `blocked_final_action`) | 純前端/API 回應增強，不改產品行為，但能解決 P13/P14 Operator 常問的「為什麼不能按」問題。 |
| **立即可採用** | `MASL` 確定性閘道器重構 `guardrails.py` | 目前 guardrail 與 server handler 耦合。抽成純函數 `evaluate_decision(intent, risk) -> Decision` 更易測試。 |
| **應先研究再採用** | `allowed_preparation` 工作流 | 需要修改 `/run` 邏輯，讓 skill 能在 `preparation` 模式下只跑分析不寫入。需小心設計。 |
| **暫不建議** | `Rolling Cognition Audit` / `synapse_updates` | 屬個人 AI 記憶與認知參數追蹤，對 B2B 製造業 Agent 關聯性低。 |
| **暫不建議** | `Afu Model` / 語音介面 | 本專案為訂單/排程/物料系統，非個人生活助理。 |

---

## C. P15 候選方向草案

**建議名稱**：`P15 Decision Governance & Explainability Layer`

**核心目標**：
將目前分散在各處的 `risk`, `approval`, `guardrail`, `rollout` 邏輯，統一收斂至一個**明確的 Decision Contract 層**，並提供完整的 Operator 可解釋性 (Explainability)。

**子項目 (Candidate Sub-tasks)**：
1. **P15-1: Unified Decision Schema** — 定義 `Decision` 資料結構 (`intent`, `risk_level`, `decision_state`, `can_prepare`, `blocked_action`, `reason`)。
2. **P15-2: MASL-style Guardrail Refactor** — 重構 `guardrails.py` 為確定性策略評估器，與 HTTP Handler 解耦。
3. **P15-3: Explainable API Responses** — 所有 403 / 409 / 審批攔截回應必須附帶 `reason` 與 `suggestion`。
4. **P15-4: Dashboard Decision Inspector** — 在 Dashboard 增加「決策檢視器」，顯示當前操作的風險評估與攔截原因。

---

## D. 第一個最小可行項目建議

**項目**：`P15-3: Explainable API Responses` (可解釋 API 回應)

**為什麼選它？**
1. **零破壞性**：不改變任何業務邏輯，只在現有 403/409 回應中增加 `reason` 與 `next_action` 欄位。
2. **Operator 痛點最直接**：目前 Dashboard 顯示「重載設定：失敗」或「待審批」，但沒告訴 Operator **為什麼**失敗、**為什麼**需要審批。
3. **為 P15-1/2 鋪路**：先讓 API 習慣輸出結構化解釋，後續再實作完整的 `Decision` 結構與 MASL 重構會更順暢。

**實作範圍**：
- 修改 `guardrails.py` 與 `rollout_profile.py` 的錯誤回應，加入 `reason` (來自 config 或 rule)。
- Dashboard `doAction()` 解析並顯示 `data.reason`。
- 3-5 個單元測試驗證解釋性欄位存在。

---

## E. Asana Sync
- Roadmap Project: `manufacturing-agent-system roadmap`
- Task to update: `1214793716355344` (P14 Research — Afu Brain Decision Contract & Safety Gate Study)
- Findings mapped to `P15 Decision Governance & Explainability Layer`.
- Recommended first item: `Explainable API Responses`.
