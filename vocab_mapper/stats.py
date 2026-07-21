from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from vocab_mapper.metric_values import (
    book_frequency_by_word,
    ngram_frequency_by_word,
    word_classes_by_word,
)
from vocab_mapper.prepare_csv import WordOccurrence, format_float
from vocab_mapper.metrics import FIC_NGRAM_PREPUB_10Y_FREQ
WORD_CLASSES = ("functional", "semantic")


@dataclass(frozen=True)
class ClassBookStats:
    word_count: int
    avg_book_f: float | None
    med_book_f: float | None
    max_book_f: float | None
    min_book_f: float | None
    fic_ngram_prepub_10y_freq_avg: float | None = None
    fic_ngram_prepub_10y_freq_med: float | None = None


def book_stats_from_occurrences(
    occurrences: list[WordOccurrence],
    prepub_ngram_frequencies: dict[str, float] | None = None,
) -> dict[str, object]:
    prepub_ngram_frequencies = prepub_ngram_frequencies or {}
    class_totals = Counter(occurrence.word_class for occurrence in occurrences)
    word_counts = Counter(
        (occurrence.word_class, occurrence.normalized_word)
        for occurrence in occurrences
    )

    class_stats: dict[str, ClassBookStats] = {}
    for word_class in WORD_CLASSES:
        total = class_totals[word_class]
        book_frequencies = [
            count / total
            for (current_class, _word), count in word_counts.items()
            if current_class == word_class and total
        ]
        ngram_values = [
            prepub_ngram_frequencies[word]
            for (current_class, word), _count in word_counts.items()
            if current_class == word_class and word in prepub_ngram_frequencies
        ]
        class_stats[word_class] = ClassBookStats(
            word_count=total,
            avg_book_f=average(book_frequencies),
            med_book_f=median(book_frequencies) if book_frequencies else None,
            max_book_f=max(book_frequencies) if book_frequencies else None,
            min_book_f=min(book_frequencies) if book_frequencies else None,
            fic_ngram_prepub_10y_freq_avg=average(ngram_values),
            fic_ngram_prepub_10y_freq_med=median(ngram_values) if ngram_values else None,
        )

    return {
        "total_words": len(occurrences),
        "total_functional_words": class_totals["functional"],
        "total_semantic_words": class_totals["semantic"],
        "classes": class_stats,
    }


def book_stats_from_rows(rows: list[dict[str, str]]) -> dict[str, object]:
    class_totals = Counter(row.get("word_class", "") for row in rows)
    word_classes = word_classes_by_word(rows)
    frequencies = book_frequency_by_word(rows, class_discrimination=True)
    prepub_frequencies = ngram_frequency_by_word(rows, FIC_NGRAM_PREPUB_10Y_FREQ)

    class_stats: dict[str, ClassBookStats] = {}
    for word_class in WORD_CLASSES:
        book_values = [
            value
            for word, value in frequencies.items()
            if word_classes.get(word) == word_class
        ]
        ngram_values = [
            value
            for word, value in prepub_frequencies.items()
            if word_classes.get(word) == word_class
        ]
        class_stats[word_class] = ClassBookStats(
            word_count=class_totals[word_class],
            avg_book_f=average(book_values),
            med_book_f=median(book_values) if book_values else None,
            max_book_f=max(book_values) if book_values else None,
            min_book_f=min(book_values) if book_values else None,
            fic_ngram_prepub_10y_freq_avg=average(ngram_values),
            fic_ngram_prepub_10y_freq_med=median(ngram_values) if ngram_values else None,
        )

    return {
        "total_words": len(rows),
        "total_functional_words": class_totals["functional"],
        "total_semantic_words": class_totals["semantic"],
        "classes": class_stats,
    }


def write_book_stats_txt(stats: dict[str, object], output_path: Path) -> None:
    classes = stats["classes"]
    assert isinstance(classes, dict)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"total_words={stats['total_words']}",
        f"total_functional_words={stats['total_functional_words']}",
        f"total_semantic_words={stats['total_semantic_words']}",
        "",
    ]
    for word_class in WORD_CLASSES:
        class_stats = classes[word_class]
        assert isinstance(class_stats, ClassBookStats)
        lines.extend(
            [
                f"[{word_class}]",
                f"avg_book_f={format_float(class_stats.avg_book_f)}",
                f"med_book_f={format_float(class_stats.med_book_f)}",
                f"max_book_f={format_float(class_stats.max_book_f)}",
                f"min_book_f={format_float(class_stats.min_book_f)}",
                (
                    "fic_ngram_prepub_10y_freq_avg="
                    f"{format_float(class_stats.fic_ngram_prepub_10y_freq_avg)}"
                ),
                (
                    "fic_ngram_prepub_10y_freq_med="
                    f"{format_float(class_stats.fic_ngram_prepub_10y_freq_med)}"
                ),
                "",
            ]
        )

    for word_class in WORD_CLASSES:
        class_stats = classes[word_class]
        assert isinstance(class_stats, ClassBookStats)
        lines.extend(
            [
                f"{word_class}_avg_book_f={format_float(class_stats.avg_book_f)}",
                f"{word_class}_med_book_f={format_float(class_stats.med_book_f)}",
                f"{word_class}_max_book_f={format_float(class_stats.max_book_f)}",
                f"{word_class}_min_book_f={format_float(class_stats.min_book_f)}",
            ]
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def book_stats_output_path(output_dir: Path, book_slug: str) -> Path:
    return output_dir / "book_stats" / f"{book_slug}_book_stats.txt"
