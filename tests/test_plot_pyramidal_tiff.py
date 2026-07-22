import csv
import shutil
import unittest
from pathlib import Path

import tifffile

from vocab_mapper.plot_pyramidal_tiff import render_pyramidal_map


class PyramidalTiffTests(unittest.TestCase):
    def test_ngram_frequency_uses_each_word_class_maximum(self):
        temp_path = Path("output") / "test_pyramidal_tiff_ngram"
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True)
        input_csv = temp_path / "occurrences.csv"
        output_tiff = temp_path / "map.ome.tif"

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
                        "normalized_word": "house",
                        "word_class": "semantic",
                        "fic_ngram_total_freq": "0.25",
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

        metadata = render_pyramidal_map(
            input_csv,
            output_tiff,
            width=256,
            metric="fic_ngram_total_freq",
            scale="linear",
            compression="deflate",
        )

        self.assertEqual(metadata["frequency_scale_reference"], "word_class_maximum")
        with tifffile.TiffFile(output_tiff) as tiff:
            pixels = tiff.pages[0].asarray()
            self.assertEqual(tuple(pixels[:, 0]), (255, 128, 255, 128))

        shutil.rmtree(temp_path, ignore_errors=True)

    def test_renders_tiled_compressed_pyramidal_bigtiff(self):
        temp_path = Path("output") / "test_pyramidal_tiff"
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True)
        input_csv = temp_path / "occurrences.csv"
        output_tiff = temp_path / "map.ome.tif"

        with input_csv.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["normalized_word", "book_avg_dev"],
            )
            writer.writeheader()
            for index in range(600):
                writer.writerow(
                    {
                        "normalized_word": f"word{index}",
                        "book_avg_dev": "-1" if index % 2 else "1",
                    }
                )

        metadata = render_pyramidal_map(
            input_csv,
            output_tiff,
            width=512,
            metric="book_avg_dev",
            scale="linear",
            compression="deflate",
        )

        self.assertEqual(metadata["format"], "pyramidal tiled compressed BigTIFF")
        self.assertTrue(output_tiff.exists())
        with output_tiff.open("rb") as tiff_file:
            self.assertEqual(tiff_file.read(4), b"II+\x00")

        with tifffile.TiffFile(output_tiff) as tiff:
            self.assertEqual(tiff.pages[0].shape, (600, 512, 3))
            self.assertTrue(tiff.pages[0].is_tiled)
            self.assertGreaterEqual(len(tiff.pages[0].pages), 1)

        shutil.rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
