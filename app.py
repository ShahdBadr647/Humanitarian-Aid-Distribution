"""
Streamlit dashboard for the Humanitarian Aid Distribution System.

Run with:   streamlit run app.py
"""

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import charts
from agents.config import DEFAULT_MIN_SHARE, DEFAULT_WEIGHTS, RESOURCES
from data_loader import clean_areas, load_areas, load_resources
from simulation import run_simulation

st.set_page_config(page_title="Aid Distribution MAS", layout="wide")

# ---------------------------------------------------------------------------
# Default values for every control (used on first load and by the Reset button)
# ---------------------------------------------------------------------------
DEFAULT_ROUNDS = 3
RESOURCE_DEFAULTS = load_resources()
DEFAULT_STOCK = dict(zip(RESOURCE_DEFAULTS["resource"], RESOURCE_DEFAULTS["available"]))
UNIT_NAMES = dict(zip(RESOURCE_DEFAULTS["resource"], RESOURCE_DEFAULTS["unit"]))

WIDGET_DEFAULTS = {
    "rounds": DEFAULT_ROUNDS,
    "min_share": int(DEFAULT_MIN_SHARE * 100),
    **{f"w_{k}": int(v * 100) for k, v in DEFAULT_WEIGHTS.items()},
    **{f"stock_{r}": int(DEFAULT_STOCK[r]) for r in RESOURCES},
}


