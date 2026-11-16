"""
Dashboard tests: run app.py headlessly with Streamlit's AppTest,
press the buttons and make sure nothing crashes.

Run with:   python -m unittest discover -s tests -v
"""

import os
import unittest

from streamlit.testing.v1 import AppTest

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def button(at, label_part):
    """Find a button by part of its label."""
    return next(b for b in at.button if label_part in b.label)


class TestDashboard(unittest.TestCase):
    def setUp(self):
        self.at = AppTest.from_file(APP_PATH, default_timeout=60)
        self.at.run()

    def test_first_load_has_no_errors(self):
        self.assertFalse(self.at.exception)
        self.assertEqual(len(self.at.info), 1)  # "press Run simulation" hint

    def test_run_simulation(self):
        button(self.at, "Run simulation").click().run()
        self.assertFalse(self.at.exception)
        self.assertIn("result", self.at.session_state)
        self.assertTrue(any("safety checks passed" in s.value for s in self.at.success))
        self.assertGreaterEqual(len(self.at.metric), 6)

    def test_changed_settings_and_reset(self):
        self.at.slider(key="rounds").set_value(5)
        self.at.slider(key="w_fairness").set_value(0)
        self.at.number_input(key="stock_food").set_value(1000)
        self.at.run()
        button(self.at, "Run simulation").click().run()
        self.assertFalse(self.at.exception)
        self.assertEqual(len(self.at.session_state["result"].round_stats), 5)

        button(self.at, "Reset").click().run()
        self.assertFalse(self.at.exception)
        self.assertNotIn("result", self.at.session_state)
        self.assertEqual(self.at.slider(key="rounds").value, 3)
        self.assertEqual(self.at.number_input(key="stock_food").value, 52000)


if __name__ == "__main__":
    unittest.main()
