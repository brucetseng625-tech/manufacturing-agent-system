# 測試資料說明 — Test Data Pack

> 本文件描述 mock_data/ 中 6 組核心測試案例，供 end-to-end 測試使用。

## 案例總覽

| # | Order ID | 案例類型 | 主要測試技能 | 備註 |
|---|----------|----------|-------------|------|
| 1 | ORD-2001 | 正常單 | delivery-risk-analysis | 料況充足、產能足夠、無排程衝突 |
| 2 | ORD-2002 | 交期風險單 | delivery-risk-analysis, expedite-options | due date 很近、CNC-03 負載 95% |
| 3 | ORD-2003 | 缺料單 | material-shortage-recovery, supplier-followup-draft | Inconel 718 + Coating Ceramic Z 雙料缺 |
| 4 | ORD-2004 | 排程衝突單 | schedule-conflict-check, capacity-rebalance | 與 ORD-2002/2005 撞 CNC-03 同時段 |
| 5 | ORD-2005 | 高風險需審批 | guardrails, approval queue, audit | Urgent + VIP + 高 penalty 觸發 guardrail |
| 6 | ORD-2006 | incident closure | alerts, auto-remediation, incident report, closure | CNC-05 在 Maintenance 狀態但仍排工單 |

## 各資料檔新增內容

### orders.json（6 筆新增）

| order_id | customer | product | due_date | priority | tier | penalty |
|----------|----------|---------|----------|----------|------|---------|
| ORD-2001 | Alpha Electronics | 精密齒輪 G1 | 2026-05-25 | Normal | Standard | 800 |
| ORD-2002 | Delta Motors | 引擎支架 M5 | 2026-05-13 | High | VIP | 12,000 |
| ORD-2003 | Gamma Aerospace | 航太法蘭 F7 | 2026-05-18 | High | VIP | 8,000 |
| ORD-2004 | Epsilon Robotics | 機器人關節 J2 | 2026-05-16 | High | Standard | 3,000 |
| ORD-2005 | Omega Defense | 國防零件 D9 | 2026-05-14 | Urgent | VIP | 50,000 |
| ORD-2006 | Zeta MedTech | 醫療植入物 I3 | 2026-05-20 | Normal | Standard | 2,000 |

### work_orders.json（6 筆新增）

| wo_id | order_id | status | machine | progress | est. completion |
|-------|----------|--------|---------|----------|-----------------|
| WO-2001-A | ORD-2001 | In Progress | CNC-04 | 40% | 2026-05-22 |
| WO-2002-A | ORD-2002 | In Progress | CNC-03 | 15% | 2026-05-15 |
| WO-2003-A | ORD-2003 | Blocked | CNC-01 | 0% | 2026-05-22 |
| WO-2004-A | ORD-2004 | Queued | CNC-03 | 0% | 2026-05-18 |
| WO-2005-A | ORD-2005 | Pending | CNC-03 | 0% | 2026-05-17 |
| WO-2006-A | ORD-2006 | In Progress | CNC-05 | 10% | 2026-05-22 |

### materials.json（7 筆新增）

| order_id | material | required | available | status | lead_time | reliability |
|----------|----------|----------|-----------|--------|-----------|-------------|
| ORD-2001 | Steel Alloy 8620 | 200 | 500 | Ready | 5 days | 0.92 |
| ORD-2002 | Titanium Ti-6Al-4V | 400 | 420 | Ready | 10 days | 0.85 |
| ORD-2003 | Inconel 718 | 150 | 30 | Shortage | 21 days | 0.65 |
| ORD-2003 | Coating Ceramic Z | 200 | 50 | Shortage | 28 days | 0.55 |
| ORD-2004 | Aluminum 7075 | 300 | 800 | Ready | 4 days | 0.90 |
| ORD-2005 | Maraging Steel 300 | 1000 | 1200 | Ready | 8 days | 0.88 |
| ORD-2006 | Stainless Steel 316L | 80 | 200 | Ready | 6 days | 0.93 |

### machines.json（3 筆新增）

