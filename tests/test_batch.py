import shutil
import unittest
from pathlib import Path

from vocab_mapper.batch import (
    book_outputs,
    discover_missing_outputs,
    generate_missing_outputs,
    iter_txt_books,
)


class BatchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_path = Path("output") / "test_batch_workflow"
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.books_dir = self.temp_path / "txt books"
        self.output_dir = self.temp_path / "output"
        self.maps_dir = self.output_dir / "maps"
        self.books_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_path, ignore_errors=True)

    def write_book(self, name, text="The house was quiet. The house returned."):
        path = self.books_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_discovers_twilight_txt_automatically(self):
        twilight = self.write_book("Twilight.txt")
        self.write_book("Book List.xlsx")

        self.assertEqual(iter_txt_books(self.books_dir), [twilight])

        missing = discover_missing_outputs(self.books_dir, self.output_dir, self.maps_dir)

        self.assertEqual([item.input_txt.name for item in missing], ["Twilight.txt"])
        self.assertEqual(missing[0].occurrence_csv.name, "twilight_occurrences.csv")
        self.assertEqual(missing[0].first_map.name, "twilight_book_freq_linear.png")
        self.assertEqual(missing[0].book_stats.name, "twilight_book_stats.txt")
        self.assertEqual(missing[0].word_metrics.name, "twilight_word_metrics.csv")

    def test_uses_existing_harry_potter_and_lord_of_the_rings_naming_baseline(self):
        harry = self.write_book("Harry Potter and the Sorcerer's Stone.txt")
        lotr = self.write_book("Lord of The Rings.txt")

        harry_outputs = book_outputs(harry, self.output_dir, self.maps_dir)
        lotr_outputs = book_outputs(lotr, self.output_dir, self.maps_dir)

        self.assertEqual(
            harry_outputs.occurrence_csv.name,
            "harry_potter_and_the_sorcerers_stone_occurrences.csv",
        )
        self.assertEqual(
            harry_outputs.first_map.name,
            "harry_potter_sorcerers_stone_book_freq_linear.png",
        )
        self.assertEqual(lotr_outputs.occurrence_csv.name, "lord_of_the_rings_occurrences.csv")
        self.assertEqual(
            lotr_outputs.first_map.name,
            "lord_of_the_rings_book_freq_linear.png",
        )

        lotr_log_outputs = book_outputs(lotr, self.output_dir, self.maps_dir, scale="log")
        self.assertEqual(
            lotr_log_outputs.first_map.name,
            "lord_of_the_rings_book_freq_log.png",
        )

    def test_generates_only_missing_outputs(self):
        existing = self.write_book("Existing Book.txt")
        missing_map = self.write_book("Missing Map.txt")
        missing_all = self.write_book("Missing All.txt")

        existing_outputs = book_outputs(existing, self.output_dir, self.maps_dir)
        missing_map_outputs = book_outputs(missing_map, self.output_dir, self.maps_dir)
        missing_all_outputs = book_outputs(missing_all, self.output_dir, self.maps_dir)

        self.output_dir.mkdir(parents=True)
        self.maps_dir.mkdir(parents=True)
        existing_outputs.occurrence_csv.write_text("already present", encoding="utf-8")
        existing_outputs.first_map.write_bytes(b"already present")
        existing_outputs.first_map.with_suffix(".json").write_text("{}", encoding="utf-8")

        missing_map_outputs.occurrence_csv.write_text(
            "normalized_word\nalpha\nalpha\nbeta\n", encoding="utf-8"
        )
        missing_map_outputs.word_metrics.parent.mkdir(parents=True)
        missing_map_outputs.word_metrics.write_text("stale", encoding="utf-8")

        results = generate_missing_outputs(
            self.books_dir,
            self.output_dir,
            self.maps_dir,
            width=4,
        )

        self.assertEqual(
            [result.input_txt.name for result in results],
            ["Existing Book.txt", "Missing All.txt", "Missing Map.txt"],
        )
        self.assertFalse(results[0].csv_created)
        self.assertFalse(results[0].map_created)
        self.assertTrue(results[0].book_stats_created)
        self.assertTrue(results[0].word_metrics_updated)
        self.assertTrue(results[2].word_metrics_updated)
        self.assertTrue(existing_outputs.word_metrics.exists())
        self.assertTrue(missing_all_outputs.occurrence_csv.exists())
        self.assertTrue(missing_all_outputs.first_map.exists())
        self.assertTrue(missing_all_outputs.first_map.with_suffix(".json").exists())
        self.assertTrue(missing_all_outputs.book_stats.exists())
        self.assertTrue(missing_all_outputs.word_metrics.exists())
        self.assertTrue(missing_map_outputs.first_map.exists())
        self.assertTrue(missing_map_outputs.first_map.with_suffix(".json").exists())
        self.assertTrue(missing_map_outputs.book_stats.exists())
        self.assertTrue(missing_map_outputs.word_metrics.exists())
        self.assertNotEqual(missing_map_outputs.word_metrics.read_text(encoding="utf-8"), "stale")


if __name__ == "__main__":
    unittest.main()
