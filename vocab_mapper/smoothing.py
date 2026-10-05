from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Sequence

import numpy as np


SMOOTHING_METHODS = {
    "none",
    "moving_average",
    "gaussian",
    "median",
    "savitzky_golay",
    "exponential",
    "adaptive_gaussian",
    "structure_gaussian",
    "display_blur",
}
SMOOTHING_DOMAINS = {"normalized", "raw", "log"}
BOUNDARY_MODES = {"reflect", "truncate", "sentence", "paragraph", "chapter"}
STRUCTURE_UNITS = {"sentence", "paragraph", "chapter"}


@dataclass(frozen=True)
class SmoothingConfig:
    method: str = "none"
    bandwidth: float = 50.0
    window: int = 51
    polynomial_order: int = 3
    alpha: float = 0.2
    cutoff: float = 4.0
    boundary: str = "reflect"
    domain: str = "normalized"
    adaptive_strength: float = 1.0
    structure: str = "paragraph"
    zoom_adaptive: bool = False

    def validated(self) -> "SmoothingConfig":
        if self.method not in SMOOTHING_METHODS:
            raise ValueError(f"Unsupported smoothing method: {self.method}")
        if self.domain not in SMOOTHING_DOMAINS:
            raise ValueError(f"Unsupported smoothing domain: {self.domain}")
        if self.boundary not in BOUNDARY_MODES:
            raise ValueError(f"Unsupported smoothing boundary: {self.boundary}")
        if self.structure not in STRUCTURE_UNITS:
            raise ValueError(f"Unsupported smoothing structure: {self.structure}")

        window = max(3, min(int(self.window), 501))
        if window % 2 == 0:
            window += 1 if window < 501 else -1
        polynomial_order = max(1, min(int(self.polynomial_order), 9, window - 1))
        return replace(
            self,
            bandwidth=max(0.1, min(float(self.bandwidth), 5000.0)),
            window=window,
            polynomial_order=polynomial_order,
            alpha=max(0.001, min(float(self.alpha), 1.0)),
            cutoff=max(1.0, min(float(self.cutoff), 6.0)),
            adaptive_strength=max(0.1, min(float(self.adaptive_strength), 10.0)),
        )

    def resolved_for_zoom(self, pixels_per_occurrence: float | None) -> "SmoothingConfig":
        config = self.validated()
        if not config.zoom_adaptive or not pixels_per_occurrence or pixels_per_occurrence <= 0:
            return config

        occurrences_per_pixel = min(5000.0, 1.0 / pixels_per_occurrence)
        bandwidth = max(config.bandwidth, occurrences_per_pixel)
        window = max(config.window, int(math.ceil(occurrences_per_pixel * 2.0 + 1.0)))
        window = min(window, 501)
        if window % 2 == 0:
            window = min(501, window + 1)
        alpha = min(config.alpha, 2.0 / (occurrences_per_pixel + 1.0))
        return replace(
            config,
            bandwidth=round(bandwidth, 3),
            window=window,
            alpha=max(0.001, alpha),
            zoom_adaptive=False,
        )


def config_from_query(params: Mapping[str, Sequence[str]]) -> SmoothingConfig:
    def first(name: str, default: str) -> str:
        values = params.get(name)
        return str(values[0]) if values else default

    def number(name: str, default: float) -> float:
        try:
            return float(first(name, str(default)))
        except ValueError:
            return default

    def integer(name: str, default: int) -> int:
        try:
            return int(float(first(name, str(default))))
        except ValueError:
            return default

    return SmoothingConfig(
        method=first("smoothingMethod", "none"),
        bandwidth=number("smoothingBandwidth", 50.0),
        window=integer("smoothingWindow", 51),
        polynomial_order=integer("smoothingPolynomial", 3),
        alpha=number("smoothingAlpha", 0.2),
        cutoff=number("smoothingCutoff", 4.0),
        boundary=first("smoothingBoundary", "reflect"),
        domain=first("smoothingDomain", "normalized"),
        adaptive_strength=number("smoothingAdaptiveStrength", 1.0),
        structure=first("smoothingStructure", "paragraph"),
        zoom_adaptive=first("smoothingZoomAdaptive", "0").lower() in {"1", "true", "yes", "on"},
    ).validated()


def smooth_values(
    values: Sequence[float],
    config: SmoothingConfig,
    structures: Mapping[str, Sequence[int]] | None = None,
) -> list[float]:
    config = config.validated()
    array = np.asarray(values, dtype=np.float64)
    if array.size < 2 or config.method in {"none", "display_blur"}:
        return array.tolist()

    boundary = config.boundary
    structure_name: str | None = None
    if config.method == "structure_gaussian":
        structure_name = config.structure
        boundary = "reflect"
    elif boundary in STRUCTURE_UNITS:
        structure_name = boundary
        boundary = "reflect"

    structure_values = structures.get(structure_name) if structures and structure_name else None
    ranges = _segment_ranges(structure_values, len(array))
    result = np.empty_like(array)
    for start, end in ranges:
        result[start:end] = _smooth_segment(array[start:end], config, boundary)
    return result.tolist()


