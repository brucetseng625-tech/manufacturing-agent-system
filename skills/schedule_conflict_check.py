
from datetime import datetime
from data_loader import load_json_or_csv


PRIORITY_RANK = {
    "High": 3,
    "Normal": 2,
    "Low": 1,
}


def choose_winner(reservation1, reservation2, order1, order2):
    order1_priority = PRIORITY_RANK.get(order1["priority"] if order1 else "Normal", 2)
    order2_priority = PRIORITY_RANK.get(order2["priority"] if order2 else "Normal", 2)
    order1_due = order1["due_date"] if order1 else "9999-12-31"
    order2_due = order2["due_date"] if order2 else "9999-12-31"

    ranked = sorted(
        [
            (reservation1["order_id"], order1_priority, order1_due, reservation1["start"]),
            (reservation2["order_id"], order2_priority, order2_due, reservation2["start"]),
        ],
        key=lambda item: (-item[1], item[2], item[3], item[0]),
    )
    winner = ranked[0][0]
    loser = ranked[1][0]
    return winner, loser


def check_schedule_conflict(order_ids, mock_data_dir):
    """
    MVP Skill: Check if given orders have schedule conflicts on the same machine.
    """
    schedule = load_json_or_csv(mock_data_dir, "schedule.json")
    orders = load_json_or_csv(mock_data_dir, "orders.json")

    target_order_ids = set(order_ids)
    if len(target_order_ids) == 1:
        relevant_reservations = schedule
    else:
        relevant_reservations = [r for r in schedule if r["order_id"] in target_order_ids]

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
                if target_order_ids.isdisjoint({r1["order_id"], r2["order_id"]}):
                    continue

                # Conflict found
                order1 = next((o for o in orders if o["order_id"] == r1["order_id"]), None)
                order2 = next((o for o in orders if o["order_id"] == r2["order_id"]), None)
                winner, loser = choose_winner(r1, r2, order1, order2)
                suggested_start = t1_end if loser == r2["order_id"] else t2_end

                conflicts.append({
                    "machine_id": r1["machine_id"],
                    "overlap_start": max(t1_start, t2_start).isoformat(),
                    "overlap_end": min(t1_end, t2_end).isoformat(),
                    "orders": [r1["order_id"], r2["order_id"]],
                    "winner": winner,
                    "loser": loser,
                    "suggestion": f"Reschedule {loser} to start after {suggested_start.isoformat()} or use alternate machine."
                })

    return {
        "conflicts": conflicts,
        "status": "conflict_detected" if conflicts else "no_conflict",
        "trace": ["loaded schedule", "loaded orders", "checked overlaps", "resolved priorities"]
    }
