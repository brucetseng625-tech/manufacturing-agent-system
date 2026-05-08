from data_loader import load_json_or_csv
from skills.schema import normalize_skill_response


def _safe_float(value, default=0.0):
    """Safely convert a value to float, handling string inputs from CSV."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value, default=0):
    """Safely convert a value to int, handling string inputs from CSV."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _requested_material(query, available_materials):
    if not query:
        return None

    query_lower = query.lower()
    for material in available_materials:
        if material.lower() in query_lower:
            return material
    return None


def _score_supplier(quote, price_range, lead_time_range):
    """
    Score a supplier quote on a 0–100 scale using weighted criteria.

    Weights:
    - Price: 30% (lower is better)
    - Supplier reliability: 25% (higher is better)
    - Quality rating: 20% (higher is better, normalized to 0–1 from 0–5 scale)
    - Lead time: 15% (lower is better)
    - Risk level: 10% (low=1.0, medium=0.5, high=0.0)

    Returns: (total_score, breakdown_dict)
    """
    unit_price = _safe_float(quote.get("unit_price"), 9999)
    reliability = _safe_float(quote.get("supplier_reliability"), None)
    quality = _safe_float(quote.get("quality_rating"), 0) / 5.0  # Normalize 0–5 to 0–1
    lead_time = _safe_int(quote.get("lead_time_days"), 999)
    risk = quote.get("risk_level", "high").lower()

    # Price score: 1.0 = cheapest, 0.0 = most expensive
    price_max, price_min = price_range
    if price_max == price_min:
        price_score = 1.0
    else:
        price_score = 1.0 - (unit_price - price_min) / (price_max - price_min)

    # Reliability score: use provided value, fallback to inverse of risk
    if reliability is not None:
        reliability_score = reliability
    else:
        # Fallback: derive from risk_level if reliability not available
        risk_fallback = {"low": 0.9, "medium": 0.7, "high": 0.4}
        reliability_score = risk_fallback.get(risk, 0.5)

    # Quality score: already normalized 0–1
    quality_score = min(max(quality, 0), 1.0)

    # Lead time score: 1.0 = fastest, 0.0 = slowest
    lt_max, lt_min = lead_time_range
    if lt_max == lt_min:
        lead_time_score = 1.0
    else:
        lead_time_score = 1.0 - (lead_time - lt_min) / (lt_max - lt_min)

    # Risk score: categorical
    risk_scores = {"low": 1.0, "medium": 0.5, "high": 0.0}
    risk_score = risk_scores.get(risk, 0.0)

    total = (
        0.30 * price_score +
        0.25 * reliability_score +
        0.20 * quality_score +
        0.15 * lead_time_score +
        0.10 * risk_score
    )

    return round(total * 100, 1), {
        "price_score": round(price_score * 100, 1),
        "reliability_score": round(reliability_score * 100, 1),
        "quality_score": round(quality_score * 100, 1),
        "lead_time_score": round(lead_time_score * 100, 1),
        "risk_score": round(risk_score * 100, 1),
    }


