import csv
import shutil
import unittest
from pathlib import Path

import tifffile

from vocab_mapper.plot_pyramidal_tiff import render_pyramidal_map


class PyramidalTiffTests(unittest.TestCase):
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
