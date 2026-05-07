
import sys
import os
import json
from skills.delivery_risk import analyze_delivery_risk

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run_agent.py <query>")
        sys.exit(1)

    query = sys.argv[1]
    mock_data_dir = os.path.join(os.path.dirname(__file__), "mock_data")
    
    print(f"🤖 Agent Received: '{query}'")
    
    # MVP Intent Classification (Hardcoded for MVP)
    # In V2, this will be an LLM call
    order_id = "ORD-1001" # Default for MVP demo
    if "ORD-" in query:
        parts = query.split("ORD-")
        if len(parts) > 1:
            order_id = "ORD-" + parts[1].split()[0]
            
    # Routing
    if "準時" in query or "出貨" in query or "delivery" in query.lower():
        print("🔍 Routing to: delivery-risk-analysis Skill")
        result = analyze_delivery_risk(order_id, mock_data_dir)
        
        print("\n" + "="*40)
        print("📊 DECISION REPORT")
        print("="*40)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("="*40)
    else:
        print("❓ Unknown intent. MVP only supports delivery risk queries.")

if __name__ == "__main__":
    main()
