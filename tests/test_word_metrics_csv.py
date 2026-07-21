import unittest

from vocab_mapper.prepare_csv import collect_occurrences
from vocab_mapper.word_metrics_csv import build_word_metric_rows


class WordMetricsCsvTests(unittest.TestCase):
    def test_builds_traditional_unique_word_metric_rows(self):
        occurrences = collect_occurrences("The house was quiet. The house returned.")
        rows = build_word_metric_rows(occurrences)

        by_word = {row["word"]: row for row in rows}

        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["word"], "the")
        self.assertEqual(by_word["the"]["word_class"], "functional")
        self.assertEqual(by_word["the"]["book_count"], 2)
        self.assertEqual(by_word["the"]["total_word_count"], 3)
        self.assertEqual(by_word["the"]["book_freq"], "0.666666666667")
        self.assertEqual(
            by_word["the"]["book_avg_dev"],
            "0.333333333333",
        )
        self.assertEqual(
            by_word["the"]["book_med_dev"],
            "0.333333333333",
        )
        self.assertEqual(by_word["house"]["word_class"], "semantic")
        self.assertEqual(by_word["house"]["book_count"], 2)
        self.assertEqual(by_word["house"]["total_word_count"], 4)
        self.assertEqual(by_word["house"]["book_freq"], "0.5")
        self.assertEqual(by_word["house"]["book_avg_dev"], "0.5")
        self.assertEqual(by_word["house"]["book_med_dev"], "1")


if __name__ == "__main__":
    unittest.main()
