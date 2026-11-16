"""
Distribution Agent

Job: turn needs + priorities + stock into a fair distribution plan.

How one resource (e.g. water) is shared among the areas:

  Step 1 - Minimum share (fairness):
      Every area first gets `min_share` (e.g. 20%) of its remaining need.
      If the stock is too small even for that, the stock is shared in
      proportion to need.

  Step 2 - Priority share:
      The rest of the stock is shared in proportion to
      (priority score x still-unmet need). No area ever gets more than it
      needs: when an area is full, its extra share is re-shared among the
      others ("water-filling").

  Step 3 - Whole units:
      Aid comes in whole parcels/kits, so the amounts are rounded down and
      the few leftover units go to the highest-priority areas that still
      need them.

The plan is sent to the Resource Agent as an ALLOCATION_REQUEST. After the
Resource Agent approves it, deliveries are reported to the Needs Agent and
the Monitoring Agent.
"""

import math

from agents.base_agent import BaseAgent
from agents.config import DEFAULT_MIN_SHARE, RESOURCES
from agents.messaging import (
    ALLOCATION_REQUEST,
    ALLOCATION_RESPONSE,
    DELIVERY_REPORT,
    INVENTORY_REPORT,
    NEEDS_REPORT,
    PRIORITY_REPORT,
)


def allocate_resource(needs: dict, priorities: dict, supply: int, min_share: float = DEFAULT_MIN_SHARE) -> dict:
    """
    Share `supply` units among areas.

    needs      = {area_id: units still needed}
    priorities = {area_id: priority score (0-100)}
    Returns {area_id: whole units allocated}. Guarantees:
      * no area gets more than its need
      * the total never exceeds the supply
      * no negative amounts
    """
    needs = {a: max(0, int(n)) for a, n in needs.items()}
    supply = max(0, int(supply))
    total_need = sum(needs.values())
    if total_need == 0 or supply == 0:
        return {a: 0 for a in needs}

    # Enough for everybody: give every area its full need.
    if supply >= total_need:
        return dict(needs)

    min_share = min(max(min_share, 0.0), 1.0)
    allocation = {a: 0.0 for a in needs}

    # ---- Step 1: minimum share for everyone -------------------------------
    base = {a: n * min_share for a, n in needs.items()}
    base_total = sum(base.values())
    if base_total > supply:
        # Not enough for the minimum: share in proportion to need
        allocation = {a: supply * n / total_need for a, n in needs.items()}
        remaining_supply = 0.0
    else:
        allocation = base
        remaining_supply = supply - base_total

    # ---- Step 2: share the rest by priority x unmet need (water-filling) ---
    active = {a for a in needs if needs[a] - allocation[a] > 1e-9}
    while remaining_supply > 1e-9 and active:
        weights = {a: max(priorities.get(a, 0.0), 0.0) * (needs[a] - allocation[a]) for a in active}
        total_weight = sum(weights.values())
        if total_weight <= 0:
            # Everybody has priority 0: fall back to unmet need only
            weights = {a: needs[a] - allocation[a] for a in active}
            total_weight = sum(weights.values())

        given_this_pass = 0.0
        newly_full = set()
        for a in active:
            share = remaining_supply * weights[a] / total_weight
            gap = needs[a] - allocation[a]
            if share >= gap:
                share = gap
                newly_full.add(a)
            allocation[a] += share
            given_this_pass += share

        remaining_supply -= given_this_pass
        active -= newly_full
        if not newly_full:
            break  # everything was handed out without hitting any cap

    # ---- Step 3: convert to whole units -----------------------------------
    whole = {a: min(needs[a], math.floor(allocation[a] + 1e-9)) for a in needs}
    target_total = min(supply, total_need)
    leftover = target_total - sum(whole.values())
    # Give leftover units one by one to the highest-priority areas still in need
    order = sorted(needs, key=lambda a: (-(allocation[a] - whole[a]), -priorities.get(a, 0.0)))
    while leftover > 0:
        progressed = False
        for a in order:
            if leftover == 0:
                break
            if whole[a] < needs[a]:
                whole[a] += 1
                leftover -= 1
                progressed = True
        if not progressed:
            break
    return whole


class DistributionAgent(BaseAgent):
    def __init__(self, min_share: float = DEFAULT_MIN_SHARE):
        super().__init__("DistributionAgent")
        self.min_share = min_share
        self.needs = None
        self.priorities = None
        self.inventory = None
        self.last_plan = {}
        self.last_deliveries = {}

    def plan(self, round_number: int):
        """Build a distribution plan and send it to the Resource Agent for approval."""
        self.current_round = round_number
        needs_msg = self.latest_message(NEEDS_REPORT)
        priority_msg = self.latest_message(PRIORITY_REPORT)
        inventory_msg = self.latest_message(INVENTORY_REPORT)
        if needs_msg is not None:
            self.needs = needs_msg.content["needs"]
        if priority_msg is not None:
            self.priorities = priority_msg.content["priorities"]
        if inventory_msg is not None:
            self.inventory = inventory_msg.content["inventory"]
        if self.needs is None or self.priorities is None or self.inventory is None:
            raise RuntimeError("DistributionAgent is missing needs, priorities or inventory")

        scores = dict(zip(self.priorities["area_id"], self.priorities["priority_score"]))
        plan = {area_id: {} for area_id in self.needs["area_id"]}
        for resource in RESOURCES:
            remaining = dict(zip(self.needs["area_id"], self.needs[f"{resource}_remaining"]))
            shares = allocate_resource(remaining, scores, self.inventory[resource], self.min_share)
            for area_id, qty in shares.items():
                plan[area_id][resource] = qty

        self.last_plan = plan
        totals = {r: sum(p[r] for p in plan.values()) for r in RESOURCES}
        self.send(
            "ResourceAgent",
            ALLOCATION_REQUEST,
            {"plan": plan, "summary": "Request - " + ", ".join(f"{r}: {q:,}" for r, q in totals.items())},
        )

    def deliver(self, round_number: int):
        """Read the Resource Agent's approval and report what was delivered."""
        self.current_round = round_number
        response = self.latest_message(ALLOCATION_RESPONSE)
        if response is None:
            raise RuntimeError("No ALLOCATION_RESPONSE received from ResourceAgent")
        deliveries = response.content["approved"]
        self.last_deliveries = deliveries

        served = sum(1 for items in deliveries.values() if sum(items.values()) > 0)
        content = {"deliveries": deliveries, "summary": f"Delivered aid to {served} area(s)"}
        self.send("NeedsAgent", DELIVERY_REPORT, content)
        self.send("MonitoringAgent", DELIVERY_REPORT, content)
