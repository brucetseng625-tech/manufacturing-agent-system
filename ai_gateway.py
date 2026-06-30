import json
import urllib.request
import urllib.error
from config import get_config_value

class AIGateway:
    """
    AI Security Gateway & Router.
    Routes queries to Local or Cloud LLMs based on data sensitivity,
    sends queries to actual endpoints (OpenAI or Ollama), and falls back
    to a high-fidelity local simulator if API keys/servers are unavailable.
    """

    def __init__(self):
        # Load configurations
        self.openai_key = get_config_value("llm.openai_api_key", default=None, raw=True)
        self.local_url = get_config_value("llm.local_api_url", default="http://localhost:11434/v1", raw=True)
        self.local_model = get_config_value("llm.local_model", default="qwen2.5-7b", raw=True)
        self.cloud_model = get_config_value("llm.cloud_model", default="gpt-4o", raw=True)
        self.sensitivity_keywords = get_config_value(
            "llm.sensitivity_keywords", 
            default=["log", "safety", "sensor", "異常", "BOM", "code", "原始碼", "感測器", "安全"],
            raw=True
        )

    def route_query(self, query, tool_data, order_ids=None):
        """
        Classify, route, and execute LLM inference.
        Returns: {
            "response": str (LLM response),
            "route": str ("local" or "cloud"),
            "model_used": str,
            "sensitivity": str ("high" or "low"),
            "reason": str,
            "simulated": bool
        }
        """
        # 1. Sensitivity Classification
        sensitivity, reason = self._classify_sensitivity(query, order_ids)
        
        # 2. Select Route
        route = "local" if sensitivity == "high" else "cloud"
        model_name = self.local_model if route == "local" else self.cloud_model
        
        # 3. Compile System Prompt & Context
        system_prompt = self._get_system_prompt(route)
        user_prompt = f"User Query: {query}\n\nRetrieved Context (from internal tools):\n{json.dumps(tool_data, ensure_ascii=False, indent=2)}"

        # 4. Try Actual Call, fallback to Simulator if it fails
        response = None
        is_simulated = False
        
        if route == "cloud" and self.openai_key:
            response = self._call_openai(system_prompt, user_prompt)
        elif route == "local" and self.local_url:
            response = self._call_local_llm(system_prompt, user_prompt)
            
        if not response:
            response = self._simulate_llm_response(query, tool_data, route, model_name, reason)
            is_simulated = True

        # 5. DLP Post-Processing (Data Loss Prevention)
        response = self._apply_dlp_filters(response)

        return {
            "response": response,
            "route": route,
            "model_used": model_name,
            "sensitivity": sensitivity,
            "reason": reason,
            "simulated": is_simulated
        }

    def _classify_sensitivity(self, query, order_ids):
        """Analyze query keywords and order importance to determine sensitivity."""
        query_lower = query.lower()
        
        # Rule A: Sensitivity Keywords Check (e.g. sensor logs, security specs)
        for kw in self.sensitivity_keywords:
            if kw.lower() in query_lower:
                return "high", f"Query context triggers security keyword: '{kw}'"

        # Rule B: VIP Order Classification (Forced Local)
        # Check if the order belongs to a high-penalty/VIP customer (Global Tech is marked as VIP)
        if order_ids:
            # VIP Check based on order ID strings or loading order metadata
            for oid in order_ids:
                if oid == "ORD-1001":
                    return "high", "Forced Local route: target ORD-1001 contains highly-classified Global Tech (VIP) order info"
        
        return "low", "No sensitive key indices or VIP markers found. Safe to route to Cloud API."

    def _get_system_prompt(self, route):
        """Construct prompt templates based on routing agent roles."""
        if route == "local":
            return (
                "You are the Local AI Inference Core of a Manufacturing Agent System.\n"
                "Your role is to analyze sensitive internal hardware data, logs, and ERP reports.\n"
                "Ensure your reply is concise, technical, and targeted directly at engineering staff.\n"
                "Do not reference any internal database paths or server credentials.\n"
                "Please output in Traditional Chinese (繁體中文)."
            )
        else:
            return (
                "You are the Cloud AI Core of a Manufacturing Agent System.\n"
                "Your role is to write polished commercial drafts, business emails, and translation copies.\n"
                "Maintain a highly professional, polite, and persuasive tone.\n"
                "Translate or compose in the language requested by the user.\n"
                "Output in Traditional Chinese (繁體中文) or the requested language."
            )

    def _call_openai(self, system_prompt, user_prompt):
        """Connect to OpenAI API using standard urllib."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.cloud_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3
        }
        return self._send_http_request(url, headers, data)

    def _call_local_llm(self, system_prompt, user_prompt):
        """Connect to Local Ollama/Local OpenAI server using standard urllib."""
        url = f"{self.local_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        data = {
            "model": self.local_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }
        return self._send_http_request(url, headers, data)

    def _send_http_request(self, url, headers, data_dict):
        """Generic HTTP poster utilizing urllib standard library."""
        try:
            payload = json.dumps(data_dict).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=8) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                return res_body["choices"][0]["message"]["content"]
        except Exception:
            return None  # Return None to trigger fallback simulator

    def _apply_dlp_filters(self, text):
        """Data Loss Prevention: redact server credentials, file paths, and secret tokens."""
        import re
        # Mask absolute server file paths (e.g. /Users/brucetseng/...)
        masked = re.sub(r'/[a-zA-Z0-9_\-\.]+(/[a-zA-Z0-9_\-\.]+)+', '[REDACTED_SYSTEM_PATH]', text)
        # Mask API tokens or auth credentials
        masked = re.sub(r'(?i)bearer\s+[a-zA-Z0-9_\-\.]+', 'Bearer [REDACTED_TOKEN]', masked)
        return masked
    def _translate_blocker(self, b):
        if not b or not isinstance(b, str):
            return b
        if "Material shortage + below safety stock:" in b:
            detail = b.split("below safety stock: ")[1] if "below safety stock: " in b else b
            detail = detail.replace("has", "目前存量為").replace("safety stock:", "安全庫存量：")
            return f"物料短缺且低於安全庫存水準：{detail}"
        if "Material shortage:" in b:
            detail = b.split("Material shortage: ")[1] if "Material shortage: " in b else b
            detail = detail.replace("has", "目前可用存量僅有").replace("available", "")
            return f"物料庫存短缺警告：{detail}"
        if "Reorder unlikely to arrive in time:" in b:
            detail = b.split("arrive in time: ")[1] if "arrive in time: " in b else b
            detail = detail.replace("needs", "預估需要").replace("effective lead time", "有效前置時間").replace("but only", "但距離交期僅剩").replace("until due date", "")
            return f"採購前置時間不足（無法準時抵達）：{detail}"
        if "is down for maintenance until" in b:
            b_trans = b.replace("Machine", "生產機台").replace("is down for maintenance until", "正進行例行性停機維修，預計至").replace("no backup available", "目前無替代備機可用")
            return f"設備維護停機警告：{b_trans}"
        if "finishes on" in b and "after due date" in b:
            b_trans = b.replace("WO", "工單").replace("finishes on", "預期完成時間為").replace("after due date", "，已超出訂單交期")
            return f"生產進度延誤警告：{b_trans}"
        if "Operator coverage risk:" in b:
            b_trans = b.replace("Operator coverage risk:", "").replace("on", "於").replace("shift is", "班次狀態為").replace("Absent", "缺勤/未排班")
            return f"人員排班不足風險：{b_trans.strip()}"
        if "Schedule conflict:" in b:
            b_trans = b.replace("Schedule conflict:", "排程時間交叉衝突：").replace("overlap on", "重疊佔用機台").replace("from", "自").replace("to", "至").replace("Suggested action:", "。建議對策：").replace("Reschedule", "重新排程").replace("to start after", "使其於之後啟動").replace("or use alternate machine", "或調配至替代機台")
            return b_trans
        return b

    def _simulate_llm_response(self, query, tool_data, route, model, reason):
        """Fallback simulation generator synthesizing responses when endpoints are offline."""
        intent = tool_data.get("intent", "unknown")
        
        # If it's a team workflow execution
        if tool_data.get("team_name"):
            results = tool_data.get("results", {})
            summary = tool_data.get("summary", {})
            
            if route == "local":
                output = ""
                output += f"針對訂單 {tool_data.get('order_id', 'N/A')} 的全面診斷已完成。\n\n"
                
                for step_name, step_res in results.items():
                    step_status = "❌ 失敗" if "error" in step_res else "✅ 成功"
                    output += f"• 步驟 [{step_name.upper()}] - {step_status}:\n"
                    if "error" in step_res:
                        output += f"  錯誤原因: {step_res['error']}\n"
                    else:
                        decision_raw = step_res.get("decision", "無決策")
                        decision = "無法準時交貨 (cannot_ship_on_time)" if decision_raw == "cannot_ship_on_time" else "可準時交貨 (can_ship_on_time)" if decision_raw == "can_ship_on_time" else decision_raw
                        confidence = step_res.get("confidence", "N/A")
                        output += f"  判定決策: {decision} (信心度: {confidence})\n"
                        if step_res.get("blockers"):
                            translated_blockers = [self._translate_blocker(b) for b in step_res.get("blockers")]
                            output += f"  阻礙因素: {', '.join(translated_blockers)}\n"
                
                output += f"\n整合分析結論：共執行 {summary.get('total_steps')} 個程序，{summary.get('success_count')} 個步驟運算正常。後續建議請參考運維排程。"
                return output
            else:
                output = ""
                output += "親愛的管理團隊，您好：\n\n"
                output += f"已為您整合產出關於訂單 {tool_data.get('order_id', 'N/A')} 的綜合商務決策包：\n\n"
                
                if "sales" in results and "error" not in results["sales"]:
                    sales_data = results["sales"]
                    output += f"1. 客戶溝通信件草稿：\n"
                    output += f"   - 決策方向: {sales_data.get('decision')}\n"
                    output += f"   - 預估交期 (ETA): {sales_data.get('eta')}\n"
                    output += f"   - 信件主旨建議: 【Global Tech】精密軸承訂單出貨排程說明\n\n"
                
                if "risk" in results and "error" not in results["risk"]:
                    risk_data = results["risk"]
                    output += f"2. 出貨風險分析摘要：\n"
                    output += f"   - 風險等級: {risk_data.get('decision')}\n"
                    if risk_data.get("blockers"):
                        translated_blockers = [self._translate_blocker(b) for b in risk_data.get("blockers")]
                        output += f"   - 風險因子: {', '.join(translated_blockers)}\n\n"
                
                output += "後續如有任何排程調整需求，請隨時於主控台下達變更指令。"
                return output

        if route == "local":
            output = ""
            
            if intent == "delivery_risk_analysis":
                decision_raw = tool_data.get("decision", "無決策")
                decision = "無法準時交貨 (cannot_ship_on_time)" if decision_raw == "cannot_ship_on_time" else "可準時交貨 (can_ship_on_time)" if decision_raw == "can_ship_on_time" else decision_raw
                confidence = tool_data.get("confidence", "N/A")
                blockers = tool_data.get("blockers", ["無"])
                output += f"診斷訂單：{tool_data.get('order_id')}\n"
                output += f"交期判斷：{decision} (演算信心值: {confidence})\n"
                output += f"系統瓶頸分析：\n"
                for b in blockers:
                    output += f" - [異常標記] {self._translate_blocker(b)}\n"
                output += f"運維指引：若要降低延誤風險，請使用『加急方案』評估機台與加班調配。"
            
            elif intent == "schedule_conflict_check":
                status = tool_data.get("status", "無狀態")
                details = tool_data.get("details", {})
                conflicts = details.get("conflicts", [])
                output += f"排程診斷狀態：{status}\n"
                output += f"時間軸重疊檢查：偵測到 {len(conflicts)} 個排程時間交叉衝突。\n"
                for c in conflicts[:3]:
                    output += f" - [衝突事件] 工單 {c.get('work_order_id')} 佔用機台 {c.get('machine_id')} ({c.get('date')})\n"
            
            elif intent == "general_query":
                output += "【系統營運快照 (Operational Snapshot)】已載入工廠即時數據。\n\n"
                query_lower = query.lower()
                orders = tool_data.get("orders", [])
                work_orders = tool_data.get("work_orders", [])
                
                def get_status(oid):
                    wos = [w for w in work_orders if w.get("order_id") == oid]
                    if not wos:
                        return "Pending"
                    if any(w.get("status") == "In Progress" for w in wos):
                        return "in_production"
                    if any(w.get("status") == "Queued" for w in wos):
                        return "scheduled"
                    return "Pending"
                
                if "生產" in query_lower or "production" in query_lower:
                    prod_orders = [o for o in orders if get_status(o.get("order_id")) == "in_production"]
                    if prod_orders:
                        output += "目前工廠進行中的生產訂單如下：\n"
                        for o in prod_orders:
                            output += f" - 訂單 {o.get('order_id')} | 產品: {o.get('product')} | 數量: {o.get('quantity')}台 | 客戶: {o.get('customer')} | 交期: {o.get('due_date')}\n"
                    else:
                        output += "目前生產線上無進行中訂單。\n"
                elif "排程" in query_lower or "schedule" in query_lower:
                    sched_orders = [o for o in orders if get_status(o.get("order_id")) == "scheduled"]
                    if sched_orders:
                        output += "目前已排程待生產的訂單如下：\n"
                        for o in sched_orders:
                            output += f" - 訂單 {o.get('order_id')} | 產品: {o.get('product')} | 數量: {o.get('quantity')}台 | 客戶: {o.get('customer')} | 交期: {o.get('due_date')}\n"
                    else:
                        output += "目前無排程等待中的訂單。\n"
                elif "機台" in query_lower or "machine" in query_lower:
                    machines = tool_data.get("machines", [])
                    output += "工廠機台狀態：\n"
                    for m in machines[:5]:
                        output += f" - 機台 {m.get('machine_id')} ({m.get('type')}) | 狀態: {m.get('status')} | 負載: {m.get('load')}\n"
                else:
                    output += "工廠現行訂單列表：\n"
                    for o in orders:
                        status_val = get_status(o.get("order_id"))
                        status_zh = "生產中" if status_val == "in_production" else "已排程" if status_val == "scheduled" else "未啟動"
                        output += f" - 訂單 {o.get('order_id')} | 產品: {o.get('product')} | 狀態: {status_zh} | 客戶: {o.get('customer')}\n"
            
            else:
                output += f"已安全處理 [{intent}] 相關數據。\n"
                output += f"結果決策：{tool_data.get('decision', 'N/A')}\n"
                output += f"信心度：{tool_data.get('confidence', 'N/A')}"
                
            return output
            
        else:
            output = ""
            
            if intent == "sales_response_draft":
                decision = tool_data.get("decision", "無決策")
                eta = tool_data.get("eta", "N/A")
                owner = tool_data.get("owner", "N/A")
                output += "Subject: Shipment Schedule Update - Order: " + str(tool_data.get('order_id')) + "\n\n"
                output += "Dear Customer,\n\n"
                output += f"Thank you for choosing our manufacturing service. Regarding your order {tool_data.get('order_id')}, "
                output += f"our system has processed the timeline and made the following scheduling decision: {decision}.\n\n"
                output += f"The estimated delivery time (ETA) is scheduled for {eta}. Our project manager {owner} will be overseeing the production.\n\n"
                output += "Please let us know if you need to expedite or have any further inquiries.\n\n"
                output += "Best regards,\nCustomer Success Team"
                
            elif intent == "quote_comparison_summary":
                output += "【供應商報價多維分析報告】\n\n"
                details = tool_data.get("details", {})
                materials = details.get("materials", [tool_data])
                for m in materials[:2]:
                    output += f"・物料編號: {m.get('material')} ➔ 建議供應商: {m.get('recommended_supplier')}\n"
                    output += f"  評估決策: {m.get('decision')}\n"
                    output += f"  比價分析: 價格區間分布 {m.get('price_spread')}\n"
                output += "\n結論：已篩選出最佳性價比供應商，建議發送採購意向書。"
            
            elif intent == "general_query":
                output += "【系統營運快照 (Operational Snapshot)】已載入工廠即時數據。\n\n"
                query_lower = query.lower()
                orders = tool_data.get("orders", [])
                work_orders = tool_data.get("work_orders", [])
                
                def get_status(oid):
                    wos = [w for w in work_orders if w.get("order_id") == oid]
                    if not wos:
                        return "Pending"
                    if any(w.get("status") == "In Progress" for w in wos):
                        return "in_production"
                    if any(w.get("status") == "Queued" for w in wos):
                        return "scheduled"
                    return "Pending"
                
                if "生產" in query_lower or "production" in query_lower:
                    prod_orders = [o for o in orders if get_status(o.get("order_id")) == "in_production"]
                    if prod_orders:
                        output += "目前工廠進行中的生產訂單如下：\n"
                        for o in prod_orders:
                            output += f" - 訂單 {o.get('order_id')} | 產品: {o.get('product')} | 數量: {o.get('quantity')}台 | 客戶: {o.get('customer')} | 交期: {o.get('due_date')}\n"
                    else:
                        output += "目前生產線上無進行中訂單。\n"
                elif "排程" in query_lower or "schedule" in query_lower:
                    sched_orders = [o for o in orders if get_status(o.get("order_id")) == "scheduled"]
                    if sched_orders:
                        output += "目前已排程待生產的訂單如下：\n"
                        for o in sched_orders:
                            output += f" - 訂單 {o.get('order_id')} | 產品: {o.get('product')} | 數量: {o.get('quantity')}台 | 客戶: {o.get('customer')} | 交期: {o.get('due_date')}\n"
                    else:
                        output += "目前無排程等待中的訂單。\n"
                elif "機台" in query_lower or "machine" in query_lower:
                    machines = tool_data.get("machines", [])
                    output += "工廠機台狀態：\n"
                    for m in machines[:5]:
                        output += f" - 機台 {m.get('machine_id')} ({m.get('type')}) | 狀態: {m.get('status')} | 負載: {m.get('load')}\n"
                else:
                    output += "工廠現行訂單列表：\n"
                    for o in orders:
                        status_val = get_status(o.get("order_id"))
                        status_zh = "生產中" if status_val == "in_production" else "已排程" if status_val == "scheduled" else "未啟動"
                        output += f" - 訂單 {o.get('order_id')} | 產品: {o.get('product')} | 狀態: {status_zh} | 客戶: {o.get('customer')}\n"
            
            else:
                output += f"Dear Team,\n\nHere is the synthesized summary for the requested '{intent}' context:\n\n"
                output += f"Decision: {tool_data.get('decision', 'N/A')}\n"
                output += f"Estimated Time: {tool_data.get('eta', 'N/A')}\n\n"
                output += "Please proceed according to standard guidelines."
                
            return output
