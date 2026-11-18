"""Repeatable local performance check for the variant 13 report."""
from __future__ import annotations

import json
import statistics
import time
import tracemalloc

from tests.helpers import WSGIClient
from analyzer.web import create_app


def make_csv(rows: int = 10_000) -> bytes:
    parts = ["id,region,revenue,quantity,discount"]
    for i in range(rows):
        parts.append(f"{i},region-{i % 8},{100 + (i % 9000)},{1 + (i % 12)},{(i % 20) / 100:.2f}")
    return ("\n".join(parts) + "\n").encode("utf-8")


def main() -> None:
    payload = make_csv()
    times = []
    last_response = None
    tracemalloc.start()
    for _ in range(5):
        client = WSGIClient(create_app())
        start = time.perf_counter()
        last_response = client.post_multipart("/analyze", file=("performance.csv", payload))
        times.append(time.perf_counter() - start)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result = {
        "rows": 10_000,
        "columns": 5,
        "payload_bytes": len(payload),
        "runs": len(times),
        "status": last_response["status"],
        "median_seconds": round(statistics.median(times), 4),
        "min_seconds": round(min(times), 4),
        "max_seconds": round(max(times), 4),
        "tracemalloc_peak_mib": round(peak / (1024 * 1024), 2),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not last_response["status"].startswith("200"):
        raise SystemExit("Performance request failed")


if __name__ == "__main__":
    main()
