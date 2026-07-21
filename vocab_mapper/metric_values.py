from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median

from vocab_mapper.metrics import (
    BOOK_AVG_DEV,
    BOOK_FREQ,
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
    metric_column_candidates,
    resolve_metric_name,
)


NGRAM_DEVIATION_SOURCES = {
    FIC_NGRAM_TOTAL_AVG_DEV: (FIC_NGRAM_TOTAL_FREQ, "average"),
    FIC_NGRAM_TOTAL_MED_DEV: (FIC_NGRAM_TOTAL_FREQ, "median"),
    FIC_NGRAM_PREPUB_10Y_AVG_DEV: (FIC_NGRAM_PREPUB_10Y_FREQ, "average"),
    FIC_NGRAM_PREPUB_10Y_MED_DEV: (FIC_NGRAM_PREPUB_10Y_FREQ, "median"),
    FIC_NGRAM_99_19_AVG_DEV: (FIC_NGRAM_99_19_FREQ, "average"),
    FIC_NGRAM_99_19_MED_DEV: (FIC_NGRAM_99_19_FREQ, "median"),
}


def row_metric_values(
    rows: list[dict[str, str]],
    metric: str,
    class_discrimination: bool = True,
) -> list[float]:
    metric = resolve_metric_name(metric)
    if class_discrimination and rows:
        for candidate in metric_column_candidates(metric):
            if candidate in rows[0]:
                return numeric_column_values(rows, metric)
    if metric in (BOOK_FREQ, BOOK_AVG_DEV, BOOK_MED_DEV):
        return book_metric_values(rows, metric, class_discrimination)
    if metric in NGRAM_DEVIATION_SOURCES:
        return ngram_deviation_values(rows, metric, class_discrimination)
    return numeric_column_values(rows, metric)


def book_metric_values(
    rows: list[dict[str, str]],
    metric: str,
    class_discrimination: bool,
) -> list[float]:
    frequencies = book_frequency_by_word(rows, class_discrimination)
    if metric == BOOK_FREQ:
        return [frequencies.get(row.get("normalized_word", ""), 0) for row in rows]

    stats = stats_for_words(frequencies, word_classes_by_word(rows), class_discrimination)
    statistic = "average" if metric == BOOK_AVG_DEV else "median"
    values: list[float] = []
    for row in rows:
        word = row.get("normalized_word", "")
        word_class = row.get("word_class", "")
        frequency = frequencies.get(word)
        denominator = class_stat(stats, word_class, statistic, class_discrimination)
        values.append(ratio_deviation(frequency, denominator) or 0)
    return values


def ngram_deviation_values(
    rows: list[dict[str, str]],
    metric: str,
    class_discrimination: bool,
) -> list[float]:
    frequency_metric, statistic = NGRAM_DEVIATION_SOURCES[metric]
    frequencies = ngram_frequency_by_word(rows, frequency_metric)
    stats = stats_for_words(frequencies, word_classes_by_word(rows), class_discrimination)
    values: list[float] = []
    for row in rows:
        word = row.get("normalized_word", "")
        word_class = row.get("word_class", "")
        frequency = frequencies.get(word)
        denominator = class_stat(stats, word_class, statistic, class_discrimination)
        values.append(ratio_deviation(frequency, denominator) or 0)
    return values


def numeric_column_values(rows: list[dict[str, str]], metric: str) -> list[float]:
    if not rows:
        return []
    for candidate in metric_column_candidates(metric):
        if candidate in rows[0]:
            return [parse_float(row.get(candidate)) or 0 for row in rows]
    available = ", ".join(rows[0].keys())
    raise ValueError(f"Metric column {metric!r} not found. Available columns: {available}")


def ngram_frequency_by_word(
    rows: list[dict[str, str]],
    frequency_metric: str,
) -> dict[str, float]:
    candidates = metric_column_candidates(frequency_metric)
    frequencies: dict[str, float] = {}
    for row in rows:
        word = row.get("normalized_word", "")
        if not word or word in frequencies:
            continue
        for candidate in candidates:
            value = parse_float(row.get(candidate))
            if value is not None:
                frequencies[word] = value
                break
    return frequencies


def book_frequency_by_word(
    rows: list[dict[str, str]],
    class_discrimination: bool,
) -> dict[str, float]:
    if not rows:
        return {}
    word_counts = Counter(row.get("normalized_word", "") for row in rows)
    if not class_discrimination:
        total = len(rows)
        return {word: count / total for word, count in word_counts.items() if word}

    class_totals = Counter(row.get("word_class", "") for row in rows)
    word_classes = word_classes_by_word(rows)
    return {
        word: count / class_totals[word_classes[word]]
        for word, count in word_counts.items()
        if word and class_totals[word_classes[word]]
    }


def word_classes_by_word(rows: list[dict[str, str]]) -> dict[str, str]:
    return {
        row.get("normalized_word", ""): row.get("word_class", "")
        for row in rows
        if row.get("normalized_word")
    }


def stats_for_words(
    values_by_word: dict[str, float],
    word_classes: dict[str, str],
    class_discrimination: bool,
) -> dict[str, dict[str, float | None]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for word, value in values_by_word.items():
        key = word_classes.get(word, "") if class_discrimination else "all"
        grouped[key].append(value)
    return {key: stats(values) for key, values in grouped.items()}


def stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"average": None, "median": None, "min": None, "max": None}
    return {
        "average": sum(values) / len(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
    }


def class_stat(
    stats_by_class: dict[str, dict[str, float | None]],
    word_class: str,
    statistic: str,
    class_discrimination: bool,
) -> float | None:
    key = word_class if class_discrimination else "all"
    return stats_by_class.get(key, {}).get(statistic)


def ratio_deviation(value: float | None, denominator: float | None) -> float | None:
    if value is None or denominator is None or denominator == 0:
        return None
    return (value / denominator) - 1


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None
