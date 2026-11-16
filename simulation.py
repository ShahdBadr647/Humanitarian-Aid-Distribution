"""
Simulation coordinator.

Creates the five agents, connects them to one MessageBus and runs the
distribution in rounds. Each round represents one aid convoy arriving:

  1. ResourceAgent     receives the convoy and reports its inventory
  2. NeedsAgent        updates deliveries and reports remaining needs
  3. PriorityAgent     calculates priority scores
  4. DistributionAgent builds a plan and asks the ResourceAgent for stock
  5. ResourceAgent     approves the plan (never over-allocating)
  6. DistributionAgent reports deliveries
  7. MonitoringAgent   checks safety rules, records statistics, raises alerts

Run this file directly for a quick text-only demo:  python simulation.py
"""

from dataclasses import dataclass

import pandas as pd

from agents import DistributionAgent, MonitoringAgent, NeedsAgent, PriorityAgent, ResourceAgent
from agents.config import DEFAULT_MIN_SHARE, DEFAULT_WEIGHTS, RESOURCES
from agents.messaging import MessageBus


@dataclass
class SimulationResult:
    """Everything the dashboard needs to display after a run."""

    area_summary: pd.DataFrame      # final needs, received, coverage per area
    priorities: pd.DataFrame        # priority scores from the first round
    final_priorities: pd.DataFrame  # priority scores from the last round
    round_allocations: pd.DataFrame # what each area received in each round
    inventory: pd.DataFrame         # initial / distributed / remaining per resource
    round_stats: pd.DataFrame       # monitoring statistics per round
    checks: pd.DataFrame            # safety check results
    alerts: pd.DataFrame            # alerts raised by the monitoring agent
    messages: pd.DataFrame          # full agent communication log

    @property
    def all_checks_passed(self) -> bool:
        return bool(self.checks["Passed"].all()) if not self.checks.empty else True


def split_into_convoys(total: int, rounds: int) -> list:
    """Split a stock quantity into `rounds` convoys of (almost) equal size."""
    rounds = max(1, int(rounds))
    base, extra = divmod(max(0, int(total)), rounds)
    return [base + (1 if i < extra else 0) for i in range(rounds)]


def run_simulation(
    areas: pd.DataFrame,
    stock: dict,
    rounds: int = 3,
    weights: dict = None,
    min_share: float = DEFAULT_MIN_SHARE,
) -> SimulationResult:
    """Run the full multi-agent simulation and return the results."""
    weights = weights or DEFAULT_WEIGHTS
    rounds = max(1, int(rounds))

    # --- Create agents and connect them to the message bus ------------------
    bus = MessageBus()
    needs_agent = NeedsAgent(areas)
    resource_agent = ResourceAgent()
    priority_agent = PriorityAgent(weights)
    distribution_agent = DistributionAgent(min_share)
    monitoring_agent = MonitoringAgent()
    for agent in (needs_agent, resource_agent, priority_agent, distribution_agent, monitoring_agent):
        bus.register(agent)

    convoys = {r: split_into_convoys(stock.get(r, 0), rounds) for r in RESOURCES}
    allocation_rows = []
    first_priorities = None

    # --- Run each round ------------------------------------------------------
    for round_number in range(1, rounds + 1):
        shipment = {r: convoys[r][round_number - 1] for r in RESOURCES}
        resource_agent.receive_convoy(shipment, round_number)
        resource_agent.report_inventory()

        needs_agent.step(round_number)
        priority_agent.step(round_number)
        if first_priorities is None:
            first_priorities = priority_agent.latest_priorities

        distribution_agent.plan(round_number)
        resource_agent.step(round_number)
        distribution_agent.deliver(round_number)
        monitoring_agent.step(round_number)

        names = dict(zip(areas["area_id"], areas["area_name"]))
        for area_id, items in distribution_agent.last_deliveries.items():
            allocation_rows.append({"Round": round_number, "area_id": area_id, "area_name": names[area_id], **items})

    # Apply the last round's deliveries to the Needs Agent's records
    needs_agent.process_deliveries()

    # --- Build result tables --------------------------------------------------
    summary = needs_agent.remaining_needs()
    final_scores = priority_agent.latest_priorities[["area_id", "priority_score", "priority_level", "rank"]]
    summary = summary.merge(final_scores, on="area_id", how="left")

    inventory = pd.DataFrame(
        {
            "resource": RESOURCES,
            "initial_stock": [resource_agent.total_received[r] for r in RESOURCES],
            "distributed": [resource_agent.total_released[r] for r in RESOURCES],
            "remaining": [resource_agent.inventory[r] for r in RESOURCES],
            "total_need": [int(areas[f"{r}_need"].sum()) for r in RESOURCES],
        }
    )
    inventory["unmet_need"] = inventory["total_need"] - inventory["distributed"]
    inventory["coverage_pct"] = (100 * inventory["distributed"] / inventory["total_need"].where(inventory["total_need"] > 0)).fillna(100).round(1)

    return SimulationResult(
        area_summary=summary,
        priorities=first_priorities,
        final_priorities=priority_agent.latest_priorities,
        round_allocations=pd.DataFrame(allocation_rows),
        inventory=inventory,
        round_stats=pd.DataFrame(monitoring_agent.history),
        checks=pd.DataFrame(monitoring_agent.checks),
        alerts=pd.DataFrame(monitoring_agent.alerts, columns=["Round", "Area", "Urgency", "Coverage", "Message"]),
        messages=pd.DataFrame(bus.log_as_records()),
    )


if __name__ == "__main__":
    # Quick demo without the dashboard
    from data_loader import load_areas, load_resources

    areas_df = load_areas()
    stock_df = load_resources()
    result = run_simulation(areas_df, dict(zip(stock_df["resource"], stock_df["available"])))

    print("=== Inventory ===")
    print(result.inventory.to_string(index=False))
    print("\n=== Coverage per area ===")
    cols = ["area_name", "priority_score", "food_coverage", "water_coverage", "medicine_coverage"]
    print(result.area_summary[cols].round(3).to_string(index=False))
    print("\n=== Monitoring per round ===")
    print(result.round_stats.round(3).to_string(index=False))
    print(f"\nAll safety checks passed: {result.all_checks_passed}")
    print(f"Messages exchanged: {len(result.messages)} | Alerts raised: {len(result.alerts)}")
