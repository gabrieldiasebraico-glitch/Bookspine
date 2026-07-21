from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from vocab_mapper.metrics import BOOK_FREQ, scaled_metric_slug
from vocab_mapper.plot_visual_map import render_frequency_map
from vocab_mapper.prepare_csv import (
    clean_text,
    collect_occurrences,
    load_ngram_frequencies,
    prepare_csv,
    read_text_file,
)
from vocab_mapper.stats import (
    book_stats_from_occurrences,
    book_stats_output_path,
    write_book_stats_txt,
)
from vocab_mapper.word_metrics_csv import prepare_word_metrics_csv


DEFAULT_BOOKS_DIR = Path("txt books")
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_MAPS_DIR = DEFAULT_OUTPUT_DIR / "maps"
DEFAULT_WIDTH = 2000
DEFAULT_SCALE = "linear"
DEFAULT_METRIC = BOOK_FREQ

MAP_SLUG_ALIASES = {
    "harry_potter_and_the_sorcerers_stone": "harry_potter_sorcerers_stone",
}


@dataclass(frozen=True)
class BookOutputs:
    input_txt: Path
    occurrence_csv: Path
    first_map: Path
    book_stats: Path
    word_metrics: Path


@dataclass(frozen=True)
class BatchResult:
    input_txt: Path
    occurrence_csv: Path
    first_map: Path
    book_stats: Path
    word_metrics: Path
    csv_created: bool
    map_created: bool
    book_stats_created: bool
    word_metrics_updated: bool


def slugify_title(title: str) -> str:
    slug = title.lower().replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def occurrence_slug(input_txt: Path) -> str:
    return slugify_title(input_txt.stem)


def first_map_slug(input_txt: Path) -> str:
    slug = occurrence_slug(input_txt)
    return MAP_SLUG_ALIASES.get(slug, slug)


def book_outputs(
    input_txt: Path,
    output_dir: Path,
    maps_dir: Path,
    scale: str = DEFAULT_SCALE,
) -> BookOutputs:
    csv_slug = occurrence_slug(input_txt)
    map_slug = first_map_slug(input_txt)
    return BookOutputs(
        input_txt=input_txt,
        occurrence_csv=output_dir / f"{csv_slug}_occurrences.csv",
        first_map=maps_dir / f"{map_slug}_{scaled_metric_slug(DEFAULT_METRIC, scale)}.png",
        book_stats=book_stats_output_path(output_dir, csv_slug),
        word_metrics=output_dir / "Word_Metrics" / f"{csv_slug}_word_metrics.csv",
    )


def iter_txt_books(books_dir: Path) -> list[Path]:
    if not books_dir.exists():
        return []
    return sorted(path for path in books_dir.glob("*.txt") if path.is_file())


def missing_sidecar(path: Path) -> bool:
    return not path.with_suffix(".json").exists()


def needs_first_map(path: Path) -> bool:
    return not path.exists() or missing_sidecar(path)


def discover_missing_outputs(
    books_dir: Path = DEFAULT_BOOKS_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    maps_dir: Path = DEFAULT_MAPS_DIR,
    scale: str = DEFAULT_SCALE,
) -> list[BookOutputs]:
    missing: list[BookOutputs] = []
    for input_txt in iter_txt_books(books_dir):
        outputs = book_outputs(input_txt, output_dir, maps_dir, scale=scale)
        if (
            not outputs.occurrence_csv.exists()
            or needs_first_map(outputs.first_map)
            or not outputs.book_stats.exists()
            or not outputs.word_metrics.exists()
        ):
            missing.append(outputs)
    return missing


