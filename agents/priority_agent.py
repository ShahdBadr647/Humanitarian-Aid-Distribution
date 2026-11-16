"""
Priority Agent

Job: decide which areas should be served first.

It reads the NEEDS_REPORT from the Needs Agent and calculates a priority
score from 0 to 100 for every area. The score is a weighted sum of five
factors, each scaled to the range 0-1:

  urgency        = (urgency - 1) / 4                 (1 -> 0.0, 5 -> 1.0)
  need           = remaining need per person, compared with the neediest area
  vulnerability  = vulnerable population %, compared with the most vulnerable area
  access         = access difficulty, compared with the hardest-to-reach area
  fairness       = 1 - coverage received so far      (less aid so far -> higher)

  score = 100 * sum(weight_i * factor_i)  (+ a small boost if Monitoring raised an alert)

The fairness factor changes every round, so areas that were served less in
earlier rounds move up the list in later rounds.
"""

import pandas as pd

from agents.base_agent import BaseAgent
from agents.config import ALERT_BOOST_POINTS, DEFAULT_WEIGHTS, RESOURCES
from agents.messaging import ALERT, NEEDS_REPORT, PRIORITY_REPORT


def normalise_weights(weights: dict) -> dict:
    """Make the weights add up to 1. If all are zero, use equal weights."""
    total = sum(max(0.0, w) for w in weights.values())
    if total == 0:
        return {k: 1 / len(weights) for k in weights}
    return {k: max(0.0, w) / total for k, w in weights.items()}


def scale_by_max(series: pd.Series) -> pd.Series:
    """Divide by the largest value so the result is between 0 and 1."""
    biggest = series.max()
    if biggest <= 0:
        return series * 0.0
    return series / biggest


def priority_level(score: float) -> str:
    """Turn a numeric score into an easy-to-read label."""
    if score >= 75:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def calculate_priorities(needs: pd.DataFrame, weights: dict, flagged_areas=()) -> pd.DataFrame:
    """Calculate the priority score for every area. Returns a new table."""
    w = normalise_weights(weights)
    table = needs[["area_id", "area_name", "region"]].copy()

    # 1) Urgency on a 1-5 scale
    table["urgency_factor"] = ((needs["urgency"].clip(1, 5) - 1) / 4).round(4)

    # 2) Remaining need per person (average over the three resources)
    per_person = pd.DataFrame(
        {r: needs[f"{r}_remaining"] / needs["population"].where(needs["population"] > 0) for r in RESOURCES}
    ).fillna(0)
    per_person_scaled = per_person.apply(scale_by_max)
    table["need_factor"] = per_person_scaled.mean(axis=1).round(4)

    # 3) Vulnerability and 4) access difficulty
    table["vulnerability_factor"] = scale_by_max(needs["vulnerable_pct"]).round(4)
    table["access_factor"] = scale_by_max(needs["access_difficulty"]).round(4)

    # 5) Fairness: less coverage so far means a higher factor
    table["fairness_factor"] = (1 - needs["overall_coverage"].clip(0, 1)).round(4)

    score = 100 * (
        w["urgency"] * table["urgency_factor"]
        + w["need"] * table["need_factor"]
        + w["vulnerability"] * table["vulnerability_factor"]
        + w["access"] * table["access_factor"]
        + w["fairness"] * table["fairness_factor"]
    )
    table["alert_boost"] = needs["area_id"].isin(list(flagged_areas)) * ALERT_BOOST_POINTS
    table["priority_score"] = (score + table["alert_boost"]).clip(0, 100).round(2)

    # An area with no remaining need does not need priority any more
    fully_served = sum(needs[f"{r}_remaining"] for r in RESOURCES) == 0
    table.loc[fully_served, "priority_score"] = 0.0

    table["priority_level"] = table["priority_score"].apply(priority_level)
    table = table.sort_values("priority_score", ascending=False).reset_index(drop=True)
    table["rank"] = table.index + 1
    return table


class PriorityAgent(BaseAgent):
    def __init__(self, weights: dict = None):
        super().__init__("PriorityAgent")
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.latest_priorities = None

    def step(self, round_number: int):
        """Read needs and alerts, calculate scores, send them to the Distribution Agent."""
        self.current_round = round_number
        needs_msg = self.latest_message(NEEDS_REPORT)
        if needs_msg is None:
            return

        # Areas flagged by the Monitoring Agent in the previous round get a boost
        flagged = set()
        for alert in self.read_messages(ALERT):
            flagged.update(alert.content.get("area_ids", []))

        priorities = calculate_priorities(needs_msg.content["needs"], self.weights, flagged)
        self.latest_priorities = priorities

        top = priorities.iloc[0]
        self.send(
            "DistributionAgent",
            PRIORITY_REPORT,
            {
                "priorities": priorities,
                "summary": f"Top priority: {top['area_name']} ({top['priority_score']:.1f}); "
                f"{len(flagged)} area(s) boosted by alerts",
            },
        )
