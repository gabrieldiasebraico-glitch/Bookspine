import unittest

from vocab_mapper.prepare_csv import collect_occurrences
from vocab_mapper.word_frequency_csv import (
    build_word_frequency_rows,
    comparison_to_ngram,
)


class WordFrequencyCsvTests(unittest.TestCase):
    def test_builds_unique_word_rows_with_ngram_comparison(self):
        occurrences = collect_occurrences("The house was quiet. The house returned.")
        rows = build_word_frequency_rows(occurrences, {"the": 0.25, "house": 0.125})

        by_word = {row["word"]: row for row in rows}

        self.assertEqual(len(rows), 5)
        self.assertEqual(by_word["the"]["word_class"], "functional")
        self.assertEqual(by_word["the"]["book_count"], 2)
        self.assertEqual(by_word["the"]["total_word_count"], 3)
        self.assertEqual(by_word["the"]["book_freq"], "0.666666666667")
        self.assertEqual(by_word["the"]["ngram_frequency"], "0.25")
        self.assertEqual(by_word["the"]["book_to_ngram_frequency_deviation"], "1.66666666667")
        self.assertEqual(by_word["house"]["word_class"], "semantic")
        self.assertEqual(by_word["was"]["ngram_frequency"], "")
        self.assertEqual(by_word["was"]["book_to_ngram_frequency_deviation"], "")

    def test_comparison_is_blank_for_missing_or_zero_ngram_frequency(self):
        self.assertIsNone(comparison_to_ngram(0.1, None))
        self.assertIsNone(comparison_to_ngram(0.1, 0))


if __name__ == "__main__":
    unittest.main()
