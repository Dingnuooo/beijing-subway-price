import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib import font_manager
import requests
import xml.etree.ElementTree as ET


XML_URL = "https://map.bjsubway.com/subwaymap/beijing.xml?v=20260210"
MapLines = List[Tuple[List[float], List[float], str]]
StationCoords = Dict[str, Tuple[float, float]]


def setup_chinese_font() -> None:
    # Try common Windows CJK fonts so station labels can render correctly.
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return


def parse_hex_color(raw: str, fallback: str = "#808080") -> str:
    if not raw:
        return fallback
    raw = raw.strip()
    if raw.startswith("0x") and len(raw) == 8:
        return "#" + raw[2:]
    if raw.startswith("#") and len(raw) in (4, 7):
        return raw
    return fallback


def parse_arc(raw: str) -> Optional[Tuple[float, float]]:
    if not raw or ":" not in raw:
        return None
    left, right = raw.split(":", 1)
    try:
        return float(left), float(right)
    except ValueError:
        return None


def quadratic_bezier(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    steps: int = 14,
) -> Tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    for i in range(steps + 1):
        t = i / steps
        omt = 1.0 - t
        x = omt * omt * p0[0] + 2.0 * omt * t * p1[0] + t * t * p2[0]
        y = omt * omt * p0[1] + 2.0 * omt * t * p1[1] + t * t * p2[1]
        xs.append(x)
        ys.append(y)
    return xs, ys


def load_prices(csv_path: Path) -> Dict[str, int]:
    prices: Dict[str, int] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = (row.get("status") or "").strip()
            end = (row.get("end") or "").strip()
            price_raw = (row.get("price") or "").strip()
            if not end or status not in {"ok", "self"} or price_raw == "":
                continue
            prices[end] = int(float(price_raw))
    return prices


def load_map_data() -> Tuple[List[Tuple[List[float], List[float], str]], Dict[str, Tuple[float, float]]]:
    xml_bytes = requests.get(XML_URL, timeout=25).content
    root = ET.fromstring(xml_bytes)

    lines: List[Tuple[List[float], List[float], str]] = []
    station_points: Dict[str, List[Tuple[float, float]]] = defaultdict(list)

    for line in root.findall(".//l"):
        color = parse_hex_color(line.attrib.get("lc", ""))
        points: List[Tuple[float, float, Optional[Tuple[float, float]]]] = []

        for p in line.findall("p"):
            x_raw = p.attrib.get("x")
            y_raw = p.attrib.get("y")
            if not x_raw or not y_raw:
                continue
            try:
                x = float(x_raw)
                y = float(y_raw)
            except ValueError:
                continue

            points.append((x, y, parse_arc(p.attrib.get("arc", ""))))

            if p.attrib.get("st") == "true":
                name = (p.attrib.get("lb") or "").strip()
                if name:
                    station_points[name].append((x, y))

        if len(points) < 2:
            continue

        def add_segment(
            p0: Tuple[float, float, Optional[Tuple[float, float]]],
            p1: Tuple[float, float, Optional[Tuple[float, float]]],
        ) -> None:
            x0, y0, arc = p0
            x1, y1, _ = p1
            if arc is None:
                lines.append(([x0, x1], [y0, y1], color))
                return
            xs, ys = quadratic_bezier((x0, y0), arc, (x1, y1))
            lines.append((xs, ys, color))

        for i in range(len(points) - 1):
            add_segment(points[i], points[i + 1])

        lcode = (line.attrib.get("lcode") or "").strip()
        if lcode in {"02", "10"}:
            add_segment(points[-1], points[0])

    stations: Dict[str, Tuple[float, float]] = {}
    for name, pts in station_points.items():
        avg_x = sum(x for x, _ in pts) / len(pts)
        avg_y = sum(y for _, y in pts) / len(pts)
        stations[name] = (avg_x, avg_y)

    return lines, stations


def create_base_map_axes(
    lines: MapLines,
    stations: StationCoords,
    line_width: float = 1.8,
    line_alpha: float = 0.45,
    base_station_size: float = 4,
) -> Tuple[Figure, Axes]:
    fig = plt.figure(figsize=(18, 10), dpi=200)
    ax = fig.add_subplot(111)

    for xs, ys, color in lines:
        ax.plot(xs, ys, color=color, linewidth=line_width, alpha=line_alpha, solid_capstyle="round", zorder=1)

    if stations:
        all_x = [xy[0] for xy in stations.values()]
        all_y = [xy[1] for xy in stations.values()]
        ax.scatter(all_x, all_y, s=base_station_size, c="#a0a0a0", zorder=2)

    return fig, ax


def mark_station(
    ax: Axes,
    stations: StationCoords,
    station_name: str,
    marker_size: float = 120,
    marker_color: str = "#0066ff",
) -> None:
    if station_name not in stations:
        return
    sx, sy = stations[station_name]
    ax.scatter([sx], [sy], s=marker_size, c=marker_color, edgecolors="#ffffff", linewidths=1.2, zorder=6)


