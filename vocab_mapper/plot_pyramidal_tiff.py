from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import tifffile

from vocab_mapper.metrics import (
    BOOK_FREQ,
    metric_definition,
    resolve_metric_name,
)
from vocab_mapper.plot_visual_map import read_occurrence_rows
from vocab_mapper.viewer_rendering import (
    BLACK_WHITE_METRICS,
    metric_color,
    metric_color_scale,
    metric_palette,
    metric_values,
)


TILE_SIZE = 256


def values_to_colors(
    values: list[float],
    row_max_values: list[float],
    metric: str,
    scale: str,
    min_value: float,
    max_value: float,
    max_abs_value: float,
) -> np.ndarray:
    metric = resolve_metric_name(metric)
    if metric in BLACK_WHITE_METRICS:
        colors = np.empty((len(values),), dtype=np.uint8)
        for index, value in enumerate(values):
            colors[index] = metric_color(
                value, metric, scale, min_value, row_max_values[index], max_abs_value
            )[0]
        return colors

    colors = np.empty((len(values), 3), dtype=np.uint8)
    for index, value in enumerate(values):
        colors[index] = metric_color(
            value,
            metric,
            scale,
            min_value,
            row_max_values[index],
            max_abs_value,
        )
    return colors


def downsample_row_colors(row_colors: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return row_colors

    usable = (len(row_colors) // factor) * factor
    if row_colors.ndim == 1:
        main = row_colors[:usable].reshape(-1, factor).mean(axis=1)
    else:
        main = row_colors[:usable].reshape(-1, factor, 3).mean(axis=1)

    if usable < len(row_colors):
        if row_colors.ndim == 1:
            tail = np.array([row_colors[usable:].mean()])
        else:
            tail = row_colors[usable:].mean(axis=0, keepdims=True)
        main = np.concatenate([main, tail], axis=0)
    return np.rint(main).astype(np.uint8)


def tile_iterator(
    row_colors: np.ndarray,
    width: int,
    tile_size: int,
    rgb: bool,
):
    height = len(row_colors)
    for tile_y in range(0, height, tile_size):
        rows = min(tile_size, height - tile_y)
        for tile_x in range(0, width, tile_size):
            cols = min(tile_size, width - tile_x)
            if rgb:
                tile = np.zeros((tile_size, tile_size, 3), dtype=np.uint8)
                tile[:rows, :cols, :] = row_colors[tile_y : tile_y + rows, None, :]
            else:
                tile = np.zeros((tile_size, tile_size), dtype=np.uint8)
                tile[:rows, :cols] = row_colors[tile_y : tile_y + rows, None]
            yield tile


def pyramid_factors(width: int, height: int) -> list[int]:
    factors: list[int] = []
    factor = 2
    while math.ceil(width / factor) >= 128 or math.ceil(height / factor) >= 128:
        factors.append(factor)
        factor *= 2
    return factors


def write_pyramidal_tiff(
    output_path: Path,
    row_colors: np.ndarray,
    width: int,
    metric: str,
    scale: str,
    compression: str,
) -> dict[str, int | str | list[int]]:
    metric = resolve_metric_name(metric)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    height = len(row_colors)
    rgb = row_colors.ndim == 2
    factors = pyramid_factors(width, height)
    photometric = "rgb" if rgb else "minisblack"
    shape = (height, width, 3) if rgb else (height, width)
    dtype = np.uint8

    with tifffile.TiffWriter(output_path, bigtiff=True) as writer:
        writer.write(
            tile_iterator(row_colors, width, TILE_SIZE, rgb),
            shape=shape,
            dtype=dtype,
            tile=(TILE_SIZE, TILE_SIZE),
            photometric=photometric,
            compression=compression,
            subifds=len(factors),
            metadata=None,
            description=f"{metric}; {metric_definition(metric)}",
        )

        for factor in factors:
            level_colors = downsample_row_colors(row_colors, factor)
            level_width = math.ceil(width / factor)
            level_height = len(level_colors)
            level_shape = (
                (level_height, level_width, 3) if rgb else (level_height, level_width)
            )
            writer.write(
                tile_iterator(level_colors, level_width, TILE_SIZE, rgb),
                shape=level_shape,
                dtype=dtype,
                tile=(TILE_SIZE, TILE_SIZE),
                photometric=photometric,
                compression=compression,
                subfiletype=1,
                metadata=None,
            )

    return {
        "format": "pyramidal tiled compressed BigTIFF",
        "compression": compression,
        "tile_size": TILE_SIZE,
        "base_width_px": width,
        "base_height_px": height,
        "mode": "RGB" if rgb else "L",
        "pyramid_factors": factors,
        "pyramid_levels": len(factors) + 1,
    }


def render_pyramidal_map(
    input_csv: Path,
    output_tiff: Path,
    width: int,
    metric: str,
    scale: str,
    compression: str,
    class_discrimination: bool = True,
) -> dict[str, float | int | str | list[int]]:
    metric = resolve_metric_name(metric)
    rows = read_occurrence_rows(input_csv)
    values = metric_values(rows, metric, class_discrimination=class_discrimination)
    color_scale = metric_color_scale(
        rows,
        values,
        metric,
        class_discrimination,
    )
    row_colors = values_to_colors(
        values,
        color_scale.row_max_values,
        metric,
        scale,
        color_scale.min_value,
        color_scale.max_value,
        color_scale.max_abs_value,
    )

    metadata: dict[str, float | int | str | list[int]] = {
        "input_csv": str(input_csv),
        "output_tiff": str(output_tiff),
        "metric": metric,
        "definition": metric_definition(metric),
        "scale": scale,
        "class_discrimination": class_discrimination,
        "palette": metric_palette(metric),
        "display_width_px": width,
        "data_rows": len(values),
        "min_value": color_scale.min_value,
        "max_value": color_scale.max_value,
        "max_abs_value": color_scale.max_abs_value,
        "frequency_scale_reference": (
            color_scale.reference if metric in BLACK_WHITE_METRICS else ""
        ),
        "horizontal_pixels_are_display_magnification": "true",
    }
    metadata.update(write_pyramidal_tiff(output_tiff, row_colors, width, metric, scale, compression))
    output_tiff.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render tiled, compressed, pyramidal BigTIFF visual maps."
    )
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_tiff", type=Path)
    parser.add_argument("--width", type=int, default=2000)
    parser.add_argument("--metric", default=BOOK_FREQ)
    parser.add_argument("--scale", choices=("linear", "log"), default="linear")
    parser.add_argument("--compression", default="deflate")
    parser.add_argument("--no-class-discrimination", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        metadata = render_pyramidal_map(
            args.input_csv,
            args.output_tiff,
            args.width,
            args.metric,
            args.scale,
            args.compression,
            class_discrimination=not args.no_class_discrimination,
        )
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}") from exc
    print(
        "Wrote {output_tiff} ({base_width_px} x {base_height_px}px), "
        "{pyramid_levels} pyramid levels, compression={compression}".format(**metadata)
    )


if __name__ == "__main__":
    main()
