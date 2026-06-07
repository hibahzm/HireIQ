"""
T084 — p95 gate for the performance audit.

Parses a Locust `--csv` stats file and fails (exit 1) if any synchronous REST
endpoint exceeds the Constitution budget of p95 ≤ 300 ms. Intended to run in CI
after a headless Locust run so a regression blocks merge.

Usage:
    python infra/perf/check_p95.py perf_report_stats.csv
"""
from __future__ import annotations

import csv
import sys

P95_BUDGET_MS = 300.0


def main(path: str) -> int:
    failures: list[str] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("Name", "")
            # Locust writes an "Aggregated" summary row — skip it for per-endpoint gating.
            if row.get("Type", "") == "" or name == "Aggregated":
                continue
            p95_raw = row.get("95%") or row.get("95%ile") or "0"
            try:
                p95 = float(p95_raw)
            except ValueError:
                continue
            if p95 > P95_BUDGET_MS:
                failures.append(f"{row.get('Type','')} {name}: p95={p95:.0f}ms > {P95_BUDGET_MS:.0f}ms")

    if failures:
        print("PERFORMANCE GATE FAILED — p95 budget exceeded:")
        for fail in failures:
            print(f"  ✗ {fail}")
        return 1
    print(f"PERFORMANCE GATE PASSED — all endpoints p95 ≤ {P95_BUDGET_MS:.0f}ms")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
