import unittest

from vocab_mapper.prepare_csv import build_rows, clean_text, collect_occurrences


class PrepareCsvTests(unittest.TestCase):
    def test_collects_word_occurrences_and_positions(self):
        text = """CHAPTER I

The house was quiet. Elizabeth opened the window.

CHAPTER II

Morning returned.
"""

        occurrences = collect_occurrences(clean_text(text))

        self.assertEqual(
            [o.normalized_word for o in occurrences],
            [
                "the",
                "house",
                "was",
                "quiet",
                "elizabeth",
                "opened",
                "the",
                "window",
                "morning",
                "returned",
            ],
        )
        self.assertEqual(occurrences[0].word_number, 1)
        self.assertEqual(occurrences[4].sentence_number, 2)
        self.assertEqual(occurrences[8].chapter_number, 2)
        self.assertEqual(occurrences[8].position_in_chapter, 1)

    def test_build_rows_calculates_signed_frequency_deviation_from_book_average(self):
        occurrences = collect_occurrences("The house was quiet. The house returned.")
        rows = build_rows(
            occurrences,
            ngram_sources={
                "Total": {"the": 0.05, "house": 0.0003},
                "-10y": {
                    "the": 0.04,
                    "was": 0.02,
                    "house": 0.001,
                    "quiet": 0.0005,
                    "returned": 0.0005,
                },
                "1999-2019": {"the": 0.08, "was": 0.04},
            },
        )

        the_rows = [row for row in rows if row["normalized_word"] == "the"]
        house_rows = [row for row in rows if row["normalized_word"] == "house"]
        was_rows = [row for row in rows if row["normalized_word"] == "was"]

        self.assertEqual(len(rows), 7)
        self.assertEqual(the_rows[0]["word_class"], "functional")
        self.assertEqual(the_rows[0]["book_freq"], "0.666666666667")
        self.assertEqual(the_rows[0]["book_avg_dev"], "0.333333333333")
        self.assertEqual(the_rows[0]["book_med_dev"], "0.333333333333")
        self.assertEqual(house_rows[0]["word_class"], "semantic")
        self.assertEqual(house_rows[0]["book_freq"], "0.5")
        self.assertEqual(house_rows[0]["book_med_dev"], "1")
        self.assertEqual(house_rows[0]["fic_ngram_total_freq"], "0.0003")
        self.assertEqual(house_rows[0]["fic_ngram_total_avg_dev"], "0")
        self.assertEqual(house_rows[0]["fic_ngram_total_med_dev"], "0")
        self.assertEqual(the_rows[0]["fic_ngram_prepub_10y_freq"], "0.04")
        self.assertEqual(
            the_rows[0]["fic_ngram_prepub_10y_avg_dev"],
            "0.333333333333",
        )
        self.assertEqual(the_rows[0]["fic_ngram_prepub_10y_med_dev"], "0.333333333333")
        self.assertNotIn("Ngrams_-10y_frequency_mad", the_rows[0])
        self.assertEqual(the_rows[0]["fic_ngram_99_19_freq"], "0.08")
        self.assertEqual(the_rows[0]["fic_ngram_99_19_med_dev"], "0.333333333333")
        self.assertNotIn("Ngrams_1999-2019_mad", the_rows[0])
        self.assertEqual(was_rows[0]["book_avg_dev"], "-0.333333333333")


if __name__ == "__main__":
    unittest.main()