def finalize_and_save_plot(fig: Figure, ax: Axes, out_path: Path) -> None:
    ax.set_aspect("equal", adjustable="box")
    ax.invert_yaxis()
    ax.axis("off")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def draw_map(
    lines: MapLines,
    stations: StationCoords,
    prices: Dict[str, int],
    out_path: Path,
    start_station: str,
    labels_out_path: Path,
) -> Tuple[int, int, int, Dict[int, int]]:
    fig, ax = create_base_map_axes(lines, stations, line_width=1.8, line_alpha=0.45, base_station_size=4)

    c_3 = "#0066ff"
    c_4 = "#009900"
    c_5 = "#9966ff"
    c_6 = "#ffcc00"
    c_7 = "#ff8800"
    c_8 = "#ae0606"

    highlight_x: List[float] = []
    highlight_y: List[float] = []
    highlight_colors: List[str] = []
    highlight_records: List[Tuple[str, int, float, float, str]] = []
    fare_counts: Dict[int, int] = {k: 0 for k in range(3, 9)}
    for name, price in prices.items():
        if name not in stations:
            continue

        color = ""
        if price == 3:
            color = c_3
        elif price == 4:
            color = c_4
        elif price == 5:
            color = c_5
        elif price == 6:
            color = c_6
        elif price == 7:
            color = c_7
        elif price == 8:
            color = c_8

        if color:
            x, y = stations[name]
            highlight_x.append(x)
            highlight_y.append(y)
            highlight_colors.append(color)
            highlight_records.append((name, price, x, y, color))
            fare_counts[price] += 1

    ax.scatter(highlight_x, highlight_y, s=26, c=highlight_colors, edgecolors="#ffffff", linewidths=0.4, zorder=5)

    label_count = 0
    for name, _, x, y, _ in sorted(highlight_records, key=lambda t: (t[1], t[0])):
        ax.text(
            x + 4,
            y - 4,
            name,
            fontsize=6,
            color="#111111",
            alpha=0.92,
            zorder=7,
            bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none", "alpha": 0.65},
        )
        label_count += 1

    mark_station(ax, stations, start_station, marker_size=120, marker_color="#0066ff")

    ax.set_title(
        f"{start_station}站 票价图",
        fontsize=14,
    )

    ax.scatter([], [], c=c_3, s=30, label="3 元")
    ax.scatter([], [], c=c_4, s=30, label="4 元")
    ax.scatter([], [], c=c_5, s=30, label="5 元")
    ax.scatter([], [], c=c_6, s=30, label="6 元")
    ax.scatter([], [], c=c_7, s=30, label="7 元")
    ax.scatter([], [], c=c_8, s=30, label="8 元")
    ax.legend(loc="upper right", frameon=True, fontsize=9)

    labels_out_path.parent.mkdir(parents=True, exist_ok=True)
    with labels_out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["station", "price", "group", "color"])
        for name, price, _, _, color in sorted(highlight_records, key=lambda t: (t[1], t[0])):
            group = f"= {price}"
            writer.writerow([name, price, group, color])

    finalize_and_save_plot(fig, ax, out_path)

    return len(highlight_x), len(stations), label_count, fare_counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Highlight 3-8 CNY fare stations on Beijing subway schematic map")
    parser.add_argument("--csv", default="beijing_subway_prices.csv", help="Fare CSV file")
    parser.add_argument("--start", default="良乡大学城", help="Start station name")
    parser.add_argument("--out", default="beijing_subway_fare_3_8.png", help="Output image path")
    parser.add_argument("--labels-out", default="beijing_subway_fare_3_8_labels.csv", help="Highlighted station list output")
    args = parser.parse_args()

    setup_chinese_font()

    csv_path = Path(args.csv)
    prices = load_prices(csv_path)
    lines, stations = load_map_data()

    highlighted, total, labeled, fare_counts = draw_map(
        lines=lines,
        stations=stations,
        prices=prices,
        out_path=Path(args.out),
        start_station=args.start,
        labels_out_path=Path(args.labels_out),
    )

    print(f"Loaded prices: {len(prices)}")
    print(f"Stations on map: {total}")
    print(f"Highlighted total (3-8): {highlighted}")
    print(
        "Fare counts: "
        f"3={fare_counts[3]}, 4={fare_counts[4]}, 5={fare_counts[5]}, "
        f"6={fare_counts[6]}, 7={fare_counts[7]}, 8={fare_counts[8]}"
    )
    print(f"Labeled stations: {labeled}")
    print(f"Saved image: {args.out}")
    print(f"Saved label list: {args.labels_out}")


if __name__ == "__main__":
    main()
