from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from zipfile import ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from vocab_mapper.import_ngram import (
    RECENT_RANGE,
    parse_ngram_header,
    parse_totalcounts,
    parse_yearly_counts,
    range_total,
    year_in_range,
)
from vocab_mapper.prepare_csv import (
    FIELDNAMES,
    NGRAM_COLUMN_SPECS,
    average_deviation,
    format_float,
    median_deviation,
    stats_by_class,
)
from vocab_mapper.metrics import BOOK_METRIC_FIELDNAMES, BOOK_FREQ, FIC_NGRAM_TOTAL_FREQ, metric_column_candidates


DEFAULT_MAP_ROOT = PROJECT_ROOT / "output" / "CSV Ocurrence Maps"
DEFAULT_NGRAM_GZ = PROJECT_ROOT / "data" / "google_ngram" / "eng-fiction" / "1-00000-of-00001.gz"
DEFAULT_TOTALCOUNTS = PROJECT_ROOT / "data" / "google_ngram" / "eng-fiction" / "totalcounts-1"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "ngram_cache"
DEFAULT_BOOK_LIST = PROJECT_ROOT / "txt books" / "Book List.xlsx"

TOTAL_RECENT_CACHE = "eng_fiction_2019_total_recent_ngram_cache.csv"
TOTAL_RECENT_METADATA = "eng_fiction_2019_total_recent_ngram_cache.metadata.json"
RECENT_LABEL = "1999-2019"
PREPUB_LABEL = "-10y"

CSV_YEAR_ALIASES = {
    "harry_potter_and_the_philosophers_stone_by_jk_rowling": "harry_potter",
    "harry_potter_and_the_philosophers_stone_uk_version": "harry_potter",
    "harry_potter_and_the_sorcerers_stone": "harry_potter",
    "heated_rivalry_game_changers": "heated_rivalry",
    "lord_of_the_rings": "the_lord_of_the_rings",
    "the_odissey": "the_odyssey",
}

MANUAL_PUBLICATION_YEARS = {
    # The spreadsheet lists The Odyssey only as a counter-sampling item.
    # The exact ancient date is not useful for Google Ngrams; this produces
    # an empty pre-publication denominator instead of reusing an unrelated era.
    "the_odyssey": 800,
    "the_odissey": 800,
}

NGRAM_COLUMNS = [
    column
    for columns in NGRAM_COLUMN_SPECS.values()
    for column in columns
]


@dataclass(frozen=True)
class CsvTarget:
    path: Path
    key: str
    publication_year: int | None
    words: set[str]


@dataclass(frozen=True)
class CachedFrequency:
    total: float
    recent: float


def slugify_title(title: object) -> str:
    text = str(title).strip().lower().replace("'", "")
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    text = text.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def map_stem(csv_path: Path) -> str:
    stem = csv_path.stem
    if stem.endswith("_occurrences"):
        stem = stem[: -len("_occurrences")]
    return stem


def csv_book_key(csv_path: Path) -> str:
    stem = map_stem(csv_path).lower()
    for suffix in (
        "_eng_fiction_2019_recent_1999_2019",
        "_eng_fiction_2019_all",
    ):
        stem = stem.replace(suffix, "")
    for marker in (
        "_eng_fiction_2019_prepub_",
        "_eng_fiction_2019_pre_publication_",
        "_eng_fiction_2019_usher_pre_publication_",
    ):
        index = stem.find(marker)
        if index >= 0:
            stem = stem[:index]
    stem = re.sub(r"_gutenberg_\d+$", "", stem)
    key = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return CSV_YEAR_ALIASES.get(key, key)


def first_year(value: object) -> int | None:
    match = re.search(r"\d{3,4}", str(value))
    return int(match.group(0)) if match else None


def load_publication_years(book_list: Path) -> dict[str, int]:
    years: dict[str, int] = dict(MANUAL_PUBLICATION_YEARS)
    if not book_list.exists():
        return years

    with ZipFile(book_list) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for row in sheet.findall(".//a:row", ns):
        cells = {
            _cell_column(cell.get("r", "")): _cell_value(cell, shared_strings, ns)
            for cell in row.findall("a:c", ns)
        }
        title = cells.get("B")
        year = first_year(cells.get("G", ""))
        if title and year:
            years[slugify_title(title)] = year
    return years


def _read_shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings: list[str] = []
    for item in root:
        strings.append("".join(text.text or "" for text in item.iter() if text.tag.endswith("}t")))
    return strings


def _cell_column(reference: str) -> str:
    return re.sub(r"[^A-Z]+", "", reference)


