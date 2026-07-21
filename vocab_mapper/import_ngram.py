from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"^[a-z][a-z'-]*$")
RECENT_RANGE = (1999, 2019)


def range_presets(publication_year: int | None = None) -> dict[str, tuple[int, int] | None]:
    presets: dict[str, tuple[int, int] | None] = {"all": None}
    if publication_year is None:
        presets["usher_pre_publication_1829_1838"] = (1829, 1838)
    else:
        presets["minus_10y"] = (publication_year - 10, publication_year - 1)
    presets["recent_1999_2019"] = RECENT_RANGE
    return presets


def normalize_ngram_token(token: str) -> str | None:
    token = token.split("_", 1)[0].lower()
    if TOKEN_RE.fullmatch(token):
        return token
    return None


def read_target_words(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if "normalized_word" not in (reader.fieldnames or []):
            raise ValueError("Target CSV must contain a normalized_word column.")
        words = {row["normalized_word"] for row in reader if row.get("normalized_word")}
    words.add("the")
    return words


def parse_totalcounts(path: Path) -> Counter[int]:
    text = path.read_text(encoding="utf-8").strip()
    totals: Counter[int] = Counter()
    for part in text.split("\t"):
        if not part:
            continue
        fields = part.split(",")
        if len(fields) < 2:
            continue
        try:
            year = int(fields[0])
            match_count = int(fields[1])
        except ValueError:
            continue
        totals[year] += match_count
    return totals


def year_in_range(year: int, year_range: tuple[int, int] | None) -> bool:
    if year_range is None:
        return True
    start_year, end_year = year_range
    return start_year <= year <= end_year


def parse_ngram_header(line: str) -> tuple[str, str] | None:
    token_text, separator, yearly_text = line.partition("\t")
    if not separator:
        return None
    token = normalize_ngram_token(token_text)
    if token is None:
        return None
    return token, yearly_text.rstrip("\n")


def parse_yearly_counts(yearly_text: str) -> list[tuple[int, int]]:
    yearly_counts: list[tuple[int, int]] = []
    for entry in yearly_text.split("\t"):
        fields = entry.split(",")
        if len(fields) < 2:
            continue
        try:
            yearly_counts.append((int(fields[0]), int(fields[1])))
        except ValueError:
            continue
    return yearly_counts


def parse_ngram_line(line: str) -> tuple[str, list[tuple[int, int]]] | None:
    parsed = parse_ngram_header(line)
    if parsed is None:
        return None
    token, yearly_text = parsed
    return token, parse_yearly_counts(yearly_text)


def collect_target_counts(
    ngram_gz_path: Path,
    target_words: set[str],
    ranges: dict[str, tuple[int, int] | None],
) -> dict[str, Counter[str]]:
    counts = {name: Counter() for name in ranges}

    with gzip.open(ngram_gz_path, "rt", encoding="utf-8", errors="replace") as gz_file:
        for line in gz_file:
            parsed = parse_ngram_header(line)
            if parsed is None:
                continue
            token, yearly_text = parsed
            if token not in target_words:
                continue
            yearly_counts = parse_yearly_counts(yearly_text)
            for range_name, year_range in ranges.items():
                counts[range_name][token] += sum(
                    match_count
                    for year, match_count in yearly_counts
                    if year_in_range(year, year_range)
                )
    return counts


def range_total(totalcounts: Counter[int], year_range: tuple[int, int] | None) -> int:
    return sum(
        match_count
        for year, match_count in totalcounts.items()
        if year_in_range(year, year_range)
    )


def write_frequency_csv(
    output_path: Path,
    target_words: set[str],
    word_counts: Counter[str],
    total_count: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["word", "ngram_f", "ngram_count"])
        writer.writeheader()
        for word in sorted(target_words):
            count = word_counts[word]
            frequency = count / total_count if total_count else 0
            writer.writerow(
                {
                    "word": word,
                    "ngram_f": f"{frequency:.12g}",
                    "ngram_count": count,
                }
            )


def import_ngram_frequencies(
    target_csv: Path,
    ngram_gz: Path,
    totalcounts: Path,
    output_dir: Path,
    publication_year: int | None = None,
) -> list[Path]:
    target_words = read_target_words(target_csv)
    corpus_totals = parse_totalcounts(totalcounts)
    ranges = range_presets(publication_year)
    counts_by_range = collect_target_counts(ngram_gz, target_words, ranges)

    output_paths: list[Path] = []
    metadata = {
        "target_csv": str(target_csv),
        "ngram_gz": str(ngram_gz),
        "totalcounts": str(totalcounts),
        "publication_year": publication_year,
        "target_word_count": len(target_words),
        "ranges": {},
    }

    for range_name, year_range in ranges.items():
        total_count = range_total(corpus_totals, year_range)
        output_path = output_dir / f"eng_fiction_2019_{range_name}_ngram_frequencies.csv"
        write_frequency_csv(output_path, target_words, counts_by_range[range_name], total_count)
        output_paths.append(output_path)
        metadata["ranges"][range_name] = {
            "year_range": year_range,
            "total_count": total_count,
            "output_csv": str(output_path),
            "the_frequency": (
                counts_by_range[range_name]["the"] / total_count if total_count else 0
            ),
        }

    (output_dir / "eng_fiction_2019_ngram_import_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build compact Ngram frequency CSVs for only the words used in a book."
    )
    parser.add_argument("target_csv", type=Path, help="Occurrence CSV with normalized_word.")
    parser.add_argument("ngram_gz", type=Path, help="Google Books 1-gram .gz file.")
    parser.add_argument("totalcounts", type=Path, help="Google Books totalcounts-1 file.")
    parser.add_argument("output_dir", type=Path, help="Directory for generated frequency CSVs.")
    parser.add_argument(
        "--publication-year",
        type=int,
        default=None,
        help=(
            "Book publication year. When provided, the pre-publication range is "
            "publication_year - 10 through publication_year - 1 and is written as "
            "minus_10y."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_paths = import_ngram_frequencies(
        args.target_csv,
        args.ngram_gz,
        args.totalcounts,
        args.output_dir,
        args.publication_year,
    )
    for output_path in output_paths:
        print(output_path)


if __name__ == "__main__":
    main()
