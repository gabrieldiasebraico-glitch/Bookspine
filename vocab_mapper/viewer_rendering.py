from __future__ import annotations

from dataclasses import dataclass
import math

from vocab_mapper.metric_values import row_metric_values
from vocab_mapper.metrics import (
    METRIC_SPECS,
    is_ngram_frequency_metric,
    resolve_metric_name,
)

RED = (220, 0, 0)
WHITE = (255, 255, 255)
BLUE = (0, 68, 220)
MAGENTA = (255, 0, 255)
GREEN = (0, 160, 0)

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


@dataclass(frozen=True)
class MetricColorScale:
    min_value: float
    max_value: float
    max_abs_value: float
    row_max_values: list[float]
    reference: str


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
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    amount: float,
) -> tuple[int, int, int]:
    amount = max(0, min(1, amount))
    return tuple(round(s + (e - s) * amount) for s, e in zip(start, end))


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


def diverging_color(value: float, min_value: float, max_value: float) -> tuple[int, int, int]:
    return signed_color(value, min_value, max_value, RED, BLUE)


def magenta_white_green_color(
    value: float,
    min_value: float,
    max_value: float,
) -> tuple[int, int, int]:
    return signed_color(value, min_value, max_value, MAGENTA, GREEN)


def metric_palette(metric: str) -> str:
    metric = resolve_metric_name(metric)
    if metric in MAGENTA_WHITE_GREEN_METRICS:
        return "magenta-white-green"
    if metric in DIVERGING_METRICS:
        return "red-white-blue"
    return "black-white"


def metric_values(
    rows: list[dict[str, str]],
    metric: str,
    class_discrimination: bool = True,
) -> list[float]:
    metric = resolve_metric_name(metric)
    return row_metric_values(rows, metric, class_discrimination)


def metric_color_scale(
    rows: list[dict[str, str]],
    values: list[float],
    metric: str,
    class_discrimination: bool,
) -> MetricColorScale:
    metric = resolve_metric_name(metric)
    min_value = min(values) if values else 0
    max_value = max(values) if values else 0
    max_abs_value = max((abs(value) for value in values), default=0)
    row_max_values = [max_value] * len(values)
    reference = "global_maximum"

    if not class_discrimination or metric not in BLACK_WHITE_METRICS:
        return MetricColorScale(
            min_value=min_value,
            max_value=max_value,
            max_abs_value=max_abs_value,
            row_max_values=row_max_values,
            reference=reference,
        )

    max_by_class: dict[str, float] = {}
    for row, value in zip(rows, values):
        word_class = row.get("word_class", "")
        max_by_class[word_class] = max(value, max_by_class.get(word_class, 0))
    row_max_values = [
        max_by_class.get(row.get("word_class", ""), max_value)
        for row in rows
    ]
    return MetricColorScale(
        min_value=min_value,
        max_value=max_value,
        max_abs_value=max_abs_value,
        row_max_values=row_max_values,
        reference="word_class_maximum",
    )


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
    if is_ngram_frequency_metric(metric):
        return grayscale_color(value, max_value, scale)
    return grayscale_color(value, max_value, scale)


def normalized_metric_value(
    value: float,
    metric: str,
    scale: str,
    min_value: float,
    max_value: float,
) -> float:
    """Convert a metric value to its signed or positive display intensity."""
    metric = resolve_metric_name(metric)
    if metric in DIVERGING_METRICS:
        if value < 0:
            return -min(abs(value) / abs(min_value), 1.0) if min_value < 0 else 0.0
        return min(value / max_value, 1.0) if max_value > 0 else 0.0
    return max(0.0, min(1.0, scale_value(value, max_value, scale)))


def normalized_metric_color(value: float, metric: str) -> tuple[int, int, int]:
    """Color a normalized display value without reapplying metric scaling."""
    metric = resolve_metric_name(metric)
    value = max(-1.0, min(1.0, value))
    if metric in MAGENTA_WHITE_GREEN_METRICS:
        return signed_color(value, -1.0, 1.0, MAGENTA, GREEN)
    if metric in DIVERGING_METRICS:
        return signed_color(value, -1.0, 1.0, RED, BLUE)
    channel = round(max(0.0, value) * 255)
    return channel, channel, channel