def _cell_value(cell: ET.Element, shared_strings: list[str], ns: dict[str, str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "s":
        value = cell.find("a:v", ns)
        if value is None or value.text is None:
            return ""
        return shared_strings[int(value.text)]
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.iter() if text.tag.endswith("}t"))
    value = cell.find("a:v", ns)
    return value.text if value is not None and value.text is not None else ""


def ngram_value_count(csv_path: Path) -> tuple[int, int]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        row_count = 0
        populated_count = 0
        for row in reader:
            row_count += 1
            if any(row.get(column) for column in NGRAM_COLUMNS):
                populated_count += 1
    return row_count, populated_count


def read_target_words(csv_path: Path) -> set[str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if "normalized_word" not in (reader.fieldnames or []):
            raise ValueError(f"{csv_path} must contain a normalized_word column.")
        words = {row["normalized_word"] for row in reader if row.get("normalized_word")}
    words.add("the")
    return words


def discover_targets(
    map_root: Path,
    publication_years: dict[str, int],
    excludes: list[str],
) -> list[CsvTarget]:
    targets: list[CsvTarget] = []
    lowered_excludes = [exclude.lower() for exclude in excludes]
    for csv_path in sorted(map_root.rglob("*.csv")):
        relative = str(csv_path.relative_to(PROJECT_ROOT)).lower()
        if any(exclude in relative for exclude in lowered_excludes):
            continue
        key = csv_book_key(csv_path)
        targets.append(
            CsvTarget(
                path=csv_path,
                key=key,
                publication_year=publication_years.get(key),
                words=read_target_words(csv_path),
            )
        )
    return targets


def target_words_hash(words: set[str]) -> str:
    digest = sha1()
    for word in sorted(words):
        digest.update(word.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def load_total_recent_cache(cache_path: Path) -> dict[str, CachedFrequency]:
    if not cache_path.exists():
        return {}
    cache: dict[str, CachedFrequency] = {}
    with cache_path.open("r", encoding="utf-8", newline="") as cache_file:
        reader = csv.DictReader(cache_file)
        for row in reader:
            word = row.get("word", "")
            if not word:
                continue
            try:
                cache[word] = CachedFrequency(
                    total=float(row["total_ngram_f"]),
                    recent=float(row["recent_1999_2019_ngram_f"]),
                )
            except (KeyError, ValueError):
                return {}
    return cache


def write_total_recent_cache(
    cache_path: Path,
    metadata_path: Path,
    target_words: set[str],
    counts_by_range: dict[str, Counter[str]],
    totalcounts_by_range: dict[str, int],
    ngram_gz: Path,
) -> dict[str, CachedFrequency]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, CachedFrequency] = {}
    with cache_path.open("w", encoding="utf-8", newline="") as cache_file:
        writer = csv.DictWriter(
            cache_file,
            fieldnames=[
                "word",
                "total_ngram_f",
                "total_ngram_count",
                "recent_1999_2019_ngram_f",
                "recent_1999_2019_ngram_count",
            ],
        )
        writer.writeheader()
        for word in sorted(target_words):
            total_count = counts_by_range["Total"][word]
            recent_count = counts_by_range[RECENT_LABEL][word]
            total_freq = total_count / totalcounts_by_range["Total"] if totalcounts_by_range["Total"] else 0
            recent_freq = recent_count / totalcounts_by_range[RECENT_LABEL] if totalcounts_by_range[RECENT_LABEL] else 0
            cache[word] = CachedFrequency(total=total_freq, recent=recent_freq)
            writer.writerow(
                {
                    "word": word,
                    "total_ngram_f": format_float(total_freq),
                    "total_ngram_count": total_count,
                    "recent_1999_2019_ngram_f": format_float(recent_freq),
                    "recent_1999_2019_ngram_count": recent_count,
                }
            )

    metadata_path.write_text(
        json.dumps(
            {
                "ngram_gz": str(ngram_gz),
                "ngram_gz_size": ngram_gz.stat().st_size,
                "ngram_gz_mtime": ngram_gz.stat().st_mtime,
                "target_word_count": len(target_words),
                "target_words_sha1": target_words_hash(target_words),
                "ranges": {
                    "Total": None,
                    RECENT_LABEL: RECENT_RANGE,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return cache


def cache_is_current(metadata_path: Path, target_words: set[str], ngram_gz: Path) -> bool:
    if not metadata_path.exists():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        metadata.get("ngram_gz_size") == ngram_gz.stat().st_size
        and metadata.get("ngram_gz_mtime") == ngram_gz.stat().st_mtime
        and metadata.get("target_words_sha1") == target_words_hash(target_words)
    )


def collect_counts(
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


def total_recent_cache(
    cache_dir: Path,
    target_words: set[str],
    ngram_gz: Path,
    totalcounts: Counter[int],
    force_cache: bool,
) -> dict[str, CachedFrequency]:
    cache_path = cache_dir / TOTAL_RECENT_CACHE
    metadata_path = cache_dir / TOTAL_RECENT_METADATA
    cache = load_total_recent_cache(cache_path)
    if (
        not force_cache
        and cache
        and target_words.issubset(cache.keys())
        and cache_is_current(metadata_path, set(cache.keys()), ngram_gz)
    ):
        return cache

    ranges = {
        "Total": None,
        RECENT_LABEL: RECENT_RANGE,
    }
    counts = collect_counts(ngram_gz, target_words, ranges)
    totals = {
        label: range_total(totalcounts, year_range)
        for label, year_range in ranges.items()
    }
    return write_total_recent_cache(cache_path, metadata_path, target_words, counts, totals, ngram_gz)


def prepublication_ranges(targets: list[CsvTarget]) -> dict[tuple[int, int], set[str]]:
    ranges: dict[tuple[int, int], set[str]] = defaultdict(set)
    for target in targets:
        if target.publication_year is None:
            continue
        year_range = (target.publication_year - 10, target.publication_year - 1)
        ranges[year_range].update(target.words)
    return dict(ranges)


def collect_prepublication_counts(
    ngram_gz_path: Path,
    range_words: dict[tuple[int, int], set[str]],
) -> dict[tuple[int, int], Counter[str]]:
    word_ranges: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for year_range, words in range_words.items():
        for word in words:
            word_ranges[word].add(year_range)

    counts = {year_range: Counter() for year_range in range_words}
    with gzip.open(ngram_gz_path, "rt", encoding="utf-8", errors="replace") as gz_file:
        for line in gz_file:
            parsed = parse_ngram_header(line)
            if parsed is None:
                continue
            token, yearly_text = parsed
            ranges = word_ranges.get(token)
            if not ranges:
                continue
            yearly_counts = parse_yearly_counts(yearly_text)
            for year_range in ranges:
                counts[year_range][token] += sum(
                    match_count
                    for year, match_count in yearly_counts
                    if year_in_range(year, year_range)
                )
    return counts


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = [
            column
            for column in FIELDNAMES
            if column not in NGRAM_COLUMNS
        ]
        fieldnames = set(reader.fieldnames or [])
        missing_columns = []
        for column in required_columns:
            if column in fieldnames:
                continue
            if column in BOOK_METRIC_FIELDNAMES and any(
                candidate in fieldnames for candidate in metric_column_candidates(column)
            ):
                continue
            missing_columns.append(column)
        if missing_columns:
            raise ValueError(f"{csv_path} is missing columns: {', '.join(missing_columns)}")
        return list(reader)


def add_ngram_values(
    rows: list[dict[str, str]],
    ngram_sources: dict[str, dict[str, float]],
) -> int:
    word_classes = {
        row["normalized_word"]: row["word_class"]
        for row in rows
        if row.get("normalized_word") and row.get("word_class")
    }
    ngram_stats_by_label = {
        label: stats_by_class(frequencies, word_classes)
        for label, frequencies in ngram_sources.items()
    }

    populated_total = 0
    for row in rows:
        word = row.get("normalized_word", "")
        word_class = row.get("word_class", "")
        for book_metric in BOOK_METRIC_FIELDNAMES:
            if not row.get(book_metric):
                row[book_metric] = format_float(
                    first_float(row, metric_column_candidates(book_metric))
                )
        for label, columns in NGRAM_COLUMN_SPECS.items():
            frequency_column, average_column, median_column = columns
            frequencies = ngram_sources.get(label, {})
            ngram_frequency = frequencies.get(word)
            ngram_stats = ngram_stats_by_label.get(label, {}).get(word_class)
            row[frequency_column] = format_float(ngram_frequency)
            row[average_column] = format_float(
                average_deviation(
                    ngram_frequency,
                    ngram_stats.average if ngram_stats else None,
                )
            )
            row[median_column] = format_float(
                median_deviation(
                    ngram_frequency,
                    ngram_stats.median if ngram_stats else None,
                )
            )
        if row.get(FIC_NGRAM_TOTAL_FREQ):
            populated_total += 1
    return populated_total


def first_float(row: dict[str, str], columns: tuple[str, ...]) -> float | None:
    for column in columns:
        value = _parse_float(row.get(column))
        if value is not None:
            return value
    return None


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def write_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    tmp_path = csv_path.with_name(f"{csv_path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDNAMES} for row in rows)
    tmp_path.replace(csv_path)


def ngram_sources_for_target(
    target: CsvTarget,
    total_recent: dict[str, CachedFrequency],
    prepub_counts: dict[tuple[int, int], Counter[str]],
    totalcounts: Counter[int],
) -> dict[str, dict[str, float]]:
    total = {
        word: total_recent.get(word, CachedFrequency(0, 0)).total
        for word in target.words
    }
    recent = {
        word: total_recent.get(word, CachedFrequency(0, 0)).recent
        for word in target.words
    }
    prepub: dict[str, float] = {}
    if target.publication_year is not None:
        year_range = (target.publication_year - 10, target.publication_year - 1)
        denominator = range_total(totalcounts, year_range)
        counts = prepub_counts.get(year_range, Counter())
        prepub = {
            word: counts[word] / denominator if denominator else 0
            for word in target.words
        }
    return {
        "Total": total,
        PREPUB_LABEL: prepub,
        RECENT_LABEL: recent,
    }


def update_csv(
    target: CsvTarget,
    ngram_sources: dict[str, dict[str, float]],
    force: bool = False,
) -> tuple[bool, int, int]:
    row_count, existing_populated = ngram_value_count(target.path)
    if existing_populated and not force:
        return False, row_count, existing_populated

    rows = read_rows(target.path)
    populated_total = add_ngram_values(rows, ngram_sources)
    write_rows(target.path, rows)
    return True, row_count, populated_total


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Populate Ngram columns on occurrence CSV maps that still have no "
            "Ngram values."
        )
    )
    parser.add_argument(
        "--map-root",
        type=Path,
        default=DEFAULT_MAP_ROOT,
        help="Root directory containing occurrence CSV maps.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute Ngram columns even when a CSV already has Ngram values.",
    )
    parser.add_argument(
        "--force-cache",
        action="store_true",
        help="Rebuild the shared Total/1999-2019 Ngram cache even if it is current.",
    )
    parser.add_argument(
        "--ngram-gz",
        type=Path,
        default=DEFAULT_NGRAM_GZ,
        help="Google Books 1-gram .gz file.",
    )
    parser.add_argument(
        "--totalcounts",
        type=Path,
        default=DEFAULT_TOTALCOUNTS,
        help="Google Books totalcounts-1 file.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Directory for the shared Total/1999-2019 Ngram cache.",
    )
    parser.add_argument(
        "--book-list",
        type=Path,
        default=DEFAULT_BOOK_LIST,
        help="Book List.xlsx used to resolve publication years for -10y windows.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=["guards_guards_by_terry_pratchett"],
        help="Case-insensitive CSV path substring to skip. Can be repeated.",
    )
    args = parser.parse_args()

    map_root = args.map_root.resolve()
    ngram_gz = args.ngram_gz.resolve()
    totalcounts_path = args.totalcounts.resolve()
    publication_years = load_publication_years(args.book_list.resolve())
    targets = discover_targets(map_root, publication_years, args.exclude)
    all_target_words = set().union(*(target.words for target in targets)) if targets else set()
    corpus_totals = parse_totalcounts(totalcounts_path)

    print(f"targets={len(targets)} unique_words={len(all_target_words)}")
    shared_cache = total_recent_cache(
        args.cache_dir.resolve(),
        all_target_words,
        ngram_gz,
        corpus_totals,
        args.force_cache,
    )
    range_words = prepublication_ranges(targets)
    prepub_counts = collect_prepublication_counts(ngram_gz, range_words)

    updated = 0
    skipped = 0
    missing_years = 0
    for target in targets:
        if target.publication_year is None:
            missing_years += 1
            print(f"warning\tmissing-publication-year\t{target.path.relative_to(PROJECT_ROOT)}")
        sources = ngram_sources_for_target(target, shared_cache, prepub_counts, corpus_totals)
        changed, row_count, populated_total = update_csv(target, sources, force=args.force)
        if changed:
            updated += 1
            print(f"updated\t{target.path.relative_to(PROJECT_ROOT)}\t{populated_total}/{row_count}")
        else:
            skipped += 1
            print(f"skipped\t{target.path.relative_to(PROJECT_ROOT)}\t{populated_total}/{row_count}")

    print(f"summary\tupdated={updated}\tskipped={skipped}\tmissing_years={missing_years}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
