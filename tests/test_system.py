"""
Automated tests for the Humanitarian Aid Distribution System.

Run with:   python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

import pandas as pd

# Make the project folder importable when running the tests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.config import DEFAULT_WEIGHTS, RESOURCES  # noqa: E402
from agents.distribution_agent import allocate_resource  # noqa: E402
from agents.messaging import Message, MessageBus  # noqa: E402
from agents.monitoring_agent import jain_fairness_index  # noqa: E402
from agents.priority_agent import calculate_priorities, normalise_weights  # noqa: E402
from agents.resource_agent import ResourceAgent  # noqa: E402
from agents.base_agent import BaseAgent  # noqa: E402
from data_loader import clean_areas, load_areas, load_resources  # noqa: E402
from simulation import run_simulation, split_into_convoys  # noqa: E402


def default_stock():
    res = load_resources()
    return dict(zip(res["resource"], res["available"]))


class TestAllocation(unittest.TestCase):
    def test_never_exceeds_supply_or_need(self):
        needs = {"A": 100, "B": 50, "C": 10}
        prios = {"A": 90, "B": 50, "C": 10}
        for supply in [0, 1, 7, 33, 80, 159, 160, 500]:
            result = allocate_resource(needs, prios, supply, 0.2)
            self.assertLessEqual(sum(result.values()), supply)
            for area, qty in result.items():
                self.assertGreaterEqual(qty, 0)
                self.assertLessEqual(qty, needs[area])

    def test_uses_all_supply_when_scarce(self):
        result = allocate_resource({"A": 100, "B": 100}, {"A": 80, "B": 20}, 120, 0.2)
        self.assertEqual(sum(result.values()), 120)

    def test_full_need_when_supply_is_enough(self):
        needs = {"A": 10, "B": 20}
        self.assertEqual(allocate_resource(needs, {"A": 1, "B": 1}, 1000), needs)

    def test_higher_priority_gets_more(self):
        result = allocate_resource({"A": 100, "B": 100}, {"A": 90, "B": 30}, 100, 0.2)
        self.assertGreater(result["A"], result["B"])

    def test_minimum_share_is_guaranteed(self):
        # Low-priority area B must still get at least 20% of its need
        result = allocate_resource({"A": 100, "B": 100}, {"A": 100, "B": 1}, 100, 0.2)
        self.assertGreaterEqual(result["B"], 20)

    def test_zero_priorities_fall_back_to_need(self):
        result = allocate_resource({"A": 30, "B": 10}, {"A": 0, "B": 0}, 20, 0.0)
        self.assertEqual(sum(result.values()), 20)
        self.assertGreater(result["A"], result["B"])


class TestResourceAgent(unittest.TestCase):
    def test_over_request_is_scaled_down(self):
        agent = ResourceAgent()
        agent.receive_convoy({"food": 100, "water": 50, "medicine": 10}, 1)
        approved = agent.approve_request({"A": {"food": 80, "water": 40, "medicine": 20},
                                          "B": {"food": 80, "water": 0, "medicine": 20}})
        self.assertLessEqual(approved["A"]["food"] + approved["B"]["food"], 100)
        self.assertLessEqual(approved["A"]["medicine"] + approved["B"]["medicine"], 10)
        for r in RESOURCES:
            self.assertGreaterEqual(agent.inventory[r], 0)

    def test_negative_convoy_ignored(self):
        agent = ResourceAgent()
        agent.receive_convoy({"food": -50, "water": 10, "medicine": 0}, 1)
        self.assertEqual(agent.inventory["food"], 0)


class TestPriority(unittest.TestCase):
    def test_scores_in_range_and_sorted(self):
        areas = load_areas()
        needs = areas.copy()
        for r in RESOURCES:
            needs[f"{r}_remaining"] = needs[f"{r}_need"]
        needs["overall_coverage"] = 0.0
        prios = calculate_priorities(needs, DEFAULT_WEIGHTS)
        self.assertTrue(prios["priority_score"].between(0, 100).all())
        self.assertTrue(prios["priority_score"].is_monotonic_decreasing)
        self.assertEqual(list(prios["rank"]), list(range(1, len(areas) + 1)))

    def test_weights_normalised(self):
        w = normalise_weights({"a": 2, "b": 2})
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertEqual(normalise_weights({"a": 0, "b": 0}), {"a": 0.5, "b": 0.5})


class TestMessaging(unittest.TestCase):
    def test_message_delivered_and_logged(self):
        bus = MessageBus()
        a, b = BaseAgent("A"), BaseAgent("B")
        bus.register(a)
        bus.register(b)
        a.send("B", "HELLO", {"summary": "hi"})
        self.assertEqual(len(b.inbox), 1)
        self.assertEqual(len(bus.log), 1)
        self.assertEqual(b.latest_message("HELLO").sender, "A")
        self.assertEqual(b.inbox, [])

    def test_unknown_receiver_raises(self):
        bus = MessageBus()
        with self.assertRaises(ValueError):
            bus.send(Message("X", "nobody", "T", {}))


class TestHelpers(unittest.TestCase):
    def test_jain_index(self):
        self.assertAlmostEqual(jain_fairness_index([0.5, 0.5, 0.5]), 1.0)
        self.assertAlmostEqual(jain_fairness_index([1, 0]), 0.5)

    def test_split_into_convoys(self):
        self.assertEqual(split_into_convoys(10, 3), [4, 3, 3])
        self.assertEqual(sum(split_into_convoys(52000, 4)), 52000)

    def test_clean_areas_fixes_bad_values(self):
        areas = load_areas()
        areas.loc[0, "food_need"] = -10
        areas.loc[1, "urgency"] = 9
        cleaned = clean_areas(areas)
        self.assertEqual(cleaned.loc[0, "food_need"], 0)
        self.assertEqual(cleaned.loc[1, "urgency"], 5)


class TestFullSimulation(unittest.TestCase):
    def check_result(self, result, areas, stock):
        self.assertTrue(result.all_checks_passed)
        inv = result.inventory.set_index("resource")
        for r in RESOURCES:
            self.assertGreaterEqual(inv.loc[r, "remaining"], 0)
            self.assertLessEqual(inv.loc[r, "distributed"], stock[r])
            self.assertEqual(inv.loc[r, "distributed"] + inv.loc[r, "remaining"], stock[r])
            self.assertTrue((result.area_summary[f"{r}_received"] <= result.area_summary[f"{r}_need"]).all())

    def test_default_run(self):
        areas, stock = load_areas(), default_stock()
        result = run_simulation(areas, stock, rounds=3)
        self.check_result(result, areas, stock)
        # Stock is scarce in the sample data, so everything should be used
        self.assertTrue((result.inventory["remaining"] == 0).all())
        self.assertGreater(len(result.messages), 0)

    def test_surplus_stock_is_kept(self):
        areas = load_areas()
        stock = {r: int(areas[f"{r}_need"].sum()) * 2 for r in RESOURCES}
        result = run_simulation(areas, stock, rounds=2)
        self.check_result(result, areas, stock)
        self.assertTrue((result.area_summary["overall_coverage"] == 1.0).all())
        self.assertTrue((result.inventory["remaining"] > 0).all())

    def test_zero_stock(self):
        areas = load_areas()
        stock = {r: 0 for r in RESOURCES}
        result = run_simulation(areas, stock, rounds=1)
        self.check_result(result, areas, stock)
        self.assertTrue((result.inventory["distributed"] == 0).all())

    def test_many_rounds_and_extreme_weights(self):
        areas, stock = load_areas(), default_stock()
        weights = {"urgency": 100, "need": 0, "vulnerability": 0, "access": 0, "fairness": 0}
        result = run_simulation(areas, stock, rounds=6, weights=weights, min_share=0.0)
        self.check_result(result, areas, stock)
        self.assertEqual(len(result.round_stats), 6)

    def test_area_with_zero_need(self):
        areas = load_areas()
        areas.loc[0, ["food_need", "water_need", "medicine_need"]] = 0
        stock = default_stock()
        result = run_simulation(areas, stock, rounds=3)
        self.check_result(result, areas, stock)
        first = result.area_summary.iloc[0]
        self.assertEqual(first["food_received"] + first["water_received"] + first["medicine_received"], 0)

    def test_charts_build(self):
        import matplotlib.pyplot as plt
        import charts

        result = run_simulation(load_areas(), default_stock(), rounds=3)
        for fig in (
            charts.needs_vs_delivered_chart(result.area_summary),
            charts.priority_chart(result.priorities),
            charts.coverage_chart(result.area_summary),
            charts.inventory_chart(result.inventory),
            charts.rounds_chart(result.round_stats),
        ):
            self.assertIsNotNone(fig)
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
