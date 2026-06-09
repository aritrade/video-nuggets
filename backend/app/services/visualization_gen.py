"""
Visualization generator that auto-creates charts, comparison graphs,
architecture diagrams, and analytics visuals from content using matplotlib/plotly.
"""
import re
import uuid
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

from app.config import VISUALIZATIONS_DIR, BRAND_COLORS, VIDEO_RESOLUTION


plt.rcParams["font.family"] = "Arial"
plt.rcParams["font.size"] = 14


def generate_comparison_chart(
    title: str,
    categories: list[str],
    values_a: list[float],
    values_b: list[float],
    label_a: str = "Traditional",
    label_b: str = "Nutanix",
) -> str:
    """Generate a side-by-side comparison bar chart."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_facecolor(BRAND_COLORS["dark_text"])

    x = np.arange(len(categories))
    width = 0.35

    bars_a = ax.bar(x - width / 2, values_a, width, label=label_a,
                    color=BRAND_COLORS["coral"], edgecolor="none")
    bars_b = ax.bar(x + width / 2, values_b, width, label=label_b,
                    color=BRAND_COLORS["teal"], edgecolor="none")

    ax.set_title(title, color=BRAND_COLORS["white"], fontsize=22, fontweight="bold", pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, color=BRAND_COLORS["white"], fontsize=14)
    ax.tick_params(axis="y", colors=BRAND_COLORS["white"])
    ax.legend(fontsize=14, facecolor=BRAND_COLORS["dark_text"],
              edgecolor=BRAND_COLORS["light_purple"], labelcolor=BRAND_COLORS["white"])
    ax.spines[:].set_visible(False)
    ax.grid(axis="y", alpha=0.2, color=BRAND_COLORS["white"])

    output_path = str(VISUALIZATIONS_DIR / f"comparison_{uuid.uuid4().hex[:8]}.png")
    plt.tight_layout()
    plt.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    return output_path


def generate_architecture_diagram(
    title: str,
    layers: list[dict],
) -> str:
    """Generate a layered architecture diagram.
    
    layers: [{"name": "Layer Name", "components": ["A", "B", "C"]}, ...]
    """
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(8, 8.5, title, ha="center", va="top",
            fontsize=24, fontweight="bold", color=BRAND_COLORS["white"])

    colors = [BRAND_COLORS["dark_purple"], BRAND_COLORS["dark_blue"],
              BRAND_COLORS["deep_purple"], BRAND_COLORS["light_purple"]]
    layer_height = 1.2
    start_y = 7.0

    for i, layer in enumerate(layers):
        y = start_y - i * (layer_height + 0.4)
        color = colors[i % len(colors)]

        rect = FancyBboxPatch(
            (1, y - layer_height), 14, layer_height,
            boxstyle="round,pad=0.1", facecolor=color, alpha=0.8, edgecolor=BRAND_COLORS["teal"],
        )
        ax.add_patch(rect)

        ax.text(1.5, y - 0.2, layer["name"], fontsize=14, fontweight="bold",
                color=BRAND_COLORS["white"], va="top")

        if layer.get("components"):
            comp_text = "  |  ".join(layer["components"])
            ax.text(8, y - layer_height / 2 - 0.1, comp_text,
                    ha="center", va="center", fontsize=12, color=BRAND_COLORS["teal"])

    output_path = str(VISUALIZATIONS_DIR / f"arch_{uuid.uuid4().hex[:8]}.png")
    plt.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    return output_path


def generate_flow_diagram(
    title: str,
    steps: list[str],
) -> str:
    """Generate a horizontal flow/process diagram."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(8, 8.3, title, ha="center", va="top",
            fontsize=22, fontweight="bold", color=BRAND_COLORS["white"])

    n = len(steps)
    box_width = min(2.5, 13.0 / n)
    spacing = (14 - n * box_width) / (n + 1)
    y_center = 4.5

    for i, step in enumerate(steps):
        x = 1 + spacing * (i + 1) + box_width * i
        color = BRAND_COLORS["light_purple"] if i % 2 == 0 else BRAND_COLORS["teal"]

        rect = FancyBboxPatch(
            (x, y_center - 0.8), box_width, 1.6,
            boxstyle="round,pad=0.15", facecolor=color, alpha=0.85, edgecolor="none",
        )
        ax.add_patch(rect)

        ax.text(x + box_width / 2, y_center, step,
                ha="center", va="center", fontsize=11, color=BRAND_COLORS["white"],
                fontweight="bold", wrap=True)

        if i < n - 1:
            arrow_x = x + box_width + spacing * 0.2
            ax.annotate("", xy=(arrow_x + spacing * 0.6, y_center),
                       xytext=(arrow_x, y_center),
                       arrowprops=dict(arrowstyle="->", color=BRAND_COLORS["coral"], lw=2))

    output_path = str(VISUALIZATIONS_DIR / f"flow_{uuid.uuid4().hex[:8]}.png")
    plt.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    return output_path


