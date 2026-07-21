from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from vocab_mapper.metrics import metric_column_candidates, metric_label, resolve_metric_name


DEFAULT_INPUT = Path(
    "output/CSV Ocurrence Maps/The Fall of The House Usher/"
    "the_fall_of_the_house_of_usher_occurrences.csv"
)
DEFAULT_OUTPUT = Path(
    "output/plots/the_fall_of_the_house_of_usher_book_freq_kde_by_word_class.png"
)


CLASS_COLORS = {
    "functional": (42, 111, 197),
    "semantic": (33, 137, 98),
}
STAT_COLORS = {
    "Mode": (201, 66, 73),
    "Average": (116, 75, 173),
    "Median": (217, 133, 38),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot metric KDEs split by word_class with shared x and y scales."
        )
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-png", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--metric", default="book_freq")
    parser.add_argument("--group-column", default="word_class")
    parser.add_argument("--grid-size", type=int, default=900)
    parser.add_argument("--title", default=None)
    return parser.parse_args()


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_paths = [
        Path("C:/Windows/Fonts") / name,
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for font_path in font_paths:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def nice_step(raw_step: float) -> float:
    if raw_step <= 0:
        return 1.0
    exponent = math.floor(math.log10(raw_step))
    fraction = raw_step / (10**exponent)
    for candidate in (1, 2, 2.5, 5, 10):
        if fraction <= candidate:
            return candidate * (10**exponent)
    return 10 * (10**exponent)


def nice_ticks(max_value: float, target_count: int = 6) -> list[float]:
    step = nice_step(max_value / target_count)
    tick_max = math.ceil(max_value / step) * step
    ticks = np.arange(0, tick_max + step * 0.5, step)
    return [float(tick) for tick in ticks]


def format_x(value: float) -> str:
    return f"{value:.3f}"


def format_y(value: float) -> str:
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def weighted_median(values: np.ndarray, counts: np.ndarray) -> float:
    n = int(counts.sum())
    cumulative = np.cumsum(counts)

    def value_at_rank(rank: int) -> float:
        index = int(np.searchsorted(cumulative, rank + 1, side="left"))
        return float(values[index])

    if n % 2:
        return value_at_rank(n // 2)
    return (value_at_rank(n // 2 - 1) + value_at_rank(n // 2)) / 2


def expanded_sample_std(values: np.ndarray, counts: np.ndarray, mean: float) -> float:
    n = int(counts.sum())
    if n < 2:
        return 0.0
    variance = float(np.sum(counts * np.square(values - mean)) / (n - 1))
    return math.sqrt(variance)


def silverman_bandwidth(values: np.ndarray, counts: np.ndarray, mean: float) -> float:
    n = int(counts.sum())
    std = expanded_sample_std(values, counts, mean)
    if std <= 0:
        return 0.0
    factor = (n * 3.0 / 4.0) ** (-1.0 / 5.0)
    return float(std * factor)


def kde_for_counts(
    values: np.ndarray, counts: np.ndarray, x_grid: np.ndarray, bandwidth: float
) -> np.ndarray:
    if bandwidth <= 0:
        raise ValueError("KDE bandwidth is zero; frequency values are not variable enough.")

    n = float(counts.sum())
    coefficient = 1.0 / (bandwidth * math.sqrt(2.0 * math.pi) * n)
    density = np.zeros_like(x_grid, dtype=float)
    chunk_size = 512

    for start in range(0, values.size, chunk_size):
        end = start + chunk_size
        chunk_values = values[start:end]
        chunk_counts = counts[start:end]
        z = (x_grid[:, None] - chunk_values[None, :]) / bandwidth
        density += np.exp(-0.5 * z * z).dot(chunk_counts)

    return density * coefficient


def compute_group_stats(
    df: pd.DataFrame, metric: str, group_column: str, x_grid: np.ndarray
) -> tuple[dict[str, dict[str, float | int]], dict[str, np.ndarray]]:
    stats: dict[str, dict[str, float | int]] = {}
    densities: dict[str, np.ndarray] = {}

    groups = sorted(df[group_column].dropna().unique())
    preferred_order = [name for name in ("functional", "semantic") if name in groups]
    ordered_groups = preferred_order + [name for name in groups if name not in preferred_order]

    for group_name in ordered_groups:
        values = df.loc[df[group_column] == group_name, metric].dropna().to_numpy(float)
        if values.size < 2:
            raise ValueError(f"Need at least two values for group {group_name!r}.")

        unique_values, counts = np.unique(values, return_counts=True)
        row_count = int(counts.sum())
        mean = float(np.sum(unique_values * counts) / row_count)
        median = weighted_median(unique_values, counts)
        bandwidth = silverman_bandwidth(unique_values, counts, mean)
        density = kde_for_counts(unique_values, counts, x_grid, bandwidth)
        densities[group_name] = density
        max_count = int(counts.max())
        empirical_mode = float(unique_values[counts == max_count].min())
        kde_mode = float(x_grid[int(np.argmax(density))])

        stats[group_name] = {
            "row_count": row_count,
            "unique_frequency_count": int(unique_values.size),
            "min": float(unique_values.min()),
            "max": float(unique_values.max()),
            "mean": mean,
            "median": median,
            "kde_mode": kde_mode,
            "empirical_mode": empirical_mode,
            "empirical_mode_row_count": max_count,
            "density_max": float(density.max()),
            "bandwidth": bandwidth,
        }

    return stats, densities


def draw_plot(
    output_png: Path,
    input_csv: Path,
    metric: str,
    group_column: str,
    title: str,
    x_grid: np.ndarray,
    y_max: float,
    x_ticks: list[float],
    y_ticks: list[float],
    stats: dict[str, dict[str, float | int]],
    densities: dict[str, np.ndarray],
) -> None:
    scale = 2
    width, height = 1800, 980
    left, right, top, bottom = 115, 55, 190, 135
    gap = 85
    panel_w = (width - left - right - gap) / 2
    panel_h = height - top - bottom

    image = Image.new("RGBA", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(image, "RGBA")

    def s(value: float) -> int:
        return int(round(value * scale))

    title_font = load_font("arialbd.ttf", 34 * scale)
    subtitle_font = load_font("arial.ttf", 20 * scale)
    label_font = load_font("arial.ttf", 18 * scale)
    tick_font = load_font("arial.ttf", 15 * scale)
    panel_title_font = load_font("arialbd.ttf", 24 * scale)
    small_font = load_font("arial.ttf", 15 * scale)

    def text(x: float, y: float, value: str, font, fill=(30, 34, 40), anchor="la") -> None:
        draw.text((s(x), s(y)), value, font=font, fill=fill + (255,), anchor=anchor)

    display_metric = metric_label(metric)
    text(width / 2, 44, f"{title}: {display_metric} KDE by word class", title_font, anchor="ma")
    text(
        width / 2,
        85,
        "Gaussian KDE with Silverman bandwidth; both panels share the same frequency and density scales",
        subtitle_font,
        fill=(82, 89, 101),
        anchor="ma",
    )
    text(
        width / 2,
        113,
        f"Input: {input_csv.as_posix()} | Metric: {metric} | Distribution: occurrence rows",
        small_font,
        fill=(96, 105, 118),
        anchor="ma",
    )

    legend_items = [
        ("KDE", (55, 118, 183), "solid"),
        ("Mode", STAT_COLORS["Mode"], "solid"),
        ("Average", STAT_COLORS["Average"], "dash"),
        ("Median", STAT_COLORS["Median"], "dashdot"),
    ]
    legend_x = width / 2 - 260
    legend_y = 148
    for label, color, style in legend_items:
        x0, x1 = legend_x, legend_x + 45
        y = legend_y
        draw_styled_line(draw, (s(x0), s(y)), (s(x1), s(y)), color, style, 4 * scale)
        text(x1 + 9, y - 8, label, small_font, fill=(54, 61, 73), anchor="la")
        legend_x += 130

    x_min = float(x_grid[0])
    x_max = float(x_grid[-1])

    for idx, group_name in enumerate(densities):
        panel_x = left + idx * (panel_w + gap)
        panel_y = top
        color = CLASS_COLORS.get(group_name, (55, 118, 183))
        density = densities[group_name]
        group_stats = stats[group_name]

        def px(x_value: float) -> float:
            return panel_x + (x_value - x_min) / (x_max - x_min) * panel_w

        def py(y_value: float) -> float:
            return panel_y + panel_h - (y_value / y_max) * panel_h

        axis_color = (28, 32, 38)
        grid_color = (224, 229, 236)
        draw.rectangle(
            [s(panel_x), s(panel_y), s(panel_x + panel_w), s(panel_y + panel_h)],
            fill=(250, 251, 253, 255),
            outline=(204, 211, 220, 255),
            width=1 * scale,
        )

        for tick in x_ticks:
            x = px(tick)
            draw.line(
                [(s(x), s(panel_y)), (s(x), s(panel_y + panel_h))],
                fill=grid_color + (255,),
                width=1 * scale,
            )
            text(x, panel_y + panel_h + 16, format_x(tick), tick_font, fill=(84, 91, 104), anchor="ma")

        for tick in y_ticks:
            y = py(tick)
            draw.line(
                [(s(panel_x), s(y)), (s(panel_x + panel_w), s(y))],
                fill=grid_color + (255,),
                width=1 * scale,
            )
            text(panel_x - 12, y + 5, format_y(tick), tick_font, fill=(84, 91, 104), anchor="ra")

        draw.line(
            [(s(panel_x), s(panel_y + panel_h)), (s(panel_x + panel_w), s(panel_y + panel_h))],
            fill=axis_color + (255,),
            width=2 * scale,
        )
        draw.line(
            [(s(panel_x), s(panel_y)), (s(panel_x), s(panel_y + panel_h))],
            fill=axis_color + (255,),
            width=2 * scale,
        )

        points = [(px(float(x)), py(float(y))) for x, y in zip(x_grid, density)]
        fill_polygon = (
            [(s(panel_x), s(panel_y + panel_h))]
            + [(s(x), s(y)) for x, y in points]
            + [(s(panel_x + panel_w), s(panel_y + panel_h))]
        )
        draw.polygon(fill_polygon, fill=color + (38,))
        draw.line([(s(x), s(y)) for x, y in points], fill=color + (255,), width=5 * scale, joint="curve")

        stat_lines = [
            ("Mode", float(group_stats["kde_mode"]), "solid"),
            ("Average", float(group_stats["mean"]), "dash"),
            ("Median", float(group_stats["median"]), "dashdot"),
        ]
        for label, x_value, style in stat_lines:
            x = px(x_value)
            draw_styled_line(
                draw,
                (s(x), s(panel_y)),
                (s(x), s(panel_y + panel_h)),
                STAT_COLORS[label],
                style,
                3 * scale,
            )

        title = f"{group_name.title()} (n={group_stats['row_count']})"
        text(panel_x + panel_w / 2, panel_y - 42, title, panel_title_font, anchor="ma")
        summary = (
            f"mode={float(group_stats['kde_mode']):.6f}  "
            f"avg={float(group_stats['mean']):.6f}  "
            f"median={float(group_stats['median']):.6f}"
        )
        text(panel_x + panel_w / 2, panel_y - 15, summary, small_font, fill=(82, 89, 101), anchor="ma")
        text(panel_x + panel_w / 2, panel_y + panel_h + 62, metric, label_font, anchor="ma")
        text(panel_x - 74, panel_y + panel_h / 2, "density", label_font, anchor="mm")

    output_png.parent.mkdir(parents=True, exist_ok=True)
    image = image.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")
    image.save(output_png)


def draw_styled_line(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    style: str,
    width: int,
) -> None:
    if style == "solid":
        draw.line([start, end], fill=color + (255,), width=width)
        return

    x0, y0 = start
    x1, y1 = end
    length = math.hypot(x1 - x0, y1 - y0)
    if length == 0:
        return

    if style == "dashdot":
        pattern = [18, 8, 4, 8]
    else:
        pattern = [16, 9]

    dx = (x1 - x0) / length
    dy = (y1 - y0) / length
    distance = 0.0
    draw_segment = True
    pattern_index = 0
    while distance < length:
        segment = min(pattern[pattern_index % len(pattern)], length - distance)
        if draw_segment:
            sx = x0 + dx * distance
            sy = y0 + dy * distance
            ex = x0 + dx * (distance + segment)
            ey = y0 + dy * (distance + segment)
            draw.line([(int(sx), int(sy)), (int(ex), int(ey))], fill=color + (255,), width=width)
        distance += segment
        draw_segment = not draw_segment
        pattern_index += 1


def main() -> None:
    args = parse_args()
    metric = resolve_metric_name(args.metric)
    metric_candidates = metric_column_candidates(metric)
    try:
        header = pd.read_csv(args.input_csv, nrows=0)
        metric_column = next(
            (candidate for candidate in metric_candidates if candidate in header.columns),
            None,
        )
        if metric_column is None:
            raise ValueError
        df = pd.read_csv(args.input_csv, usecols=[args.group_column, metric_column])
    except ValueError as exc:
        raise ValueError(
            f"Could not read required columns {args.group_column!r} and {metric!r}."
        ) from exc

    df = df.rename(columns={metric_column: metric})
    df[metric] = pd.to_numeric(df[metric], errors="coerce")
    df = df.dropna(subset=[args.group_column, metric])
    title = args.title or args.input_csv.stem.replace("_occurrences", "").replace("_", " ").title()

    max_frequency = float(df[metric].max())
    x_ticks = nice_ticks(max_frequency * 1.03, target_count=7)
    x_grid = np.linspace(0, x_ticks[-1], args.grid_size)

    stats, densities = compute_group_stats(df, metric, args.group_column, x_grid)
    max_density = max(float(density.max()) for density in densities.values())
    y_ticks = nice_ticks(max_density * 1.08, target_count=6)
    y_max = y_ticks[-1]

    draw_plot(
        output_png=args.output_png,
        input_csv=args.input_csv,
        metric=metric,
        group_column=args.group_column,
        title=title,
        x_grid=x_grid,
        y_max=y_max,
        x_ticks=x_ticks,
        y_ticks=y_ticks,
        stats=stats,
        densities=densities,
    )

    sidecar = {
        "input_csv": str(args.input_csv),
        "output_png": str(args.output_png),
        "metric": metric,
        "group_column": args.group_column,
        "distribution": "occurrence rows",
        "kde": "Gaussian kernel, Silverman bandwidth",
        "shared_scales": {
            "frequency_axis_min": float(x_grid[0]),
            "frequency_axis_max": float(x_grid[-1]),
            "density_axis_min": 0.0,
            "density_axis_max": float(y_max),
        },
        "groups": stats,
    }
    args.output_png.with_suffix(".json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
