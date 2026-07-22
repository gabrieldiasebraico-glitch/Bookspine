from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw

from vocab_mapper.metrics import (
    BOOK_FREQ,
    metric_definition,
    resolve_metric_name,
)
from vocab_mapper.viewer_rendering import (
    BLACK_WHITE_METRICS,
    DIVERGING_METRICS,
    MAGENTA_WHITE_GREEN_METRICS,
    metric_color,
    metric_color_scale,
    metric_palette,
    metric_values,
)

BIGTIFF_SUFFIXES = {".tif", ".tiff"}
ROWS_PER_STRIP = 256


def read_occurrence_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


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
    color_scale = metric_color_scale(
        rows,
        values,
        metric,
        class_discrimination,
    )

    output_png.parent.mkdir(parents=True, exist_ok=True)
    if output_png.suffix.lower() in BIGTIFF_SUFFIXES:
        save_bigtiff_line_map(
            output_png,
            values,
            color_scale.row_max_values,
            width,
            metric,
            scale,
            color_scale.min_value,
            color_scale.max_value,
            color_scale.max_abs_value,
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
                    color_scale.min_value,
                    color_scale.row_max_values[y],
                    color_scale.max_abs_value,
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
        "min_value": color_scale.min_value,
        "max_value": color_scale.max_value,
        "max_abs_value": color_scale.max_abs_value,
        "frequency_scale_reference": (
            color_scale.reference if metric in BLACK_WHITE_METRICS else ""
        ),
        "negative_scale_min": color_scale.min_value if color_scale.min_value < 0 else 0,
        "positive_scale_max": color_scale.max_value if color_scale.max_value > 0 else 0,
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
