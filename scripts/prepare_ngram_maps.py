from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from vocab_mapper.plot_pyramidal_tiff import render_pyramidal_map
from vocab_mapper.metrics import BOOK_MAP_METRICS, MAP_METRICS, NGRAM_MAP_METRICS, scaled_metric_slug, resolve_metric_name


DEFAULT_CSV_ROOT = PROJECT_ROOT / "output" / "CSV Ocurrence Maps"
DEFAULT_MAP_ROOT = PROJECT_ROOT / "output" / "maps"

RenderTask = tuple[Path, Path, int, str, str, str]


def map_stem(csv_path: Path) -> str:
    stem = csv_path.stem
    if stem.endswith("_occurrences"):
        return stem[: -len("_occurrences")]
    return stem


def book_key(csv_path: Path) -> str:
    stem = map_stem(csv_path).lower()
    suffixes = (
        "_eng_fiction_2019_recent_1999_2019",
        "_eng_fiction_2019_all",
    )
    for suffix in suffixes:
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
    return re.sub(r"[^a-z0-9]+", "_", stem).strip("_")


def csv_priority(csv_path: Path, csv_root: Path) -> tuple[int, int, int, str]:
    relative_csv = csv_path.relative_to(csv_root)
    path_parts = [part.lower() for part in relative_csv.parts]
    stem = map_stem(csv_path).lower()
    normalized_stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    is_downloaded = int("downloaded from gutenberg" in path_parts)
    is_source_variant = int(normalized_stem != book_key(csv_path))
    is_nested = int(len(relative_csv.parts) > 1)
    return (is_downloaded, is_source_variant, is_nested, str(relative_csv).lower())


def output_path_for(
    csv_path: Path,
    csv_root: Path,
    map_root: Path,
    metric: str,
    scale: str,
) -> Path:
    relative_csv = csv_path.relative_to(csv_root)
    return (
        map_root
        / relative_csv.parent
        / f"{map_stem(csv_path)}_{scaled_metric_slug(metric, scale)}.pyramid.ome.tif"
    )


def prepare_maps(
    csv_root: Path,
    map_root: Path,
    width: int,
    scale: str,
    compression: str,
    force: bool,
    workers: int,
    include: str | None = None,
    excludes: list[str] | None = None,
    metrics: list[str] | None = None,
) -> tuple[int, int, int]:
    created = 0
    skipped = 0
    failed = 0
    include_filter = include.lower() if include else None
    exclude_filters = [exclude.lower() for exclude in excludes or []]
    selected_metrics = list(metrics or MAP_METRICS)
    seen: set[tuple[str, str]] = set()
    tasks: list[RenderTask] = []

    csv_paths = sorted(
        csv_root.rglob("*.csv"),
        key=lambda path: csv_priority(path, csv_root),
    )

    for csv_path in csv_paths:
        relative_csv = csv_path.relative_to(csv_root)
        relative_text = str(relative_csv).lower()
        if include_filter and include_filter not in str(relative_csv).lower():
            continue
        if any(exclude in relative_text for exclude in exclude_filters):
            continue

        for metric in selected_metrics:
            dedupe_key = (book_key(csv_path), metric)
            if dedupe_key in seen:
                skipped += 1
                print(f"skipped-duplicate\t{csv_path.relative_to(PROJECT_ROOT)}\t{metric}")
                continue
            output_tiff = output_path_for(csv_path, csv_root, map_root, metric, scale)
            metadata_path = output_tiff.with_suffix(".json")
            if not force and output_tiff.exists() and metadata_path.exists():
                seen.add(dedupe_key)
                skipped += 1
                print(f"skipped\t{output_tiff.relative_to(PROJECT_ROOT)}")
                continue

            seen.add(dedupe_key)
            tasks.append(
                (
                    csv_path,
                    output_tiff,
                    width,
                    metric,
                    scale,
                    compression,
                )
            )

    if workers <= 1:
        for task in tasks:
            status, path, rows, levels, error = render_map_task(task)
            if status == "created":
                created += 1
                print(
                    f"created\t{path.relative_to(PROJECT_ROOT)}\t{rows} rows\t{levels} levels",
                    flush=True,
                )
            else:
                failed += 1
                print(f"failed\t{path.relative_to(PROJECT_ROOT)}\t{error}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(render_map_task, task) for task in tasks]
            for future in as_completed(futures):
                status, path, rows, levels, error = future.result()
                if status == "created":
                    created += 1
                    print(
                        f"created\t{path.relative_to(PROJECT_ROOT)}\t{rows} rows\t{levels} levels",
                        flush=True,
                    )
                else:
                    failed += 1
                    print(f"failed\t{path.relative_to(PROJECT_ROOT)}\t{error}", flush=True)

    return created, skipped, failed


def render_map_task(task: RenderTask) -> tuple[str, Path, int, int, str | None]:
    csv_path, output_tiff, width, metric, scale, compression = task
    try:
        metadata = render_pyramidal_map(
            csv_path,
            output_tiff,
            width=width,
            metric=metric,
            scale=scale,
            compression=compression,
        )
    except Exception as exc:
        return "failed", output_tiff, 0, 0, f"{csv_path}: {metric}: {exc}"
    return (
        "created",
        output_tiff,
        int(metadata["data_rows"]),
        int(metadata["pyramid_levels"]),
        None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare pyramidal BigTIFF maps for every current metric column."
    )
    parser.add_argument(
        "--csv-root",
        type=Path,
        default=DEFAULT_CSV_ROOT,
        help="Root directory containing occurrence CSV maps.",
    )
    parser.add_argument(
        "--map-root",
        type=Path,
        default=DEFAULT_MAP_ROOT,
        help="Root directory where rendered maps should be written.",
    )
    parser.add_argument("--width", type=int, default=2000)
    parser.add_argument("--scale", choices=("linear", "log"), default="linear")
    parser.add_argument("--compression", default="deflate")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel render workers. Use 1 for deterministic sequential rendering.",
    )
    parser.add_argument(
        "--include",
        default=None,
        help="Only process CSV paths containing this case-insensitive text.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Skip CSV paths containing this case-insensitive text. Can be repeated.",
    )
    parser.add_argument(
        "--metric-group",
        choices=("all", "book", "ngram"),
        default="all",
        help="Limit maps to all metrics, book metrics, or Ngram metrics.",
    )
    parser.add_argument(
        "--metric",
        action="append",
        default=[],
        help="Specific metric to render. Can be repeated and overrides --metric-group.",
    )
    args = parser.parse_args()
    if args.metric:
        selected_metrics = [resolve_metric_name(metric) for metric in args.metric]
    elif args.metric_group == "book":
        selected_metrics = BOOK_MAP_METRICS
    elif args.metric_group == "ngram":
        selected_metrics = NGRAM_MAP_METRICS
    else:
        selected_metrics = MAP_METRICS

    created, skipped, failed = prepare_maps(
        args.csv_root.resolve(),
        args.map_root.resolve(),
        width=args.width,
        scale=args.scale,
        compression=args.compression,
        force=args.force,
        workers=max(1, args.workers),
        include=args.include,
        excludes=args.exclude,
        metrics=selected_metrics,
    )
    print(f"summary\tcreated={created}\tskipped={skipped}\tfailed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
