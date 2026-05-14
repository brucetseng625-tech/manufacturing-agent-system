# P15 Completion Assessment

> 日期：2026-05-14
> HEAD: `8732e53` `feat(P15-4): add dashboard decision inspector for explainability`
> 本文件不修改任何產品程式碼，僅作評估與建議。

---

## A. P15 已完成與未完成盤點

### 已完成 (Delivered)

| 項目 | Commit | 核心交付 |
|------|--------|----------|
| **P15-3 Explainable API Responses** | `af66cec` | `guardrails.py` / `rollout_profile.py` 回傳 `reason`, `decision_state`, `next_action`, `requires_approval`；`server.py` `_send_error_response` 支援 `explainability` 參數 |
| **P15-4 Dashboard Decision Inspector** | `8732e53` | `static/dashboard.html` 新增 `renderDecisionInspector()` 與 `#decision-inspector`；10 項單元測試；繁中 UI 標籤 |

### 未完成 (Pending)

| 項目 | 原始目的 | 目前狀態 |
|------|----------|----------|
| **P15-1 Unified Decision Schema** | 定義 `Decision` 資料結構 (`intent`, `risk_level`, `can_prepare`, `blocked_action` 等) | **事實上已存在** (De facto) |
| **P15-2 MASL-style Guardrail Refactor** | 重構 `guardrails.py` 為確定性策略評估器，與 HTTP Handler 解耦 | **已部分完成**，剩餘僅為程式碼清理 |

---

## B. P15-1 判斷：可延後 (De Facto Complete)

### 判斷：**不必單獨實作，可延後**

### 原因

1. **API 層面已收斂**：P15-3 已讓 `guardrails.py` 和 `rollout_profile.py` 統一輸出 `reason`, `decision_state`, `next_action`, `requires_approval` 四個欄位。這正是原研究中定義的 Decision Schema 核心。
2. **UI 層面已收斂**：P15-4 的 `renderDecisionInspector()` 能正確解析上述四個欄位並渲染為繁中結構化卡片。
3. **測試已覆蓋**：`test_guardrails.py` 和 `test_rollout_profile.py` 各有 2 項 `ExplainabilityTest`，驗證欄位存在與內容正確。
4. **「統一資料結構」已透過 API 回應格式事實存在**，不需要額外建立一個 `decision.py` 模組來「宣告」它。

### 若未來要做，最小範圍

- 將 `reason`, `decision_state`, `next_action`, `requires_approval` 封裝為一個 `@dataclass` 或 `TypedDict` (例如 `Decision`)
- 加入 type hints 與 docstrings
- 這屬於 **中長期程式碼健康度優化**，不阻擋 P16

---

## C. P15-2 判斷：可延後 (Architecturally Sound)

### 判斷：**不必重構，可延後**

### 原因

1. **現有架構已正確**：
   - `guardrails.py` 已是純函數模組 (`check_guardrail(operation, headers) -> dict or None`)，無 HTTP 依賴
   - `rollout_profile.py` 也是純函數 (`check_rollout(capability, operation) -> dict`)
   - 與 HTTP handler 的整合層 (`_check_guardrail_with_queue`) 位於 `server.py`，**邊界正確**
2. **審批隊列整合位置正確**：`_check_guardrail_with_queue` 在 handler 層呼叫 `create_pending_item`，這才是正確的分層（guardrail 核心不應知道隊列的存在）
3. **Afu Brain MASL 模式的核心訴求已滿足**：
   - 確定性評估：✅ (`guardrails.py` 是純函數)
   - 可解釋輸出：✅ (P15-3 的 `reason` 等欄位)
   - 與執行解耦：✅ (handler 負責串接，核心模組純策略)

### 唯一發現

- `server.py` line 23 與 line 31 **重複 import** 了 `from guardrails import check_guardrail, get_guardrails_status`
- 這是小問題（Python 忽略重複 import），可在方便時清理

### 若未來要做，最小範圍

- 移除 `server.py` 的 duplicate import (line 31)
- 將 `_check_guardrail_with_queue` 的 docstring 補上與 handler 邊界的明確說明
- 這屬於 **程式碼風格清理**，不阻擋 P16

---

## D. P16 Readiness Judgment

### 判斷：**可以開始 P16**

### 原因

1. **P15 核心目標已達成**：「統一 Decision Contract 層 + Operator 可解釋性」的價值已由 P15-3/P15-4 交付。P15-1 事實存在、P15-2 架構已正確。
2. **無功能缺口**：所有 guardrail、rollout、explainability 情境 (blocked / pending_approval / rollout_gated) 都有明確的 `reason` 和 `next_action` 顯示在 Dashboard 上。
3. **測試完整**：887/887 通過，包含 4 項 P15-3 和 10 項 P15-4 測試。
4. **零破壞性**：所有變更為向後相容的欄位新增。

### P16 前置條件（已完成 ✅）

- [x] P15-3 API explainability 欄位就位
- [x] P15-4 Dashboard Decision Inspector 上線
- [x] 所有測試通過
- [x] Working tree clean
- [x] Asana P15 section 已同步

### 建議的 P16 前清理（可選，不阻擋）

- `server.py` duplicate import cleanup (2 行)
- 這可以在 P16 的第一個 commit 中順便處理，不需要獨立 task

---

## E. 風險缺口

| 風險 | 嚴重度 | 緩解方式 |
|------|--------|----------|
| P15-1 未正式封裝 `Decision` 型別 | 低 | API 回應格式已事實統一；P16 開始前可補 type hints |
| `server.py` duplicate import | 極低 | 不影響功能，隨時可清理 |
| 尚未實作 `allowed_preparation` / `blocked_final_action` 分離 | 中 | 原研究中列為「應先研究再採用」，不屬 P15 必做範圍；建議在 P16 之後評估 |

---

## F. 總結

| 項目 | 判斷 | 核心理由 |
|------|------|----------|
| **P15-1** | 可延後 | Decision schema 已透過 P15-3/4 API 回應格式事實存在 |
| **P15-2** | 可延後 | Guardrail 架構已是純函數 + handler 分層，MASL 模式已滿足 |
| **P15 可視為完成？** | ✅ 是 | 核心目標 (explainability + operator visibility) 已交付 |
| **P16 可開始？** | ✅ 是 | 無阻擋、無功能缺口、測試全數通過 |
