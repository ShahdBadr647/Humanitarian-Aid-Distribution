"""
Needs Agent

Job: know what every area needs.
  * Loads the area data (population, needs, urgency, ...).
  * Keeps track of how much aid each area has already received.
  * Each round, sends a NEEDS_REPORT with the *remaining* needs to the
    Priority Agent and the Distribution Agent.
  * Updates its records when the Distribution Agent reports deliveries.
"""

import pandas as pd

from agents.base_agent import BaseAgent
from agents.config import RESOURCES
from agents.messaging import DELIVERY_REPORT, NEEDS_REPORT


class NeedsAgent(BaseAgent):
    def __init__(self, areas: pd.DataFrame):
        super().__init__("NeedsAgent")
        self.areas = areas.copy().reset_index(drop=True)
        # How much of each resource each area has received so far
        for resource in RESOURCES:
            self.areas[f"{resource}_received"] = 0

    def remaining_needs(self) -> pd.DataFrame:
        """Return a table with remaining need and coverage so far for each area."""
        table = self.areas.copy()
        for resource in RESOURCES:
            need = table[f"{resource}_need"]
            received = table[f"{resource}_received"]
            table[f"{resource}_remaining"] = (need - received).clip(lower=0)
            # Coverage = share of the need already delivered (0.0 - 1.0)
            table[f"{resource}_coverage"] = (received / need.where(need > 0)).fillna(1.0)
        table["overall_coverage"] = table[[f"{r}_coverage" for r in RESOURCES]].mean(axis=1)
        return table

    def step(self, round_number: int):
        """Process delivery reports, then broadcast the remaining needs."""
        self.current_round = round_number
        self.process_deliveries()

        report = self.remaining_needs()
        total_remaining = {r: int(report[f"{r}_remaining"].sum()) for r in RESOURCES}
        content = {
            "needs": report,
            "summary": (
                f"Remaining needs - food: {total_remaining['food']:,}, "
                f"water: {total_remaining['water']:,}, "
                f"medicine: {total_remaining['medicine']:,}"
            ),
        }
        self.send("PriorityAgent", NEEDS_REPORT, content)
        self.send("DistributionAgent", NEEDS_REPORT, content)
        self.send("MonitoringAgent", NEEDS_REPORT, content)

    def process_deliveries(self):
        """Add delivered quantities (from DELIVERY_REPORT messages) to each area."""
        for message in self.read_messages(DELIVERY_REPORT):
            deliveries = message.content["deliveries"]  # {area_id: {resource: qty}}
            for area_id, items in deliveries.items():
                row = self.areas.index[self.areas["area_id"] == area_id][0]
                for resource, qty in items.items():
                    self.areas.loc[row, f"{resource}_received"] += int(qty)
