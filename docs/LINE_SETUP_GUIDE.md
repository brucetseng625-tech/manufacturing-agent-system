# LINE Webhook 設定教學

文件名稱：LINE Webhook 設定教學  
適用模式：輕量版（Sheets / LINE）  
適用對象：導入人員、資訊人員、系統管理者

---

## 1. 文件目的

本文件用於說明如何將本系統接到 LINE 官方帳號，使使用者可透過 LINE 進行：

- 查詢待出貨
- 查詢待回覆
- 查詢缺貨
- 查看待核可項目
- 核可 / 退回指定項目

---

## 2. 需要準備的項目

設定前請先準備：

1. LINE Official Account
2. LINE Developers Channel
3. 可被 LINE 存取的 webhook URL
4. 本系統伺服器
5. 已設定好的 Google Sheets 或其他資料來源

---

## 3. 你會用到的設定值

本系統需要以下三個 LINE 設定值：

### 3.1 `channel_access_token`

用途：

- 系統回覆 LINE 訊息時使用

對應設定檔：

- `line.channel_access_token`

### 3.2 `channel_secret`

用途：

- 驗證 LINE webhook 簽章

對應設定檔：

- `line.channel_secret`

### 3.3 `allowed_user_ids`

用途：

- 限制哪些 LINE 使用者可以查詢或核可

對應設定檔：

- `line.allowed_user_ids`

### 3.4 `webhook_url`

用途：

- 讓 LINE 把使用者訊息送進本系統

對應 LINE 後台：

- Messaging API > Webhook settings > Webhook URL

---

## 3.5 這些值要去哪裡拿

### `channel_access_token`

取得位置：

1. 登入 LINE Developers Console
2. 選擇你的 Provider
3. 進入 Messaging API channel
4. 打開 `Messaging API` 頁
5. 在 Channel access token 區塊產生並複製 token

### `channel_secret`

取得位置：

1. 登入 LINE Developers Console
2. 選擇你的 Provider
3. 進入 Messaging API channel
4. 打開 `Basic settings`
5. 複製 `Channel secret`

### `allowed_user_ids`

這個值不是在後台直接列給你挑，而是要從實際互動取得。

最簡單的方式：

1. 先讓測試使用者加 bot 好友
2. 讓他傳一則訊息給 bot
3. 本系統收到 webhook 後，從 event 的 `source.userId` 取得該使用者 ID
4. 把這個值填回 `line.allowed_user_ids`

若目前先做測試，也可先暫時留空，代表不限制。

### `webhook_url`

取得方式：

1. 先決定你的系統實際對外網址
2. 本系統 endpoint 固定為：

```text
/webhook/line
```

例如：

```text
https://example.com/webhook/line
```

---

## 4. 設定檔位置

請參考：

- [config.example.json](/Users/brucetseng/Documents/Codex/2026-05-08/github-repo-https-github-com-brucetseng625/config.example.json)

LINE 區段如下：

```json
"line": {
  "channel_access_token": "",
  "channel_secret": "",
  "allowed_user_ids": [],
  "default_data_source": "sheets"
}
```

---

## 5. LINE 官方後台設定步驟

### 步驟 1：建立 LINE Channel

在 LINE Developers 建立 Messaging API channel。

完成後你會拿到：

- Channel secret
- Channel access token

### 步驟 2：設定 Webhook URL

Webhook URL 應指向：

```text
https://你的網域/webhook/line
```

例如：

```text
https://example.com/webhook/line
```

若目前在內網或測試機上，可先透過：

- 反向代理
- 公網測試網址
- Tunnel 工具

讓 LINE 能存取此 URL。

### 步驟 3：開啟 Webhook

在 LINE 後台將 Webhook 啟用。

### 步驟 4：關閉不需要的自動回應

若使用官方帳號的預設自動回覆，可能會干擾本系統的回覆。  
建議依實際情況停用或調整。

---

## 6. 本系統設定步驟

### 步驟 1：填入 token 與 secret

在實際設定檔中填入：

```json
"line": {
  "channel_access_token": "你的 access token",
  "channel_secret": "你的 channel secret",
  "allowed_user_ids": [],
  "default_data_source": "sheets"
}
```

### 步驟 2：設定允許清單

若要限制使用者，請填入：

```json
"allowed_user_ids": [
  "U1234567890abcdef",
  "Uabcdef1234567890"
]
```

說明：

- 只有在此清單中的 LINE User ID 能查詢或核可
- 若此清單為空，代表不限制（僅建議開發或測試用）

### 步驟 3：設定預設資料來源

若你希望 LINE 走輕量模式，建議設定：

```json
"default_data_source": "sheets"
```

這表示：

- LINE 訊息查詢預設會去查 Google Sheets

---

