from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vocab_mapper.plot_visual_map import read_occurrence_rows
from vocab_mapper.viewer_rendering import (
    BLACK_WHITE_METRICS,
    metric_color,
    metric_color_scale,
    metric_palette,
    metric_values,
)
from vocab_mapper.metrics import metric_definition, resolve_metric_name


BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (120, 120, 120)


def nice_interval(max_value: int, target_ticks: int = 12) -> int:
    if max_value <= target_ticks:
        return 1
    raw = max_value / target_ticks
    exponent = math.floor(math.log10(raw))
    base = 10**exponent
    for multiplier in (1, 2, 5, 10):
        interval = multiplier * base
        if interval >= raw:
            return int(interval)
    return int(10 * base)


def chapter_starts(rows: list[dict[str, str]]) -> list[tuple[int, int]]:
    starts: list[tuple[int, int]] = []
    previous_chapter: str | None = None
    for row in rows:
        chapter = row.get("chapter_number", "")
        if chapter != previous_chapter:
            try:
                starts.append((int(chapter), int(row["word_number"])))
            except ValueError:
                pass
            previous_chapter = chapter
    return starts


def load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def render_annotated_map(
    input_csv: Path,
    output_path: Path,
    metric: str,
    map_width: int = 2000,
    left_margin: int = 130,
    right_margin: int = 90,
    scale: str = "linear",
) -> dict[str, float | int | str | list[dict[str, int]]]:
    metric = resolve_metric_name(metric)
    rows = read_occurrence_rows(input_csv)
    values = metric_values(rows, metric)
    color_scale = metric_color_scale(rows, values, metric, class_discrimination=True)
    height = len(values)
    total_width = left_margin + map_width + right_margin

    image = Image.new("RGB", (total_width, height), BLACK)
    draw = ImageDraw.Draw(image)
    label_font = load_font(12)
    small_font = load_font(10)

    map_x0 = left_margin
    map_x1 = left_margin + map_width - 1
    right_x0 = left_margin + map_width

    for y, value in enumerate(values):
        draw.line(
            (map_x0, y, map_x1, y),
            fill=metric_color(
                value,
                metric,
                scale,
                color_scale.min_value,
                color_scale.row_max_values[y],
                color_scale.max_abs_value,
            ),
        )

    draw.line((map_x0 - 1, 0, map_x0 - 1, height - 1), fill=GRAY)
    draw.line((right_x0, 0, right_x0, height - 1), fill=GRAY)

    major_interval = nice_interval(height)
    minor_interval = max(1, major_interval // 2)

    for word_number in range(0, height + 1, minor_interval):
        y = min(max(word_number - 1, 0), height - 1)
        tick_len = 9 if word_number % major_interval == 0 else 5
        draw.line((map_x0 - tick_len, y, map_x0 - 1, y), fill=WHITE)

    for word_number in range(0, height + 1, major_interval):
        y = min(max(word_number - 1, 0), height - 1)
        label = str(word_number)
        bbox = draw.textbbox((0, 0), label, font=label_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        y_text = min(max(y - text_h // 2, 0), max(height - text_h, 0))
        draw.text((map_x0 - 14 - text_w, y_text), label, fill=WHITE, font=label_font)

    chapter_metadata: list[dict[str, int]] = []
    for chapter_number, word_number in chapter_starts(rows):
        y = min(max(word_number - 1, 0), height - 1)
        draw.line((right_x0 + 1, y, right_x0 + 22, y), fill=WHITE)
        label = f"Ch {chapter_number}"
        bbox = draw.textbbox((0, 0), label, font=small_font)
        text_h = bbox[3] - bbox[1]
        y_text = min(max(y - text_h // 2, 0), max(height - text_h, 0))
        draw.text((right_x0 + 27, y_text), label, fill=WHITE, font=small_font)
        chapter_metadata.append({"chapter_number": chapter_number, "word_number": word_number})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)

    metadata: dict[str, float | int | str | list[dict[str, int]]] = {
        "input_csv": str(input_csv),
        "output_image": str(output_path),
        "metric": metric,
        "definition": metric_definition(metric),
        "map_width_px": map_width,
        "left_margin_px": left_margin,
        "right_margin_px": right_margin,
        "total_width_px": total_width,
        "height_px": height,
        "word_scale_major_interval": major_interval,
        "word_scale_minor_interval": minor_interval,
        "chapter_ticks": chapter_metadata,
        "palette": metric_palette(metric),
        "frequency_scale_reference": (
            color_scale.reference if metric in BLACK_WHITE_METRICS else ""
        ),
    }
    output_path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a visual map with side scales.")
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_image", type=Path)
    parser.add_argument("--metric", default="book_avg_dev")
    parser.add_argument("--width", type=int, default=2000)
    parser.add_argument("--left-margin", type=int, default=130)
    parser.add_argument("--right-margin", type=int, default=90)
    parser.add_argument("--scale", choices=("linear", "log"), default="linear")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = render_annotated_map(
        args.input_csv,
        args.output_image,
        args.metric,
        args.width,
        args.left_margin,
        args.right_margin,
        args.scale,
    )
    print(
        "Wrote {output_image} ({total_width_px} x {height_px}px), metric={metric}".format(
            **metadata
        )
    )


if __name__ == "__main__":
    main()
