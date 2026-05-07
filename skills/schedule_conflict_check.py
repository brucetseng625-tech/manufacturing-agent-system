
import json
import os
from datetime import datetime

def check_schedule_conflict(order_ids, mock_data_dir):
    """
    MVP Skill: Check if given orders have schedule conflicts on the same machine.
    """
    schedule = json.load(open(os.path.join(mock_data_dir, "schedule.json")))
    orders = json.load(open(os.path.join(mock_data_dir, "orders.json")))
    
    # Filter reservations for given orders
    relevant_reservations = [r for r in schedule if r["order_id"] in order_ids]
    
    conflicts = []
    # Check pairwise conflicts
    for i in range(len(relevant_reservations)):
        for j in range(i + 1, len(relevant_reservations)):
            r1 = relevant_reservations[i]
            r2 = relevant_reservations[j]
            
            if r1["machine_id"] != r2["machine_id"]:
                continue
                
            t1_start = datetime.fromisoformat(r1["start"])
            t1_end = datetime.fromisoformat(r1["end"])
            t2_start = datetime.fromisoformat(r2["start"])
            t2_end = datetime.fromisoformat(r2["end"])
            
            if t1_start < t2_end and t2_start < t1_end:
                # Conflict found
                order1 = next((o for o in orders if o["order_id"] == r1["order_id"]), None)
                order2 = next((o for o in orders if o["order_id"] == r2["order_id"]), None)
                
                # Determine priority
                p1 = order1["priority"] if order1 else "Normal"
                p2 = order2["priority"] if order2 else "Normal"
                
                winner = r1["order_id"] if p1 == "High" else r2["order_id"]
                loser = r2["order_id"] if winner == r1["order_id"] else r1["order_id"]
                
                conflicts.append({
                    "machine_id": r1["machine_id"],
                    "overlap_start": max(t1_start, t2_start).isoformat(),
                    "overlap_end": min(t1_end, t2_end).isoformat(),
                    "orders": [r1["order_id"], r2["order_id"]],
                    "winner": winner,
                    "loser": loser,
                    "suggestion": f"Reschedule {loser} to start after {min(t1_end, t2_end).isoformat()} or use alternate machine."
                })
                
    return {
        "conflicts": conflicts,
        "status": "conflict_detected" if conflicts else "no_conflict",
        "trace": ["loaded schedule", "loaded orders", "checked overlaps", "resolved priorities"]
    }
