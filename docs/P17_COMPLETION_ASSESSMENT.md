# P17 Completion Assessment

> 日期：2026-05-14
> HEAD: `6b81eb8` `feat(P17-4): add Discord approval retry visibility and handoff clarity`
> 本文件不修改任何產品程式碼，僅作評估與建議。

---

## A. P17 已完成部分

| 項目 | 狀態 | 說明 |
|------|------|------|
| **P17-1** Discord vs LINE 評估 | ✅ 完成 | 產出完整評估報告，明確建議優先導入 Discord |
| **P17-2** Discord Notification & Query Bot | ✅ 完成 | Webhook 通知 + 唯讀查詢 + explainability + allowlist + audit |
| **P17-3** Discord Approval-Assisted Flow | ✅ 完成 | 審批指令 (list/detail/approve/reject) + 身分映射 + audit |
| **P17-3 Bugfix** Error response crash | ✅ 完成 | 修正 `_send_json_response` 參數錯誤 |
| **P17-4** Discord Approval Retry Visibility | ✅ 完成 | replay visibility + handoff clarity + "審批 ≠ 執行" 區分 |

### 已交付能力總結
- ✅ **Notification-first**: 系統警報可透過 Discord webhook 發送（embed 格式）
- ✅ **Query-only**: Discord 訊息可轉為 `/run` dry_run 查詢
- ✅ **Approval-assisted**: 可查詢待審批列表、查看詳情、核准、拒絕
- ✅ **Retry visibility**: 審批後可清楚看到是否支援重試、原始請求為何、是否已執行
- ✅ **Explainability**: 所有回應包含 reason/next_action/decision_state（Discord 友善格式）
- ✅ **Security**: allowlist-based 身份映射，未授權使用者無法操作
- ✅ **Audit**: 所有 Discord 操作寫入 audit chain，channel='discord'
- ✅ **Error handling**: malformed command 回傳穩定 JSON 錯誤而非 crash

### 測試涵蓋
- Unit tests: 29 項 Discord 相關測試（通知、查詢、審批格式化、指令路由、replay visibility）
- Total: 948/948 passed
- Smoke: 112/112 passed
- Verify: 204/204 passed

---

## B. P17 未完成部分（相對於 P17-1 評估報告中的「理想狀態」）

| 項目 | 狀態 | 必要性 | 說明 |
|------|------|--------|------|
| Discord button/interaction UI | ❌ 未做 | 加值 | P17 MVP 策略明確採文字指令，按鈕留待後續 |
| Discord Role → Operator 權限映射 | ❌ 未做 | 加值 | 目前用 allowlist，足夠 MVP |
| LINE adapter | ❌ 未做 | 不在範圍 | P17-1 已建議 Discord 優先，LINE 留作後續 |
| 多輪對話上下文 | ❌ 未做 | 加值 | 不在 MVP 範圍 |
| Discord Bot 主動推播（非 webhook）| ❌ 未做 | 加值 | 目前用 webhook outbound 發送通知 |

---

## C. 風險缺口

1. **No active Discord bot process**: 目前的 Discord 整合是 passive（接收 webhook + 發送 webhook），沒有 running bot process。這表示 Discord 端需要自行設定 webhook 指向 MAS server。這對 MVP 可接受，但生產環境需要一個輕量 bot runner 或 cron 排程。
2. **Allowlist 非 Role-based**: 目前是 flat list of user IDs，沒有 Discord Role → MAS Role 的映射。對 MVP 足夠。
3. **No inbound approval trigger**: approve 動作只在 Discord 記錄狀態，不會自動觸發 approve-and-retry 執行。這是設計決策（安全邊界），不是 bug。

---

## D. P17 判定：**可視為完成**

### 原因

1. **MVP 目標已達成**: P17-1 評估報告中建議的 MVP（Notification-First + Query-Only + Approval-Assisted）已完整交付。
2. **安全邊界存在**: allowlist + audit + read-only-first 已建立最小安全邊界。
3. **Explainability 到位**: 所有 Discord 回應都包含人類可讀的說明。
4. **Handoff clarity 已補**: P17-4 補齊了「審批 ≠ 執行」的關鍵認知落差。
5. **測試涵蓋充分**: 29 項測試覆蓋所有 Discord 功能路徑。
6. **Bug 已修**: P17-3 error response crash 已修正。

### 未完成項目的定位
所有未完成項目均屬於 **加值項目 (nice-to-have)**，不阻擋 P17 收斂：
- Button UI: 是 UX 升級，不是功能缺口
- Role mapping: 是權限擴展，MVP allowlist 已夠用
- LINE: 是平行通道擴展，不是 Discord MVP 的必要條件

---

## E. 下一步主線推薦

### 🎯 明確推薦：**回到 P16-4 Isometric Scene Layout（畫面產品化升級）**

### 原因

1. **P16 當初因視覺管線升級需求而暫停**，用戶明確表示要做「像原作者那樣的視覺效果但更易上手」。
2. **P17 Discord 通道已經建立**，下一步自然是要讓 Dashboard 本身也達到產品化視覺水準。
3. **Discord + Scene View 是相輔相成**: Discord 提供「遠端操作入口」，Scene View 提供「本機視覺化儀表板」，兩者結合才是完整產品體驗。
4. **P16-4 不依賴 P17**: 場景視覺升級是純前端工作，與 Discord 整合無耦合，可獨立推進。
5. **用戶原始意圖**: 用戶提供像素風工廠佈局參考圖時，明確說「想做出原作者的效果，只是讓一般使用者更容易上手」，這個目標目前尚未達成。

### 回到 P16 後應做的項目

| 優先順序 | 項目 | 說明 |
|----------|------|------|
| **P16-4** | Isometric Scene Layout | CSS 2.5D 工廠場景佈局（非像素精靈資產） |
| **P16-5** | SVG Pipeline Connections | Agent 節點之間的 SVG 管線 + 任務光點流動動畫 |
| **P16-6** | Discord Panel Integration | 場景視圖旁並列 Discord 風格聊天面板 |

### 不推薦的選項

- ❌ **P17-5 繼續擴充 Discord**: 目前 Discord MVP 已足夠，繼續做會偏離用戶的視覺化核心需求。
- ❌ **P18 新階段**: P16 畫面產品化尚未完成，跳到 P18 是跳躍。
- ❌ **P16-4/5/6 之後才做 P17**: P17 已完成，不需要回頭。

---

## F. 總結

| 項目 | 結論 |
|------|------|
| **P17 是否完成** | ✅ 可視為完成 |
| **下一步** | 回到 P16-4 Isometric Scene Layout |
| **理由** | 用戶原始視覺化需求尚未滿足，P16 場景升級是產品化關鍵路徑 |
| **風險** | 無 blocker，可安全推進 |