def _smooth_segment(values: np.ndarray, config: SmoothingConfig, boundary: str) -> np.ndarray:
    if values.size < 2:
        return values.copy()
    if config.method == "moving_average":
        kernel = np.ones(config.window, dtype=np.float64)
        kernel /= kernel.sum()
        return _weighted_convolution(values, kernel, boundary)
    if config.method in {"gaussian", "structure_gaussian"}:
        return _gaussian(values, config.bandwidth, config.cutoff, boundary)
    if config.method == "median":
        return _median(values, config.window, boundary)
    if config.method == "savitzky_golay":
        return _savitzky_golay(values, config.window, config.polynomial_order, boundary)
    if config.method == "exponential":
        return _zero_phase_exponential(values, config.alpha)
    if config.method == "adaptive_gaussian":
        broad = _gaussian(values, config.bandwidth, config.cutoff, boundary)
        narrow = _gaussian(values, max(0.5, config.bandwidth / 3.0), config.cutoff, boundary)
        contrast = np.abs(values - broad)
        contrast_scale = float(np.percentile(contrast, 75))
        if contrast_scale <= np.finfo(np.float64).eps:
            return broad
        broad_weight = np.exp(
            -config.adaptive_strength * contrast / (contrast_scale + np.finfo(np.float64).eps)
        )
        return broad_weight * broad + (1.0 - broad_weight) * narrow
    return values.copy()


def _gaussian(values: np.ndarray, bandwidth: float, cutoff: float, boundary: str) -> np.ndarray:
    radius = max(1, int(math.ceil(bandwidth * cutoff)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (offsets / bandwidth) ** 2)
    kernel /= kernel.sum()
    return _weighted_convolution(values, kernel, boundary)


def _weighted_convolution(values: np.ndarray, kernel: np.ndarray, boundary: str) -> np.ndarray:
    radius = len(kernel) // 2
    if boundary == "truncate":
        padded = np.pad(values, (radius, radius), mode="constant")
        weights = np.pad(np.ones_like(values), (radius, radius), mode="constant")
        numerator = _valid_convolution(padded, kernel)
        denominator = _valid_convolution(weights, kernel)
        return numerator / np.maximum(denominator, np.finfo(np.float64).eps)

    pad_mode = "reflect" if values.size > 1 else "edge"
    padded = np.pad(values, (radius, radius), mode=pad_mode)
    return _valid_convolution(padded, kernel)


def _valid_convolution(values: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    output_size = values.size - kernel.size + 1
    if output_size <= 0:
        return np.array([], dtype=np.float64)
    if values.size * kernel.size <= 20_000_000:
        return np.convolve(values, kernel, mode="valid")

    full_size = values.size + kernel.size - 1
    fft_size = 1 << (full_size - 1).bit_length()
    transformed = np.fft.rfft(values, fft_size) * np.fft.rfft(kernel, fft_size)
    full = np.fft.irfft(transformed, fft_size)[:full_size]
    start = kernel.size - 1
    return full[start : start + output_size]


def _median(values: np.ndarray, window: int, boundary: str) -> np.ndarray:
    window = _usable_window(window, values.size)
    if window < 3:
        return values.copy()
    radius = window // 2
    if boundary == "truncate":
        padded = np.pad(values, (radius, radius), mode="constant", constant_values=np.nan)
        windows = np.lib.stride_tricks.sliding_window_view(padded, window)
        return np.nanmedian(windows, axis=1)
    padded = np.pad(values, (radius, radius), mode="reflect")
    windows = np.lib.stride_tricks.sliding_window_view(padded, window)
    return np.median(windows, axis=1)


def _savitzky_golay(
    values: np.ndarray,
    window: int,
    polynomial_order: int,
    boundary: str,
) -> np.ndarray:
    window = _usable_window(window, values.size)
    if window < 3:
        return values.copy()
    polynomial_order = min(polynomial_order, window - 1)
    radius = window // 2
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    design = np.vander(offsets, polynomial_order + 1, increasing=True)
    kernel = np.linalg.pinv(design)[0]
    pad_mode = "reflect" if boundary != "truncate" and values.size > 1 else "edge"
    padded = np.pad(values, (radius, radius), mode=pad_mode)
    return _valid_convolution(padded, kernel)


def _zero_phase_exponential(values: np.ndarray, alpha: float) -> np.ndarray:
    forward = np.empty_like(values)
    forward[0] = values[0]
    for index in range(1, values.size):
        forward[index] = alpha * values[index] + (1.0 - alpha) * forward[index - 1]

    backward = np.empty_like(values)
    backward[-1] = values[-1]
    for index in range(values.size - 2, -1, -1):
        backward[index] = alpha * values[index] + (1.0 - alpha) * backward[index + 1]
    return (forward + backward) / 2.0


def _usable_window(window: int, size: int) -> int:
    window = min(window, size if size % 2 == 1 else size - 1)
    return max(1, window)


def _segment_ranges(structure_values: Sequence[int] | None, size: int) -> list[tuple[int, int]]:
    if not structure_values or len(structure_values) != size:
        return [(0, size)]
    ranges: list[tuple[int, int]] = []
    start = 0
    current = structure_values[0]
    for index, value in enumerate(structure_values[1:], start=1):
        if value != current:
            ranges.append((start, index))
            start = index
            current = value
    ranges.append((start, size))
    return ranges
