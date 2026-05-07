from data_loader import load_json_or_csv


def _requested_material(query, available_materials):
    if not query:
        return None

    query_lower = query.lower()
    for material in available_materials:
        if material.lower() in query_lower:
            return material
    return None


def handle_quote_comparison(order_ids, data_dir, query=None):
    """
    Analyze quotes for a specific material (extracted from query context or defaults).
    Compares suppliers based on price, lead time, risk, and quality.
    """
    quotes = load_json_or_csv(data_dir, "quotes.json")
    
    if not quotes:
        return {"error": "No quotes data found. Provide quotes.json or quotes.csv."}
    
    # Group by material
    materials = {}
    for q in quotes:
        mat = q.get("material", "Unknown")
        if mat not in materials:
            materials[mat] = []
        materials[mat].append(q)

    material_filter = _requested_material(query, materials.keys())
    if material_filter:
        materials = {material_filter: materials[material_filter]}
    
    summary = []
    for mat, mat_quotes in materials.items():
        if not mat_quotes:
            continue
            
        # Sort by risk (low < medium < high) then price
        risk_order = {"low": 0, "medium": 1, "high": 2}
        sorted_quotes = sorted(mat_quotes, key=lambda x: (risk_order.get(x.get("risk_level", "high"), 3), x.get("unit_price", 9999)))
        
        recommended = sorted_quotes[0]
        all_suppliers = mat_quotes
        
        prices = [q["unit_price"] for q in all_suppliers]
        min_price = min(prices)
        max_price = max(prices)
        price_spread = max_price - min_price
        
        lead_times = [q["lead_time_days"] for q in all_suppliers]
        avg_lead = sum(lead_times) / len(lead_times)
        
        risks = [q.get("risk_level", "unknown") for q in all_suppliers]
        high_risk_count = risks.count("high")
        
        evidence = []
        for q in sorted_quotes:
            evidence.append(f"{q['supplier']}: ${q['unit_price']}, Lead: {q['lead_time_days']}d, Risk: {q['risk_level']}, Rating: {q['quality_rating']}")
            
        decision = f"Recommended: {recommended['supplier']} for {mat}"
        confidence = "high" if recommended["risk_level"] == "low" else "medium"
        
        supplier_reply = f"Dear {recommended['supplier']},\n\nWe are considering your quote ({recommended['quote_id']}) for {mat}.\nPrice: ${recommended['unit_price']}, Lead Time: {recommended['lead_time_days']} days.\n\nPlease confirm availability.\n\nBest regards,\nProcurement Team"
        
        summary.append({
            "material": mat,
            "recommended_supplier": recommended["supplier"],
            "decision": decision,
            "confidence": confidence,
            "price_spread": round(price_spread, 2),
            "lead_time_summary": {"avg_days": round(avg_lead, 1), "min_days": min(lead_times), "max_days": max(lead_times)},
            "risks": {"high_risk_suppliers": high_risk_count, "risk_levels": risks},
            "evidence": evidence,
            "recommendation": f"Select {recommended['supplier']} for best balance of price and risk. Negotiate lead time if possible.",
            "supplier_reply_draft": supplier_reply,
            "trace": [f"loaded {len(all_suppliers)} quotes for {mat}", "sorted by risk and price", "selected recommended supplier"]
        })
        
    if len(summary) == 1:
        return summary[0]
    return {"materials": summary, "trace": ["loaded quotes", "grouped by material", "analyzed all materials"]}