## 7. Google Sheets 搭配方式

如果 LINE 要查 Google Sheets，請一併確認：

- `google_sheets.enabled = true`
- `google_sheets.datasets.orders`
- `google_sheets.datasets.materials`
- `google_sheets.datasets.work_orders`
- 建議補齊：`google_sheets.datasets.machines`
- 建議補齊：`google_sheets.datasets.operators`
- 建議補齊：`google_sheets.datasets.schedule`
- 建議補齊：`google_sheets.datasets.quotes`

說明：

- 若只做最基本的訂單 / 缺料 / 工單查詢，前三項通常已足夠
- 若要讓系統回答交期、排程、產能、加急、報價比較等完整問題，建議把上面資料集都接齊
- 若缺少對應資料集，某些查詢可能只能部分回答，或直接失敗

詳細欄位請參考：

- [GOOGLE_SHEETS_FIELD_MAPPING.md](/Users/brucetseng/Documents/Codex/2026-05-08/github-repo-https-github-com-brucetseng625/docs/GOOGLE_SHEETS_FIELD_MAPPING.md)

---

## 8. Webhook 驗證原理

本系統會驗證 LINE 傳進來的：

- `X-Line-Signature`

驗證方式：

- 使用 `channel_secret`
- 對 request body 做 HMAC SHA256
- 若比對失敗，系統會拒絕此 webhook

這也是為什麼 `channel_secret` 必須正確設定。

---

## 9. 可用指令

### 9.1 查詢類

可直接傳送：

- `今天有哪些待出貨訂單？`
- `哪些客戶或訂單還沒回覆？`
- `目前哪些料件低於安全庫存？`
- `請整理今天新收到的訂單與後續動作`

### 9.2 核可 / 退回類

可直接傳送：

- `approval list`
- `approval <id>`
- `approve <id>`
- `reject <id> 原因`

完整範例請參考：

- [LINE_COMMAND_REFERENCE.md](/Users/brucetseng/Documents/Codex/2026-05-08/github-repo-https-github-com-brucetseng625/docs/LINE_COMMAND_REFERENCE.md)

---

## 10. 測試步驟

### 測試 1：基本查詢

在 LINE 傳送：

```text
今天有哪些待出貨訂單？
```

預期結果：

- LINE 收到系統整理結果
- 回覆中包含處理對象、系統判斷與下一步

### 測試 2：待回覆查詢

在 LINE 傳送：

```text
哪些客戶或訂單還沒回覆？
```

預期結果：

- 回覆待跟進名單或相關摘要

### 測試 3：待核可查詢

在 LINE 傳送：

```text
approval list
```

預期結果：

- 顯示待核可清單

### 測試 4：核可或退回

在 LINE 傳送：

```text
approve approval-3
```

或：

```text
reject approval-4 不建議現在執行
```

預期結果：

- 系統回覆核可或退回結果

---

## 11. 常見錯誤與排除

### 11.1 LINE 沒有回覆

請檢查：

1. Webhook URL 是否正確
2. `channel_access_token` 是否正確
3. `channel_secret` 是否正確
4. Webhook 是否已啟用
5. 伺服器是否可由外網存取

### 11.2 顯示未授權

回覆範例：

```text
❌ 未經授權的使用者。請聯繫管理員將您的 LINE User ID 加入允許清單。
```

處理方式：

1. 取得該使用者的 LINE User ID
2. 加入 `line.allowed_user_ids`
3. 重新測試

### 11.3 查得到 webhook，但沒有查到資料

請檢查：

1. `google_sheets.enabled` 是否開啟
2. `default_data_source` 是否為 `sheets`
3. Google Sheets 欄位是否正確
4. 資料內容是否存在

### 11.4 核可指令格式錯誤

系統可能回：

```text
⚠️ 未知的核可指令。支援：approval list、approval <id>、approve <id>、reject <id> [原因]
```

請重新依正確格式輸入。

---

## 12. 建議交付方式

正式交付給客戶時，建議搭配以下資料：

1. 本設定教學
2. LINE 指令範例
3. Google Sheets 欄位對照表
4. 主工作台畫面截圖
5. 輕量模式操作手冊

---

## 13. 官方參考

- LINE Messaging API getting started  
  [https://developers.line.biz/en/docs/messaging-api/getting-started/](https://developers.line.biz/en/docs/messaging-api/getting-started/)
- Channel access token  
  [https://developers.line.biz/en/docs/basics/channel-access-token/](https://developers.line.biz/en/docs/basics/channel-access-token/)
- Receive messages (webhook)  
  [https://developers.line.biz/en/docs/messaging-api/receiving-messages/](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)
- Messaging API reference  
  [https://developers.line.biz/en/reference/messaging-api/](https://developers.line.biz/en/reference/messaging-api/)
