import argparse
import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict


class FareRecord(TypedDict):
    price: Optional[int]
    status: str
    error: str


FareTable = Dict[str, FareRecord]
ComparisonRows = Tuple[List[Dict[str, object]], List[Dict[str, object]]]


def load_fares(csv_path: Path) -> FareTable:
    fares: FareTable = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            station = (row.get("end") or "").strip()
            status = (row.get("status") or "").strip()
            price_raw = (row.get("price") or "").strip()
            price = None
            if status in {"ok", "self"} and price_raw != "":
                price = int(float(price_raw))
            fares[station] = {"price": price, "status": status, "error": (row.get("error") or "").strip()}
    return fares


def compare_fares(fares_1: FareTable, fares_2: FareTable, origin_1: str, origin_2: str) -> ComparisonRows:
    all_stations = sorted(set(fares_1.keys()) | set(fares_2.keys()))

    diff_rows: List[Dict[str, object]] = []
    cheaper_rows: List[Dict[str, object]] = []

    for station in all_stations:
        record_1 = fares_1.get(station)
        record_2 = fares_2.get(station)
        price_1 = record_1["price"] if record_1 is not None else None
        price_2 = record_2["price"] if record_2 is not None else None
        cheaper_origin = "N/A"
        delta = ""

        if price_1 is not None and price_2 is not None:
            diff = price_1 - price_2
            delta = str(diff)
            if diff < 0:
                cheaper_origin = origin_1
            elif diff > 0:
                cheaper_origin = origin_2
            else:
                cheaper_origin = "Same"

            diff_rows.append(
                {
                    "station": station,
                    "price_1": price_1,
                    "price_2": price_2,
                    "delta_1_minus_2": diff,
                }
            )

        cheaper_rows.append(
            {
                "station": station,
                "price_1": price_1 if price_1 is not None else "",
                "price_2": price_2 if price_2 is not None else "",
                "cheaper_origin": cheaper_origin,
                "delta_1_minus_2": delta,
            }
        )

    return cheaper_rows, diff_rows


def write_csv_rows(path: Path, rows: List[Dict[str, object]], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv1", help="CSV for origin 1")
    parser.add_argument("name1", help="Name of origin 1")
    parser.add_argument("csv2", help="CSV for origin 2")
    parser.add_argument("name2", help="Name of origin 2")
    parser.add_argument("out_cheaper", help="Output cheaper CSV")
    parser.add_argument("out_diff", help="Output diff CSV")
    args = parser.parse_args()

    fares_1 = load_fares(Path(args.csv1))
    fares_2 = load_fares(Path(args.csv2))
    cheaper_rows, diff_rows = compare_fares(fares_1, fares_2, args.name1, args.name2)

    write_csv_rows(
        Path(args.out_diff),
        diff_rows,
        ["station", "price_1", "price_2", "delta_1_minus_2"],
    )
    write_csv_rows(
        Path(args.out_cheaper),
        cheaper_rows,
        ["station", "price_1", "price_2", "cheaper_origin", "delta_1_minus_2"],
    )

    print(f"Generated {args.out_cheaper} and {args.out_diff}")

if __name__ == "__main__":
    main()
