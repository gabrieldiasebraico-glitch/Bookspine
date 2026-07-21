from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

from vocab_mapper.prepare_csv import (
    WordOccurrence,
    average_deviation,
    book_frequencies_by_word,
    clean_text,
    collect_occurrences,
    format_float,
    frequency_stats,
    median_deviation,
    read_text_file,
    word_classes_by_word,
)
from vocab_mapper.metrics import BOOK_AVG_DEV, BOOK_FREQ, BOOK_MED_DEV, BOOK_METRIC_FIELDNAMES


FIELDNAMES = [
    "word",
    "word_class",
    "book_count",
    "total_word_count",
    *BOOK_METRIC_FIELDNAMES,
]


def build_word_metric_rows(
    occurrences: list[WordOccurrence],
) -> list[dict[str, str | int]]:
    word_counts = Counter(occurrence.normalized_word for occurrence in occurrences)
    class_totals = Counter(occurrence.word_class for occurrence in occurrences)
    word_classes = word_classes_by_word(occurrences)
    book_frequencies = book_frequencies_by_word(occurrences)
    values_by_class: dict[str, list[float]] = {}

    for word, frequency in book_frequencies.items():
        values_by_class.setdefault(word_classes[word], []).append(frequency)

    stats_by_word_class = {
        word_class: frequency_stats(values)
        for word_class, values in values_by_class.items()
    }

    rows: list[dict[str, str | int]] = []
    for word, book_count in word_counts.items():
        word_class = word_classes[word]
        book_frequency = book_frequencies[word]
        stats = stats_by_word_class[word_class]
        rows.append(
            {
                "word": word,
                "word_class": word_class,
                "book_count": book_count,
                "total_word_count": class_totals[word_class],
                BOOK_FREQ: format_float(book_frequency),
                BOOK_AVG_DEV: format_float(
                    average_deviation(book_frequency, stats.average)
                ),
                BOOK_MED_DEV: format_float(
                    median_deviation(book_frequency, stats.median)
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            -float(row[BOOK_FREQ]),
            str(row["word_class"]),
            str(row["word"]),
        )
    )
    return rows


def write_csv(rows: list[dict[str, str | int]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def prepare_word_metrics_csv(input_path: Path, output_path: Path) -> int:
    text = clean_text(read_text_file(input_path))
    occurrences = collect_occurrences(text)
    rows = build_word_metric_rows(occurrences)
    write_csv(rows, output_path)
    return len(rows)


def slugify_title(title: str) -> str:
    slug = title.lower().replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def default_output_path(input_path: Path) -> Path:
    return Path("output") / f"{slugify_title(input_path.stem)}_word_metrics.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a traditional per-word metrics CSV with one row for each "
            "distinct normalized word in a book."
        )
    )
    parser.add_argument("input_txt", type=Path, help="Path to a .txt book file.")
    parser.add_argument(
        "output_csv",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "Path where the CSV will be written. Default: "
            "output/<book_slug>_word_metrics.csv."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_csv = args.output_csv or default_output_path(args.input_txt)
    row_count = prepare_word_metrics_csv(args.input_txt, output_csv)
    print(f"Wrote {row_count} per-word metric rows to {output_csv}")


if __name__ == "__main__":
    main()
