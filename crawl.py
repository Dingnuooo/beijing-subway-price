import argparse
import csv
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests


BASE_URL = "https://map.bjsubway.com"
STATIONS_URL = f"{BASE_URL}/stations"
SEARCH_URL = f"{BASE_URL}/searchstartend"
CACHE_DIR = Path("beijing-subway-cache")


def get_all_station_names(session: requests.Session) -> List[str]:
	resp = session.get(STATIONS_URL, timeout=15)
	resp.raise_for_status()
	data = resp.json()

	names = []
	for item in data:
		name = (item.get("c_name") or "").strip()
		if name:
			names.append(name)

	return sorted(set(names))


def get_ticket_price(session: requests.Session, start: str, end: str, mintype: str = "1") -> int:
	params = {
		"start": start,
		"end": end,
		"mintype": mintype,
	}
	resp = session.get(SEARCH_URL, params=params, timeout=20)
	resp.raise_for_status()
	data = resp.json()

	if data.get("result") != "success":
		raise ValueError(f"接口返回失败: {data}")

	return int(data["price"])


def crawl_prices(start_station: str, sleep_sec: float = 0.05) -> List[Dict[str, object]]:
	session = requests.Session()
	session.headers.update(
		{
			"User-Agent": (
				"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
				"AppleWebKit/537.36 (KHTML, like Gecko) "
				"Chrome/130.0.0.0 Safari/537.36"
			),
			"Referer": "https://map.bjsubway.com/",
			"Accept": "application/json, text/javascript, */*; q=0.01",
		}
	)

	stations = get_all_station_names(session)
	if start_station not in stations:
		raise ValueError(f"起点不存在: {start_station}")

	results: List[Dict[str, object]] = []
	for idx, end_station in enumerate(stations, start=1):
		if end_station == start_station:
			price = 0
			status = "self"
			err = ""
		else:
			try:
				price = get_ticket_price(session, start_station, end_station, mintype="1")
				status = "ok"
				err = ""
			except Exception as e:
				price = None
				status = "error"
				err = str(e)

		results.append(
			{
				"start": start_station,
				"end": end_station,
				"price": price,
				"status": status,
				"error": err,
			}
		)

		if idx % 20 == 0 or idx == len(stations):
			print(f"进度: {idx}/{len(stations)}")

		if sleep_sec > 0:
			time.sleep(sleep_sec)

	return results


def save_outputs(records: List[Dict[str, object]], json_path: Optional[Path], csv_path: Path) -> None:
	if json_path is not None:
		json_path.parent.mkdir(parents=True, exist_ok=True)
		json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

	csv_path.parent.mkdir(parents=True, exist_ok=True)
	with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
		writer = csv.DictWriter(f, fieldnames=["start", "end", "price", "status", "error"])
		writer.writeheader()
		writer.writerows(records)


def main() -> None:
	parser = argparse.ArgumentParser(description="抓取北京地铁起点到全站票价")
	parser.add_argument("--start", default="魏公村", help="起点站，默认：魏公村")
	parser.add_argument("--json", default=str(CACHE_DIR / "beijing_subway_prices.json"), help="JSON 输出文件")
	parser.add_argument("--csv", default=str(CACHE_DIR / "beijing_subway_prices.csv"), help="CSV 输出文件")
	parser.add_argument("--no-json", action="store_true", help="不输出 JSON，仅输出 CSV")
	parser.add_argument("--sleep", type=float, default=0.02, help="每次请求间隔秒数")
	args = parser.parse_args()

	records = crawl_prices(args.start, sleep_sec=args.sleep)
	json_path = None if args.no_json else Path(args.json)
	save_outputs(records, json_path, Path(args.csv))

	ok_count = sum(1 for r in records if r["status"] in {"ok", "self"})
	err_count = sum(1 for r in records if r["status"] == "error")
	print(f"完成: 成功 {ok_count} 条, 失败 {err_count} 条")
	if json_path is not None:
		print(f"JSON: {args.json}")
	print(f"CSV : {args.csv}")


if __name__ == "__main__":
	main()
