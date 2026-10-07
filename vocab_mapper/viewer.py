from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
from concurrent.futures import Future
import csv
import hashlib
import json
import math
import mimetypes
import re
import threading
import webbrowser
from bisect import bisect_left
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from vocab_mapper.ngram_backfill import NgramSourceSpec, ensure_ngram_frequency_sources
from vocab_mapper.prepare_csv import clean_text, collect_occurrences, prepare_csv
from vocab_mapper.import_ngram import RECENT_RANGE
from vocab_mapper.stats import (
    book_stats_from_rows,
    book_stats_output_path,
    write_book_stats_txt,
)
from vocab_mapper.smoothing import SmoothingConfig, config_from_query, smooth_values
from vocab_mapper.metric_values import TOKEN_FREQUENCY_BASIS, normalize_frequency_basis
from vocab_mapper.word_metrics_csv import prepare_word_metrics_csv
from vocab_mapper.viewer_rendering import (
    MetricColorScale,
    metric_color,
    metric_color_scale,
    metric_palette,
    metric_values,
    normalized_metric_color,
    normalized_metric_value,
)
from vocab_mapper.metrics import (
    BOOK_AVG_DEV,
    BOOK_FREQ,
    BOOK_MAP_METRICS,
    BOOK_MED_DEV,
    FIC_NGRAM_99_19_AVG_DEV,
    FIC_NGRAM_99_19_FREQ,
    FIC_NGRAM_99_19_MED_DEV,
    FIC_NGRAM_PREPUB_10Y_AVG_DEV,
    FIC_NGRAM_PREPUB_10Y_FREQ,
    FIC_NGRAM_PREPUB_10Y_MED_DEV,
    FIC_NGRAM_TOTAL_AVG_DEV,
    FIC_NGRAM_TOTAL_FREQ,
    FIC_NGRAM_TOTAL_MED_DEV,
    MAP_METRICS,
    is_excluded_metric,
    is_ngram_frequency_metric,
    is_current_metric,
    metric_definition,
    metric_label,
    metric_spec,
    metric_slug,
    scale_slug,
    scaled_metric_slug,
    resolve_metric_name,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).with_name("web_viewer")
OUTPUT_MAPS_DIR = PROJECT_ROOT / "output" / "maps"
OUTPUT_CSV_DIR = PROJECT_ROOT / "output" / "CSV Ocurrence Maps"
BOOK_METADATA_PATH = PROJECT_ROOT / "output" / "book_metadata.json"
DATA_NGRAM_DIR = PROJECT_ROOT / "data" / "ngram_frequencies"
GOOGLE_NGRAM_GZ = PROJECT_ROOT / "data" / "google_ngram" / "eng-fiction" / "1-00000-of-00001.gz"
GOOGLE_NGRAM_TOTALCOUNTS = PROJECT_ROOT / "data" / "google_ngram" / "eng-fiction" / "totalcounts-1"
USER_TEXT_DIR = PROJECT_ROOT / "output" / "source_texts"
GENERATED_CSV_DIR = OUTPUT_CSV_DIR / "generated"
GENERATED_MAPS_DIR = OUTPUT_MAPS_DIR / "generated"
DEFAULT_GENERATED_WIDTH = 2000
MAX_GENERATION_TEXT_CHARS = 50_000_000
WORD_STATS_DIR = PROJECT_ROOT / "output" / "Word_Metrics"
NGRAM_BACKFILL_LOCK = threading.Lock()
EXPORT_MAX_PIXELS = 40_000_000

NGRAM_SOURCE_BY_METRIC = {
    FIC_NGRAM_TOTAL_FREQ: "Total",
    FIC_NGRAM_TOTAL_AVG_DEV: "Total",
    FIC_NGRAM_TOTAL_MED_DEV: "Total",
    FIC_NGRAM_PREPUB_10Y_FREQ: "-10y",
    FIC_NGRAM_PREPUB_10Y_AVG_DEV: "-10y",
    FIC_NGRAM_PREPUB_10Y_MED_DEV: "-10y",
    FIC_NGRAM_99_19_FREQ: "1999-2019",
    FIC_NGRAM_99_19_AVG_DEV: "1999-2019",
    FIC_NGRAM_99_19_MED_DEV: "1999-2019",
}


