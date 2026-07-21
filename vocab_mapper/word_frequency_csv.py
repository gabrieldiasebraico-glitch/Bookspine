from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

from vocab_mapper.prepare_csv import (
    WordOccurrence,
    book_frequencies_by_word,
    clean_text,
    collect_occurrences,
    format_float,
    load_ngram_frequencies,
    read_text_file,
    word_classes_by_word,
)
from vocab_mapper.metrics import BOOK_FREQ


FIELDNAMES = [
    "word",
    "word_class",
    "book_count",
    "total_word_count",
    BOOK_FREQ,
    "ngram_frequency",
    "book_to_ngram_frequency_deviation",
]


def comparison_to_ngram(book_frequency: float, ngram_frequency: float | None) -> float | None:
    if ngram_frequency is None or ngram_frequency <= 0:
        return None
    return (book_frequency - ngram_frequency) / ngram_frequency


def build_word_frequency_rows(
    occurrences: list[WordOccurrence],
    ngram_frequencies: dict[str, float],
) -> list[dict[str, str | int]]:
    word_counts = Counter(occurrence.normalized_word for occurrence in occurrences)
    class_totals = Counter(occurrence.word_class for occurrence in occurrences)
    word_classes = word_classes_by_word(occurrences)
    book_frequencies = book_frequencies_by_word(occurrences)

    rows: list[dict[str, str | int]] = []
    for word, book_count in word_counts.items():
        word_class = word_classes[word]
        book_frequency = book_frequencies[word]
        ngram_frequency = ngram_frequencies.get(word)
        comparison = comparison_to_ngram(book_frequency, ngram_frequency)
        rows.append(
            {
                "word": word,
                "word_class": word_class,
                "book_count": book_count,
                "total_word_count": class_totals[word_class],
                BOOK_FREQ: format_float(book_frequency),
                "ngram_frequency": format_float(ngram_frequency),
                "book_to_ngram_frequency_deviation": format_float(comparison),
            }
        )

    rows.sort(
        key=lambda row: (
            row["book_to_ngram_frequency_deviation"] == "",
            -float(row["book_to_ngram_frequency_deviation"])
            if row["book_to_ngram_frequency_deviation"] != ""
            else 0,
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


def prepare_word_frequency_csv(
    input_path: Path,
    output_path: Path,
    ngram_path: Path | None,
) -> int:
    text = clean_text(read_text_file(input_path))
    occurrences = collect_occurrences(text)
    ngram_frequencies = load_ngram_frequencies(ngram_path)
    rows = build_word_frequency_rows(occurrences, ngram_frequencies)
    write_csv(rows, output_path)
    return len(rows)


def slugify_title(title: str) -> str:
    slug = title.lower().replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def default_output_path(input_path: Path) -> Path:
    return Path("output") / f"{slugify_title(input_path.stem)}_word_frequencies.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a unique-word CSV comparing book frequency with Google Ngram "
            "frequency."
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
            "output/<book_slug>_word_frequencies.csv."
        ),
    )
    parser.add_argument(
        "--ngram-csv",
        type=Path,
        required=True,
        help=(
            "CSV with word/ngram_f columns. Also accepts normalized_word/token and "
            "frequency/freq."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_csv = args.output_csv or default_output_path(args.input_txt)
    row_count = prepare_word_frequency_csv(args.input_txt, output_csv, args.ngram_csv)
    print(f"Wrote {row_count} unique-word rows to {output_csv}")


if __name__ == "__main__":
    main()
