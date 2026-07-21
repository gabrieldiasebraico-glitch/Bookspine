from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import median

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from vocab_mapper.prepare_csv import classify_word


DEFAULT_INPUT = PROJECT_ROOT / "data" / "ngram_frequencies" / "eng_fiction_2019_all_ngram_frequencies.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "plots" / "fic_ngram_total_freq_corpus_kde.png"

COLORS = {
    "all": (44, 62, 80),
    "functional": (42, 111, 197),
    "semantic": (33, 137, 98),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot KDE density of fiction Ngram corpus frequencies."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-png", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--grid-size", type=int, default=900)
    parser.add_argument("--title", default="English Fiction 2019 1-gram Corpus")
    return parser.parse_args()


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_paths = [Path("C:/Windows/Fonts") / name, Path("C:/Windows/Fonts/arial.ttf")]
    for font_path in font_paths:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def read_ngram_rows(input_csv: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with input_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            word = (row.get("word") or row.get("normalized_word") or row.get("token") or "").strip()
            raw_frequency = row.get("ngram_f") or row.get("frequency") or row.get("freq") or ""
            if not word or raw_frequency == "":
                continue
            try:
                frequency = float(raw_frequency)
            except ValueError:
                continue
            rows.append(
                {
                    "word": word,
                    "word_class": classify_word(word.lower()),
                    "frequency": frequency,
                }
            )
    return rows


def silverman_bandwidth(values: np.ndarray) -> float:
    if values.size < 2:
        return 0.0
    std = float(values.std(ddof=1))
    if std <= 0:
        return 0.0
    return std * (values.size * 3.0 / 4.0) ** (-1.0 / 5.0)


def kde(values: np.ndarray, x_grid: np.ndarray, bandwidth: float) -> np.ndarray:
    if bandwidth <= 0:
        raise ValueError("KDE bandwidth is zero; frequency values are not variable enough.")
    density = np.zeros_like(x_grid)
    coefficient = 1.0 / (bandwidth * math.sqrt(2.0 * math.pi) * values.size)
    chunk_size = 512
    for start in range(0, values.size, chunk_size):
        chunk = values[start : start + chunk_size]
        z = (x_grid[:, None] - chunk[None, :]) / bandwidth
        density += np.exp(-0.5 * z * z).sum(axis=1)
    return density * coefficient


def group_stats(rows: list[dict[str, object]], x_grid: np.ndarray) -> tuple[dict[str, dict[str, object]], dict[str, np.ndarray]]:
    stats: dict[str, dict[str, object]] = {}
    densities: dict[str, np.ndarray] = {}
    groups = {
        "all": rows,
        "functional": [row for row in rows if row["word_class"] == "functional"],
        "semantic": [row for row in rows if row["word_class"] == "semantic"],
    }
    for name, group_rows in groups.items():
        frequencies = np.array([float(row["frequency"]) for row in group_rows], dtype=float)
        positive = frequencies[frequencies > 0]
        log_values = np.log10(positive)
        bandwidth = silverman_bandwidth(log_values)
        density = kde(log_values, x_grid, bandwidth)
        densities[name] = density
        mode_log = float(x_grid[int(np.argmax(density))])
        stats[name] = {
            "word_count": int(frequencies.size),
            "zero_frequency_words": int((frequencies <= 0).sum()),
            "positive_frequency_words": int(positive.size),
            "min_frequency": float(frequencies.min()) if frequencies.size else 0.0,
            "min_positive_frequency": float(positive.min()) if positive.size else 0.0,
            "max_frequency": float(frequencies.max()) if frequencies.size else 0.0,
            "avg_frequency": float(frequencies.mean()) if frequencies.size else 0.0,
            "median_frequency": float(median(frequencies)) if frequencies.size else 0.0,
            "kde_mode_log10_frequency": mode_log,
            "kde_mode_frequency": 10**mode_log,
            "log10_bandwidth": bandwidth,
            "density_max": float(density.max()),
        }
    return stats, densities


def nice_log_ticks(x_min: float, x_max: float) -> list[float]:
    first = math.ceil(x_min)
    last = math.floor(x_max)
    return [float(value) for value in range(first, last + 1)]


def format_frequency_tick(log_value: float) -> str:
    frequency = 10**log_value
    if frequency >= 0.01:
        return f"{frequency:.2g}"
    return f"{frequency:.0e}"


def draw_plot(
    output_png: Path,
    input_csv: Path,
    title: str,
    x_grid: np.ndarray,
    stats: dict[str, dict[str, object]],
    densities: dict[str, np.ndarray],
) -> None:
    scale = 2
    width, height = 1800, 1050
    left, right, top, bottom = 135, 405, 180, 140
    plot_w = width - left - right
    plot_h = height - top - bottom
    image = Image.new("RGBA", (width * scale, height * scale), "white")
    draw = ImageDraw.Draw(image, "RGBA")

    def s(value: float) -> int:
        return int(round(value * scale))

    title_font = load_font("arialbd.ttf", 34 * scale)
    subtitle_font = load_font("arial.ttf", 20 * scale)
    label_font = load_font("arial.ttf", 18 * scale)
    tick_font = load_font("arial.ttf", 15 * scale)
    small_font = load_font("arial.ttf", 15 * scale)
    summary_font = load_font("arial.ttf", 16 * scale)
    summary_bold = load_font("arialbd.ttf", 17 * scale)

    def text(x: float, y: float, value: str, font, fill=(30, 34, 40), anchor="la") -> None:
        draw.text((s(x), s(y)), value, font=font, fill=fill + (255,), anchor=anchor)

    text(width / 2, 44, f"{title}: fic_ngram_total_freq KDE", title_font, anchor="ma")
    text(
        width / 2,
        85,
        "Word-level distribution from the fiction Ngram corpus; x-axis is log-scaled frequency",
        subtitle_font,
        fill=(82, 89, 101),
        anchor="ma",
    )
    text(
        width / 2,
        114,
        f"Input: {input_csv.as_posix()} | zero-frequency words are counted in stats and excluded from log KDE",
        small_font,
        fill=(96, 105, 118),
        anchor="ma",
    )

    x_min = float(x_grid[0])
    x_max = float(x_grid[-1])
    y_max = max(float(density.max()) for density in densities.values()) * 1.08
    y_ticks = np.linspace(0, y_max, 7)
    x_ticks = nice_log_ticks(x_min, x_max)

    def px(x_value: float) -> float:
        return left + (x_value - x_min) / (x_max - x_min) * plot_w

    def py(y_value: float) -> float:
        return top + plot_h - (y_value / y_max) * plot_h

    draw.rectangle(
        [s(left), s(top), s(left + plot_w), s(top + plot_h)],
        fill=(250, 251, 253, 255),
        outline=(204, 211, 220, 255),
        width=1 * scale,
    )
    for tick in x_ticks:
        x = px(tick)
        draw.line([(s(x), s(top)), (s(x), s(top + plot_h))], fill=(224, 229, 236, 255), width=1 * scale)
        text(x, top + plot_h + 18, format_frequency_tick(tick), tick_font, fill=(84, 91, 104), anchor="ma")
    for tick in y_ticks:
        y = py(float(tick))
        draw.line([(s(left), s(y)), (s(left + plot_w), s(y))], fill=(224, 229, 236, 255), width=1 * scale)
        text(left - 12, y + 5, f"{tick:.2f}", tick_font, fill=(84, 91, 104), anchor="ra")

    draw.line([(s(left), s(top + plot_h)), (s(left + plot_w), s(top + plot_h))], fill=(28, 32, 38, 255), width=2 * scale)
    draw.line([(s(left), s(top)), (s(left), s(top + plot_h))], fill=(28, 32, 38, 255), width=2 * scale)

    for name in ("all", "semantic", "functional"):
        density = densities[name]
        color = COLORS[name]
        points = [(px(float(x)), py(float(y))) for x, y in zip(x_grid, density)]
        polygon = (
            [(s(left), s(top + plot_h))]
            + [(s(x), s(y)) for x, y in points]
            + [(s(left + plot_w), s(top + plot_h))]
        )
        draw.polygon(polygon, fill=color + (28 if name == "all" else 38,))
        draw.line([(s(x), s(y)) for x, y in points], fill=color + (255,), width=4 * scale, joint="curve")

    text(left + plot_w / 2, height - 56, "fic_ngram_total_freq", label_font, anchor="ma")
    text(left, top - 18, "density over log10(frequency)", label_font, anchor="la")

    legend_x = left
    legend_y = 145
    for name in ("all", "functional", "semantic"):
        color = COLORS[name]
        draw.line([(s(legend_x), s(legend_y)), (s(legend_x + 45), s(legend_y))], fill=color + (255,), width=5 * scale)
        text(legend_x + 56, legend_y - 8, name, small_font, fill=(54, 61, 73), anchor="la")
        legend_x += 150

    summary_x = left + plot_w + 45
    summary_y = top + 10
    text(summary_x, summary_y, "Corpus Stats", summary_bold)
    summary_y += 42
    for name in ("all", "functional", "semantic"):
        color = COLORS[name]
        group = stats[name]
        text(summary_x, summary_y, name.title(), summary_bold, fill=color)
        summary_y += 26
        lines = [
            f"words: {group['word_count']}",
            f"zeros: {group['zero_frequency_words']}",
            f"avg: {float(group['avg_frequency']):.6g}",
            f"median: {float(group['median_frequency']):.6g}",
            f"mode: {float(group['kde_mode_frequency']):.6g}",
            f"max: {float(group['max_frequency']):.6g}",
        ]
        for line in lines:
            text(summary_x, summary_y, line, summary_font, fill=(64, 72, 84))
            summary_y += 23
        summary_y += 18

    output_png.parent.mkdir(parents=True, exist_ok=True)
    image = image.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")
    image.save(output_png)


def main() -> None:
    args = parse_args()
    rows = read_ngram_rows(args.input_csv)
    if not rows:
        raise SystemExit(f"No usable rows found in {args.input_csv}")

    positive = np.array([float(row["frequency"]) for row in rows if float(row["frequency"]) > 0], dtype=float)
    x_min = math.floor(float(np.log10(positive.min())) * 10) / 10
    x_max = math.ceil(float(np.log10(positive.max())) * 10) / 10
    x_grid = np.linspace(x_min, x_max, args.grid_size)

    stats, densities = group_stats(rows, x_grid)
    draw_plot(args.output_png, args.input_csv, args.title, x_grid, stats, densities)

    sidecar = {
        "input_csv": str(args.input_csv),
        "output_png": str(args.output_png),
        "metric": "fic_ngram_total_freq",
        "distribution": "word-level rows from the fiction Ngram corpus",
        "kde": "Gaussian kernel over log10(frequency), Silverman bandwidth",
        "zero_frequency_handling": "Zero-frequency words are counted in stats and excluded from log10 KDE.",
        "x_axis": {
            "scale": "log10 frequency",
            "min_log10_frequency": float(x_grid[0]),
            "max_log10_frequency": float(x_grid[-1]),
            "min_frequency": 10 ** float(x_grid[0]),
            "max_frequency": 10 ** float(x_grid[-1]),
        },
        "groups": stats,
    }
    args.output_png.with_suffix(".json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
