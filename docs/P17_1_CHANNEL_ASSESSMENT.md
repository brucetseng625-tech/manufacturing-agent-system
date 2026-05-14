# P17-1 Discord vs LINE Integration Prerequisites Assessment

> 日期：2026-05-14
> HEAD: `daa6074` `docs(P16): add completion assessment — P16 complete, P17 ready`
> 本文件不修改任何產品程式碼，僅作評估與建議。

---

## A. P17 Channel Readiness Assessment

### 現況能力盤點

從現有系統盤點，若要接外部通道（Discord/LINE），已具備以下基礎能力：

| 能力模組 | 現況 | 對外通道適配度 | 備註 |
|----------|------|----------------|------|
| **Routing** (skills/registry.py) | ✅ 成熟 | 高 | 已有 keyword-based routing，可將通道訊息轉為 query |
| **Approval** (approval_queue.py) | ✅ 成熟 | 高 | 已有待審批項目管理，可轉為通道互動（按鈕/回覆） |
| **Explainability** (P15-3/4) | ✅ 成熟 | 高 | 已有 `reason`/`next_action` 結構化輸出，適合通道訊息呈現 |
| **Audit** (audit_chain.py) | ✅ 成熟 | 高 | 已有 channel 欄位（目前僅 cli/http），可擴展為 discord/line |
| **Receipts** (execution_receipts.py) | ✅ 成熟 | 中 | 自動化執行紀錄，可轉為通道通知 |
| **Incident** (incident_report.py) | ✅ 成熟 | 中 | 事故報告摘要，適合通道警報 |
| **Rollout/Permission** (rollout_profile.py) | ✅ 成熟 | 高 | 已有能力層級控制，可限制通道操作權限 |
| **Dashboard Visibility** (P16) | ✅ 成熟 | 中 | 場景視圖提供 operator 監控，通道操作結果可同步至 Dashboard |
| **Webhook** (alert.py) | ✅ 已有 | 高 | 已有 webhook 發送能力，可直接用於 Discord/LINE webhook |
| **HTTP API** (server.py) | ✅ 成熟 | 高 | 所有能力已暴露為 REST API，通道 bot 只需轉譯 |

### 已具備能力總結
- ✅ 核心業務邏輯完整（routing, approval, explainability, audit）
- ✅ API 層已解耦（所有功能可透過 HTTP API 存取）
- ✅ Webhook 基礎存在（alert.py 已有 webhook 發送）
- ✅ 繁中輸出已成熟（所有訊息已繁體中文化）

### 尚缺能力
- ❌ 通道身份映射（目前無 Discord/LINE user ID → operator 映射）
- ❌ 通道專屬權限模型（目前僅有 API token，無通道角色權限）
- ❌ 通道訊息格式轉譯（目前輸出為 JSON/HTML，需轉為 Discord embed / LINE flex message）
- ❌ Webhook 接收端（目前僅有發送，無接收通道訊息的 endpoint）
- ❌ 會話狀態管理（通道對話需維持上下文，目前為單一 query 模式）

---

## B. Discord Assessment

### 優點
1. **Operator Usage Fit**: 工程師/PM 熟悉度高，Discord 已是開發團隊常用工具
2. **Button/Interaction Support**: Discord 支援 button、select menu、modal 互動，非常適合 approval flow（核准/退回按鈕）
3. **Webhook Native**: Discord 有原生 webhook 支援，發送通知極簡（POST JSON 即可）
4. **Rich Embeds**: Discord embed 可完美呈現 explainability 訊息（reason/next_action 結構化顯示）
5. **Role/Permission Model**: Discord 已有成熟的角色權限系統，可映射 operator/admin 權限
6. **Thread Support**: 每個訂單/事件可開獨立 thread，方便追蹤上下文
7. **低導入複雜度**: 僅需建立 bot app + webhook URL，無複雜審核流程

### 風險
1. **身分映射**: 需建立 Discord user ID → operator 映射表
2. **Rate Limiting**: Discord API 有速率限制，大量通知需排隊
3. **Privacy**: 內部製造資料不應暴露在公開伺服器

### 適用場景
- 工程師/PM 日常操作通知
- 審批互動（button 點擊核准/退回）
- 事故警報推送
- 訂單查詢與回覆

---

## C. LINE Assessment

### 優點
1. **Operator Usage Fit**: 台灣製造業現場人員（廠長、產線主管）習慣使用 LINE
2. **Push Notification**: LINE Push Message 可即時推播警報
3. **Rich Menu**: 可建立固定選單，方便非技術人員操作
4. **Broadcast**: 可同時通知多人，適合團隊警報

