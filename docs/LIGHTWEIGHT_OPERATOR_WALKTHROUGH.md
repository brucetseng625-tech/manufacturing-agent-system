# Lightweight 模式實作走查

文件名稱：Lightweight 模式實作走查  
適用模式：輕量版（Sheets / LINE）  
適用對象：導入人員、測試人員、第一線操作人員

---

## 1. 目的

這份文件不是介紹概念，而是用來真的跑一次：

1. Google Sheets 作為資料來源
2. LINE 作為外部查詢入口
3. 主工作台與營運治理是否有對應資料

---

## 2. 本次已驗證成功的流程

以下流程已用本 repo 內資料實測成功：

1. 啟用 `workspace_mode = lightweight`
2. 啟用 `google_sheets.enabled = true`
3. 設定 Google Sheets 資料集
4. 啟用 LINE webhook
5. 送出 `/config/reload`
6. 用 `data_source = sheets` 呼叫 `/run`
7. 用 LINE webhook 發送查詢訊息
8. 用 `/history?channel=line` 查到剛剛的 LINE 查詢紀錄

實測成功案例：

- 查詢內容：`ORD-CSV-001 今天能不能準時出貨？`
- 結果：成功回傳 `delivery_risk_analysis`
- LINE 歷史：成功出現在 `/history?channel=line`

---

## 3. 前置條件

你至少要準備：

1. 一份可用的 `config.json`
2. Google Sheets 匯出 CSV 或可直接存取的 CSV URL
3. LINE Channel Access Token
4. LINE Channel Secret
5. 允許查詢的 LINE User ID

---

## 4. 建議資料集

最少可先接：

1. `orders`
2. `materials`
3. `work_orders`

若要讓系統能回答較完整的交期、排程、產能、加急、報價問題，建議一併接齊：

4. `machines`
5. `operators`
6. `schedule`
7. `quotes`

---

## 5. 建議設定範例

```json
{
  "runtime": {
    "default_data_source": "sheets",
    "workspace_mode": "lightweight"
  },
  "google_sheets": {
    "enabled": true,
    "datasets": {
      "orders": { "csv_url": "..." },
      "materials": { "csv_url": "..." },
      "work_orders": { "csv_url": "..." },
      "machines": { "csv_url": "..." },
      "operators": { "csv_url": "..." },
      "schedule": { "csv_url": "..." },
      "quotes": { "csv_url": "..." }
    }
  },
  "line": {
    "channel_access_token": "...",
    "channel_secret": "...",
    "allowed_user_ids": ["Uxxxxxxxx"],
    "default_data_source": "sheets"
  }
}
```

---

## 6. 啟動後第一件事

系統啟動後，若你剛改過 `config.json`，要先做一次：

`POST /config/reload`

原因：

- server 啟動後不會自動重新載入剛修改的 config
- 若沒 reload，工作台與 webhook 可能還在用舊設定

---

## 7. 測試步驟

### 7.1 先驗證設定有吃進去

看 `/config`：

應確認：

1. `runtime.workspace_mode = lightweight`
2. `runtime.default_data_source = sheets`
3. `google_sheets.enabled = true`
4. `line.allowed_user_ids` 有你要測的帳號

### 7.2 驗證 Sheets 查詢

送出：

```json
{
  "query": "ORD-CSV-001 今天能不能準時出貨？",
  "data_source": "sheets"
}
```

預期：

1. `status = success`
2. `intent = delivery_risk_analysis`
3. `data_source = google_sheets`

### 7.3 驗證 LINE webhook

用 LINE 傳：

`ORD-CSV-001 今天能不能準時出貨？`

預期：

1. webhook 可正常處理
2. LINE 可收到整理結果
3. `/history?channel=line` 查得到這次互動

### 7.4 驗證主工作台 / 營運治理

切到輕量版後，至少確認：

1. 主工作台可切換到 `輕量版（Sheets / LINE）`
2. 營運治理會顯示 Google Sheets / LINE 相關摘要
3. 最近 LINE 互動不再是永遠空白

---

## 8. 這次實測中已確認修正的問題

### 8.1 LINE 查詢原本不會進 `/history`

已修正。

現在 LINE 查詢會寫進 `runs.jsonl`，所以：

- `今天收到幾次 LINE`
- `最近有新的 LINE 互動`

這類畫面才會有資料。

### 8.2 Sheets CSV 型別轉換原本不完整

已修正。

目前已補齊常用欄位型別轉換，例如：

- `penalty_per_day`
- `expedite_cost`
- `safety_stock`
- `supplier_lead_time_days`
- `unit_cost`
- `supplier_reliability`
- `max_capacity_percent`
- `backup_available`
- `overtime_available`

---

## 9. 若測試失敗，先看哪裡

### 9.1 `/run` 回 `validation_failed`

先檢查：

1. CSV 欄位名稱是否正確
2. 數字欄位是否真的為數字格式
3. 是否少接 `machines / operators / schedule / quotes`

### 9.2 LINE webhook 有進來，但畫面沒資料

先檢查：

1. 是否已修正成會寫入 `/history?channel=line`
2. 是否真的用授權中的 `LINE User ID`
3. 是否在測完後重新整理工作台

### 9.3 改了設定但系統沒反應

先檢查：

1. 是否真的執行過 `/config/reload`
2. `/config` 顯示的是否為新設定

---

## 10. 下一步建議

這份 walkthrough 跑通後，下一步不要再先改畫面，而是先做：

1. 換成你的真實 Google Sheets
2. 換成你的真實 LINE Channel
3. 讓第一位實際使用者照這份文件跑一次
4. 再依照卡住點調整主工作台與營運治理
