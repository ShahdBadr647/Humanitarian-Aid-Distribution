"""Shared settings used by several agents."""

# The three types of humanitarian aid handled by the system
RESOURCES = ["food", "water", "medicine"]

# Default weights for the priority algorithm (they are normalised to sum to 1)
DEFAULT_WEIGHTS = {
    "urgency": 0.30,        # how severe the situation is (1-5 scale)
    "need": 0.25,           # remaining need per person
    "vulnerability": 0.20,  # share of children, elderly, sick, pregnant women
    "access": 0.10,         # hard-to-reach areas are often under-served
    "fairness": 0.15,       # areas that received less so far get a boost
}

# Every area first receives this share of its need (if stock allows) before
# the rest is shared by priority. This stops low-priority areas from getting nothing.
DEFAULT_MIN_SHARE = 0.20

# Extra priority points for areas flagged by the Monitoring Agent
ALERT_BOOST_POINTS = 5.0

# An area is "critical" if urgency >= this value
CRITICAL_URGENCY = 4

# Coverage below this value counts as "badly under-served" in the statistics
LOW_COVERAGE_THRESHOLD = 0.50

# A critical area is "lagging" (and triggers an alert) when its coverage is
# below this fraction of the average coverage of all areas
LAGGING_RATIO = 0.90