def handle_quote_comparison(order_ids, data_dir, query=None):
    """
    Analyze quotes for a specific material (extracted from query context or defaults).
    Compares suppliers using a weighted scoring system:
    - Price (30%), Supplier Reliability (25%), Quality (20%), Lead Time (15%), Risk (10%).
    """
    quotes = load_json_or_csv(data_dir, "quotes.json")

    if not quotes:
        return {"error": "No quotes data found. Provide quotes.json or quotes.csv."}

    # Normalize numeric types for CSV sources
    for q in quotes:
        q["unit_price"] = _safe_float(q.get("unit_price"), 0)
        q["lead_time_days"] = _safe_int(q.get("lead_time_days"), 0)
        q["quality_rating"] = _safe_float(q.get("quality_rating"), 0)
        q["moq"] = _safe_int(q.get("moq"), 0)
        if "supplier_reliability" in q:
            q["supplier_reliability"] = _safe_float(q["supplier_reliability"], None)

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

        prices = [q["unit_price"] for q in mat_quotes]
        price_range = (max(prices), min(prices))  # (max, min) for score calc

        lead_times = [q["lead_time_days"] for q in mat_quotes]
        lead_time_range = (max(lead_times), min(lead_times))

        # Score each supplier
        scored = []
        for q in mat_quotes:
            total_score, breakdown = _score_supplier(q, price_range, lead_time_range)
            scored.append((q, total_score, breakdown))

        # Sort by score descending
        scored.sort(key=lambda x: -x[1])
        recommended_q, recommended_score, recommended_breakdown = scored[0]

        # Generate tradeoff analysis
        tradeoffs = _analyze_tradeoffs(scored)

        evidence = []
        for q, score, breakdown in scored:
            reliability = q.get("supplier_reliability")
            reliability_str = f"{reliability:.0%}" if reliability is not None else "N/A"
            evidence.append(
                f"{q['supplier']}: ${q['unit_price']}, Lead: {q['lead_time_days']}d, "
                f"Risk: {q['risk_level']}, Quality: {q['quality_rating']}, "
                f"Reliability: {reliability_str}, Score: {score}"
            )

        # Decision and confidence
        decision = f"Recommended: {recommended_q['supplier']} for {mat} (score: {recommended_score})"
        # Confidence based on score margin over second place
        if len(scored) > 1:
            margin = recommended_score - scored[1][1]
            confidence = "high" if margin >= 10 else ("medium" if margin >= 5 else "low")
        else:
            confidence = "medium"

        # Build recommendation text with tradeoff context
        recommendation = _build_recommendation(recommended_q, recommended_score, tradeoffs, mat)

        supplier_reply = (
            f"Dear {recommended_q['supplier']},\n\n"
            f"We are considering your quote ({recommended_q['quote_id']}) for {mat}.\n"
            f"Price: ${recommended_q['unit_price']}, Lead Time: {recommended_q['lead_time_days']} days.\n"
            f"Your reliability rating: {recommended_q.get('supplier_reliability', 'N/A')}.\n\n"
            f"Please confirm availability and final terms.\n\n"
            f"Best regards,\nProcurement Team"
        )

        summary.append({
            "material": mat,
            "recommended_supplier": recommended_q["supplier"],
            "decision": decision,
            "confidence": confidence,
            "price_spread": round(price_range[0] - price_range[1], 2),
            "lead_time_summary": {
                "avg_days": round(sum(lead_times) / len(lead_times), 1),
                "min_days": min(lead_times),
                "max_days": max(lead_times)
            },
            "risks": {
                "high_risk_suppliers": sum(1 for q in mat_quotes if q.get("risk_level", "").lower() == "high"),
                "risk_levels": [q.get("risk_level", "unknown") for q in mat_quotes]
            },
            "evidence": evidence,
            "recommendation": recommendation,
            "supplier_reply_draft": supplier_reply,
            "supplier_scores": {
                q["supplier"]: {"score": score, "breakdown": breakdown}
                for q, score, breakdown in scored
            },
            "tradeoffs": tradeoffs,
            "trace": [
                f"loaded {len(mat_quotes)} quotes for {mat}",
                "scored suppliers on price (30%), reliability (25%), quality (20%), lead time (15%), risk (10%)",
                f"selected {recommended_q['supplier']} with score {recommended_score}"
            ]
        })

    if len(summary) == 1:
        raw_data = summary[0]
        raw_data["order_ids"] = []
        return normalize_skill_response("quote-comparison-summary", raw_data)

    raw_data = {
        "materials": summary,
        "trace": ["loaded quotes", "grouped by material", "scored all suppliers", "analyzed all materials"],
        "order_ids": []
    }
    return normalize_skill_response("quote-comparison-summary", raw_data)


def _analyze_tradeoffs(scored):
    """Identify notable tradeoffs among top suppliers."""
    tradeoffs = []
    if len(scored) < 2:
        return tradeoffs

    top_q, top_score, _ = scored[0]
    for q, score, _ in scored[1:3]:  # Check 2nd and 3rd place
        notes = []
        if q["unit_price"] < top_q["unit_price"]:
            notes.append(f"{q['supplier']} is cheaper (${q['unit_price']} vs ${top_q['unit_price']})")
        if q.get("supplier_reliability") is not None and top_q.get("supplier_reliability") is not None:
            if q["supplier_reliability"] > top_q["supplier_reliability"]:
                notes.append(f"{q['supplier']} has higher reliability ({q['supplier_reliability']:.0%} vs {top_q['supplier_reliability']:.0%})")
        if q["lead_time_days"] < top_q["lead_time_days"]:
            notes.append(f"{q['supplier']} has shorter lead time ({q['lead_time_days']}d vs {top_q['lead_time_days']}d)")
        if q["quality_rating"] > top_q["quality_rating"]:
            notes.append(f"{q['supplier']} has higher quality rating ({q['quality_rating']} vs {top_q['quality_rating']})")

        if notes:
            tradeoffs.append(
                f"Tradeoff: {top_q['supplier']} wins on overall score ({top_score} vs {score}), "
                f"but {'; '.join(notes)}."
            )
    return tradeoffs


def _build_recommendation(recommended, score, tradeoffs, material):
    """Build a human-readable recommendation with tradeoff context."""
    reliability = recommended.get("supplier_reliability")
    reliability_str = f" ({reliability:.0%} reliability)" if reliability is not None else ""

    base = (
        f"Select {recommended['supplier']} for {material} with the best overall score ({score})"
        f"{reliability_str}. "
        f"Price: ${recommended['unit_price']}, Lead: {recommended['lead_time_days']}d, "
        f"Quality: {recommended['quality_rating']}, Risk: {recommended['risk_level']}."
    )

    if tradeoffs:
        base += f" Note: {' '.join(tradeoffs[:1])}"

    base += " Negotiate pricing and confirm lead time commitment before placing order."
    return base
