from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable

from vocab_mapper.metrics import (
    BOOK_METRIC_FIELDNAMES,
    BOOK_NGRAM_COMPARISON_FIELDNAMES,
    BOOK_AVG_DEV,
    BOOK_FREQ,
    BOOK_MED_DEV,
    NGRAM_COLUMN_SPECS,
)


WORD_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
SENTENCE_END_RE = re.compile(r"[.!?]+(?:[\"')\]]+)?\s+")
CHAPTER_RE = re.compile(
    r"^\s*(chapter|book|part)\s+([ivxlcdm]+|\d+|[a-z]+)\b|^\s*[ivxlcdm]+\.\s*$",
    re.IGNORECASE,
)


FUNCTION_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "he'd",
    "he'll",
    "he's",
    "her",
    "here",
    "here's",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "how's",
    "i",
    "i'd",
    "i'll",
    "i'm",
    "i've",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "let's",
    "me",
    "more",
    "most",
    "must",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "shan't",
    "she",
    "she'd",
    "she'll",
    "she's",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "they'd",
    "they'll",
    "they're",
    "they've",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "we'd",
    "we'll",
    "we're",
    "we've",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "when's",
    "where",
    "where's",
    "which",
    "while",
    "who",
    "who's",
    "whom",
    "why",
    "why's",
    "will",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "you'd",
    "you'll",
    "you're",
    "you've",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


LOCATION_FIELDNAMES = [
    "word",
    "normalized_word",
    "word_number",
    "word_class",
    "position_in_sentence",
    "relative_position_in_sentence",
    "position_in_paragraph",
    "relative_position_in_paragraph",
    "position_in_chapter",
    "relative_position_in_chapter",
    "sentence_number",
    "paragraph_number",
    "chapter_number",
]

FIELDNAMES = [
    *LOCATION_FIELDNAMES,
    *BOOK_METRIC_FIELDNAMES,
    *[
        fieldname
        for columns in NGRAM_COLUMN_SPECS.values()
        for fieldname in columns
    ],
    *BOOK_NGRAM_COMPARISON_FIELDNAMES,
]

TYPOGRAPHY_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2013": " ",
        "\u2014": " ",
        "\u2212": " ",
        "\ufeff": "",
    }
)


@dataclass
class WordOccurrence:
    word: str
    normalized_word: str
    word_number: int
    word_class: str
    position_in_sentence: int
    sentence_number: int
    position_in_paragraph: int
    paragraph_number: int
    position_in_chapter: int
    chapter_number: int
    sentence_token_total: int = 0
    paragraph_token_total: int = 0
    chapter_token_total: int = 0


@dataclass(frozen=True)
class FrequencyStats:
    average: float | None
    median: float | None


def normalize_word(word: str) -> str:
    return word.lower().strip("'")


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"Could not decode {path}")


def strip_gutenberg_boilerplate(text: str) -> str:
    lines = text.splitlines()
    start_index = 0
    end_index = len(lines)

    for index, line in enumerate(lines):
        lowered = line.lower()
        if (
            "*** start of" in lowered
            or "***start of" in lowered
            or "start of the project gutenberg" in lowered
        ):
            start_index = index + 1
            break

    for index in range(len(lines) - 1, -1, -1):
        lowered = lines[index].lower()
        if (
            "*** end of" in lowered
            or "***end of" in lowered
            or "end of the project gutenberg" in lowered
        ):
            end_index = index
            break

    return "\n".join(lines[start_index:end_index])


