from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw

from vocab_mapper.metric_values import row_metric_values
from vocab_mapper.metrics import (
    BOOK_FREQ,
    METRIC_SPECS,
    is_ngram_frequency_metric,
    metric_column_candidates,
    metric_definition,
    resolve_metric_name,
)

RED = (220, 0, 0)
WHITE = (255, 255, 255)
BLUE = (0, 68, 220)
MAGENTA = (255, 0, 255)
GREEN = (0, 160, 0)

METRIC_DEFINITIONS = {
    spec.name: spec.definition
    for spec in METRIC_SPECS
}

NGRAM_FREQUENCY_METRICS = {
    spec.name
    for spec in METRIC_SPECS
    if spec.ngram_frequency
}

BLACK_WHITE_METRICS = {
    spec.name
    for spec in METRIC_SPECS
    if spec.palette == "black-white"
}
MAGENTA_WHITE_GREEN_METRICS: set[str] = set()
DIVERGING_METRICS = {
    spec.name
    for spec in METRIC_SPECS
    if spec.palette in {"red-white-blue", "magenta-white-green"}
}
BIGTIFF_SUFFIXES = {".tif", ".tiff"}
ROWS_PER_STRIP = 256


def read_occurrence_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def scale_value(value: float, max_value: float, scale: str) -> float:
    if max_value <= 0:
        return 0
    if scale == "linear":
        return value / max_value
    if scale == "log":
        return math.log1p(value) / math.log1p(max_value)
    raise ValueError(f"Unsupported scale: {scale}")


def grayscale_color(value: float, max_value: float, scale: str) -> tuple[int, int, int]:
    scaled = max(0, min(1, scale_value(value, max_value, scale)))
    channel = round(scaled * 255)
    return channel, channel, channel