### 風險
1. **Approval Flow 限制**: LINE 不支援原生互動按鈕（需透過 Flex Message + reply token，實作複雜）
2. **Webhook 複雜度高**: LINE webhook 需回應 200 且在 1 秒內回覆，需非同步處理
3. **身分映射風險**: LINE 顯示名稱可能重複，需綁定 LINE user ID
4. **審核流程**: LINE Official Account 需通過審核才能使用某些 API
5. **費用**: LINE Messaging API 有大量發送費用考量
6. **Explainability 呈現**: LINE 訊息格式較扁平，難以完美呈現結構化 explainability

### 適用場景
- 現場主管警報通知
- 非技術人員簡單查詢
- 團隊廣播通知

---

## D. First Channel Recommendation

### 明確建議：先接 **Discord**

### 原因

1. **Approval Flow 適配度最高**：Discord 的 button interaction 完美匹配現有 approval queue 的核准/退回需求，LINE 需複雜的 Flex Message + reply token 處理
2. **開發複雜度最低**：Discord webhook 發送只需 POST JSON，接收訊息只需簡單的 HTTP endpoint；LINE 需處理 reply token、validating signature、1 秒回應限制等
3. **Explainability 呈現最佳**：Discord embed 可完美呈現 P15-3 的 `reason`/`next_action` 結構化訊息，LINE 訊息格式較受限
4. **Operator 群體匹配**：目前系統主要使用者為工程師/PM，Discord 已是協作工具；LINE 適合現場人員，但現場人員目前非主要操作者
5. **權限映射較簡單**：Discord role 系統可直接映射 operator/admin 權限
6. **零成本測試**：Discord bot 開發與測試完全免費，LINE 有 API 限制與潛在費用

**結論**：Discord 在技術適配度、開發複雜度、互動能力上全面領先，應作為 P17-2 第一個通道整合目標。

---

## E. P17-2 MVP Recommendation

### 建議範圍：**Notification-First + Query-Only**

### MVP 內容

| 功能 | 範圍 | 理由 |
|------|------|------|
| **1. Webhook 通知發送** | 警報推送（alert.py 擴展） | 利用現有 webhook 基礎，最小改動即可推送 Discord |
| **2. 簡單查詢** | `/run` 轉譯為 Discord 訊息 | 已有 routing，只需將 JSON 輸出轉為 embed |
| **3. Explainability 呈現** | reason/next_action 轉為 embed field | P15-3 已成熟，直接映射 |
| **4. 身份映射** | 簡易 mapping file（Discord ID → operator） | 最小必要，不需完整權限系統 |
| **暫不做** | Approval interaction、receipt 推送、incident 完整報告 | 留給 P17-3 |

### 為什麼這樣切最合理

1. **Notification-first** 風險最低：即使查詢功能有問題，通知功能仍可獨立運作
2. **Query-only** 不需改動後端：現有 `/run` API 已成熟，bot 只需做訊息轉譯
3. **Approval 留給下一期**：Discord button interaction 需額外開發，不屬於 MVP 核心
4. **可快速驗證**：1-2 天即可完成第一個 Discord bot MVP，快速取得使用者回饋

### 技術切入點
- 新增 `integrations/discord_bot.py`：處理 webhook 發送與訊息接收
- 擴展 `alert.py`：支援 Discord webhook URL
- 新增 `server.py` endpoint：`POST /webhook/discord` 接收 Discord 訊息
- 最小 mapping file：`config/discord_mapping.json`（user ID → operator name）

---

## F. 風險缺口與緩解

| 風險 | 嚴重度 | 緩解方式 |
|------|--------|----------|
| Discord user ID 映射錯誤 | 中 | 初始採用簡易 mapping file，後續可改為動態綁定流程 |
| Webhook 速率限制 | 低 | 警報推送已有 cooldown 機制，查詢為使用者觸發，頻率可控 |
| 內部資料外洩 | 中 | 限制 bot 僅在私人伺服器運作，不加入公開伺服器 |

---

## G. 總結

| 項目 | 判斷 | 核心理由 |
|------|------|----------|
| **第一個通道** | Discord | 互動能力強、開發複雜度低、explainability 呈現佳、operator 匹配度高 |
| **MVP 範圍** | Notification-first + Query-only | 風險最低、利用現有基礎、可快速驗證 |
| **P17-2 可開始？** | ✅ 是 | P16 已完成，核心能力已具備，無阻擋 |
