from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from vocab_mapper.metric_values import row_metric_values
from vocab_mapper.metrics import MAP_METRICS
from vocab_mapper.prepare_csv import FIELDNAMES, LOCATION_FIELDNAMES, format_float


DEFAULT_CSV_ROOT = PROJECT_ROOT / "output" / "CSV Ocurrence Maps"


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def migrate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    metric_values = {}
    for metric in MAP_METRICS:
        try:
            metric_values[metric] = row_metric_values(
                rows,
                metric,
                class_discrimination=True,
            )
        except ValueError:
            metric_values[metric] = [None] * len(rows)
    migrated: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        new_row = {field: row.get(field, "") for field in LOCATION_FIELDNAMES}
        for metric in MAP_METRICS:
            new_row[metric] = format_float(metric_values[metric][index])
        migrated.append(new_row)
    return migrated


def write_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    tmp_path = csv_path.with_name(f"{csv_path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(csv_path)


def migrate_csv(csv_path: Path) -> int:
    rows = read_rows(csv_path)
    write_rows(csv_path, migrate_rows(rows))
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite occurrence CSVs with only current metric columns."
    )
    parser.add_argument("--csv-root", type=Path, default=DEFAULT_CSV_ROOT)
    parser.add_argument("--include", default=None)
    args = parser.parse_args()

    csv_root = args.csv_root.resolve()
    include = args.include.lower() if args.include else None
    migrated = 0
    for csv_path in sorted(csv_root.rglob("*.csv")):
        if include and include not in str(csv_path.relative_to(csv_root)).lower():
            continue
        row_count = migrate_csv(csv_path)
        migrated += 1
        print(f"migrated\t{csv_path.relative_to(PROJECT_ROOT)}\t{row_count}")
    print(f"summary\tmigrated={migrated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
