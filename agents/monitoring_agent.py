"""
Monitoring Agent

Job: watch the whole process and make sure it is correct and fair.
  * Safety checks every round:
      - inventory is never negative
      - no area receives more than it still needs
      - the total delivered is never more than the stock that was available
  * Statistics every round: coverage per resource, fairness index,
    number of areas still below 50% coverage.
  * Sends ALERT messages to the Priority Agent about critical areas
    (urgency >= 4) whose coverage is behind the average, so they get a
    boost next round.

Fairness index (Jain's index): 1.0 means every area has the same coverage,
lower values mean coverage is unequal.
"""

from agents.base_agent import BaseAgent
from agents.config import CRITICAL_URGENCY, LAGGING_RATIO, LOW_COVERAGE_THRESHOLD, RESOURCES
from agents.messaging import ALERT, DELIVERY_REPORT, INVENTORY_REPORT, NEEDS_REPORT


def jain_fairness_index(values) -> float:
    """Jain's fairness index: (sum x)^2 / (n * sum x^2). Returns 1.0 for an empty or all-zero list."""
    values = [float(v) for v in values]
    n = len(values)
    squares = sum(v * v for v in values)
    if n == 0 or squares == 0:
        return 1.0
    return (sum(values) ** 2) / (n * squares)


class MonitoringAgent(BaseAgent):
    def __init__(self):
        super().__init__("MonitoringAgent")
        self.history = []   # one statistics record per round
        self.checks = []    # result of every safety check
        self.alerts = []    # every alert raised

    def add_check(self, name: str, passed: bool, detail: str):
        self.checks.append({"Round": self.current_round, "Check": name, "Passed": passed, "Detail": detail})

    def step(self, round_number: int):
        """Validate this round's deliveries, record statistics and raise alerts."""
        self.current_round = round_number
        needs_msg = self.latest_message(NEEDS_REPORT)
        delivery_msg = self.latest_message(DELIVERY_REPORT)
        inventory_msgs = self.read_messages(INVENTORY_REPORT)
        if needs_msg is None or delivery_msg is None or len(inventory_msgs) < 2:
            raise RuntimeError("MonitoringAgent did not receive all reports for this round")

        needs = needs_msg.content["needs"].set_index("area_id")
        deliveries = delivery_msg.content["deliveries"]
        stock_before = inventory_msgs[0].content["inventory"]
        stock_after = inventory_msgs[-1].content["inventory"]

        # ---- Safety check 1: no negative inventory ------------------------
        negative = {r: q for r, q in stock_after.items() if q < 0}
        self.add_check(
            "No negative inventory",
            not negative,
            "All stock levels are zero or positive" if not negative else f"Negative stock: {negative}",
        )

        # ---- Safety check 2: no area receives more than it needs ----------
        over = []
        for area_id, items in deliveries.items():
            for resource, qty in items.items():
                if qty > needs.loc[area_id, f"{resource}_remaining"] or qty < 0:
                    over.append(f"{area_id}/{resource}")
        self.add_check(
            "No over-allocation to areas",
            not over,
            "Every delivery is within the remaining need" if not over else f"Problems: {', '.join(over)}",
        )

        # ---- Safety check 3: total delivered <= stock available -----------
        delivered = {r: sum(items.get(r, 0) for items in deliveries.values()) for r in RESOURCES}
        too_much = [r for r in RESOURCES if delivered[r] > stock_before[r]]
        self.add_check(
            "Delivered within available stock",
            not too_much,
            "Total delivered never exceeds stock" if not too_much else f"Exceeded for: {too_much}",
        )

        # ---- Statistics after this round's deliveries ---------------------
        coverage_by_area = {}
        record = {"Round": round_number}
        for resource in RESOURCES:
            need_total = needs[f"{resource}_need"].sum()
            received_total = needs[f"{resource}_received"].sum() + delivered[resource]
            record[f"{resource}_delivered"] = delivered[resource]
            record[f"{resource}_coverage"] = received_total / need_total if need_total else 1.0
            record[f"{resource}_stock_left"] = stock_after[resource]

        for area_id in needs.index:
            ratios = []
            for resource in RESOURCES:
                need = needs.loc[area_id, f"{resource}_need"]
                got = needs.loc[area_id, f"{resource}_received"] + deliveries[area_id].get(resource, 0)
                ratios.append(got / need if need else 1.0)
            coverage_by_area[area_id] = sum(ratios) / len(ratios)

        record["fairness_index"] = jain_fairness_index(coverage_by_area.values())
        record["areas_below_50pct"] = sum(1 for c in coverage_by_area.values() if c < LOW_COVERAGE_THRESHOLD)
        self.history.append(record)

        # ---- Alerts: critical areas lagging behind the average -------------
        average = sum(coverage_by_area.values()) / len(coverage_by_area) if coverage_by_area else 0
        record["average_coverage"] = average
        flagged = [
            area_id
            for area_id, cov in coverage_by_area.items()
            if needs.loc[area_id, "urgency"] >= CRITICAL_URGENCY and cov < LAGGING_RATIO * average
        ]
        for area_id in flagged:
            self.alerts.append(
                {
                    "Round": round_number,
                    "Area": needs.loc[area_id, "area_name"],
                    "Urgency": int(needs.loc[area_id, "urgency"]),
                    "Coverage": round(coverage_by_area[area_id] * 100, 1),
                    "Message": f"Critical area behind average coverage ({average * 100:.1f}%) "
                    "- priority boost requested",
                }
            )
        if flagged:
            self.send(
                "PriorityAgent",
                ALERT,
                {"area_ids": flagged, "summary": f"{len(flagged)} critical area(s) lagging behind average coverage"},
            )
