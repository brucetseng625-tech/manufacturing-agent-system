# Google Sheets 欄位對照表

文件名稱：Google Sheets 欄位對照表  
適用模式：輕量版（Sheets / LINE）  
適用對象：導入人員、資料維護人員、Google Sheets 管理者

---

## 1. 文件目的

本文件用於說明輕量模式下，Google Sheets 各資料表建議欄位、必要欄位與用途。

系統目前主要支援以下資料集：

- `orders`
- `materials`
- `work_orders`
- `machines`
- `operators`
- `schedule`
- `quotes`

---

## 2. 設定位置

Google Sheets 來源設定請參考：

- [config.example.json](/Users/brucetseng/Documents/Codex/2026-05-08/github-repo-https-github-com-brucetseng625/config.example.json)

相關區段：

- `google_sheets.enabled`
- `google_sheets.datasets.orders`
- `google_sheets.datasets.materials`
- `google_sheets.datasets.work_orders`
- `google_sheets.datasets.machines`
- `google_sheets.datasets.operators`
- `google_sheets.datasets.schedule`
- `google_sheets.datasets.quotes`

支援兩種設定方式：

1. `csv_url`
2. `sheet_id + gid`

---

## 3. orders 資料表

用途：

- 訂單整理
- 待出貨查詢
- 客戶與交期查詢
- 今日新單整理

### 3.1 必要欄位

| 欄位名稱 | 說明 | 範例 |
|---|---|---|
| `order_id` | 訂單編號 | `ORD-2026-001` |
| `customer` | 客戶名稱 | `宏達商行` |
| `product` | 品名 / 品項 | `鋁件 A-01` |
| `quantity` | 數量 | `120` |
| `due_date` | 交期 | `2026-05-25` |
| `priority` | 優先順序 | `high` |

### 3.2 建議欄位

| 欄位名稱 | 說明 | 範例 |
|---|---|---|
| `status` | 訂單狀態 | `pending` |
| `contact_status` | 客戶回覆狀態 | `waiting_reply` |
| `shipping_status` | 出貨狀態 | `ready_to_ship` |
| `notes` | 備註 | `客戶要求先出一半` |
| `customer_tier` | 客戶等級 | `VIP` |
| `penalty_per_day` | 延遲成本 | `5000` |

### 3.3 輕量模式常用查詢對應

| 使用者問題 | 主要依賴欄位 |
|---|---|
| 今天有哪些待出貨訂單？ | `order_id`, `shipping_status`, `due_date`, `customer` |
| 哪些客戶或訂單還沒回覆？ | `order_id`, `customer`, `contact_status` |
| 今天新收到哪些訂單？ | `order_id`, `customer`, `created_at` 或資料新增列 |

---

## 4. materials 資料表

用途：

- 缺貨查詢
- 安全庫存提醒
- 補料建議

### 4.1 必要欄位

| 欄位名稱 | 說明 | 範例 |
|---|---|---|
| `order_id` | 關聯訂單編號 | `ORD-2026-001` |
| `material` | 料件名稱 | `鋁板 2mm` |
| `required_qty` | 需求數量 | `300` |
| `available_qty` | 可用數量 | `120` |
| `status` | 料況狀態 | `shortage` |

### 4.2 建議欄位

| 欄位名稱 | 說明 | 範例 |
|---|---|---|
| `safety_stock` | 安全庫存 | `150` |
| `supplier` | 供應商 | `永大材料` |
| `supplier_lead_time_days` | 補貨天數 | `5` |
| `supplier_reliability` | 供應商準時率 | `0.92` |
| `unit_cost` | 單價 | `35.5` |
| `notes` | 備註 | `月底前可能延遲` |

### 4.3 輕量模式常用查詢對應

| 使用者問題 | 主要依賴欄位 |
|---|---|
| 目前哪些料件低於安全庫存？ | `material`, `available_qty`, `safety_stock`, `status` |
| 哪些料件缺貨？ | `material`, `required_qty`, `available_qty`, `status` |
| 缺貨要怎麼補救？ | `supplier`, `supplier_lead_time_days`, `notes` |

---

## 5. work_orders 資料表

用途：

- 出貨安排
- 工作重排
- 進度追蹤

### 5.1 必要欄位

| 欄位名稱 | 說明 | 範例 |
|---|---|---|
| `wo_id` | 工作單號 | `WO-2026-1001` |
| `order_id` | 關聯訂單編號 | `ORD-2026-001` |
| `status` | 工單狀態 | `in_progress` |
| `machine_id` | 機台 / 工作站 | `MC-01` |
| `progress_percent` | 完成百分比 | `65` |
| `estimated_completion` | 預估完成時間 | `2026-05-22 18:00` |

### 5.2 建議欄位

| 欄位名稱 | 說明 | 範例 |
|---|---|---|
| `owner` | 負責人 | `王小明` |
| `shift` | 班別 | `day` |
| `notes` | 備註 | `待確認最後檢驗` |
| `shipping_ready` | 是否可出貨 | `false` |

### 5.3 輕量模式常用查詢對應

| 使用者問題 | 主要依賴欄位 |
|---|---|
| 今天有哪些待出貨訂單？ | `order_id`, `status`, `shipping_ready`, `estimated_completion` |
| 現在進度到哪？ | `wo_id`, `progress_percent`, `estimated_completion` |
| 哪些工作還沒完成？ | `status`, `progress_percent` |

---

## 6. 欄位命名原則

建議採以下原則：

1. 盡量使用英文欄位名稱
2. 欄位名稱固定，不要同一欄不同寫法
3. 日期欄位盡量使用一致格式
4. 狀態欄位盡量用固定值，不要自由輸入

範例：

- `pending`
- `waiting_reply`
- `ready_to_ship`
- `shortage`
- `in_progress`
- `done`

---

## 7. 常見導入建議

### 7.1 小型團隊最小導入

最少先建三張表：

1. `orders`
2. `materials`
3. `work_orders`

如果要支援較完整的交期、產能、排程、報價與加急分析，建議再補：

4. `machines`
5. `operators`
6. `schedule`
7. `quotes`

### 7.2 若目前資料很亂

建議先做：

1. 訂單表
2. 待回覆欄位
3. 出貨狀態欄位
4. 缺料狀態欄位

不要一開始塞太多欄位。

---

## 8. 導入檢查清單

正式上線前請確認：

- 已開啟 `google_sheets.enabled`
- 已設定 `sheet_id` 或 `csv_url`
- 三張表欄位名稱一致
- 資料格式可被穩定讀取
- 主工作台在輕量模式下查得到資料
