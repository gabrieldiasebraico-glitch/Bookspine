import unittest
from unittest.mock import patch

from vocab_mapper.prepare_csv import build_rows, collect_occurrences
from vocab_mapper.word_metrics_csv import build_word_metric_rows
from vocab_mapper.word_frequency_csv import build_word_frequency_rows
from vocab_mapper.metric_values import book_frequency_by_word, row_metric_values
from vocab_mapper.stats import book_stats_from_occurrences, book_stats_from_rows
from vocab_mapper.word_classifier import load_pipeline


class ContextualClassificationTests(unittest.TestCase):
    def test_same_spelling_has_different_classes_and_frequencies(self):
        occurrences = collect_occurrences("I can swim. Open the can. Open the can.")
        cans = [o for o in occurrences if o.normalized_word == "can"]
        self.assertEqual([o.word_class for o in cans], ["functional", "semantic", "semantic"])
        rows = build_rows(occurrences, {"can": 0.1, "the": 0.2, "i": 0.3})
        can_rows = [r for r in rows if r["normalized_word"] == "can"]
        self.assertAlmostEqual(float(can_rows[0]["book_freq"]), 1 / 4)
        self.assertAlmostEqual(float(can_rows[1]["book_freq"]), 2 / 5)
        frequencies = book_frequency_by_word(rows, True)
        self.assertAlmostEqual(frequencies[("can", "functional")], 1 / 4)
        self.assertAlmostEqual(frequencies[("can", "semantic")], 2 / 5)
        for metric in ("book_avg_dev", "book_med_dev", "fic_ngram_total_avg_dev", "fic_ngram_total_med_dev"):
            # Force the viewer to recalculate instead of reading stored columns.
            unstored = [{k: v for k, v in row.items() if k != metric} for row in rows]
            recalculated = row_metric_values(unstored, metric, True)
            for row, value in zip(rows, recalculated):
                self.assertAlmostEqual(float(row[metric] or 0), value)
        for export in (build_word_metric_rows(occurrences), build_word_frequency_rows(occurrences, {"can": 0.1})):
            can_exports = [r for r in export if r["word"] == "can"]
            self.assertEqual(len(can_exports), 2)
            self.assertEqual(sum(r["book_count"] for r in can_exports), 3)
        for basis in ("token", "word"):
            actual = row_metric_values(rows, "book_freq", True, basis)
            for word_class in ("functional", "semantic"):
                indices = [i for i, r in enumerate(rows) if r["word_class"] == word_class]
                expected = row_metric_values([rows[i] for i in indices], "book_freq", False, basis)
                for actual_value, expected_value in zip([actual[i] for i in indices], expected):
                    self.assertAlmostEqual(actual_value, expected_value)
        self.assertEqual(book_stats_from_rows(rows), book_stats_from_occurrences(occurrences))

    def test_contractions_and_hyphenated_words_preserve_positions(self):
        occurrences = collect_occurrences("I don't like John's well-known book.")
        self.assertEqual([o.normalized_word for o in occurrences], ["i", "don't", "like", "john's", "well-known", "book"])
        self.assertEqual([o.word_number for o in occurrences], list(range(1, 7)))
        by_word = {o.normalized_word: o for o in occurrences}
        self.assertEqual(by_word["don't"].word_class, "functional")
        self.assertEqual(by_word["john's"].word_class, "semantic")
        self.assertEqual(by_word["well-known"].word_class, "semantic")

    def test_missing_model_produces_actionable_error(self):
        load_pipeline.cache_clear()
        try:
            with patch("spacy.load", side_effect=OSError("missing")):
                with self.assertRaisesRegex(RuntimeError, "spacy download"):
                    load_pipeline()
        finally:
            load_pipeline.cache_clear()


if __name__ == "__main__":
    unittest.main()