| machine_id | status | load | maintenance | backup | max_cap | overtime |
|------------|--------|------|-------------|--------|---------|----------|
| CNC-03 | Running | 95% | 2026-05-12 | No | 100% | No |
| CNC-04 | Idle | 30% | 2026-06-01 | Yes | 120% | Yes |
| CNC-05 | Maintenance | 0% | 2026-05-11 | No | 100% | No |

### operators.json（3 筆新增）

| operator_id | skill | shift | status |
|-------------|-------|-------|--------|
| OP-03 | CNC Turning | Day | Available |
| OP-04 | CNC Milling | Day | Absent |
| OP-05 | CNC Turning | Night | Available |

### schedule.json（6 筆新增）

排程衝突設計（CNC-03 同時段三單重疊）：

| order_id | machine | start | end | 備註 |
|----------|---------|-------|-----|------|
| ORD-2001 | CNC-04 | 5/14 08:00 | 5/14 16:00 | 正常 |
| ORD-2002 | CNC-03 | 5/12 08:00 | 5/12 16:00 | 與 ORD-2004/2005 衝突 |
| ORD-2004 | CNC-03 | 5/12 10:00 | 5/12 18:00 | 與 ORD-2002/2005 衝突 |
| ORD-2005 | CNC-03 | 5/12 12:00 | 5/12 20:00 | 與 ORD-2002/2004 衝突 |
| ORD-2006 | CNC-05 | 5/14 08:00 | 5/14 16:00 | 機台在 Maintenance |

### quotes.json（3 筆新增）

支援 ORD-2003（缺料）與 ORD-2005 的報價比較：

| quote_id | material | supplier | price | lead_time | reliability |
|----------|----------|----------|-------|-----------|-------------|
| Q-3001 | Inconel 718 | Supplier E | $350 | 21 days | 0.65 |
| Q-3002 | Inconel 718 | Supplier F | $400 | 14 days | 0.80 |
| Q-3003 | Maraging Steel 300 | Supplier A | $250 | 8 days | 0.95 |

## 測試路徑建議

### Case 1 — 正常單
```
POST /run {"query": "帮我查一下 ORD-2001 的交期風險"}
→ 應回傳 low risk
```

### Case 2 — 交期風險單
```
POST /run {"query": "ORD-2002 能不能如期交貨？"}
→ 應觸發 delivery-risk-analysis + expedite-options
```

### Case 3 — 缺料單
```
POST /run {"query": "ORD-2003 缺料怎麼辦？"}
→ 應觸發 material-shortage-recovery
POST /run {"query": "幫我跟進 ORD-2003 的供應商"}
→ 應觸發 supplier-followup-draft
```

### Case 4 — 排程衝突單
```
POST /run {"query": "ORD-2004 的排程有衝突嗎？"}
→ 應觸發 schedule-conflict-check
POST /run {"query": "怎麼解決 ORD-2004 的產能問題？"}
→ 應觸發 capacity-rebalance
```

### Case 5 — 高風險需審批
此案例需要配合 API 操作觸發 approval 流程：

1. 先觸發 delivery-risk 查詢（會因 Urgent + VIP + high penalty 觸發 high-risk routing）
2. 若系統 guardrail 設定了 `delivery-risk-analysis` 為 approval-required，則會回傳 403 並建立 approval item
3. 查詢 `GET /approvals` 確認 pending item
4. `POST /approvals/{id}/approve-and-retry` 重新執行

### Case 6 — incident closure
此案例需要配合 API 操作建立完整 incident lifecycle：

1. 先觸發 system status check（CNC-05 在 Maintenance 但仍有工單）
2. `GET /alerts` 檢查是否有 alert
3. 若有 alert，`POST /auto-remediation/evaluate` 觸發 remediation
4. `GET /incident/report` 產生 incident report
5. `POST /incident/closures/{id}` 建立 closure
6. `GET /pilot/checklist` 確認 checklist 狀態

## 備註

- 案例 5 和 6 的部分狀態（approval items、alerts、closures）需透過 API 操作建立，無法僅靠靜態資料觸發
- 資料設計沿用既有 mock_data schema，未新增欄位
- 所有 order_id 使用 ORD-20xx 範圍，避免與既有 ORD-10xx 衝突
