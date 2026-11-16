"""
Matplotlib charts for the dashboard.

Every resource keeps the same color in every chart, so a reader learns it once:
    water = blue, food = orange, medicine = aqua
"""

import matplotlib

matplotlib.use("Agg")  # draw without opening a window (needed for Streamlit)
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter

from agents.config import RESOURCES

# ---- Colors (colorblind-checked categorical palette) -----------------------
RESOURCE_COLORS = {"water": "#2a78d6", "food": "#eb6834", "medicine": "#1baf7a"}
NEED_COLOR = "#e1e0d9"       # light neutral used for "need" / background tracks
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
PRIORITY_COLOR = "#2a78d6"

UNITS = {"food": "food parcels", "water": "water units (20 L)", "medicine": "medical kits"}


def thousands(x, _pos=None):
    """Axis label formatter: 12000 -> 12k, 1250 -> 1.25k."""
    return f"{x / 1000:g}k" if abs(x) >= 1000 else f"{x:.0f}"


def _style(ax, grid_axis="x"):
    """Apply a clean, quiet style to an axis."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9, length=0)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(width, height, ncols=1):
    fig, axes = plt.subplots(1, ncols, figsize=(width, height), facecolor=SURFACE)
    return fig, axes


def needs_vs_delivered_chart(summary):
    """Three small panels (one per resource): need as a grey track, delivered on top in color."""
    data = summary.sort_values("priority_score", ascending=True)
    fig, axes = _figure(13, 4.8, ncols=3)
    for ax, resource in zip(axes, ["food", "water", "medicine"]):
        _style(ax)
        y = range(len(data))
        ax.barh(y, data[f"{resource}_need"], height=0.62, color=NEED_COLOR, label="Need")
        ax.barh(y, data[f"{resource}_received"], height=0.62, color=RESOURCE_COLORS[resource], label="Delivered")
        ax.set_yticks(list(y))
        ax.set_yticklabels(data["area_name"] if ax is axes[0] else [""] * len(data))
        ax.xaxis.set_major_formatter(FuncFormatter(thousands))
        ax.set_title(f"{resource.capitalize()}  ·  {UNITS[resource]}", loc="left", fontsize=11, color=INK)
        ax.legend(loc="lower right", fontsize=8, frameon=False, labelcolor=INK_SECONDARY)
    fig.text(0.01, 0.01, "Areas sorted by final priority score (highest at top)", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def priority_chart(priorities):
    """Horizontal bars of priority scores, highest at the top, value printed at the end of each bar."""
    data = priorities.sort_values("priority_score", ascending=True)
    fig, ax = _figure(7, 4.8)
    _style(ax)
    bars = ax.barh(data["area_name"], data["priority_score"], height=0.62, color=PRIORITY_COLOR)
    for bar, score in zip(bars, data["priority_score"]):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2, f"{score:.1f}",
                va="center", fontsize=9, color=INK_SECONDARY)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Priority score (0-100)", color=INK_SECONDARY, fontsize=9)
    fig.tight_layout()
    return fig


def coverage_chart(summary):
    """Grouped bars: % of each area's need covered, per resource."""
    data = summary.sort_values("priority_score", ascending=True).reset_index(drop=True)
    fig, ax = _figure(7, 5.6)
    _style(ax)
    bar_h = 0.26
    for i, resource in enumerate(RESOURCES):
        # First resource on top of each group, so bars read in the same order as the legend
        positions = [k + (1 - i) * (bar_h + 0.02) for k in range(len(data))]
        ax.barh(positions, data[f"{resource}_coverage"] * 100, height=bar_h,
                color=RESOURCE_COLORS[resource], label=resource.capitalize())
    ax.set_yticks(range(len(data)))
    ax.set_yticklabels(data["area_name"])
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(PercentFormatter())
    ax.set_xlabel("Share of need covered", color=INK_SECONDARY, fontsize=9)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, frameon=False,
              fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    return fig


def inventory_chart(inventory):
    """One small panel per resource: total need, stock received, distributed, remaining."""
    fig, axes = _figure(13, 2.9, ncols=3)
    labels = ["Total need", "Stock received", "Distributed", "Remaining stock"]
    for ax, (_, row) in zip(axes, inventory.iterrows()):
        resource = row["resource"]
        _style(ax)
        values = [row["total_need"], row["initial_stock"], row["distributed"], row["remaining"]]
        colors = [NEED_COLOR, BASELINE, RESOURCE_COLORS[resource], MUTED]
        y = list(range(len(labels)))[::-1]
        ax.barh(y, values, height=0.6, color=colors)
        for yi, v in zip(y, values):
            ax.text(v + max(values) * 0.01, yi, f"{v:,.0f}", va="center", fontsize=8.5, color=INK_SECONDARY)
        ax.set_yticks(y)
        ax.set_yticklabels(labels if ax is axes[0] else [""] * len(labels))
        ax.set_xlim(0, max(values) * 1.18 if max(values) else 1)
        ax.xaxis.set_major_formatter(FuncFormatter(thousands))
        ax.set_title(f"{resource.capitalize()}  ·  {UNITS[resource]}", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    return fig


def rounds_chart(round_stats):
    """Line chart: cumulative coverage of total need after each round, per resource."""
    fig, ax = _figure(7, 4.2)
    _style(ax, grid_axis="y")
    rounds = round_stats["Round"]
    end_values = {}
    for resource in RESOURCES:
        values = round_stats[f"{resource}_coverage"] * 100
        ax.plot(rounds, values, color=RESOURCE_COLORS[resource], linewidth=2, marker="o",
                markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5, label=resource.capitalize())
        end_values[resource] = values.iloc[-1]

    # Direct labels at the end of each line, pushed apart so they never overlap
    min_gap = 5.0  # percentage points between labels
    label_y = {}
    for resource in sorted(end_values, key=end_values.get, reverse=True):
        y = end_values[resource]
        if label_y:
            y = min(y, min(label_y.values()) - min_gap)
        label_y[resource] = y
    for resource, y in label_y.items():
        ax.annotate(f"{resource.capitalize()} {end_values[resource]:.0f}%", (rounds.iloc[-1], end_values[resource]),
                    xytext=(rounds.iloc[-1] + 0.12, y), textcoords="data", va="center",
                    fontsize=8.5, color=INK_SECONDARY)
    ax.set_xticks(list(rounds))
    ax.set_xticklabels([f"Round {r}" for r in rounds])
    ax.set_xlim(rounds.min() - 0.3, rounds.max() + 0.9)
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(PercentFormatter())
    ax.set_ylabel("Cumulative coverage of total need", color=INK_SECONDARY, fontsize=9)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    return fig
