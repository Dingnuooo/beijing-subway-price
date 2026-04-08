#!/usr/bin/env python3
"""
生成单车站3-8元票价地图，或两个车站的票价差价对比图。
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from compare_origin_fares import compare_fares, load_fares
from crawl import crawl_prices, save_outputs
from plot_fare_diff_map import build_diff_lookup, draw_diff_map
from plot_fare_map import draw_map, load_map_data, load_prices, setup_chinese_font

CACHE_DIR = Path("beijing-subway-cache")
MapLines = List[Tuple[List[float], List[float], str]]
StationCoords = Dict[str, Tuple[float, float]]

_map_data_cache: Optional[Tuple[MapLines, StationCoords]] = None


def sanitize_station_name(station: str) -> str:
    return station.replace("/", "-").strip()


def get_cache_filename(station: str) -> str:
    safe_name = sanitize_station_name(station)
    return str(CACHE_DIR / f"beijing_subway_prices_{safe_name}.csv")


def get_output_filename(station: str) -> str:
    safe_name = sanitize_station_name(station)
    return f"beijing_subway_fare_3_8_{safe_name}.png"


def get_labels_filename(station: str) -> str:
    safe_name = sanitize_station_name(station)
    return f"beijing_subway_fare_3_8_{safe_name}_labels.csv"


def get_diff_filename(station_1: str, station_2: str) -> str:
    safe_name_1 = sanitize_station_name(station_1)
    safe_name_2 = sanitize_station_name(station_2)
    return f"beijing_subway_fare_diff_{safe_name_1}_vs_{safe_name_2}.png"


def get_shared_map_data() -> Tuple[MapLines, StationCoords]:
    global _map_data_cache
    if _map_data_cache is None:
        _map_data_cache = load_map_data()
    return _map_data_cache


def ensure_cache(station: str, no_crawl: bool, force_crawl: bool) -> bool:
    cache_csv = get_cache_filename(station)
    cache_path = Path(cache_csv)

    if no_crawl:
        if not cache_path.exists():
            print(f"❌ 缓存文件不存在且禁用爬虫: {cache_csv}")
            return False
        print(f"✓ 使用缓存文件: {cache_csv}")
        return True

    if cache_path.exists() and not force_crawl:
        print(f"✓ 使用缓存文件: {cache_csv}")
        return True

    if force_crawl and cache_path.exists():
        print(f"强制重新爬取数据（覆盖已有缓存）: {station}")
    else:
        print(f"缓存不存在，开始爬取: {station}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        records = crawl_prices(station, sleep_sec=0.05)
        save_outputs(records, json_path=None, csv_path=cache_path)
        ok_count = sum(1 for r in records if r["status"] in {"ok", "self"})
        err_count = sum(1 for r in records if r["status"] == "error")
        print(f"✅ 爬虫完成: 成功 {ok_count} 条, 失败 {err_count} 条")
        print(f"CSV : {cache_csv}")
        return True
    except Exception as exc:
        print(f"❌ 爬虫失败: {exc}")
        return False


def generate_fare_map(station: str) -> bool:
    cache_csv = Path(get_cache_filename(station))
    out_image = Path(get_output_filename(station))
    out_labels = Path(get_labels_filename(station))

    print(f"生成票价地图: {station}")
    try:
        prices = load_prices(cache_csv)
        lines, stations = get_shared_map_data()
        highlighted, total, labeled, fare_counts = draw_map(
            lines=lines,
            stations=stations,
            prices=prices,
            out_path=out_image,
            start_station=station,
            labels_out_path=out_labels,
        )
    except Exception as exc:
        print(f"❌ 票价地图生成失败: {exc}")
        return False

    print(f"Loaded prices: {len(prices)}")
    print(f"Stations on map: {total}")
    print(f"Highlighted total (3-8): {highlighted}")
    print(
        "Fare counts: "
        f"3={fare_counts[3]}, 4={fare_counts[4]}, 5={fare_counts[5]}, "
        f"6={fare_counts[6]}, 7={fare_counts[7]}, 8={fare_counts[8]}"
    )
    print(f"Labeled stations: {labeled}")
    print(f"Saved image: {out_image}")
    print(f"Saved label list: {out_labels}")

    print(f"✅ 车站 {station} 处理完成")
    print(f"   图表: {str(out_image)}")
    print(f"   标签: {str(out_labels)}")
    return True


def generate_diff_map(station_1: str, station_2: str) -> bool:
    cache_csv_1 = Path(get_cache_filename(station_1))
    cache_csv_2 = Path(get_cache_filename(station_2))
    out_image = Path(get_diff_filename(station_1, station_2))

    print(f"生成差价地图: {station_1} vs {station_2}")
    try:
        fares_1 = load_fares(cache_csv_1)
        fares_2 = load_fares(cache_csv_2)
        cheaper_rows, _ = compare_fares(fares_1, fares_2, station_1, station_2)
        diff_lookup = build_diff_lookup(cheaper_rows)
        lines, stations = get_shared_map_data()
        draw_diff_map(lines, stations, diff_lookup, out_image, station_1, station_2)
    except Exception as exc:
        print(f"❌ 差价地图生成失败: {exc}")
        return False

    print(f"Saved diff map to {str(out_image)}")
    print(f"✅ 完成！差价图表: {str(out_image)}")
    return True


def cleanup_non_cache_json_files() -> None:
    removed_count = 0
    for file_path in CACHE_DIR.glob("beijing_subway_prices*.json"):
        try:
            file_path.unlink()
            removed_count += 1
        except OSError:
            continue

    for file_path in Path(".").glob("beijing_subway_prices*.json"):
        try:
            file_path.unlink()
            removed_count += 1
        except OSError:
            continue

    if removed_count > 0:
        print(f"🧹 已自动清理非缓存 JSON 文件: {removed_count} 个")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成3-8元票价地图或差价对比地图")

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--station", help="单车站模式起点站")
    mode_group.add_argument("--multiple", nargs="+", help="批量单车站模式，后接多个车站名")
    mode_group.add_argument("--diff", nargs=2, metavar=("STATION1", "STATION2"), help="差价模式：比较两个起点站")

    parser.add_argument("--no-crawl", action="store_true", help="禁止爬虫，仅使用已有缓存文件")
    parser.add_argument("--force-crawl", action="store_true", help="忽略旧缓存，强制重爬并覆盖")
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    setup_chinese_font()

    if args.no_crawl and args.force_crawl:
        print("❌ 错误: --no-crawl 和 --force-crawl 不能同时使用")
        sys.exit(1)

    if args.diff:
        station_1, station_2 = args.diff
        if not ensure_cache(station_1, no_crawl=args.no_crawl, force_crawl=args.force_crawl):
            sys.exit(1)
        if not ensure_cache(station_2, no_crawl=args.no_crawl, force_crawl=args.force_crawl):
            sys.exit(1)
        if not generate_diff_map(station_1, station_2):
            sys.exit(1)
        sys.exit(0)

    stations = args.multiple if args.multiple else [args.station]
    print(f"开始处理 {len(stations)} 个车站...")

    all_success = True
    for idx, station in enumerate(stations, 1):
        print(f"\n[{idx}/{len(stations)}] 处理车站: {station}")
        print("=" * 60)

        if not ensure_cache(station, no_crawl=args.no_crawl, force_crawl=args.force_crawl):
            all_success = False
            continue
        if not generate_fare_map(station):
            all_success = False
            continue

    print("\n" + "=" * 60)
    if all_success:
        print("✅ 所有车站处理完成")
        sys.exit(0)

    print("❌ 部分车站处理失败")
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup_non_cache_json_files()