def interpolate_color(
    start: tuple[int, int, int], end: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    amount = max(0, min(1, amount))
    return tuple(round(s + (e - s) * amount) for s, e in zip(start, end))


def diverging_color(value: float, min_value: float, max_value: float) -> tuple[int, int, int]:
    return signed_color(value, min_value, max_value, RED, BLUE)


def magenta_white_green_color(
    value: float, min_value: float, max_value: float
) -> tuple[int, int, int]:
    return signed_color(value, min_value, max_value, MAGENTA, GREEN)


def signed_color(
    value: float,
    min_value: float,
    max_value: float,
    negative_color: tuple[int, int, int],
    positive_color: tuple[int, int, int],
) -> tuple[int, int, int]:
    if value == 0:
        return WHITE
    if value < 0:
        if min_value >= 0:
            return WHITE
        scaled = min(abs(value) / abs(min_value), 1)
        return interpolate_color(WHITE, negative_color, scaled)
    if max_value <= 0:
        return WHITE
    scaled = min(value / max_value, 1)
    return interpolate_color(WHITE, positive_color, scaled)


def metric_palette(metric: str) -> str:
    metric = resolve_metric_name(metric)
    if metric in MAGENTA_WHITE_GREEN_METRICS:
        return "magenta-white-green"
    if metric in DIVERGING_METRICS:
        return "red-white-blue"
    return "black-white"


def metric_zero_color(metric: str) -> str:
    metric = resolve_metric_name(metric)
    return "white" if metric in DIVERGING_METRICS else "black"


def metric_negative_color(metric: str) -> str:
    metric = resolve_metric_name(metric)
    if metric in MAGENTA_WHITE_GREEN_METRICS:
        return "magenta"
    return "red" if metric in DIVERGING_METRICS else ""


def metric_positive_color(metric: str) -> str:
    metric = resolve_metric_name(metric)
    if metric in MAGENTA_WHITE_GREEN_METRICS:
        return "green"
    return "blue" if metric in DIVERGING_METRICS else "white"


def row_float(row: dict[str, str], column: str) -> float | None:
    raw_value = row.get(column, "")
    if raw_value == "":
        return None
    return float(raw_value)


def ngram_the_frequency(rows: list[dict[str, str]], metric: str = "fic_ngram_total_freq") -> float:
    candidates = metric_column_candidates(metric)
    for row in rows:
        if row.get("normalized_word", "").lower() == "the":
            for candidate in candidates:
                value = row_float(row, candidate)
                if value is not None:
                    return value
    raise ValueError(
        f"Cannot render {metric}: the CSV has no {metric} value for normalized_word 'the'. "
        "Regenerate the occurrence CSV with the matching Ngram frequency file that includes 'the'."
    )


def metric_values(
    rows: list[dict[str, str]],
    metric: str,
    class_discrimination: bool = True,
) -> list[float]:
    metric = resolve_metric_name(metric)
    return row_metric_values(rows, metric, class_discrimination)


def metric_color_maxima(
    rows: list[dict[str, str]],
    values: list[float],
    metric: str,
    max_value: float,
    class_discrimination: bool,
) -> list[float]:
    metric = resolve_metric_name(metric)
    if metric != BOOK_FREQ or not class_discrimination:
        return [max_value] * len(values)

    max_by_class: dict[str, float] = {}
    for row, value in zip(rows, values):
        word_class = row.get("word_class", "")
        max_by_class[word_class] = max(value, max_by_class.get(word_class, 0))
    return [max_by_class.get(row.get("word_class", ""), max_value) for row in rows]


def metric_color(
    value: float,
    metric: str,
    scale: str,
    min_value: float,
    max_value: float,
    max_abs_value: float,
) -> tuple[int, int, int]:
    metric = resolve_metric_name(metric)
    if metric in MAGENTA_WHITE_GREEN_METRICS:
        return magenta_white_green_color(value, min_value, max_value)
    if metric in DIVERGING_METRICS:
        return diverging_color(value, min_value, max_value)
    return grayscale_color(value, max_value, scale)


def pack_bigtiff_value(field_type: int, values: list[int] | bytes, data_offset: int) -> bytes:
    if field_type == 3:
        raw = b"".join(struct.pack("<H", value) for value in values)  # type: ignore[arg-type]
    elif field_type == 4:
        raw = b"".join(struct.pack("<I", value) for value in values)  # type: ignore[arg-type]
    elif field_type == 16:
        raw = b"".join(struct.pack("<Q", value) for value in values)  # type: ignore[arg-type]
    elif field_type == 2:
        raw = values  # type: ignore[assignment]
    else:
        raise ValueError(f"Unsupported BigTIFF field type: {field_type}")

    if len(raw) <= 8:
        return raw.ljust(8, b"\x00")
    return struct.pack("<Q", data_offset)


def bigtiff_entry(
    tag: int, field_type: int, count: int, value_or_offset: bytes
) -> bytes:
    return struct.pack("<HHQ", tag, field_type, count) + value_or_offset


def align_offset(offset: int, alignment: int = 8) -> int:
    remainder = offset % alignment
    return offset if remainder == 0 else offset + alignment - remainder


def save_bigtiff_line_map(
    output_path: Path,
    values: list[float],
    row_max_values: list[float],
    width: int,
    metric: str,
    scale: str,
    min_value: float,
    max_value: float,
    max_abs_value: float,
) -> None:
    height = len(values)
    is_grayscale = metric in BLACK_WHITE_METRICS
    samples_per_pixel = 1 if is_grayscale else 3
    bytes_per_pixel = samples_per_pixel
    row_byte_count = width * bytes_per_pixel
    strip_count = math.ceil(height / ROWS_PER_STRIP) if height else 0
    image_data_offset = 16

    strip_offsets: list[int] = []
    strip_byte_counts: list[int] = []
    cursor = image_data_offset
    for strip_index in range(strip_count):
        rows_in_strip = min(ROWS_PER_STRIP, height - strip_index * ROWS_PER_STRIP)
        byte_count = rows_in_strip * row_byte_count
        strip_offsets.append(cursor)
        strip_byte_counts.append(byte_count)
        cursor += byte_count

    ifd_offset = align_offset(cursor)
    entries_count = 10
    ifd_size = 8 + entries_count * 20 + 8
    extra_offset = align_offset(ifd_offset + ifd_size)

    bits_per_sample = [8] if is_grayscale else [8, 8, 8]
    bits_per_sample_offset = extra_offset
    extra_offset = align_offset(bits_per_sample_offset + 6)
    strip_offsets_offset = extra_offset
    extra_offset = align_offset(strip_offsets_offset + len(strip_offsets) * 8)
    strip_byte_counts_offset = extra_offset

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as image_file:
        image_file.write(b"II")
        image_file.write(struct.pack("<H", 43))
        image_file.write(struct.pack("<H", 8))
        image_file.write(struct.pack("<H", 0))
        image_file.write(struct.pack("<Q", ifd_offset))

        for strip_index in range(strip_count):
            start = strip_index * ROWS_PER_STRIP
            end = min(start + ROWS_PER_STRIP, height)
            strip = bytearray()
            for index, value in enumerate(values[start:end], start=start):
                color = metric_color(
                    value,
                    metric,
                    scale,
                    min_value,
                    row_max_values[index],
                    max_abs_value,
                )
                if is_grayscale:
                    strip.extend(bytes([color[0]]) * width)
                else:
                    strip.extend(bytes(color) * width)
            image_file.write(strip)

        image_file.write(b"\x00" * (ifd_offset - image_file.tell()))

        entries = [
            bigtiff_entry(256, 4, 1, pack_bigtiff_value(4, [width], 0)),
            bigtiff_entry(257, 4, 1, pack_bigtiff_value(4, [height], 0)),
            bigtiff_entry(258, 3, 3, pack_bigtiff_value(3, bits_per_sample, bits_per_sample_offset)),
            bigtiff_entry(259, 3, 1, pack_bigtiff_value(3, [1], 0)),
            bigtiff_entry(262, 3, 1, pack_bigtiff_value(3, [1 if is_grayscale else 2], 0)),
            bigtiff_entry(273, 16, len(strip_offsets), pack_bigtiff_value(16, strip_offsets, strip_offsets_offset)),
            bigtiff_entry(277, 3, 1, pack_bigtiff_value(3, [samples_per_pixel], 0)),
            bigtiff_entry(278, 4, 1, pack_bigtiff_value(4, [ROWS_PER_STRIP], 0)),
            bigtiff_entry(
                279,
                16,
                len(strip_byte_counts),
                pack_bigtiff_value(16, strip_byte_counts, strip_byte_counts_offset),
            ),
            bigtiff_entry(284, 3, 1, pack_bigtiff_value(3, [1], 0)),
        ]

        image_file.write(struct.pack("<Q", len(entries)))
        for entry in entries:
            image_file.write(entry)
        image_file.write(struct.pack("<Q", 0))

        image_file.write(b"\x00" * (bits_per_sample_offset - image_file.tell()))
        for value in bits_per_sample:
            image_file.write(struct.pack("<H", value))
        image_file.write(b"\x00" * (strip_offsets_offset - image_file.tell()))
        for value in strip_offsets:
            image_file.write(struct.pack("<Q", value))
        image_file.write(b"\x00" * (strip_byte_counts_offset - image_file.tell()))
        for value in strip_byte_counts:
            image_file.write(struct.pack("<Q", value))


def render_frequency_map(
    input_csv: Path,
    output_png: Path,
    width: int,
    scale: str,
    metric: str = BOOK_FREQ,
    class_discrimination: bool = True,
) -> dict[str, float | int | str]:
    metric = resolve_metric_name(metric)
    rows = read_occurrence_rows(input_csv)
    values = metric_values(rows, metric, class_discrimination=class_discrimination)
    height = len(values)
    max_value = (
        ngram_the_frequency(rows, metric)
        if is_ngram_frequency_metric(metric)
        else max(values) if values else 0
    )
    min_value = min(values) if values else 0
    max_abs_value = max((abs(value) for value in values), default=0)
    row_max_values = metric_color_maxima(
        rows,
        values,
        metric,
        max_value,
        class_discrimination,
    )

    output_png.parent.mkdir(parents=True, exist_ok=True)
    if output_png.suffix.lower() in BIGTIFF_SUFFIXES:
        save_bigtiff_line_map(
            output_png,
            values,
            row_max_values,
            width,
            metric,
            scale,
            min_value,
            max_value,
            max_abs_value,
        )
    else:
        image = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        for y, value in enumerate(values):
            draw.line(
                (0, y, width - 1, y),
                fill=metric_color(
                    value,
                    metric,
                    scale,
                    min_value,
                    row_max_values[y],
                    max_abs_value,
                ),
            )
        image.save(output_png)

    metadata = {
        "input_csv": str(input_csv),
        "output_png": str(output_png),
        "metric": metric,
        "definition": metric_definition(metric),
        "width_px": width,
        "height_px": height,
        "format": "BigTIFF" if output_png.suffix.lower() in BIGTIFF_SUFFIXES else "PNG",
        "scale": scale,
        "class_discrimination": class_discrimination,
        "palette": metric_palette(metric),
        "zero_color": metric_zero_color(metric),
        "negative_color": metric_negative_color(metric),
        "positive_color": metric_positive_color(metric),
        "min_value": min_value,
        "max_value": max_value,
        "max_abs_value": max_abs_value,
        "ngram_scale_top_word": "the" if is_ngram_frequency_metric(metric) else "",
        "negative_scale_min": min_value if min_value < 0 else 0,
        "positive_scale_max": max_value if max_value > 0 else 0,
    }
    output_png.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a visual map where each word occurrence is a 1-pixel-high "
            "horizontal line."
        )
    )
    parser.add_argument("input_csv", type=Path, help="Occurrence CSV produced by prepare_csv.")
    parser.add_argument("output_png", type=Path, help="PNG image path to write.")
    parser.add_argument(
        "--width",
        type=int,
        default=2000,
        help="Image width in pixels. Default: 2000.",
    )
    parser.add_argument(
        "--scale",
        choices=("linear", "log"),
        default="linear",
        help="Color scaling for non-diverging positive metrics. Default: linear.",
    )
    parser.add_argument(
        "--metric",
        default=BOOK_FREQ,
        help=(
            "Metric to map. Use book_freq for count(word)/class-total words, "
            "or a numeric metric such as book_avg_dev, fic_ngram_total_freq, "
            "or fic_ngram_total_med_dev."
        ),
    )
    parser.add_argument(
        "--no-class-discrimination",
        action="store_true",
        help="Use all words together instead of functional/semantic class normalization.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        metadata = render_frequency_map(
            args.input_csv,
            args.output_png,
            args.width,
            args.scale,
            args.metric,
            class_discrimination=not args.no_class_discrimination,
        )
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}") from exc
    print(
        "Wrote {output_png} ({width_px} x {height_px}px), metric={metric}, "
        "palette={palette}, min={min_value}, max={max_value}".format(**metadata)
    )


if __name__ == "__main__":
    main()
