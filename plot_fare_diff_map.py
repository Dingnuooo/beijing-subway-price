import argparse
from pathlib import Path
from typing import Dict, List, Tuple, TypedDict

import matplotlib.pyplot as plt

from compare_origin_fares import compare_fares, load_fares
from plot_fare_map import create_base_map_axes, finalize_and_save_plot, load_map_data, setup_chinese_font


class DiffLookupItem(TypedDict):
    cheaper_origin: str
    savings: int


def build_diff_lookup(cheaper_rows: List[Dict[str, object]]) -> Dict[str, DiffLookupItem]:
    lookup: Dict[str, DiffLookupItem] = {}
    for row in cheaper_rows:
        station_name = str(row.get("station") or "").strip()
        cheaper_origin = str(row.get("cheaper_origin") or "").strip()
        delta_raw = str(row.get("delta_1_minus_2") or "").strip()
        if not station_name or not delta_raw or cheaper_origin in {"N/A", "Same"}:
            continue

        try:
            savings = abs(int(delta_raw))
        except ValueError:
            continue

        lookup[station_name] = {
            "cheaper_origin": cheaper_origin,
            "savings": savings,
        }

    return lookup


def draw_diff_map(
    lines: List[Tuple[List[float], List[float], str]],
    stations: Dict[str, Tuple[float, float]],
    diff_lookup: Dict[str, DiffLookupItem],
    out_path: Path,
    origin_1: str,
    origin_2: str,
) -> None:
    fig, ax = create_base_map_axes(lines, stations, line_width=2.0, line_alpha=0.35, base_station_size=8)

    highlight_1_x: List[float] = []
    highlight_1_y: List[float] = []
    highlight_1_records: List[Tuple[str, float, float, int]] = []
    color_1 = "#0066ff"

    highlight_2_x: List[float] = []
    highlight_2_y: List[float] = []
    highlight_2_records: List[Tuple[str, float, float, int]] = []
    color_2 = "#ff3b30"

    for station_name, (x, y) in stations.items():
        data = diff_lookup.get(station_name)
        if not data:
            continue

        cheaper_origin = data["cheaper_origin"]
        savings = data["savings"]

        if cheaper_origin == origin_1:
            highlight_1_x.append(x)
            highlight_1_y.append(y)
            highlight_1_records.append((station_name, x, y, savings))
        elif cheaper_origin == origin_2:
            highlight_2_x.append(x)
            highlight_2_y.append(y)
            highlight_2_records.append((station_name, x, y, savings))

    ax.scatter(highlight_1_x, highlight_1_y, s=36, c=color_1, edgecolors="#ffffff", linewidths=0.6, zorder=5)
    ax.scatter(highlight_2_x, highlight_2_y, s=36, c=color_2, edgecolors="#ffffff", linewidths=0.6, zorder=5)

    all_highlights = highlight_1_records + highlight_2_records
    for station_name, x, y, savings in all_highlights:
        label_text = f"{station_name} ({savings})"
        ax.text(
            x + 4,
            y - 4,
            label_text,
            fontsize=7,
            color="#111111",
            alpha=0.92,
            zorder=7,
            bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none", "alpha": 0.7},
        )

    marker_color = "#000000"
    for station_name in [origin_1, origin_2]:
        if station_name in stations:
            sx, sy = stations[station_name]
            ax.scatter([sx], [sy], s=100, c=marker_color, edgecolors="#ffffff", linewidths=1.2, zorder=6)
            dy = -10 if station_name == origin_1 else 10
            ax.text(sx + 5, sy + dy, station_name, fontsize=10, color=marker_color, fontweight="bold")

    ax.set_title(
        f"{origin_1}站 与 {origin_2}站 票价对比图",
        fontsize=14,
    )

    ax.scatter([], [], c=color_1, s=40, label=f"{origin_1}站 更便宜")
    ax.scatter([], [], c=color_2, s=40, label=f"{origin_2}站 更便宜")
    ax.scatter([], [], c="#a0a0a0", s=40, label="同价或未开通")
    ax.legend(loc="upper right", frameon=True, fontsize=10)

    finalize_and_save_plot(fig, ax, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot a fare-difference map between two origins")
    parser.add_argument("csv1", help="Fare CSV for origin 1")
    parser.add_argument("csv2", help="Fare CSV for origin 2")
    parser.add_argument("name1", help="Origin 1 name")
    parser.add_argument("name2", help="Origin 2 name")
    parser.add_argument("out_img", help="Output diff map path")
    args = parser.parse_args()

    setup_chinese_font()
    lines, stations = load_map_data()

    fares_1 = load_fares(Path(args.csv1))
    fares_2 = load_fares(Path(args.csv2))
    cheaper_rows, _ = compare_fares(fares_1, fares_2, args.name1, args.name2)
    diff_lookup = build_diff_lookup(cheaper_rows)

    draw_diff_map(lines, stations, diff_lookup, Path(args.out_img), args.name1, args.name2)
    print(f"Saved diff map to {args.out_img}")


if __name__ == "__main__":
    main()
