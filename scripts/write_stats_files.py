from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from vocab_mapper.prepare_csv import classify_word, format_float, load_ngram_frequencies
from vocab_mapper.stats import book_stats_from_rows, write_book_stats_txt


DEFAULT_CSV_ROOT = PROJECT_ROOT / "output" / "CSV Ocurrence Maps"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output"
DEFAULT_NGRAM_TOTAL_CSV = (
    PROJECT_ROOT
    / "data"
    / "ngram_frequencies"
    / "eng_fiction_2019_all_ngram_frequencies.csv"
)
DEFAULT_NGRAM_RECENT_CSV = (
    PROJECT_ROOT
    / "data"
    / "ngram_frequencies"
    / "eng_fiction_2019_recent_1999_2019_ngram_frequencies.csv"
)


def map_stem(csv_path: Path) -> str:
    stem = csv_path.stem
    if stem.endswith("_occurrences"):
        return stem[: -len("_occurrences")]
    return stem


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_all_book_stats(csv_root: Path, output_root: Path) -> int:
    written = 0
    for csv_path in sorted(csv_root.rglob("*.csv")):
        rows = read_rows(csv_path)
        relative_parent = csv_path.relative_to(csv_root).parent
        output_path = (
            output_root
            / "book_stats"
            / relative_parent
            / f"{map_stem(csv_path)}_book_stats.txt"
        )
        write_book_stats_txt(book_stats_from_rows(rows), output_path)
        written += 1
    return written


def grouped_frequency_stats(frequencies: dict[str, float]) -> dict[str, dict[str, float | None]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for word, value in frequencies.items():
        grouped[classify_word(word)].append(value)
    return {
        word_class: {
            "average": average(values),
            "median": median(values) if values else None,
        }
        for word_class, values in grouped.items()
    }


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def write_ngram_stats(
    output_path: Path,
    total_csv: Path,
    recent_csv: Path,
) -> None:
    total_stats = grouped_frequency_stats(load_ngram_frequencies(total_csv))
    recent_stats = grouped_frequency_stats(load_ngram_frequencies(recent_csv))
    lines = [
        "# Ngram_Stats",
        "",
        "These parameters are calculated separately for functional and semantic words.",
        "",
    ]
    for word_class in ("functional", "semantic"):
        total = total_stats.get(word_class, {})
        recent = recent_stats.get(word_class, {})
        lines.extend(
            [
                f"[{word_class}]",
                f"fic_ngrams_total_freq_avg={format_float(total.get('average'))}",
                f"fic_ngrams_total_freq_med={format_float(total.get('median'))}",
                f"fic_ngram_99_19_freq_avg={format_float(recent.get('average'))}",
                f"fic_ngrams_99_19_freq_med={format_float(recent.get('median'))}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write book_stats text files and the project-level Ngram_Stats.txt file."
    )
    parser.add_argument("--csv-root", type=Path, default=DEFAULT_CSV_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--ngram-total-csv", type=Path, default=DEFAULT_NGRAM_TOTAL_CSV)
    parser.add_argument("--ngram-recent-csv", type=Path, default=DEFAULT_NGRAM_RECENT_CSV)
    parser.add_argument(
        "--ngram-stats-output",
        type=Path,
        default=PROJECT_ROOT / "Ngram_Stats.txt",
    )
    args = parser.parse_args()

    written = write_all_book_stats(args.csv_root.resolve(), args.output_root.resolve())
    write_ngram_stats(
        args.ngram_stats_output.resolve(),
        args.ngram_total_csv.resolve(),
        args.ngram_recent_csv.resolve(),
    )
    print(f"book_stats_written={written}")
    print(f"ngram_stats={args.ngram_stats_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
