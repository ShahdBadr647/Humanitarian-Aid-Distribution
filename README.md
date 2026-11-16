# Humanitarian Aid Distribution System Using Multi-Agent Systems

A Python simulation in which five cooperating software agents share **food, water and medicine**
among ten areas in Palestine (Gaza Strip and West Bank). Aid is shared according to
**need, urgency, available resources and fairness**. Results appear in an interactive
**Streamlit** dashboard.

> **All numbers are fictional.** Area names are real places, but the populations, needs,
> urgency levels and stock levels are invented for this university project.

---

## 1. Quick start

```bash
# 1. Install the required packages
pip install -r requirements.txt

# 2. Start the dashboard (opens in your browser at http://localhost:8501)
streamlit run app.py
```

Other useful commands:

```bash
python simulation.py                         # text-only demo in the terminal
python -m unittest discover -s tests -v      # run all automated tests
```

---

## 2. Project structure

```
project Agent/
├── app.py                    # Streamlit dashboard
├── simulation.py             # Coordinator: creates the agents and runs the rounds
├── charts.py                 # Matplotlib charts used by the dashboard
├── data_loader.py            # Loads and validates the CSV files
├── requirements.txt
├── README.md
├── data/
│   ├── areas.csv             # 10 fictional areas: population, needs, urgency, ...
│   └── resources.csv         # fictional warehouse stock
├── agents/
│   ├── config.py             # shared settings (resources, default weights, thresholds)
│   ├── messaging.py          # Message + MessageBus (agent communication)
│   ├── base_agent.py         # parent class for all agents
│   ├── needs_agent.py        # Needs Agent
│   ├── resource_agent.py     # Resource Agent
│   ├── priority_agent.py     # Priority Agent
│   ├── distribution_agent.py # Distribution Agent + allocation algorithm
│   └── monitoring_agent.py   # Monitoring Agent
├── run_dashboard.bat         # Windows shortcut: starts the dashboard from D:\aid-venv
└── tests/
    ├── test_system.py        # 21 tests: algorithm, agents, messaging, full simulation, charts
    └── test_app.py           # 3 tests: runs the dashboard headlessly, clicks Run and Reset
```

---

## 3. The five agents

| Agent | Responsibility | Sends |
|---|---|---|
| **Needs Agent** | Knows each area's needs and records what it has received | `NEEDS_REPORT` (remaining needs and coverage) |
| **Resource Agent** | Manages the warehouse, receives convoys, approves stock releases, **never lets stock go negative** | `INVENTORY_REPORT`, `ALLOCATION_RESPONSE` |
| **Priority Agent** | Calculates a 0-100 priority score for every area | `PRIORITY_REPORT` |
| **Distribution Agent** | Builds the distribution plan and asks the Resource Agent for the stock | `ALLOCATION_REQUEST`, `DELIVERY_REPORT` |
| **Monitoring Agent** | Runs the safety checks, computes statistics and the fairness index, raises alerts | `ALERT` |

### How the agents communicate

Agents never call each other directly. They send `Message` objects through a shared
`MessageBus`, which delivers each one to the receiver's inbox and logs it. The dashboard's
**Agent messages** tab shows this log.

Stock arrives in several **convoys (rounds)**. Each round:

```
ResourceAgent     --INVENTORY_REPORT-->      DistributionAgent, MonitoringAgent
NeedsAgent        --NEEDS_REPORT-->          PriorityAgent, DistributionAgent, MonitoringAgent
PriorityAgent     --PRIORITY_REPORT-->       DistributionAgent
DistributionAgent --ALLOCATION_REQUEST-->    ResourceAgent
ResourceAgent     --ALLOCATION_RESPONSE-->   DistributionAgent
ResourceAgent     --INVENTORY_REPORT-->      MonitoringAgent   (stock after release)
DistributionAgent --DELIVERY_REPORT-->       NeedsAgent, MonitoringAgent
MonitoringAgent   --ALERT-->                 PriorityAgent     (only if a critical area lags behind)
```

This is a feedback loop: the Monitoring Agent's alerts and the Needs Agent's updated coverage
change the Priority Agent's scores in the next round.

---

## 4. The priority algorithm

Every factor is scaled to between 0 and 1:

| Factor | Formula | Default weight |
|---|---|---|
| Urgency | `(urgency - 1) / 4` | 30% |
| Need | remaining need per person, divided by the highest value among the areas (average of the 3 resources) | 25% |
| Vulnerability | vulnerable population %, divided by the highest value | 20% |
| Access | access difficulty, divided by the highest value | 10% |
| Fairness | `1 - coverage received so far` | 15% |

```
priority score = 100 × Σ (weight × factor)   + 5 points if the Monitoring Agent raised an alert
```

The weights can be changed in the dashboard and are always normalised to 100%. An area whose
needs are fully met gets a score of 0.

## 5. The distribution algorithm (fair and safe)

For each resource, the Distribution Agent:

1. **Guarantees a minimum share:** every area first receives a minimum share of its remaining
   need (20% by default), so no area is left with nothing. If stock is too low even for that,
   the stock is shared in proportion to need.
2. **Shares the rest by priority:** each area's share of the remaining stock is proportional to
   `priority score × unmet need`. An area never receives more than it needs. When an area is
   full, its extra share is re-shared among the others (the "water-filling" method).
3. **Uses whole units:** amounts are rounded down to whole parcels or kits, and the few leftover
   units go to the highest-priority areas that still need them.

### Safety guarantees

- The **Resource Agent** checks every request against its stock. If a request asks for too
  much, it is scaled down, so the stock can never go negative.
- The **Monitoring Agent** checks three rules every round and reports the result in the dashboard:
  no negative inventory, no area receiving more than its need, and total delivered ≤ stock available.
- If every need is met, the leftover stock stays in the warehouse.

### Fairness index

The Monitoring Agent calculates **Jain's fairness index** for the coverage of the areas:
`(Σx)² / (n · Σx²)`. A value of 1.0 means every area has the same share of its need covered.

---

## 6. Dashboard features

- **Sidebar settings:** stock for each resource, number of convoys (1-6), guaranteed minimum
  share, and the five priority weights.
- **Editable area table:** change population, needs or urgency before you run the simulation.
- **▶ Run simulation** runs all five agents. **↺ Reset** restores the default data and settings
  and clears the results.
- **Headline statistics:** coverage per resource, fairness index, areas below 50% coverage,
  number of agent messages, and the result of the safety checks.
- **Tabs:**
  - *Distribution*: need vs delivered for each area, coverage chart, results table, deliveries per round
  - *Priorities*: priority score chart, how each score is built from its factors, how rankings changed by the final round
  - *Inventory*: need, stock received, distributed and remaining stock for each resource
  - *Monitoring*: coverage over the rounds, round statistics, safety checks, alerts
  - *Agent messages*: the full message log with a filter by message type

---

## 7. Data files

`data/areas.csv`: one row per area

| column | meaning |
|---|---|
| area_id, area_name, region | identification |
| population | number of people |
| food_need / water_need / medicine_need | units needed (parcels, 20 L water units, medical kits) |
| urgency | 1 (low) to 5 (extreme) |
| vulnerable_pct | % of children, elderly, sick and pregnant people |
| access_difficulty | 1 (easy) to 5 (very hard to reach) |

`data/resources.csv`: available stock of food, water and medicine with their units.