def _json_response(handler: SimpleHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _as_project_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _human_label(stem: str) -> str:
    replacements = (
        "_frequency_total_F",
        "_book_freq",
        "_book_avg_dev",
        "_book_med_dev",
        "_book_frequency",
        "_book_frequency_average_deviation",
        "_book_frequency_median_deviation",
        "_book_frequency_mad",
        "_book_frequency_F",
        "_negative_f_ngram_total_deviation",
        ".pyramid.ome",
    )
    label = stem
    for replacement in replacements:
        label = label.replace(replacement, "")
    return label.replace("_", " ").strip().title()


def _book_label_from_csv(csv_path: Path) -> str:
    stem = csv_path.stem
    suffixes = (
        "_occurrences",
        "_eng_fiction_2019_recent_1999_2019",
        "_eng_fiction_2019_all",
    )
    label = stem
    for suffix in suffixes:
        label = label.replace(suffix, "")
    label = _strip_prepublication_suffix(label)
    label = re.sub(r"_gutenberg_\d+$", "", label)
    return label.replace("_", " ").strip().title()


def _slug_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _filename_stem(value: str) -> str:
    stem = Path(value).stem.strip()
    return stem or "Uploaded text"


def _safe_generation_slug(filename: str, content: str) -> str:
    base = _slug_key(_filename_stem(filename)) or "uploaded_text"
    digest = hashlib.sha1((filename + "\0" + content).encode("utf-8")).hexdigest()[:10]
    return f"{base}_{digest}"


def _bounded_int(value: object, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


@dataclass(frozen=True)
class CorpusOption:
    id: str
    label: str
    total_path: Path | None = None
    minus_10y_path: Path | None = None
    recent_1999_2019_path: Path | None = None
    dynamic_sources: tuple[str, ...] = ()

    @property
    def source_paths(self) -> dict[str, Path]:
        paths: dict[str, Path] = {}
        if self.total_path is not None:
            paths["Total"] = self.total_path
        if self.minus_10y_path is not None:
            paths["-10y"] = self.minus_10y_path
        if self.recent_1999_2019_path is not None:
            paths["1999-2019"] = self.recent_1999_2019_path
        return paths

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "sources": {
                key: _relative(path).replace("\\", "/")
                for key, path in self.source_paths.items()
            },
            "dynamicSources": list(self.dynamic_sources),
        }


def _find_first_csv(directory: Path, *needles: str) -> Path | None:
    csv_paths = sorted(directory.glob("*.csv"))
    for needle in needles:
        lowered = needle.lower()
        for path in csv_paths:
            if lowered in path.name.lower():
                return path
    return None


def _corpus_option_for_directory(directory: Path) -> CorpusOption | None:
    total_path = _find_first_csv(directory, "_all_ngram_frequencies")
    minus_10y_path = _find_first_csv(directory, "_minus_10y_ngram_frequencies")
    recent_path = _find_first_csv(directory, "_recent_1999_2019_ngram_frequencies")
    if total_path is None and minus_10y_path is None and recent_path is None:
        return None

    if directory == DATA_NGRAM_DIR:
        corpus_id = "eng_fiction_2019"
        label = "English Fiction 2019"
    else:
        corpus_id = _slug_key(str(directory.relative_to(DATA_NGRAM_DIR))) or _slug_key(directory.name)
        label = _human_label(directory.name)

    return CorpusOption(
        id=corpus_id,
        label=label,
        total_path=total_path,
        minus_10y_path=minus_10y_path,
        recent_1999_2019_path=recent_path,
        dynamic_sources=("-10y",) if directory == DATA_NGRAM_DIR and _can_backfill_ngram_data() else (),
    )


def _can_backfill_ngram_data() -> bool:
    return GOOGLE_NGRAM_GZ.exists() and GOOGLE_NGRAM_TOTALCOUNTS.exists()


def discover_corpora() -> list[CorpusOption]:
    corpora = [CorpusOption(id="book_only", label="Book metrics only")]
    if not DATA_NGRAM_DIR.exists():
        return corpora

    option = _corpus_option_for_directory(DATA_NGRAM_DIR)
    if option is not None:
        corpora.append(option)
    return corpora


def _corpus_by_id(corpus_id: str) -> CorpusOption:
    for corpus in discover_corpora():
        if corpus.id == corpus_id:
            return corpus
    raise ValueError(f"Unknown corpus: {corpus_id}")


def _required_corpus_source(metric: str) -> str:
    return NGRAM_SOURCE_BY_METRIC.get(resolve_metric_name(metric), "")


def generation_metric_options() -> list[dict[str, object]]:
    options: list[dict[str, object]] = []
    for metric in MAP_METRICS:
        spec = metric_spec(metric)
        if spec is None or not spec.mappable:
            continue
        options.append(
            {
                "name": metric,
                "label": metric_label(metric),
                "definition": metric_definition(metric),
                "palette": spec.palette,
                "group": "book" if metric in BOOK_MAP_METRICS else "ngram",
                "requiresCorpusSource": _required_corpus_source(metric),
                "defaultSelected": metric == BOOK_FREQ,
            }
        )
    return options


def generation_options_payload() -> dict[str, object]:
    return {
        "corpora": [corpus.to_payload() for corpus in discover_corpora()],
        "metrics": generation_metric_options(),
        "defaults": {
            "corpusId": "book_only",
            "width": DEFAULT_GENERATED_WIDTH,
            "scale": "linear",
        },
    }


def discover_word_stat_files() -> list[dict[str, object]]:
    roots = [WORD_STATS_DIR, PROJECT_ROOT / "output"]
    files: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            lowered = path.name.lower()
            if "word_metrics" not in lowered and "word_frequencies" not in lowered:
                continue
            relative = _relative(path).replace("\\", "/")
            files.setdefault(relative, path)

    payload: list[dict[str, object]] = []
    for relative, path in sorted(files.items(), key=lambda item: item[0].lower()):
        payload.append(
            {
                "id": hashlib.sha1(relative.encode("utf-8")).hexdigest()[:16],
                "name": _human_label(path.stem),
                "path": relative,
                "size": path.stat().st_size,
            }
        )
    return payload


def word_stat_file_by_id(file_id: str) -> Path | None:
    for entry in discover_word_stat_files():
        if entry["id"] == file_id:
            return PROJECT_ROOT / str(entry["path"]).replace("/", "\\")
    return None


def _load_book_metadata() -> dict[str, dict[str, str]]:
    if not BOOK_METADATA_PATH.exists():
        return {}
    try:
        raw = json.loads(BOOK_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(key): value
        for key, value in raw.items()
        if isinstance(value, dict)
    }


def _strip_prepublication_suffix(value: str) -> str:
    markers = (
        "_eng_fiction_2019_prepub_",
        "_eng_fiction_2019_pre_publication_",
        "_eng_fiction_2019_usher_pre_publication_",
    )
    for marker in markers:
        index = value.find(marker)
        if index >= 0:
            return value[:index]
    return value


def _map_type_label(title: str, book: str, metric: str) -> str:
    try:
        return metric_label(metric)
    except ValueError:
        pass
    normalized_title = title.lower()
    normalized_book = book.lower()
    if normalized_title == normalized_book:
        base = ""
    elif normalized_title.startswith(normalized_book + " "):
        base = title[len(book) :].strip()
    else:
        base = title
    rendered_metric_label = metric.replace("_", " ")
    return f"{base} / {rendered_metric_label}".strip(" /").title()


def _append_scale_suffix(label: str, scale: str) -> str:
    suffix = f"_{scale_slug(scale)}"
    return label if label.lower().endswith(suffix) else f"{label}{suffix}"


def _strip_scale_suffix(label: str) -> str:
    return re.sub(r"_(linear|log)$", "", label, flags=re.IGNORECASE)


def _scan_csvs() -> dict[str, list[Path]]:
    csvs: dict[str, list[Path]] = {}
    for base in (OUTPUT_CSV_DIR, PROJECT_ROOT / "output"):
        if not base.exists():
            continue
        for path in base.rglob("*.csv"):
            csvs.setdefault(path.name.lower(), []).append(path)
    return csvs


def _resolve_csv(metadata: dict[str, object], csv_index: dict[str, list[Path]]) -> Path | None:
    declared = _as_project_path(str(metadata.get("input_csv", "")))
    if declared and declared.exists():
        return declared
    if declared:
        matches = csv_index.get(declared.name.lower(), [])
        if matches:
            return matches[0]
    return None


def _metadata_int(metadata: dict[str, object], *keys: str) -> int:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def discover_maps(include_excluded: bool = False, deduplicate: bool = True) -> list[dict[str, object]]:
    if not OUTPUT_MAPS_DIR.exists():
        return []

    csv_index = _scan_csvs()
    maps: list[dict[str, object]] = []
    for metadata_path in sorted(OUTPUT_MAPS_DIR.rglob("*.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        excluded = bool(metadata.get("excluded_from_viewer"))
        if excluded and not include_excluded:
            continue

        csv_path = _resolve_csv(metadata, csv_index)
        if csv_path is None:
            continue

        raw_metric = str(metadata.get("metric") or BOOK_FREQ)
        if is_excluded_metric(raw_metric):
            continue
        try:
            metric = resolve_metric_name(raw_metric)
        except ValueError:
            continue
        if not is_current_metric(metric):
            continue
        map_width = _metadata_int(metadata, "width_px", "display_width_px", "base_width_px", "map_width_px")
        total_rows = _metadata_int(metadata, "height_px", "data_rows", "base_height_px")
        if map_width <= 0 or total_rows <= 0:
            continue

        rel_metadata = _relative(metadata_path).replace("\\", "/")
        map_id = hashlib.sha1(rel_metadata.encode("utf-8")).hexdigest()[:16]
        image_path = _as_project_path(
            str(metadata.get("output_png") or metadata.get("output_tiff") or "")
        )
        title = _human_label(metadata_path.stem)
        book = str(metadata.get("book_title") or _book_label_from_csv(csv_path))
        corpus_label = str(metadata.get("corpus_label") or "")
        map_type = _map_type_label(title, book, metric)
        if corpus_label and (is_ngram_frequency_metric(metric) or metric in NGRAM_SOURCE_BY_METRIC):
            map_type = f"{metric_label(metric)} ({corpus_label})"
        map_type = str(metadata.get("map_type_override") or map_type)
        scale = str(metadata.get("scale", "linear"))
        map_type = _append_scale_suffix(map_type, scale)
        maps.append(
            {
                "id": map_id,
                "title": title,
                "book": book,
                "mapType": map_type,
                "group": _relative(metadata_path.parent).replace("\\", "/"),
                "metric": metric,
                "definition": metric_definition(metric),
                "palette": metadata.get("palette", metric_palette(metric)),
                "scale": scale,
                "corpusId": metadata.get("corpus_id", ""),
                "corpusLabel": corpus_label,
                "generationSlug": metadata.get("generation_slug", ""),
                "sourceFilename": metadata.get("source_filename", ""),
                "width": map_width,
                "totalRows": total_rows,
                "metadataPath": rel_metadata,
                "csvPath": _relative(csv_path).replace("\\", "/"),
                "imagePath": _relative(image_path).replace("\\", "/") if image_path and image_path.exists() else "",
                "excluded": excluded,
                "minValue": metadata.get("min_value", 0),
                "maxValue": metadata.get("max_value", 0),
                "maxAbsValue": metadata.get("max_abs_value", 0),
            }
        )

    if deduplicate:
        maps = _deduplicate_maps(maps)
    maps.sort(key=lambda item: (str(item["book"]).lower(), str(item["mapType"]).lower(), str(item["metric"]).lower()))
    return maps


def _deduplicate_maps(maps: list[dict[str, object]]) -> list[dict[str, object]]:
    best: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for entry in maps:
        identity = str(entry.get("generationSlug") or _slug_key(str(entry["book"])))
        corpus = _slug_key(str(entry.get("corpusId") or entry.get("corpusLabel") or ""))
        key = (identity, str(entry["metric"]), corpus, str(entry.get("scale") or "linear"))
        current = best.get(key)
        if current is None or _map_preference(entry) > _map_preference(current):
            best[key] = entry
    return list(best.values())


def _map_preference(entry: dict[str, object]) -> tuple[int, int, int, int]:
    metadata_path = str(entry.get("metadataPath", "")).lower()
    csv_path = str(entry.get("csvPath", "")).lower()
    score = 0
    if "downloaded from gutenberg" not in metadata_path and "downloaded from gutenberg" not in csv_path:
        score += 50
    if "/the fall of the house usher/" in metadata_path or "\\the fall of the house usher\\" in metadata_path:
        score += 20
    if "annotated" not in metadata_path:
        score += 10
    if metric_slug(str(entry.get("metric", ""))) in metadata_path:
        score += 8
    if ".pyramid.ome" in metadata_path:
        score += 5
    if "eng_fiction_2019_" not in metadata_path:
        score += 3
    return (
        score,
        -len(metadata_path),
        int(entry.get("totalRows", 0) or 0),
        int(entry.get("width", 0) or 0),
    )


def manage_maps_payload() -> dict[str, object]:
    return {"maps": discover_maps(include_excluded=True, deduplicate=False)}


def map_entry_by_id(map_id: str, include_excluded: bool = True) -> dict[str, object] | None:
    return next(
        (
            entry
            for entry in discover_maps(include_excluded=include_excluded, deduplicate=False)
            if str(entry.get("id")) == map_id
        ),
        None,
    )


def _metadata_path_for_entry(entry: dict[str, object]) -> Path:
    path = PROJECT_ROOT / str(entry["metadataPath"]).replace("/", "\\")
    resolved = path.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("Map metadata path is outside the project.") from exc
    return resolved


def _read_map_metadata(entry: dict[str, object]) -> dict[str, object]:
    metadata_path = _metadata_path_for_entry(entry)
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _write_map_metadata(entry: dict[str, object], metadata: dict[str, object]) -> None:
    metadata_path = _metadata_path_for_entry(entry)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    STATE.refresh()


def rename_map_entry(map_id: str, book_title: str, map_type: str) -> dict[str, object]:
    entry = map_entry_by_id(map_id)
    if entry is None:
        raise ValueError("Map not found.")

    book_title = book_title.strip()
    map_type = map_type.strip()
    if not book_title:
        raise ValueError("Book name cannot be blank.")
    if not map_type:
        raise ValueError("Map name cannot be blank.")

    metadata = _read_map_metadata(entry)
    metadata["book_title"] = book_title
    metadata["map_type_override"] = map_type
    _write_map_metadata(entry, metadata)
    updated = map_entry_by_id(map_id)
    if updated is None:
        raise ValueError("Updated map is no longer available.")
    return updated


def set_map_excluded(map_id: str, excluded: bool) -> dict[str, object]:
    entry = map_entry_by_id(map_id)
    if entry is None:
        raise ValueError("Map not found.")

    metadata = _read_map_metadata(entry)
    metadata["excluded_from_viewer"] = bool(excluded)
    _write_map_metadata(entry, metadata)
    updated = map_entry_by_id(map_id)
    if updated is None:
        raise ValueError("Updated map is no longer available.")
    return updated


def duplicate_map_entry(map_id: str) -> dict[str, object]:
    entry = map_entry_by_id(map_id)
    if entry is None:
        raise ValueError("Map not found.")

    metadata_path = _metadata_path_for_entry(entry)
    metadata = _read_map_metadata(entry)
    copy_path = _next_duplicate_metadata_path(metadata_path)
    copy_number = _duplicate_number(copy_path)
    original_slug = str(metadata.get("generation_slug") or metadata_path.stem)
    metadata["book_title"] = str(metadata.get("book_title") or entry.get("book") or "Untitled")
    base_map_type = _strip_scale_suffix(str(entry.get("mapType") or entry.get("metric") or "Map"))
    metadata["map_type_override"] = f"{base_map_type} Copy"
    metadata["generation_slug"] = f"{_slug_key(original_slug) or 'map'}_copy_{copy_number}"
    metadata["excluded_from_viewer"] = False
    metadata["managed_duplicate_of"] = str(entry.get("metadataPath") or "")
    copy_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    STATE.refresh()

    duplicated_id = hashlib.sha1(_relative(copy_path).replace("\\", "/").encode("utf-8")).hexdigest()[:16]
    duplicated = map_entry_by_id(duplicated_id)
    if duplicated is None:
        raise ValueError("Duplicated map could not be loaded.")
    return duplicated


def _next_duplicate_metadata_path(metadata_path: Path) -> Path:
    for index in range(1, 10_000):
        candidate = metadata_path.with_name(f"{metadata_path.stem}_copy_{index}.json")
        if not candidate.exists():
            return candidate
    raise ValueError("Could not create a duplicate map name.")


def _duplicate_number(path: Path) -> int:
    match = re.search(r"_copy_(\d+)\.json$", path.name)
    return int(match.group(1)) if match else 1


@dataclass(frozen=True)
class ExportedMap:
    filename: str
    content_type: str
    data: bytes | None = None
    path: Path | None = None


def export_map_entry(map_id: str, export_format: str) -> ExportedMap:
    entry = map_entry_by_id(map_id)
    if entry is None:
        raise ValueError("Map not found.")

    export_format = export_format.lower().strip()
    if export_format == "tif":
        export_format = "tiff"
    if export_format not in {"tiff", "png", "pdf"}:
        raise ValueError("Export format must be tiff, png, or pdf.")

    source_path = _source_image_path(entry, prefer_tiff=export_format == "tiff")
    if source_path is None:
        raise ValueError("Rendered map image not found.")

    filename_base = _slug_key(f"{entry.get('book', '')}_{entry.get('mapType', '')}") or "map"
    if export_format == "tiff":
        if source_path.suffix.lower() in {".tif", ".tiff"}:
            return ExportedMap(
                filename=f"{filename_base}.tif",
                content_type="image/tiff",
                path=source_path,
            )
        return ExportedMap(
            filename=f"{filename_base}.tif",
            content_type="image/tiff",
            data=_convert_image_bytes(source_path, "TIFF"),
        )

    if export_format == "png":
        if source_path.suffix.lower() == ".png":
            return ExportedMap(
                filename=f"{filename_base}.png",
                content_type="image/png",
                path=source_path,
            )
        return ExportedMap(
            filename=f"{filename_base}.png",
            content_type="image/png",
            data=_convert_image_bytes(source_path, "PNG"),
        )

    return ExportedMap(
        filename=f"{filename_base}.pdf",
        content_type="application/pdf",
        data=_convert_image_bytes(source_path, "PDF"),
    )


def _source_image_path(entry: dict[str, object], prefer_tiff: bool = False) -> Path | None:
    metadata = _read_map_metadata(entry)
    keys = ("output_tiff", "output_png", "imagePath") if prefer_tiff else ("output_png", "output_tiff", "imagePath")
    for key in keys:
        value = metadata.get(key) or entry.get(key)
        path = _safe_project_file(value)
        if path is not None:
            return path
    return None


def _safe_project_file(value: object) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        resolved = path.resolve()
        resolved.relative_to(PROJECT_ROOT.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.exists() and resolved.is_file() else None


def _convert_image_bytes(source_path: Path, image_format: str) -> bytes:
    image = _export_image(source_path)
    buffer = BytesIO()
    if image_format == "PDF":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffer, format="PDF", resolution=144)
    else:
        image.save(buffer, format=image_format)
    return buffer.getvalue()


def _export_image(source_path: Path):
    from PIL import Image

    if source_path.suffix.lower() in {".tif", ".tiff"}:
        return _export_image_from_tiff(source_path)

    with Image.open(source_path) as image:
        image.load()
        copy = image.copy()
    return _downsample_for_export(copy)


def _export_image_from_tiff(source_path: Path):
    from PIL import Image
    import tifffile

    with tifffile.TiffFile(source_path) as tiff:
        levels = getattr(tiff.series[0], "levels", None) or [tiff.pages[0]]
        selected = levels[-1]
        for level in levels:
            shape = level.shape
            pixel_count = int(shape[0]) * int(shape[1])
            if pixel_count <= EXPORT_MAX_PIXELS:
                selected = level
                break
        array = selected.asarray()

    if array.ndim == 2:
        return Image.fromarray(array, mode="L")
    if array.ndim == 3 and array.shape[2] >= 3:
        return Image.fromarray(array[:, :, :3], mode="RGB")
    return Image.fromarray(array)


def _downsample_for_export(image):
    pixel_count = image.width * image.height
    if pixel_count <= EXPORT_MAX_PIXELS:
        return image

    ratio = math.sqrt(EXPORT_MAX_PIXELS / pixel_count)
    width = max(1, int(image.width * ratio))
    height = max(1, int(image.height * ratio))
    return image.resize((width, height))


def _read_occurrence_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def _validate_generation_metrics(
    metrics: object,
    corpus: CorpusOption,
    publication_year: int | None = None,
) -> list[str]:
    if not isinstance(metrics, list):
        raise ValueError("Select at least one map to generate.")

    selected: list[str] = []
    for raw_metric in metrics:
        metric = resolve_metric_name(str(raw_metric))
        if metric not in MAP_METRICS:
            raise ValueError(f"Unsupported map metric: {raw_metric}")
        if metric not in selected:
            selected.append(metric)

    if not selected:
        raise ValueError("Select at least one map to generate.")

    available_sources = corpus.source_paths
    for metric in selected:
        required_source = _required_corpus_source(metric)
        has_static_source = required_source in available_sources
        has_dynamic_source = required_source in corpus.dynamic_sources
        if required_source == "-10y" and has_dynamic_source and publication_year is None:
            raise ValueError(
                f"{metric_label(metric)} requires a publication year for the pre-publication window."
            )
        if required_source and not has_static_source and not has_dynamic_source:
            raise ValueError(
                f"{metric_label(metric)} requires a corpus with {required_source} data."
            )
    return selected


def _generation_corpus_paths(corpus: CorpusOption) -> dict[str, Path | None]:
    return {
        "ngram_total_path": corpus.total_path,
        "ngram_minus_10y_path": corpus.minus_10y_path,
        "ngram_1999_2019_path": corpus.recent_1999_2019_path,
    }


def _parse_publication_year(value: object, filename: str) -> int | None:
    if value not in (None, ""):
        try:
            year = int(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValueError("Publication year must be a number.") from exc
        if year < 1 or year > 9999:
            raise ValueError("Publication year must be between 1 and 9999.")
        return year

    match = re.search(r"(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)", filename)
    return int(match.group(1)) if match else None


def _needs_ngram_sources(metrics: list[str]) -> bool:
    return any(_required_corpus_source(metric) for metric in metrics)


def _needs_prepublication_source(metrics: list[str]) -> bool:
    return any(_required_corpus_source(metric) == "-10y" for metric in metrics)


def _runtime_corpus_for_generation(
    corpus: CorpusOption,
    selected_metrics: list[str],
    publication_year: int | None,
    generation_slug: str,
) -> CorpusOption:
    if (
        _needs_prepublication_source(selected_metrics)
        and corpus.minus_10y_path is None
        and "-10y" in corpus.dynamic_sources
        and publication_year is not None
    ):
        start_year = publication_year - 10
        end_year = publication_year - 1
        return CorpusOption(
            id=corpus.id,
            label=corpus.label,
            total_path=corpus.total_path,
            minus_10y_path=(
                DATA_NGRAM_DIR
                / "generated"
                / generation_slug
                / f"eng_fiction_2019_minus_10y_{start_year}_{end_year}_ngram_frequencies.csv"
            ),
            recent_1999_2019_path=corpus.recent_1999_2019_path,
            dynamic_sources=corpus.dynamic_sources,
        )
    return corpus


def _target_words_from_content(content: str) -> set[str]:
    return {
        occurrence.normalized_word
        for occurrence in collect_occurrences(clean_text(content))
        if occurrence.normalized_word
    }


def _ngram_source_specs(
    corpus: CorpusOption,
    selected_metrics: list[str],
    publication_year: int | None,
) -> list[NgramSourceSpec]:
    if not _needs_ngram_sources(selected_metrics):
        return []

    specs: list[NgramSourceSpec] = []
    if corpus.total_path is not None:
        specs.append(NgramSourceSpec("Total", corpus.total_path, None))
    if corpus.recent_1999_2019_path is not None:
        specs.append(NgramSourceSpec("1999-2019", corpus.recent_1999_2019_path, RECENT_RANGE))
    if corpus.minus_10y_path is not None and publication_year is not None:
        specs.append(
            NgramSourceSpec(
                "-10y",
                corpus.minus_10y_path,
                (publication_year - 10, publication_year - 1),
            )
        )
    return specs


def _backfill_ngram_sources(
    corpus: CorpusOption,
    selected_metrics: list[str],
    publication_year: int | None,
    content: str,
) -> list[dict[str, object]]:
    specs = _ngram_source_specs(corpus, selected_metrics, publication_year)
    if not specs:
        return []

    target_words = _target_words_from_content(content)
    with NGRAM_BACKFILL_LOCK:
        results = ensure_ngram_frequency_sources(
            specs,
            target_words,
            GOOGLE_NGRAM_GZ,
            GOOGLE_NGRAM_TOTALCOUNTS,
        )
    return [
        {
            "source": result.label,
            "path": _relative(result.path).replace("\\", "/"),
            "addedWords": result.added_words,
        }
        for result in results
    ]


def _metadata_path_for(output_tiff: Path) -> Path:
    return output_tiff.with_suffix(".json")


def _tag_generated_metadata(
    metadata_path: Path,
    *,
    filename: str,
    book_title: str,
    generation_slug: str,
    source_text: Path,
    corpus: CorpusOption,
) -> None:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        metadata = {}
    metadata.update(
        {
            "book_title": book_title,
            "source_filename": filename,
            "source_text": str(source_text),
            "generation_slug": generation_slug,
            "corpus_id": corpus.id,
            "corpus_label": "" if corpus.id == "book_only" else corpus.label,
            "generated_by_viewer": True,
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def generate_maps_from_payload(payload: dict[str, object]) -> dict[str, object]:
    filename = str(payload.get("filename") or "uploaded.txt")
    content = str(payload.get("content") or "")
    if not content.strip():
        raise ValueError("Choose a non-empty .txt file.")
    if len(content) > MAX_GENERATION_TEXT_CHARS:
        raise ValueError("The selected text file is too large for this local viewer.")

    generation_slug = _safe_generation_slug(filename, content)
    base_corpus = _corpus_by_id(str(payload.get("corpusId") or "book_only"))
    publication_year = _parse_publication_year(payload.get("publicationYear"), filename)
    preliminary_metrics = _validate_generation_metrics(
        payload.get("metrics"),
        base_corpus,
        publication_year=publication_year,
    )
    corpus = _runtime_corpus_for_generation(
        base_corpus,
        preliminary_metrics,
        publication_year,
        generation_slug,
    )
    selected_metrics = _validate_generation_metrics(
        payload.get("metrics"),
        corpus,
        publication_year=publication_year,
    )
    width = _bounded_int(payload.get("width"), DEFAULT_GENERATED_WIDTH, 200, 8000)
    scale = "log" if str(payload.get("scale") or "linear").lower() == "log" else "linear"

    corpus_slug = _slug_key(corpus.id) or "book_only"
    book_title = _filename_stem(filename)
    source_text = USER_TEXT_DIR / f"{generation_slug}.txt"
    occurrence_csv = GENERATED_CSV_DIR / f"{generation_slug}_{corpus_slug}_occurrences.csv"
    book_stats_path = book_stats_output_path(PROJECT_ROOT / "output", generation_slug)
    word_metrics_csv = WORD_STATS_DIR / f"{generation_slug}_word_metrics.csv"

    USER_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_CSV_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    source_text.write_text(content, encoding="utf-8")

    ngram_backfill = _backfill_ngram_sources(
        corpus,
        selected_metrics,
        publication_year,
        content,
    )
    prepare_csv(
        source_text,
        occurrence_csv,
        **_generation_corpus_paths(corpus),
    )
    prepare_word_metrics_csv(source_text, word_metrics_csv)
    rows = _read_occurrence_rows(occurrence_csv)
    write_book_stats_txt(book_stats_from_rows(rows), book_stats_path)

    try:
        from vocab_mapper.plot_pyramidal_tiff import render_pyramidal_map
    except ImportError as exc:
        raise RuntimeError(
            "Map generation needs Pillow, NumPy, and tifffile installed."
        ) from exc

    generated_metadata_paths: list[str] = []
    failures: list[dict[str, str]] = []
    for metric in selected_metrics:
        output_tiff = GENERATED_MAPS_DIR / (
            f"{generation_slug}_{corpus_slug}_{scaled_metric_slug(metric, scale)}.pyramid.ome.tif"
        )
        try:
            render_pyramidal_map(
                occurrence_csv,
                output_tiff,
                width=width,
                metric=metric,
                scale=scale,
                compression="deflate",
            )
            metadata_path = _metadata_path_for(output_tiff)
            _tag_generated_metadata(
                metadata_path,
                filename=filename,
                book_title=book_title,
                generation_slug=generation_slug,
                source_text=source_text,
                corpus=corpus,
            )
            generated_metadata_paths.append(_relative(metadata_path).replace("\\", "/"))
        except Exception as exc:  # Keep any successful maps usable.
            failures.append({"metric": metric, "error": str(exc)})

    maps = STATE.refresh()
    generated_maps = [
        entry
        for entry in maps
        if str(entry.get("metadataPath")) in set(generated_metadata_paths)
    ]
    if not generated_maps and failures:
        errors = "; ".join(f"{item['metric']}: {item['error']}" for item in failures)
        raise RuntimeError(errors)

    generated_maps.sort(key=lambda item: str(item.get("mapType") or item.get("metric")))
    return {
        "sourceText": _relative(source_text).replace("\\", "/"),
        "occurrenceCsv": _relative(occurrence_csv).replace("\\", "/"),
        "wordMetricsCsv": _relative(word_metrics_csv).replace("\\", "/"),
        "bookStats": _relative(book_stats_path).replace("\\", "/"),
        "maps": generated_maps,
        "failures": failures,
        "ngramBackfill": ngram_backfill,
        "firstMapId": generated_maps[0]["id"] if generated_maps else "",
    }


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    value: int


MapLoadKey = tuple[str, str, str, int | None, int | None]


def _entry_csv_path(entry: dict[str, object]) -> Path:
    return PROJECT_ROOT / str(entry["csvPath"]).replace("/", "\\")


def _map_load_key(entry: dict[str, object]) -> MapLoadKey:
    csv_path = _entry_csv_path(entry)
    try:
        stat = csv_path.stat()
        file_size: int | None = stat.st_size
        modified_ns: int | None = stat.st_mtime_ns
    except OSError:
        file_size = None
        modified_ns = None
    return (
        str(csv_path),
        str(entry.get("metric") or ""),
        str(entry.get("scale") or "linear"),
        file_size,
        modified_ns,
    )


class LoadedMap:
    def __init__(self, entry: dict[str, object]) -> None:
        self.entry = entry
        self.csv_path = _entry_csv_path(entry)
        self.metric = str(entry["metric"])
        self.scale = str(entry.get("scale") or "linear")
        self.words: list[str] = []
        self.normalized_words: list[str] = []
        self.word_classes: list[str] = []
        self.rows: list[dict[str, str]] = []
        self._mode_cache: dict[
            tuple[bool, str], tuple[list[float], list[tuple[int, int, int]]]
        ] = {}
        self._smoothing_cache: OrderedDict[
            tuple[bool, str, SmoothingConfig],
            tuple[list[float] | None, list[float], list[tuple[int, int, int]]],
        ] = OrderedDict()
        self._display_score_cache: dict[
            tuple[bool, str], tuple[MetricColorScale, list[float]]
        ] = {}
        self._mode_lock = threading.Lock()
        self.chapters: list[int] = []
        self.paragraphs: list[int] = []
        self.sentences: list[int] = []
        self._segments: dict[str, list[Segment]] = {}
        self._segment_starts: dict[str, list[int]] = {}
        self._load()

    @property
    def total_rows(self) -> int:
        return len(self.words)

    def _effective_frequency_basis(self, frequency_basis: str) -> str:
        normalized = normalize_frequency_basis(frequency_basis)
        if resolve_metric_name(self.metric) not in BOOK_MAP_METRICS:
            return TOKEN_FREQUENCY_BASIS
        return normalized

    def _load(self) -> None:
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row_index, row in enumerate(reader, start=1):
                self.rows.append(row)
                word = row.get("word") or row.get("normalized_word") or ""
                normalized = (row.get("normalized_word") or word).lower()
                self.words.append(word)
                self.normalized_words.append(normalized)
                self.word_classes.append(row.get("word_class", ""))
                self.chapters.append(_parse_int(row.get("chapter_number"), 0))
                self.paragraphs.append(_parse_int(row.get("paragraph_number"), 0))
                self.sentences.append(_parse_int(row.get("sentence_number"), 0))
        self._segments = {
            "paragraph": _build_segments(self.paragraphs),
            "sentence": _build_segments(self.sentences),
        }
        chapter_segments = _build_segments(self.chapters)
        if _has_valid_chapter_structure(chapter_segments):
            self._segments["chapter"] = chapter_segments
        self._segment_starts = {
            key: [segment.start for segment in segments]
            for key, segments in self._segments.items()
        }
        self.entry["totalRows"] = len(self.words)
        values, _colors = self._values_and_colors(
            class_discrimination=True,
            frequency_basis=TOKEN_FREQUENCY_BASIS,
        )
        self.entry["minValue"] = min(values) if values else 0
        self.entry["maxValue"] = max(values) if values else 0
        self.entry["maxAbsValue"] = max((abs(value) for value in values), default=0)

    def _values_and_colors(
        self,
        class_discrimination: bool,
        frequency_basis: str = TOKEN_FREQUENCY_BASIS,
    ) -> tuple[list[float], list[tuple[int, int, int]]]:
        frequency_basis = self._effective_frequency_basis(frequency_basis)
        cache_key = (class_discrimination, frequency_basis)
        with self._mode_lock:
            cached = self._mode_cache.get(cache_key)
            if cached is not None:
                return cached

            values = metric_values(
                self.rows,
                self.metric,
                class_discrimination=class_discrimination,
                frequency_basis=frequency_basis,
            )
            color_scale = metric_color_scale(
                self.rows,
                values,
                self.metric,
                class_discrimination,
            )
            colors = [
                metric_color(
                    value,
                    self.metric,
                    self.scale,
                    color_scale.min_value,
                    color_scale.row_max_values[index],
                    color_scale.max_abs_value,
                )
                for index, value in enumerate(values)
            ]
            result = (values, colors)
            self._mode_cache[cache_key] = result
            return result

    def _display_scale_and_scores(
        self,
        values: list[float],
        class_discrimination: bool,
        frequency_basis: str = TOKEN_FREQUENCY_BASIS,
    ) -> tuple[MetricColorScale, list[float]]:
        frequency_basis = self._effective_frequency_basis(frequency_basis)
        cache_key = (class_discrimination, frequency_basis)
        with self._mode_lock:
            cached = self._display_score_cache.get(cache_key)
            if cached is not None:
                return cached

        color_scale = metric_color_scale(
            self.rows,
            values,
            self.metric,
            class_discrimination,
        )
        scores = [
            normalized_metric_value(
                value,
                self.metric,
                self.scale,
                color_scale.min_value,
                color_scale.row_max_values[index],
            )
            for index, value in enumerate(values)
        ]
        result = (color_scale, scores)
        with self._mode_lock:
            self._display_score_cache[cache_key] = result
        return result

    def _smoothed_view(
        self,
        class_discrimination: bool,
        frequency_basis: str,
        smoothing: SmoothingConfig | None,
        pixels_per_occurrence: float | None,
    ) -> tuple[
        list[float],
        list[float] | None,
        list[float],
        list[tuple[int, int, int]],
        SmoothingConfig,
    ]:
        frequency_basis = self._effective_frequency_basis(frequency_basis)
        values, base_colors = self._values_and_colors(class_discrimination, frequency_basis)
        config = (smoothing or SmoothingConfig()).resolved_for_zoom(pixels_per_occurrence)
        color_scale, base_scores = self._display_scale_and_scores(
            values,
            class_discrimination,
            frequency_basis,
        )
        if config.method in {"none", "display_blur"}:
            return values, None, base_scores, base_colors, config

        cache_key = (class_discrimination, frequency_basis, config)
        with self._mode_lock:
            cached = self._smoothing_cache.get(cache_key)
            if cached is not None:
                self._smoothing_cache.move_to_end(cache_key)
                smoothed_metric_values, scores, colors = cached
                return values, smoothed_metric_values, scores, colors, config

        structures = {
            "sentence": self.sentences,
            "paragraph": self.paragraphs,
            "chapter": self.chapters,
        }
        smoothed_metric_values: list[float] | None = None
        if config.domain == "normalized":
            scores = smooth_values(base_scores, config, structures)
        else:
            working_values = values
            if config.domain == "log":
                working_values = [
                    math.copysign(math.log1p(abs(value)), value)
                    for value in values
                ]
            smoothed_metric_values = smooth_values(working_values, config, structures)
            if config.domain == "log":
                smoothed_metric_values = [
                    math.copysign(math.expm1(abs(value)), value)
                    for value in smoothed_metric_values
                ]
            scores = [
                normalized_metric_value(
                    value,
                    self.metric,
                    self.scale,
                    color_scale.min_value,
                    color_scale.row_max_values[index],
                )
                for index, value in enumerate(smoothed_metric_values)
            ]

        if metric_palette(self.metric) == "black-white":
            scores = [max(0.0, min(1.0, value)) for value in scores]
        else:
            scores = [max(-1.0, min(1.0, value)) for value in scores]
        colors = [normalized_metric_color(value, self.metric) for value in scores]
        cached_result = (smoothed_metric_values, scores, colors)
        with self._mode_lock:
            self._smoothing_cache[cache_key] = cached_result
            self._smoothing_cache.move_to_end(cache_key)
            while len(self._smoothing_cache) > 8:
                self._smoothing_cache.popitem(last=False)
        return values, smoothed_metric_values, scores, colors, config

    def viewport(
        self,
        start: int,
        end: int,
        limit: int,
        class_discrimination: bool = True,
        frequency_basis: str = TOKEN_FREQUENCY_BASIS,
        smoothing: SmoothingConfig | None = None,
        pixels_per_occurrence: float | None = None,
    ) -> dict[str, object]:
        values, smoothed_values, display_scores, colors, resolved_smoothing = self._smoothed_view(
            class_discrimination,
            frequency_basis,
            smoothing,
            pixels_per_occurrence,
        )
        start = max(0, min(start, self.total_rows))
        end = max(start + 1, min(end, self.total_rows))
        visible_count = end - start
        limit = max(16, min(limit, 5000))

        if visible_count <= limit:
            samples = []
            for index in range(start, end):
                sample: dict[str, object] = {
                    "start": index,
                    "end": index + 1,
                    "color": _hex(colors[index]),
                    "word": self.words[index],
                    "wordClass": self.word_classes[index],
                    "metric": self.metric,
                    "metricValue": values[index],
                    "wordNumber": index + 1,
                    "chapter": self.chapters[index],
                    "paragraph": self.paragraphs[index],
                    "sentence": self.sentences[index],
                }
                if smoothed_values is not None:
                    sample["smoothedMetricValue"] = smoothed_values[index]
                if resolved_smoothing.method != "none":
                    sample["smoothedDisplayValue"] = display_scores[index]
                samples.append(sample)
            mode = "rows"
        else:
            samples = []
            step = visible_count / limit
            for sample_index in range(limit):
                bin_start = start + math.floor(sample_index * step)
                bin_end = start + math.floor((sample_index + 1) * step)
                if sample_index == limit - 1:
                    bin_end = end
                bin_end = max(bin_start + 1, min(bin_end, end))
                average_score = sum(display_scores[bin_start:bin_end]) / (bin_end - bin_start)
                samples.append(
                    {
                        "start": bin_start,
                        "end": bin_end,
                        "color": _hex(normalized_metric_color(average_score, self.metric)),
                    }
                )
            mode = "bins"

        return {
            "mode": mode,
            "start": start,
            "end": end,
            "totalRows": self.total_rows,
            "frequencyBasis": self._effective_frequency_basis(frequency_basis),
            "samples": samples,
            "smoothing": {
                "method": resolved_smoothing.method,
                "bandwidth": resolved_smoothing.bandwidth,
                "window": resolved_smoothing.window,
                "domain": resolved_smoothing.domain,
                "boundary": resolved_smoothing.boundary,
            },
            "segments": {
                key: [
                    {"start": max(segment.start, start), "end": min(segment.end, end), "value": segment.value}
                    for segment in self._visible_segments(key, start, end)
                ]
                for key in self._segments
            },
        }

    def summary(
        self,
        class_discrimination: bool = True,
        frequency_basis: str = TOKEN_FREQUENCY_BASIS,
    ) -> dict[str, object]:
        frequency_basis = self._effective_frequency_basis(frequency_basis)
        values, colors = self._values_and_colors(class_discrimination, frequency_basis)
        entry = self.entry
        total_words = len(self.rows)
        counts = Counter(self.word_classes)
        functional_words = counts.get("functional", 0)
        lexical_words = counts.get("semantic", 0)
        class_stats = _class_stats(values, self.word_classes)
        average_color = _average_color(colors, 0, len(colors)) if colors else (0, 0, 0)
        positive_values = [value for value in values if value > 0]
        negative_values = [value for value in values if value < 0]
        grayscale_average = (
            (sum(color[0] for color in colors) / len(colors)) / 255 * 1000
            if colors
            else 0
        )
        metadata = _book_metadata_for_entry(entry)
        return {
            "book": entry.get("book", ""),
            "mapType": entry.get("mapType", ""),
            "metric": self.metric,
            "frequencyBasis": frequency_basis,
            "palette": entry.get("palette", ""),
            "bibliographic": metadata,
            "wordCounts": {
                "total": total_words,
                "functional": functional_words,
                "lexical": lexical_words,
                "functionalRatio": functional_words / total_words if total_words else 0,
            },
            "frequency": {
                "classStats": class_stats,
                "grayscaleAverage0To1000": grayscale_average,
            },
            "deviation": {
                "maxPositive": max(positive_values) if positive_values else 0,
                "maxNegative": min(negative_values) if negative_values else 0,
                "average": sum(values) / len(values) if values else 0,
                "averageRgb": {
                    "red": average_color[0],
                    "green": average_color[1],
                    "blue": average_color[2],
                },
            },
        }

    def _visible_segments(self, key: str, start: int, end: int) -> list[Segment]:
        segments = self._segments[key]
        starts = self._segment_starts[key]
        index = max(0, bisect_left(starts, start) - 1)
        visible: list[Segment] = []
        while index < len(segments):
            segment = segments[index]
            if segment.start >= end:
                break
            if segment.end > start:
                visible.append(segment)
            index += 1
        return visible


def _parse_int(value: str | None, fallback: int) -> int:
    if value is None or value == "":
        return fallback
    try:
        return int(float(value))
    except ValueError:
        return fallback


def _class_stats(values: list[float], word_classes: list[str]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[float]] = {}
    for value, word_class in zip(values, word_classes):
        label = "lexical" if word_class == "semantic" else word_class or "unknown"
        grouped.setdefault(label, []).append(value)
    return {
        label: {
            "min": min(items),
            "max": max(items),
            "average": sum(items) / len(items),
        }
        for label, items in grouped.items()
        if items
    }


def _book_metadata_for_entry(entry: dict[str, object]) -> dict[str, str]:
    metadata = _load_book_metadata()
    book = str(entry.get("book", ""))
    candidate_keys = _metadata_key_variants(_slug_key(book))
    csv_path = str(entry.get("csvPath", ""))
    if csv_path:
        candidate_keys.extend(
            _metadata_key_variants(_slug_key(Path(csv_path).stem.replace("_occurrences", "")))
        )
    selected: dict[str, str] = {}
    for key in candidate_keys:
        if key in metadata:
            selected = metadata[key]
            break

    edition = _infer_edition(entry)
    return {
        "title": str(selected.get("title") or book or "Unknown"),
        "author": str(selected.get("author") or "Unknown"),
        "publicationYear": str(selected.get("publication_year") or "Unknown"),
        "edition": edition,
    }


def _metadata_key_variants(key: str) -> list[str]:
    variants = [key]
    if "_s_" in key:
        variants.append(key.replace("_s_", "s_"))
    if "s_" in key:
        variants.append(key.replace("s_", "_s_", 1))
    return variants


def _infer_edition(entry: dict[str, object]) -> str:
    haystack = " ".join(
        str(entry.get(key, ""))
        for key in ("book", "title", "metadataPath", "csvPath")
    ).lower()
    if "gutenberg" in haystack:
        return "Project Gutenberg"
    if "sorcerer" in haystack or "us version" in haystack:
        return "US version"
    if "philosopher" in haystack or "uk version" in haystack:
        return "UK version"
    return "Unknown"


def _build_segments(values: list[int]) -> list[Segment]:
    if not values:
        return []
    segments: list[Segment] = []
    start = 0
    current = values[0]
    for index, value in enumerate(values[1:], start=1):
        if value != current:
            segments.append(Segment(start, index, current))
            start = index
            current = value
    segments.append(Segment(start, len(values), current))
    return segments


def _has_valid_chapter_structure(segments: list[Segment]) -> bool:
    chapter_values = {segment.value for segment in segments if segment.value > 0}
    return len(chapter_values) > 1


def _hex(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def _average_color(colors: list[tuple[int, int, int]], start: int, end: int) -> tuple[int, int, int]:
    count = max(1, end - start)
    red = green = blue = 0
    for color in colors[start:end]:
        red += color[0]
        green += color[1]
        blue += color[2]
    return round(red / count), round(green / count), round(blue / count)


class ViewerState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._maps: dict[str, dict[str, object]] = {}
        self._map_load_keys: dict[str, MapLoadKey] = {}
        self._loaded: dict[str, LoadedMap] = {}
        self._loading: dict[str, tuple[MapLoadKey, Future[LoadedMap]]] = {}
        self.refresh()

    def refresh(self) -> list[dict[str, object]]:
        maps = discover_maps()
        new_maps = {str(entry["id"]): entry for entry in maps}
        new_load_keys = {
            map_id: _map_load_key(entry)
            for map_id, entry in new_maps.items()
        }
        with self._lock:
            preserved_loaded: dict[str, LoadedMap] = {}
            for map_id, loaded in self._loaded.items():
                if self._map_load_keys.get(map_id) != new_load_keys.get(map_id):
                    continue
                new_entry = new_maps[map_id]
                for field in ("totalRows", "minValue", "maxValue", "maxAbsValue"):
                    if field in loaded.entry:
                        new_entry[field] = loaded.entry[field]
                loaded.entry = new_entry
                preserved_loaded[map_id] = loaded

            self._loading = {
                map_id: pending
                for map_id, pending in self._loading.items()
                if new_load_keys.get(map_id) == pending[0]
            }
            self._maps = new_maps
            self._map_load_keys = new_load_keys
            self._loaded = preserved_loaded
        return maps

    def maps(self) -> list[dict[str, object]]:
        with self._lock:
            return list(self._maps.values())

    def load(self, map_id: str) -> LoadedMap | None:
        with self._lock:
            entry = self._maps.get(map_id)
            if entry is None:
                return None
            loaded = self._loaded.get(map_id)
            if loaded is not None:
                return loaded

            load_key = self._map_load_keys[map_id]
            pending = self._loading.get(map_id)
            if pending is None or pending[0] != load_key:
                future: Future[LoadedMap] = Future()
                self._loading[map_id] = (load_key, future)
                entry_snapshot = dict(entry)
                owns_load = True
            else:
                future = pending[1]
                entry_snapshot = {}
                owns_load = False

        if not owns_load:
            return future.result()

        try:
            loaded = LoadedMap(entry_snapshot)
        except BaseException as exc:
            with self._lock:
                if self._loading.get(map_id) == (load_key, future):
                    del self._loading[map_id]
            future.set_exception(exc)
            raise

        with self._lock:
            if self._loading.get(map_id) == (load_key, future):
                if self._map_load_keys.get(map_id) == load_key:
                    current_entry = self._maps[map_id]
                    for field in ("totalRows", "minValue", "maxValue", "maxAbsValue"):
                        if field in loaded.entry:
                            current_entry[field] = loaded.entry[field]
                    loaded.entry = current_entry
                    self._loaded[map_id] = loaded
                del self._loading[map_id]
        future.set_result(loaded)
        return loaded


STATE = ViewerState()


class ViewerHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/manage/maps":
            _json_response(self, manage_maps_payload())
            return
        if path.startswith("/api/manage/maps/") and path.endswith("/export"):
            self._handle_map_export(path, parsed.query)
            return
        if path == "/api/maps":
            _json_response(self, {"maps": STATE.refresh()})
            return
        if path == "/api/generation-options":
            _json_response(self, generation_options_payload())
            return
        if path == "/api/word-stats":
            _json_response(self, {"files": discover_word_stat_files()})
            return
        if path.startswith("/api/word-stats/"):
            self._handle_word_stats_file(path)
            return
        if path.startswith("/api/maps/") and path.endswith("/summary"):
            self._handle_summary(path, parsed.query)
            return
        if path.startswith("/api/maps/") and path.endswith("/viewport"):
            self._handle_viewport(path, parsed.query)
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/generate":
            self._handle_generate()
            return
        if path.startswith("/api/manage/maps/"):
            self._handle_manage_map_action(path)
            return
        _json_response(self, {"error": "Endpoint not found."}, 404)

    def _handle_generate(self) -> None:
        try:
            payload = self._read_json_body()
            result = generate_maps_from_payload(payload)
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, 400)
            return
        except RuntimeError as exc:
            _json_response(self, {"error": str(exc)}, 500)
            return
        except Exception as exc:
            _json_response(self, {"error": f"Generation failed: {exc}"}, 500)
            return
        _json_response(self, result)

    def _handle_manage_map_action(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 5 or parts[:3] != ["api", "manage", "maps"]:
            _json_response(self, {"error": "Invalid map management endpoint."}, 404)
            return
        map_id = parts[3]
        action = parts[4]
        try:
            payload = self._read_json_body()
            if action == "rename":
                result = rename_map_entry(
                    map_id,
                    str(payload.get("book") or ""),
                    str(payload.get("mapType") or ""),
                )
            elif action == "exclude":
                result = set_map_excluded(map_id, bool(payload.get("excluded")))
            elif action == "duplicate":
                result = duplicate_map_entry(map_id)
            else:
                _json_response(self, {"error": "Unknown map management action."}, 404)
                return
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, 400)
            return
        except Exception as exc:
            _json_response(self, {"error": f"Map management failed: {exc}"}, 500)
            return
        _json_response(self, {"map": result, **manage_maps_payload()})

    def _handle_map_export(self, path: str, query: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 5 or parts[:3] != ["api", "manage", "maps"] or parts[4] != "export":
            _json_response(self, {"error": "Invalid map export endpoint."}, 404)
            return
        params = parse_qs(query)
        export_format = params.get("format", [""])[0]
        try:
            exported = export_map_entry(parts[3], export_format)
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, 400)
            return
        except Exception as exc:
            _json_response(self, {"error": f"Export failed: {exc}"}, 500)
            return

        if exported.path is not None:
            self._send_file(exported.path, exported.content_type, exported.filename)
            return
        self._send_bytes(exported.data or b"", exported.content_type, exported.filename)

    def _handle_word_stats_file(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 3:
            _json_response(self, {"error": "Invalid word stats endpoint."}, 404)
            return
        csv_path = word_stat_file_by_id(parts[2])
        if csv_path is None or not csv_path.exists():
            _json_response(self, {"error": "Word stats CSV not found."}, 404)
            return
        _json_response(
            self,
            {
                "path": _relative(csv_path).replace("\\", "/"),
                "name": _human_label(csv_path.stem),
                "content": csv_path.read_text(encoding="utf-8-sig"),
            },
        )

    def _read_json_body(self) -> dict[str, object]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid request body.") from exc
        if content_length <= 0:
            raise ValueError("Missing request body.")
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON request body.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Invalid generation request.")
        return payload

    def _send_bytes(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _handle_summary(self, path: str, query: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            _json_response(self, {"error": "Invalid summary endpoint."}, 404)
            return

        loaded = STATE.load(parts[2])
        if loaded is None:
            _json_response(self, {"error": "Map not found."}, 404)
            return

        params = parse_qs(query)
        class_discrimination = _parse_query_bool(params, "classDiscrimination", True)
        try:
            frequency_basis = normalize_frequency_basis(
                _parse_query_text(params, "frequencyBasis", TOKEN_FREQUENCY_BASIS)
            )
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, 400)
            return
        _json_response(
            self,
            loaded.summary(
                class_discrimination=class_discrimination,
                frequency_basis=frequency_basis,
            ),
        )

    def _handle_viewport(self, path: str, query: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            _json_response(self, {"error": "Invalid viewport endpoint."}, 404)
            return

        loaded = STATE.load(parts[2])
        if loaded is None:
            _json_response(self, {"error": "Map not found."}, 404)
            return

        params = parse_qs(query)
        start = _parse_query_int(params, "start", 0)
        end = _parse_query_int(params, "end", min(loaded.total_rows, 2000))
        limit = _parse_query_int(params, "limit", 1200)
        class_discrimination = _parse_query_bool(params, "classDiscrimination", True)
        pixels_per_occurrence = _parse_query_float(params, "pixelsPerOccurrence", 1.0)
        try:
            frequency_basis = normalize_frequency_basis(
                _parse_query_text(params, "frequencyBasis", TOKEN_FREQUENCY_BASIS)
            )
            smoothing = config_from_query(params)
        except ValueError as exc:
            _json_response(self, {"error": str(exc)}, 400)
            return
        _json_response(
            self,
            loaded.viewport(
                start,
                end,
                limit,
                class_discrimination=class_discrimination,
                frequency_basis=frequency_basis,
                smoothing=smoothing,
                pixels_per_occurrence=pixels_per_occurrence,
            ),
        )

    def _serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        relative = Path(path.lstrip("/"))
        target = (STATIC_DIR / relative).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(404)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _parse_query_int(params: dict[str, list[str]], key: str, fallback: int) -> int:
    values = params.get(key)
    if not values:
        return fallback
    try:
        return int(float(values[0]))
    except ValueError:
        return fallback


def _parse_query_float(params: dict[str, list[str]], key: str, fallback: float) -> float:
    values = params.get(key)
    if not values:
        return fallback
    try:
        return float(values[0])
    except ValueError:
        return fallback


def _parse_query_bool(params: dict[str, list[str]], key: str, fallback: bool) -> bool:
    values = params.get(key)
    if not values:
        return fallback
    return values[0].lower() not in {"0", "false", "no", "off"}


def _parse_query_text(params: dict[str, list[str]], key: str, fallback: str) -> str:
    values = params.get(key)
    if not values:
        return fallback
    return values[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Bookspine Alpha 0.2.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the viewer URL in the default browser after the server starts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Bookspine Alpha 0.2 running at {url}")
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
