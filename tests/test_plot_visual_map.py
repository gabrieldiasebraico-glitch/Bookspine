import csv
import shutil
import unittest
from pathlib import Path

from PIL import Image

from vocab_mapper.plot_visual_map import render_frequency_map


class PlotVisualMapTests(unittest.TestCase):
    def test_renders_one_pixel_row_per_word_occurrence(self):
        temp_path = Path("output") / "test_plot_visual_map"
        shutil.rmtree(temp_path, ignore_errors=True)

    def test_renders_deviation_column_with_red_white_blue_palette(self):
        temp_path = Path("output") / "test_plot_visual_map_deviation"
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True)
        input_csv = temp_path / "occurrences.csv"
        output_png = temp_path / "deviation.png"

        with input_csv.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["normalized_word", "book_avg_dev"],
            )
            writer.writeheader()
            writer.writerows(
                [
                    {"normalized_word": "rare", "book_avg_dev": "-2"},
                    {"normalized_word": "average", "book_avg_dev": "0"},
                    {"normalized_word": "common", "book_avg_dev": "2"},
                ]
            )

        metadata = render_frequency_map(
            input_csv,
            output_png,
            width=20,
            scale="linear",
            metric="book_avg_dev",
        )

        self.assertEqual(metadata["palette"], "red-white-blue")
        self.assertEqual(metadata["max_abs_value"], 2)

        with Image.open(output_png) as image:
            self.assertEqual(image.size, (20, 3))
            self.assertEqual(image.getpixel((0, 0)), (220, 0, 0))
            self.assertEqual(image.getpixel((0, 1)), (255, 255, 255))
            self.assertEqual(image.getpixel((0, 2)), (0, 68, 220))

        shutil.rmtree(temp_path, ignore_errors=True)

    def test_renders_ngram_column_scaled_to_each_word_class_maximum(self):
        temp_path = Path("output") / "test_plot_visual_map_ngram"
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True)
        input_csv = temp_path / "occurrences.csv"
        output_png = temp_path / "ngram.png"

        with input_csv.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["normalized_word", "word_class", "fic_ngram_total_freq"],
            )
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "normalized_word": "unknown",
                        "word_class": "semantic",
                        "fic_ngram_total_freq": "",
                    },
                    {
                        "normalized_word": "house",
                        "word_class": "semantic",
                        "fic_ngram_total_freq": "0.25",
                    },
                    {
                        "normalized_word": "theory",
                        "word_class": "semantic",
                        "fic_ngram_total_freq": "0.5",
                    },
                    {
                        "normalized_word": "the",
                        "word_class": "functional",
                        "fic_ngram_total_freq": "0.8",
                    },
                    {
                        "normalized_word": "and",
                        "word_class": "functional",
                        "fic_ngram_total_freq": "0.4",
                    },
                ]
            )

        metadata = render_frequency_map(
            input_csv,
            output_png,
            width=20,
            scale="linear",
            metric="fic_ngram_total_freq",
        )

        self.assertEqual(metadata["palette"], "black-white")
        self.assertEqual(metadata["max_value"], 0.8)
        self.assertEqual(metadata["frequency_scale_reference"], "word_class_maximum")

        with Image.open(output_png) as image:
            self.assertEqual(image.size, (20, 5))
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))
            self.assertEqual(image.getpixel((0, 1)), (128, 128, 128))
            self.assertEqual(image.getpixel((0, 2)), (255, 255, 255))
            self.assertEqual(image.getpixel((0, 3)), (255, 255, 255))
            self.assertEqual(image.getpixel((0, 4)), (128, 128, 128))

        shutil.rmtree(temp_path, ignore_errors=True)

    def test_renders_ngram_column_scaled_to_global_maximum_without_classes(self):
        temp_path = Path("output") / "test_plot_visual_map_ngram_global"
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True)
        input_csv = temp_path / "occurrences.csv"
        output_png = temp_path / "ngram.png"

        with input_csv.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["normalized_word", "word_class", "fic_ngram_total_freq"],
            )
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "normalized_word": "theory",
                        "word_class": "semantic",
                        "fic_ngram_total_freq": "0.5",
                    },
                    {
                        "normalized_word": "the",
                        "word_class": "functional",
                        "fic_ngram_total_freq": "0.8",
                    },
                    {
                        "normalized_word": "and",
                        "word_class": "functional",
                        "fic_ngram_total_freq": "0.4",
                    },
                ]
            )

        metadata = render_frequency_map(
            input_csv,
            output_png,
            width=20,
            scale="linear",
            metric="fic_ngram_total_freq",
            class_discrimination=False,
        )

        self.assertEqual(metadata["frequency_scale_reference"], "global_maximum")
        with Image.open(output_png) as image:
            self.assertEqual(image.getpixel((0, 0)), (159, 159, 159))
            self.assertEqual(image.getpixel((0, 1)), (255, 255, 255))
            self.assertEqual(image.getpixel((0, 2)), (128, 128, 128))

        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True)
        input_csv = temp_path / "occurrences.csv"
        output_png = temp_path / "map.png"

        with input_csv.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=["normalized_word"])
            writer.writeheader()
            writer.writerows(
                [
                    {"normalized_word": "the"},
                    {"normalized_word": "house"},
                    {"normalized_word": "the"},
                ]
            )

        metadata = render_frequency_map(input_csv, output_png, width=20, scale="linear")

        self.assertEqual(metadata["width_px"], 20)
        self.assertEqual(metadata["height_px"], 3)
        self.assertTrue(output_png.exists())
        self.assertTrue(output_png.with_suffix(".json").exists())

        with Image.open(output_png) as image:
            self.assertEqual(image.size, (20, 3))
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(image.getpixel((0, 1)), (128, 128, 128))

        shutil.rmtree(temp_path, ignore_errors=True)

    def test_rejects_mad_metric(self):
        temp_path = Path("output") / "test_plot_visual_map_mad"
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True)
        input_csv = temp_path / "occurrences.csv"
        output_png = temp_path / "mad.png"

        with input_csv.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["normalized_word", "Ngrams_Total_frequency_mad"],
            )
            writer.writeheader()
            writer.writerow({"normalized_word": "the", "Ngrams_Total_frequency_mad": "0"})

        with self.assertRaises(ValueError):
            render_frequency_map(
                input_csv,
                output_png,
                width=20,
                scale="linear",
                metric="Ngrams_Total_frequency_mad",
            )

        shutil.rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
