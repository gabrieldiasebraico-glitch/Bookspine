from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from vocab_mapper.import_ngram import collect_target_counts, parse_totalcounts, range_total
from vocab_mapper.prepare_csv import format_float, normalize_word


@dataclass(frozen=True)
class NgramSourceSpec:
    label: str
    path: Path
    year_range: tuple[int, int] | None


@dataclass(frozen=True)
class NgramBackfillResult:
    label: str
    path: Path
    added_words: int


def complete_frequency_words(path: Path) -> set[str]:
    if not path.exists():
        return set()

    words: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        headers = {header.lower(): header for header in reader.fieldnames or []}
        word_header = headers.get("word") or headers.get("normalized_word") or headers.get("token")
        frequency_header = headers.get("ngram_f") or headers.get("frequency") or headers.get("freq")
        if not word_header or not frequency_header:
            return set()
        for row in reader:
            word = normalize_word(row.get(word_header, ""))
            if word and row.get(frequency_header, "") != "":
                words.add(word)
    return words


def ensure_ngram_frequency_sources(
    specs: list[NgramSourceSpec],
    target_words: set[str],
    ngram_gz: Path,
    totalcounts_path: Path,
) -> list[NgramBackfillResult]:
    target_words = {word for word in target_words if word}
    target_words.add("the")
    pending: list[tuple[NgramSourceSpec, set[str]]] = []
    for spec in specs:
        missing_words = target_words - complete_frequency_words(spec.path)
        if missing_words:
            pending.append((spec, missing_words))

    if not pending:
        return [
            NgramBackfillResult(spec.label, spec.path, 0)
            for spec in specs
        ]
    if not ngram_gz.exists():
        raise FileNotFoundError(f"Google Ngram archive not found: {ngram_gz}")
    if not totalcounts_path.exists():
        raise FileNotFoundError(f"Google Ngram totalcounts file not found: {totalcounts_path}")

    missing_union = set().union(*(missing for _spec, missing in pending))
    ranges = {spec.label: spec.year_range for spec, _missing in pending}
    counts_by_label = collect_target_counts(ngram_gz, missing_union, ranges)
    totalcounts = parse_totalcounts(totalcounts_path)

    results: list[NgramBackfillResult] = []
    pending_by_path = {spec.path: missing for spec, missing in pending}
    for spec in specs:
        missing_words = pending_by_path.get(spec.path, set())
        if missing_words:
            denominator = range_total(totalcounts, spec.year_range)
            append_frequency_rows(
                spec.path,
                missing_words,
                counts_by_label.get(spec.label, Counter()),
                denominator,
            )
        results.append(NgramBackfillResult(spec.label, spec.path, len(missing_words)))
    return results


def append_frequency_rows(
    path: Path,
    words: set[str],
    counts: Counter[str],
    denominator: int,
) -> None:
    rows_by_word = read_frequency_rows(path)
    for word in words:
        count = counts[word]
        rows_by_word[word] = {
            "word": word,
            "ngram_f": format_float(count / denominator if denominator else 0),
            "ngram_count": str(count),
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["word", "ngram_f", "ngram_count"])
        writer.writeheader()
        for word in sorted(rows_by_word):
            row = rows_by_word[word]
            writer.writerow(
                {
                    "word": row.get("word") or word,
                    "ngram_f": row.get("ngram_f", ""),
                    "ngram_count": row.get("ngram_count", ""),
                }
            )
    tmp_path.replace(path)


def read_frequency_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}

    rows_by_word: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        headers = {header.lower(): header for header in reader.fieldnames or []}
        word_header = headers.get("word") or headers.get("normalized_word") or headers.get("token")
        frequency_header = headers.get("ngram_f") or headers.get("frequency") or headers.get("freq")
        count_header = headers.get("ngram_count") or headers.get("count")
        if not word_header or not frequency_header:
            return {}
        for row in reader:
            word = normalize_word(row.get(word_header, ""))
            if not word:
                continue
            rows_by_word[word] = {
                "word": word,
                "ngram_f": row.get(frequency_header, ""),
                "ngram_count": row.get(count_header, "") if count_header else "",
            }
    return rows_by_word