def generate_missing_outputs(
    books_dir: Path = DEFAULT_BOOKS_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    maps_dir: Path = DEFAULT_MAPS_DIR,
    width: int = DEFAULT_WIDTH,
    scale: str = DEFAULT_SCALE,
    ngram_minus_10y_path: Path | None = None,
    dry_run: bool = False,
) -> list[BatchResult]:
    results: list[BatchResult] = []
    for outputs in discover_missing_outputs(books_dir, output_dir, maps_dir, scale=scale):
        csv_created = False
        map_created = False
        book_stats_created = False
        word_metrics_updated = False

        if not outputs.occurrence_csv.exists():
            csv_created = True
            if not dry_run:
                prepare_csv(outputs.input_txt, outputs.occurrence_csv)

        if needs_first_map(outputs.first_map):
            map_created = True
            if not dry_run:
                render_frequency_map(
                    outputs.occurrence_csv,
                    outputs.first_map,
                    width=width,
                    scale=scale,
                    metric=DEFAULT_METRIC,
                )

        if (
            not outputs.word_metrics.exists()
            or csv_created
            or map_created
        ):
            word_metrics_updated = True
            if not dry_run:
                prepare_word_metrics_csv(outputs.input_txt, outputs.word_metrics)

        if not outputs.book_stats.exists():
            book_stats_created = True
            if not dry_run:
                text = clean_text(read_text_file(outputs.input_txt))
                occurrences = collect_occurrences(text)
                prepub_frequencies = load_ngram_frequencies(ngram_minus_10y_path)
                write_book_stats_txt(
                    book_stats_from_occurrences(occurrences, prepub_frequencies),
                    outputs.book_stats,
                )

        results.append(
            BatchResult(
                input_txt=outputs.input_txt,
                occurrence_csv=outputs.occurrence_csv,
                first_map=outputs.first_map,
                book_stats=outputs.book_stats,
                word_metrics=outputs.word_metrics,
                csv_created=csv_created,
                map_created=map_created,
                book_stats_created=book_stats_created,
                word_metrics_updated=word_metrics_updated,
            )
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan a directory of .txt books and generate missing occurrence CSVs "
            "and first visual maps."
        )
    )
    parser.add_argument(
        "--books-dir",
        type=Path,
        default=DEFAULT_BOOKS_DIR,
        help="Directory containing .txt book files. Default: 'txt books'.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for occurrence CSVs. Default: output.",
    )
    parser.add_argument(
        "--maps-dir",
        type=Path,
        default=DEFAULT_MAPS_DIR,
        help="Directory for first visual maps. Default: output/maps.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        help="Map width in pixels. Default: 2000.",
    )
    parser.add_argument(
        "--scale",
        choices=("linear", "log"),
        default=DEFAULT_SCALE,
        help="Color scaling for the first map. Default: linear.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the missing outputs without creating files.",
    )
    parser.add_argument(
        "--ngram-minus-10y-csv",
        type=Path,
        default=None,
        help="Optional pre-publication Ngram CSV used to populate book_stats.",
    )
    return parser.parse_args()


def describe_result(result: BatchResult) -> str:
    actions = []
    if result.csv_created:
        actions.append(f"CSV -> {result.occurrence_csv}")
    if result.map_created:
        actions.append(f"map -> {result.first_map}")
    if result.book_stats_created:
        actions.append(f"book_stats -> {result.book_stats}")
    if result.word_metrics_updated:
        actions.append(f"word_metrics -> {result.word_metrics}")
    action_text = ", ".join(actions) if actions else "already complete"
    return f"{result.input_txt}: {action_text}"


def main() -> None:
    args = parse_args()
    results = generate_missing_outputs(
        books_dir=args.books_dir,
        output_dir=args.output_dir,
        maps_dir=args.maps_dir,
        width=args.width,
        scale=args.scale,
        ngram_minus_10y_path=args.ngram_minus_10y_csv,
        dry_run=args.dry_run,
    )

    if not results:
        print("All .txt books already have occurrence CSVs and first visual maps.")
        return

    prefix = "Would create" if args.dry_run else "Created"
    for result in results:
        print(f"{prefix}: {describe_result(result)}")


if __name__ == "__main__":
    main()
