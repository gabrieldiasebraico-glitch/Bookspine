from __future__ import annotations

import unittest

from vocab_mapper.metric_values import book_frequency_by_word, row_metric_values
from vocab_mapper.metrics import BOOK_FREQ, FIC_NGRAM_TOTAL_FREQ


def occurrence_rows(*, include_stored_book_frequency: bool = False) -> list[dict[str, str]]:
    """Return rows whose token and distinct-word denominators differ."""
    rows = [
        {"normalized_word": "a", "word_class": "functional"},
        {"normalized_word": "a", "word_class": "functional"},
        {"normalized_word": "b", "word_class": "functional"},
        {"normalized_word": "c", "word_class": "semantic"},
    ]
    if include_stored_book_frequency:
        for row in rows:
            row[BOOK_FREQ] = "9.0"
    return rows


class BookFrequencyBasisTests(unittest.TestCase):
    def assert_frequencies(
        self,
        actual: dict[str, float],
        expected: dict[str, float],
    ) -> None:
        self.assertEqual(set(actual), set(expected))
        for word, expected_value in expected.items():
            with self.subTest(word=word):
                self.assertAlmostEqual(actual[word], expected_value)

    def test_token_basis_without_class_normalization_uses_all_token_rows(self) -> None:
        actual = book_frequency_by_word(
            occurrence_rows(),
            class_discrimination=False,
            frequency_basis="token",
        )

        self.assert_frequencies(actual, {"a": 2 / 4, "b": 1 / 4, "c": 1 / 4})

    def test_word_basis_without_class_normalization_uses_all_distinct_words(self) -> None:
        actual = book_frequency_by_word(
            occurrence_rows(),
            class_discrimination=False,
            frequency_basis="word",
        )

        self.assert_frequencies(actual, {"a": 2 / 3, "b": 1 / 3, "c": 1 / 3})

    def test_token_basis_with_class_normalization_uses_token_rows_in_each_class(self) -> None:
        actual = book_frequency_by_word(
            occurrence_rows(),
            class_discrimination=True,
            frequency_basis="token",
        )

        self.assert_frequencies(actual, {"a": 2 / 3, "b": 1 / 3, "c": 1.0})

    def test_word_basis_with_class_normalization_uses_distinct_words_in_each_class(self) -> None:
        actual = book_frequency_by_word(
            occurrence_rows(),
            class_discrimination=True,
            frequency_basis="word",
        )

        self.assert_frequencies(actual, {"a": 2 / 2, "b": 1 / 2, "c": 1.0})

    def test_word_basis_recomputes_rows_instead_of_using_stored_token_frequency(self) -> None:
        actual = row_metric_values(
            occurrence_rows(include_stored_book_frequency=True),
            BOOK_FREQ,
            class_discrimination=True,
            frequency_basis="word",
        )

        self.assertEqual(len(actual), 4)
        for actual_value, expected_value in zip(actual, [1.0, 1.0, 0.5, 1.0]):
            self.assertAlmostEqual(actual_value, expected_value)

    def test_invalid_frequency_basis_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "(?i)frequency.*basis"):
            book_frequency_by_word(
                occurrence_rows(),
                class_discrimination=False,
                frequency_basis="characters",
            )

    def test_raw_ngram_frequency_does_not_change_with_book_frequency_basis(self) -> None:
        rows = occurrence_rows()
        expected = [0.01, 0.01, 0.02, 0.03]
        for row, value in zip(rows, expected):
            row[FIC_NGRAM_TOTAL_FREQ] = str(value)

        for class_discrimination in (False, True):
            for frequency_basis in ("token", "word"):
                with self.subTest(
                    class_discrimination=class_discrimination,
                    frequency_basis=frequency_basis,
                ):
                    actual = row_metric_values(
                        rows,
                        FIC_NGRAM_TOTAL_FREQ,
                        class_discrimination=class_discrimination,
                        frequency_basis=frequency_basis,
                    )
                    self.assertEqual(actual, expected)

    def test_legacy_word_column_is_a_case_insensitive_normalized_word_fallback(self) -> None:
        rows = [
            {"word": "Alpha", "word_class": "semantic"},
            {"word": "ALPHA", "word_class": "semantic"},
            {"word": "Beta", "word_class": "semantic"},
        ]
        expectations = {
            "token": ({"alpha": 2 / 3, "beta": 1 / 3}, [2 / 3, 2 / 3, 1 / 3]),
            "word": ({"alpha": 2 / 2, "beta": 1 / 2}, [1.0, 1.0, 0.5]),
        }

        for frequency_basis, (expected_by_word, expected_by_row) in expectations.items():
            with self.subTest(frequency_basis=frequency_basis):
                actual_by_word = book_frequency_by_word(
                    rows,
                    class_discrimination=False,
                    frequency_basis=frequency_basis,
                )
                self.assert_frequencies(actual_by_word, expected_by_word)

                actual_by_row = row_metric_values(
                    rows,
                    BOOK_FREQ,
                    class_discrimination=False,
                    frequency_basis=frequency_basis,
                )
                self.assertEqual(len(actual_by_row), len(expected_by_row))
                for actual_value, expected_value in zip(actual_by_row, expected_by_row):
                    self.assertAlmostEqual(actual_value, expected_value)

    def test_blank_word_rows_are_excluded_from_token_and_word_denominators(self) -> None:
        rows = [
            {"normalized_word": "a", "word_class": "semantic"},
            {"normalized_word": "a", "word_class": "semantic"},
            {"normalized_word": "b", "word_class": "semantic"},
            {"normalized_word": "", "word_class": "semantic"},
            {"word": "", "word_class": "semantic"},
            {"word_class": "semantic"},
        ]
        expectations = {
            "token": {"a": 2 / 3, "b": 1 / 3},
            "word": {"a": 2 / 2, "b": 1 / 2},
        }

        for class_discrimination in (False, True):
            for frequency_basis, expected in expectations.items():
                with self.subTest(
                    class_discrimination=class_discrimination,
                    frequency_basis=frequency_basis,
                ):
                    actual = book_frequency_by_word(
                        rows,
                        class_discrimination=class_discrimination,
                        frequency_basis=frequency_basis,
                    )
                    self.assert_frequencies(actual, expected)


if __name__ == "__main__":
    unittest.main()