def generate_pie_chart(
    title: str,
    labels: list[str],
    values: list[float],
) -> str:
    """Generate a styled pie/donut chart."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_facecolor(BRAND_COLORS["dark_text"])

    colors = [BRAND_COLORS["light_purple"], BRAND_COLORS["teal"],
              BRAND_COLORS["green"], BRAND_COLORS["coral"],
              BRAND_COLORS["dark_blue"], BRAND_COLORS["deep_purple"]]

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colors[:len(values)],
        autopct="%1.0f%%", pctdistance=0.8, startangle=90,
        wedgeprops=dict(width=0.5, edgecolor=BRAND_COLORS["dark_text"]),
    )

    for text in texts:
        text.set_color(BRAND_COLORS["white"])
        text.set_fontsize(13)
    for autotext in autotexts:
        autotext.set_color(BRAND_COLORS["white"])
        autotext.set_fontsize(12)
        autotext.set_fontweight("bold")

    ax.set_title(title, color=BRAND_COLORS["white"], fontsize=22, fontweight="bold", pad=20)

    output_path = str(VISUALIZATIONS_DIR / f"pie_{uuid.uuid4().hex[:8]}.png")
    plt.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    return output_path


def generate_key_points_visual(
    title: str,
    points: list[dict],
) -> str:
    """Generate a key points infographic.
    
    points: [{"icon": "emoji/number", "title": "Point", "description": "Details"}, ...]
    """
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(8, 8.3, title, ha="center", va="top",
            fontsize=24, fontweight="bold", color=BRAND_COLORS["white"])

    n = len(points)
    col_width = 14.0 / n
    start_x = 1.0

    for i, point in enumerate(points):
        x = start_x + i * col_width + col_width / 2
        color = BRAND_COLORS["teal"] if i % 2 == 0 else BRAND_COLORS["light_purple"]

        circle = plt.Circle((x, 5.5), 0.6, color=color, alpha=0.9)
        ax.add_patch(circle)
        ax.text(x, 5.5, point.get("icon", str(i + 1)),
                ha="center", va="center", fontsize=20, color=BRAND_COLORS["white"],
                fontweight="bold")

        ax.text(x, 4.3, point["title"], ha="center", va="top",
                fontsize=14, fontweight="bold", color=BRAND_COLORS["white"])

        if point.get("description"):
            ax.text(x, 3.5, point["description"], ha="center", va="top",
                    fontsize=11, color=BRAND_COLORS["white"], alpha=0.8,
                    wrap=True)

    output_path = str(VISUALIZATIONS_DIR / f"points_{uuid.uuid4().hex[:8]}.png")
    plt.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    return output_path


def generate_timeline_visual(
    title: str,
    events: list[dict],
) -> str:
    """Generate a timeline visualization.
    
    events: [{"label": "2011", "description": "Founded"}, ...]
    """
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    fig.patch.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_facecolor(BRAND_COLORS["dark_text"])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(8, 8.3, title, ha="center", va="top",
            fontsize=22, fontweight="bold", color=BRAND_COLORS["white"])

    y_line = 4.5
    ax.plot([1, 15], [y_line, y_line], color=BRAND_COLORS["light_purple"], lw=3, alpha=0.7)

    n = len(events)
    spacing = 14.0 / (n + 1)

    for i, event in enumerate(events):
        x = 1 + spacing * (i + 1)
        color = BRAND_COLORS["teal"] if i % 2 == 0 else BRAND_COLORS["coral"]

        ax.plot(x, y_line, "o", color=color, markersize=14, zorder=5)

        y_text = y_line + 1.2 if i % 2 == 0 else y_line - 1.2
        va = "bottom" if i % 2 == 0 else "top"

        ax.text(x, y_text, event["label"], ha="center", va=va,
                fontsize=13, fontweight="bold", color=color)
        ax.text(x, y_text + (0.4 if i % 2 == 0 else -0.4),
                event.get("description", ""), ha="center", va=va,
                fontsize=10, color=BRAND_COLORS["white"], alpha=0.8)

    output_path = str(VISUALIZATIONS_DIR / f"timeline_{uuid.uuid4().hex[:8]}.png")
    plt.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    return output_path