def reset_simulation():
    """Remove results and restore every control to its default value."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    for key, value in WIDGET_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["areas"] = load_areas()
    st.session_state["editor_version"] = 0


# First visit: set the defaults
if "areas" not in st.session_state:
    reset_simulation()


def show_chart(fig):
    """Display a Matplotlib figure and free its memory."""
    st.pyplot(fig)
    plt.close(fig)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


# ---------------------------------------------------------------------------
# Sidebar: simulation settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Simulation settings")

    st.subheader("Available stock")
    stock = {}
    for r in RESOURCES:
        stock[r] = st.number_input(
            f"{r.capitalize()} ({UNIT_NAMES[r]})", min_value=0, step=500, key=f"stock_{r}"
        )

    st.subheader("Distribution")
    rounds = st.slider("Number of convoys (rounds)", 1, 6, key="rounds",
                       help="The stock arrives in this many equal convoys. Priorities are re-calculated each round.")
    min_share = st.slider("Guaranteed minimum share of need (%)", 0, 50, key="min_share",
                          help="Every area first receives this share of its need before the rest is shared by priority.")

    st.subheader("Priority weights")
    st.caption("Relative importance of each factor. They are normalised to 100%.")
    weights = {
        "urgency": st.slider("Urgency", 0, 100, key="w_urgency"),
        "need": st.slider("Need per person", 0, 100, key="w_need"),
        "vulnerability": st.slider("Vulnerable population", 0, 100, key="w_vulnerability"),
        "access": st.slider("Access difficulty", 0, 100, key="w_access"),
        "fairness": st.slider("Fairness (less aid so far)", 0, 100, key="w_fairness"),
    }
    total_w = sum(weights.values())
    if total_w == 0:
        st.warning("All weights are 0 - equal weights will be used.")
    else:
        st.caption(" · ".join(f"{k} {v / total_w:.0%}" for k, v in weights.items()))

# ---------------------------------------------------------------------------
# Header and action buttons
# ---------------------------------------------------------------------------
st.title("Humanitarian Aid Distribution System")
st.caption(
    "A multi-agent simulation that shares food, water and medicine among areas in Palestine "
    "based on need, urgency, available stock and fairness. **All data is fictional.**"
)

col_run, col_reset, _ = st.columns([1.3, 1, 5])
run_clicked = col_run.button("▶ Run simulation", type="primary")
col_reset.button("↺ Reset", on_click=reset_simulation)

# ---------------------------------------------------------------------------
# Input data (editable)
# ---------------------------------------------------------------------------
with st.expander("Area needs (input data - you can edit the numbers)", expanded="result" not in st.session_state):
    edited = st.data_editor(
        st.session_state["areas"],
        num_rows="fixed",
        disabled=["area_id"],
        hide_index=True,
        key=f"area_editor_{st.session_state['editor_version']}",
        column_config={
            "urgency": st.column_config.NumberColumn("urgency (1-5)", min_value=1, max_value=5, step=1),
            "access_difficulty": st.column_config.NumberColumn("access difficulty (1-5)", min_value=1, max_value=5, step=1),
            "vulnerable_pct": st.column_config.NumberColumn("vulnerable %", min_value=0, max_value=100, step=1),
        },
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Areas", len(edited))
    c2.metric("Population", f"{int(edited['population'].sum()):,}")
    for col, r in zip((c3, c4), ("food", "water")):
        need, have = int(edited[f"{r}_need"].sum()), int(stock[r])
        col.metric(f"{r.capitalize()} stock vs need", f"{have / need:.0%}" if need else "n/a",
                   help=f"{have:,} available for {need:,} needed")

# ---------------------------------------------------------------------------
# Run the simulation
# ---------------------------------------------------------------------------
if run_clicked:
    try:
        areas = clean_areas(pd.DataFrame(edited))
        if areas.empty:
            st.error("There are no areas to distribute aid to.")
        else:
            with st.spinner("Agents are working..."):
                st.session_state["result"] = run_simulation(
                    areas, stock, rounds=rounds, weights=weights, min_share=min_share / 100
                )
    except ValueError as error:
        st.error(f"Input data problem: {error}")

if "result" not in st.session_state:
    st.info("Adjust the settings in the sidebar if you like, then press **Run simulation**.")
    st.stop()

result = st.session_state["result"]
summary = result.area_summary
inventory = result.inventory.set_index("resource")
last_stats = result.round_stats.iloc[-1]

# ---------------------------------------------------------------------------
# Headline statistics
# ---------------------------------------------------------------------------
st.divider()
if result.all_checks_passed:
    st.success(f"✔ All {len(result.checks)} safety checks passed - no negative inventory and no over-allocation.")
else:
    st.error("✖ Some safety checks failed - see the Monitoring tab.")

k = st.columns(6)
for col, r in zip(k[:3], RESOURCES):
    col.metric(f"{r.capitalize()} need covered", f"{inventory.loc[r, 'coverage_pct']:.1f}%",
               help=f"{inventory.loc[r, 'distributed']:,} of {inventory.loc[r, 'total_need']:,} {UNIT_NAMES[r]}")
k[3].metric("Fairness index", f"{last_stats['fairness_index']:.3f}",
            help="Jain's index of area coverage: 1.000 = every area covered equally.")
k[4].metric("Areas below 50% coverage", int(last_stats["areas_below_50pct"]))
k[5].metric("Agent messages", len(result.messages))

# ---------------------------------------------------------------------------
# Result tabs
# ---------------------------------------------------------------------------
tab_dist, tab_prio, tab_inv, tab_mon, tab_msg = st.tabs(
    ["📦 Distribution", "🎯 Priorities", "🏬 Inventory", "🩺 Monitoring", "💬 Agent messages"]
)

with tab_dist:
    st.subheader("Need vs delivered, per area")
    show_chart(charts.needs_vs_delivered_chart(summary))

    left, right = st.columns([1.1, 1])
    with left:
        st.subheader("Coverage of each area's need")
        show_chart(charts.coverage_chart(summary))
    with right:
        st.subheader("Distribution results")
        table = summary[["area_name", "priority_level"]].copy()
        for r in RESOURCES:
            table[f"{r} received"] = summary[f"{r}_received"]
            table[f"{r} unmet"] = summary[f"{r}_remaining"]
        table["overall coverage"] = (summary["overall_coverage"] * 100).round(1)
        st.dataframe(
            table.sort_values("overall coverage", ascending=False),
            hide_index=True,
            column_config={"overall coverage": st.column_config.ProgressColumn(
                "overall coverage", format="%.1f%%", min_value=0, max_value=100)},
        )

    st.subheader("Deliveries per convoy round")
    per_round = result.round_allocations.pivot_table(
        index="area_name", columns="Round", values=RESOURCES, aggfunc="sum"
    )
    per_round.columns = [f"{res} · round {rnd}" for res, rnd in per_round.columns]
    st.dataframe(per_round)

with tab_prio:
    left, right = st.columns([1, 1.1])
    with left:
        st.subheader("Priority scores (round 1)")
        show_chart(charts.priority_chart(result.priorities))
    with right:
        st.subheader("How each score is built")
        st.caption("Each factor is scaled 0-1. Score = 100 × weighted sum (+5 if Monitoring raised an alert).")
        cols = ["rank", "area_name", "priority_score", "priority_level", "urgency_factor", "need_factor",
                "vulnerability_factor", "access_factor", "fairness_factor", "alert_boost"]
        st.dataframe(result.priorities[cols], hide_index=True)

    if len(result.round_stats) > 1:
        st.subheader("Priority scores in the final round")
        st.caption("Fairness re-ranks areas: those that received a smaller share earlier move up.")
        merged = result.priorities[["area_name", "priority_score", "rank"]].merge(
            result.final_priorities[["area_name", "priority_score", "rank"]],
            on="area_name", suffixes=(" (round 1)", " (final round)"),
        )
        st.dataframe(merged.sort_values("rank (final round)"), hide_index=True)

with tab_inv:
    st.subheader("Stock and need per resource")
    show_chart(charts.inventory_chart(result.inventory))
    inv_table = result.inventory.copy()
    inv_table["unit"] = inv_table["resource"].map(UNIT_NAMES)
    st.dataframe(inv_table[["resource", "unit", "total_need", "initial_stock", "distributed",
                            "remaining", "unmet_need", "coverage_pct"]], hide_index=True)
    if (result.inventory["remaining"] > 0).any():
        st.info("Some stock is left because every area's need for that resource is fully met.")

with tab_mon:
    left, right = st.columns([1.1, 1])
    with left:
        st.subheader("Progress over the rounds")
        show_chart(charts.rounds_chart(result.round_stats))
    with right:
        st.subheader("Round statistics")
        stats = result.round_stats.copy()
        show = pd.DataFrame({"Round": stats["Round"]})
        for r in RESOURCES:
            show[f"{r} delivered"] = stats[f"{r}_delivered"]
            show[f"{r} coverage %"] = (stats[f"{r}_coverage"] * 100).round(1)
        show["fairness index"] = stats["fairness_index"].round(3)
        show["areas < 50%"] = stats["areas_below_50pct"]
        st.dataframe(show, hide_index=True)

    st.subheader("Safety checks")
    st.dataframe(result.checks, hide_index=True)

    st.subheader("Alerts")
    if result.alerts.empty:
        st.success("No alerts: no critical area fell behind the average coverage.")
    else:
        st.warning(f"⚠ {len(result.alerts)} alert(s) raised. Flagged areas received a priority boost in the next round.")
        st.dataframe(result.alerts, hide_index=True)

with tab_msg:
    st.subheader("Communication between agents")
    st.caption("Every message sent through the message bus, in order.")
    msgs = result.messages
    counts = msgs.groupby(["From", "To"]).size().reset_index(name="Messages")
    c1, c2 = st.columns([1, 2])
    c1.dataframe(counts, hide_index=True)
    types = c2.multiselect("Filter by message type", sorted(msgs["Type"].unique()))
    c2.dataframe(msgs[msgs["Type"].isin(types)] if types else msgs, hide_index=True)