def clean_text(text: str) -> str:
    text = text.translate(TYPOGRAPHY_TRANSLATION)
    text = strip_gutenberg_boilerplate(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def classify_word(normalized_word: str) -> str:
    if normalized_word in FUNCTION_WORDS:
        return "functional"
    return "semantic"


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def sentence_spans(paragraph: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in SENTENCE_END_RE.finditer(paragraph + " "):
        end = match.end()
        if paragraph[start:end].strip():
            spans.append((start, min(end, len(paragraph))))
        start = end
    if not spans and paragraph.strip():
        spans.append((0, len(paragraph)))
    elif start < len(paragraph) and paragraph[start:].strip():
        spans.append((start, len(paragraph)))
    return spans


def iter_words(sentence: str) -> Iterable[re.Match[str]]:
    return WORD_RE.finditer(sentence)


def is_chapter_heading(paragraph: str) -> bool:
    compact = " ".join(paragraph.split())
    if len(compact) > 80:
        return False
    return bool(CHAPTER_RE.search(compact))


def collect_occurrences(text: str) -> list[WordOccurrence]:
    occurrences: list[WordOccurrence] = []
    sentence_number = 0
    paragraph_number = 0
    chapter_number = 1
    position_in_chapter = 0
    word_number = 0

    for paragraph in split_paragraphs(text):
        if is_chapter_heading(paragraph) and occurrences:
            chapter_number += 1
            position_in_chapter = 0
            continue
        if is_chapter_heading(paragraph) and not occurrences:
            continue

        paragraph_number += 1
        position_in_paragraph = 0

        for start, end in sentence_spans(paragraph):
            sentence = paragraph[start:end]
            sentence_words = list(iter_words(sentence))
            if not sentence_words:
                continue

            sentence_number += 1
            for position_in_sentence, match in enumerate(sentence_words, start=1):
                word = match.group(0)
                normalized = normalize_word(word)
                if not normalized:
                    continue

                word_number += 1
                position_in_paragraph += 1
                position_in_chapter += 1
                occurrences.append(
                    WordOccurrence(
                        word=word,
                        normalized_word=normalized,
                        word_number=word_number,
                        word_class=classify_word(normalized),
                        position_in_sentence=position_in_sentence,
                        sentence_number=sentence_number,
                        position_in_paragraph=position_in_paragraph,
                        paragraph_number=paragraph_number,
                        position_in_chapter=position_in_chapter,
                        chapter_number=chapter_number,
                    )
                )

    add_scope_totals(occurrences)
    return occurrences


def add_scope_totals(occurrences: list[WordOccurrence]) -> None:
    sentence_totals = Counter(o.sentence_number for o in occurrences)
    paragraph_totals = Counter(o.paragraph_number for o in occurrences)
    chapter_totals = Counter(o.chapter_number for o in occurrences)

    for occurrence in occurrences:
        occurrence.sentence_token_total = sentence_totals[occurrence.sentence_number]
        occurrence.paragraph_token_total = paragraph_totals[occurrence.paragraph_number]
        occurrence.chapter_token_total = chapter_totals[occurrence.chapter_number]


def load_ngram_frequencies(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}

    with path.open("r", encoding="utf-8-sig", newline="") as ngram_file:
        reader = csv.DictReader(ngram_file)
        headers = {header.lower(): header for header in reader.fieldnames or []}
        word_header = headers.get("word") or headers.get("normalized_word") or headers.get("token")
        frequency_header = headers.get("ngram_f") or headers.get("frequency") or headers.get("freq")
        if not word_header or not frequency_header:
            raise ValueError(
                "Ngram CSV must contain a word column and a frequency column. "
                "Accepted names: word/normalized_word/token and ngram_f/frequency/freq."
            )

        frequencies: dict[str, float] = {}
        for row in reader:
            word = normalize_word(row[word_header])
            if not word:
                continue
            try:
                frequencies[word] = float(row[frequency_header])
            except ValueError:
                continue
        return frequencies


def load_ngram_source_paths(
    ngram_path: Path | None = None,
    ngram_total_path: Path | None = None,
    ngram_minus_10y_path: Path | None = None,
    ngram_1999_2019_path: Path | None = None,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    total_path = ngram_total_path or ngram_path
    if total_path is not None:
        paths["Total"] = total_path
    if ngram_minus_10y_path is not None:
        paths["-10y"] = ngram_minus_10y_path
    if ngram_1999_2019_path is not None:
        paths["1999-2019"] = ngram_1999_2019_path
    return paths


def load_ngram_sources(source_paths: dict[str, Path]) -> dict[str, dict[str, float]]:
    return {label: load_ngram_frequencies(path) for label, path in source_paths.items()}


def format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.12g}"


def average_deviation(value: float | None, average: float | None) -> float | None:
    if value is None or average is None or average == 0:
        return None
    return (value / average) - 1


def median_deviation(value: float | None, median_value: float | None) -> float | None:
    if value is None or median_value is None or median_value == 0:
        return None
    return (value / median_value) - 1


def frequency_ratio_deviation(
    numerator: float | None, denominator: float | None
) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return (numerator / denominator) - 1


def frequency_stats(values: list[float]) -> FrequencyStats:
    if not values:
        return FrequencyStats(None, None)
    median_value = median(values)
    return FrequencyStats(
        average=sum(values) / len(values),
        median=median_value,
    )


def word_classes_by_word(occurrences: list[WordOccurrence]) -> dict[str, str]:
    return {
        occurrence.normalized_word: occurrence.word_class
        for occurrence in occurrences
    }


def book_frequencies_by_word(
    occurrences: list[WordOccurrence],
) -> dict[str, float]:
    class_totals = Counter(occurrence.word_class for occurrence in occurrences)
    word_counts_by_class = Counter(
        (occurrence.word_class, occurrence.normalized_word)
        for occurrence in occurrences
    )

    return {
        word: count / class_totals[word_class]
        for (word_class, word), count in word_counts_by_class.items()
        if class_totals[word_class]
    }


def stats_by_class(
    values_by_word: dict[str, float],
    word_classes: dict[str, str],
) -> dict[str, FrequencyStats]:
    values_by_class: dict[str, list[float]] = defaultdict(list)
    for word, word_class in word_classes.items():
        if word in values_by_word:
            values_by_class[word_class].append(values_by_word[word])
    return {
        word_class: frequency_stats(values)
        for word_class, values in values_by_class.items()
    }


def build_rows(
    occurrences: list[WordOccurrence],
    ngram_frequencies: dict[str, float] | None = None,
    ngram_sources: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, str | int]]:
    if ngram_sources is None:
        ngram_sources = {}
    if ngram_frequencies:
        ngram_sources = {"Total": ngram_frequencies, **ngram_sources}

    word_classes = word_classes_by_word(occurrences)
    book_frequencies = book_frequencies_by_word(occurrences)
    book_stats_by_class = stats_by_class(book_frequencies, word_classes)
    ngram_stats_by_label = {
        label: stats_by_class(frequencies, word_classes)
        for label, frequencies in ngram_sources.items()
    }

    rows: list[dict[str, str | int]] = []
    for occurrence in occurrences:
        book_frequency = book_frequencies.get(occurrence.normalized_word)
        book_stats = book_stats_by_class.get(occurrence.word_class)
        row: dict[str, str | int] = {
            "word": occurrence.word,
            "normalized_word": occurrence.normalized_word,
            "word_number": occurrence.word_number,
            "word_class": occurrence.word_class,
            "position_in_sentence": occurrence.position_in_sentence,
            "relative_position_in_sentence": format_float(
                occurrence.position_in_sentence / occurrence.sentence_token_total
            ),
            "position_in_paragraph": occurrence.position_in_paragraph,
            "relative_position_in_paragraph": format_float(
                occurrence.position_in_paragraph / occurrence.paragraph_token_total
            ),
            "position_in_chapter": occurrence.position_in_chapter,
            "relative_position_in_chapter": format_float(
                occurrence.position_in_chapter / occurrence.chapter_token_total
            ),
            "sentence_number": occurrence.sentence_number,
            "paragraph_number": occurrence.paragraph_number,
            "chapter_number": occurrence.chapter_number,
            BOOK_FREQ: format_float(book_frequency),
            BOOK_AVG_DEV: format_float(
                average_deviation(book_frequency, book_stats.average if book_stats else None)
            ),
            BOOK_MED_DEV: format_float(
                median_deviation(book_frequency, book_stats.median if book_stats else None)
            ),
        }

        for label, columns in NGRAM_COLUMN_SPECS.items():
            frequency_column, average_column, median_column = columns
            frequencies = ngram_sources.get(label, {})
            ngram_frequency = frequencies.get(occurrence.normalized_word)
            ngram_stats = ngram_stats_by_label.get(label, {}).get(occurrence.word_class)
            row[frequency_column] = format_float(ngram_frequency)
            row[average_column] = format_float(
                average_deviation(
                    ngram_frequency,
                    ngram_stats.average if ngram_stats else None,
                )
            )
            row[median_column] = format_float(
                median_deviation(
                    ngram_frequency,
                    ngram_stats.median if ngram_stats else None,
                )
            )

        rows.append(row)
    return rows


def write_csv(rows: list[dict[str, str | int]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def prepare_csv(
    input_path: Path,
    output_path: Path,
    ngram_path: Path | None = None,
    ngram_total_path: Path | None = None,
    ngram_minus_10y_path: Path | None = None,
    ngram_1999_2019_path: Path | None = None,
) -> int:
    text = clean_text(read_text_file(input_path))
    ngram_sources = load_ngram_sources(
        load_ngram_source_paths(
            ngram_path=ngram_path,
            ngram_total_path=ngram_total_path,
            ngram_minus_10y_path=ngram_minus_10y_path,
            ngram_1999_2019_path=ngram_1999_2019_path,
        )
    )
    occurrences = collect_occurrences(text)
    rows = build_rows(occurrences, ngram_sources=ngram_sources)
    write_csv(rows, output_path)
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare word occurrence CSV data for vocabulary diversity visual maps."
    )
    parser.add_argument("input_txt", type=Path, help="Path to a UTF-8 .txt book file.")
    parser.add_argument("output_csv", type=Path, help="Path where the CSV will be written.")
    parser.add_argument(
        "--ngram-csv",
        type=Path,
        default=None,
        help=(
            "Legacy alias for --ngram-total-csv. Optional CSV with columns "
            "word/ngram_f. Also accepts normalized_word/token and frequency/freq."
        ),
    )
    parser.add_argument(
        "--ngram-total-csv",
        type=Path,
        default=None,
        help="Ngram frequency CSV for all years in the fictional corpus.",
    )
    parser.add_argument(
        "--ngram-minus-10y-csv",
        type=Path,
        default=None,
        help="Ngram frequency CSV for the ten years before the book publication year.",
    )
    parser.add_argument(
        "--ngram-1999-2019-csv",
        type=Path,
        default=None,
        help="Ngram frequency CSV for the 1999-2019 fictional corpus window.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    row_count = prepare_csv(
        args.input_txt,
        args.output_csv,
        args.ngram_csv,
        args.ngram_total_csv,
        args.ngram_minus_10y_csv,
        args.ngram_1999_2019_csv,
    )
    print(f"Wrote {row_count} word-occurrence rows to {args.output_csv}")


if __name__ == "__main__":
    main()
