import csv
import gzip
import shutil
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from vocab_mapper import viewer
from vocab_mapper.smoothing import SmoothingConfig


class ViewerStateConcurrencyTests(unittest.TestCase):
    @staticmethod
    def map_entry(map_id):
        return {
            "id": map_id,
            "csvPath": f"output/{map_id}.csv",
            "metric": "book_freq",
            "scale": "linear",
        }

    def test_loading_one_map_does_not_block_a_different_map(self):
        entries = [self.map_entry("slow"), self.map_entry("fast")]
        slow_started = threading.Event()
        release_slow = threading.Event()
        fast_finished = threading.Event()
        results = {}

        class ControlledLoadedMap:
            def __init__(self, entry):
                self.entry = entry
                if entry["id"] == "slow":
                    slow_started.set()
                    release_slow.wait(2)

        with patch.object(viewer, "discover_maps", return_value=entries):
            state = viewer.ViewerState()
        with patch.object(viewer, "LoadedMap", ControlledLoadedMap):
            slow_thread = threading.Thread(
                target=lambda: results.setdefault("slow", state.load("slow"))
            )

            def load_fast():
                results["fast"] = state.load("fast")
                fast_finished.set()

            fast_thread = threading.Thread(target=load_fast)
            slow_thread.start()
            self.assertTrue(slow_started.wait(1))
            fast_thread.start()
            try:
                self.assertTrue(
                    fast_finished.wait(1),
                    "A different map was blocked by the slow map load.",
                )
            finally:
                release_slow.set()
                slow_thread.join(2)
                fast_thread.join(2)

        self.assertFalse(slow_thread.is_alive())
        self.assertFalse(fast_thread.is_alive())
        self.assertEqual(set(results), {"slow", "fast"})

    def test_concurrent_requests_for_one_map_share_one_load(self):
        entry = self.map_entry("shared")
        load_started = threading.Event()
        release_load = threading.Event()
        construction_count = 0
        count_lock = threading.Lock()
        results = []

        class ControlledLoadedMap:
            def __init__(self, loaded_entry):
                nonlocal construction_count
                self.entry = loaded_entry
                with count_lock:
                    construction_count += 1
                load_started.set()
                release_load.wait(2)

        with patch.object(viewer, "discover_maps", return_value=[entry]):
            state = viewer.ViewerState()
        with patch.object(viewer, "LoadedMap", ControlledLoadedMap):
            first = threading.Thread(target=lambda: results.append(state.load("shared")))
            second = threading.Thread(target=lambda: results.append(state.load("shared")))
            first.start()
            self.assertTrue(load_started.wait(1))
            second.start()
            try:
                second.join(0.1)
                self.assertTrue(second.is_alive())
            finally:
                release_load.set()
                first.join(2)
                second.join(2)

        self.assertEqual(construction_count, 1)
        self.assertEqual(len(results), 2)
        self.assertIs(results[0], results[1])

    def test_refresh_preserves_unchanged_loaded_maps(self):
        original_entry = self.map_entry("cached")
        with patch.object(viewer, "discover_maps", return_value=[original_entry]):
            state = viewer.ViewerState()

        class CachedMap:
            def __init__(self, entry):
                self.entry = entry

        cached = CachedMap(original_entry)
        cached.entry["totalRows"] = 123
        state._loaded["cached"] = cached
        refreshed_entry = {**original_entry, "book": "Updated display name"}

        with patch.object(viewer, "discover_maps", return_value=[refreshed_entry]):
            maps = state.refresh()

        self.assertIs(state.load("cached"), cached)
        self.assertIs(cached.entry, maps[0])
        self.assertEqual(cached.entry["book"], "Updated display name")
        self.assertEqual(cached.entry["totalRows"], 123)

        changed_entry = {**refreshed_entry, "scale": "log"}
        with patch.object(viewer, "discover_maps", return_value=[changed_entry]):
            state.refresh()
        with patch.object(viewer, "LoadedMap", CachedMap):
            replacement = state.load("cached")

        self.assertIsNot(replacement, cached)

    def test_concurrent_color_requests_share_one_mode_calculation(self):
        loaded = viewer.LoadedMap.__new__(viewer.LoadedMap)
        loaded.rows = [{"normalized_word": "word", "word_class": "semantic"}]
        loaded.metric = "book_freq"
        loaded.scale = "linear"
        loaded._mode_cache = {}
        loaded._mode_lock = threading.Lock()
        calculation_started = threading.Event()
        release_calculation = threading.Event()
        calculation_count = 0
        count_lock = threading.Lock()
        results = []

        def controlled_metric_values(rows, metric, class_discrimination, frequency_basis="token"):
            nonlocal calculation_count
            with count_lock:
                calculation_count += 1
            calculation_started.set()
            release_calculation.wait(2)
            return [1.0]

        with patch.object(viewer, "metric_values", controlled_metric_values):
            first = threading.Thread(
                target=lambda: results.append(loaded._values_and_colors(False))
            )
            second = threading.Thread(
                target=lambda: results.append(loaded._values_and_colors(False))
            )
            first.start()
            self.assertTrue(calculation_started.wait(1))
            second.start()
            try:
                second.join(0.1)
                self.assertTrue(second.is_alive())
            finally:
                release_calculation.set()
                first.join(2)
                second.join(2)

        self.assertEqual(calculation_count, 1)
        self.assertEqual(len(results), 2)
        self.assertIs(results[0], results[1])


class ViewerGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp_path = Path("output") / f"test_viewer_generation_{self._testMethodName}"
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        self.original_paths = {
            "DATA_NGRAM_DIR": viewer.DATA_NGRAM_DIR,
            "GOOGLE_NGRAM_GZ": viewer.GOOGLE_NGRAM_GZ,
            "GOOGLE_NGRAM_TOTALCOUNTS": viewer.GOOGLE_NGRAM_TOTALCOUNTS,
            "OUTPUT_MAPS_DIR": viewer.OUTPUT_MAPS_DIR,
            "OUTPUT_CSV_DIR": viewer.OUTPUT_CSV_DIR,
            "USER_TEXT_DIR": viewer.USER_TEXT_DIR,
            "GENERATED_CSV_DIR": viewer.GENERATED_CSV_DIR,
            "GENERATED_MAPS_DIR": viewer.GENERATED_MAPS_DIR,
            "WORD_STATS_DIR": viewer.WORD_STATS_DIR,
        }
        viewer.DATA_NGRAM_DIR = self.temp_path / "ngram_frequencies"
        viewer.GOOGLE_NGRAM_GZ = self.temp_path / "google_ngram" / "1-00000-of-00001.gz"
        viewer.GOOGLE_NGRAM_TOTALCOUNTS = self.temp_path / "google_ngram" / "totalcounts-1"
        viewer.OUTPUT_MAPS_DIR = self.temp_path / "maps"
        viewer.OUTPUT_CSV_DIR = self.temp_path / "csv"
        viewer.USER_TEXT_DIR = self.temp_path / "source_texts"
        viewer.GENERATED_CSV_DIR = viewer.OUTPUT_CSV_DIR / "generated"
        viewer.GENERATED_MAPS_DIR = viewer.OUTPUT_MAPS_DIR / "generated"
        viewer.WORD_STATS_DIR = self.temp_path / "word_metrics"
        viewer.STATE.refresh()

    def tearDown(self):
        for name, path in self.original_paths.items():
            setattr(viewer, name, path)
        viewer.STATE.refresh()
        shutil.rmtree(self.temp_path, ignore_errors=True)

    def write_ngram_file(self, name):
        viewer.DATA_NGRAM_DIR.mkdir(parents=True, exist_ok=True)
        path = viewer.DATA_NGRAM_DIR / name
        path.write_text("word,ngram_f\nThe,0.5\nhouse,0.1\n", encoding="utf-8")
        return path

    def write_google_ngram_fixture(self):
        viewer.GOOGLE_NGRAM_GZ.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(viewer.GOOGLE_NGRAM_GZ, "wt", encoding="utf-8") as gz_file:
            gz_file.write("house\t1998,10\t2000,20\n")
            gz_file.write("quiet\t2010,5\n")
            gz_file.write("the\t1998,60\t2000,60\t2010,60\n")
        viewer.GOOGLE_NGRAM_TOTALCOUNTS.write_text(
            "1998,100\t2000,100\t2010,100",
            encoding="utf-8",
        )

    def read_ngram_words(self, path):
        with path.open("r", encoding="utf-8", newline="") as csv_file:
            return {
                row["word"]: row["ngram_f"]
                for row in csv.DictReader(csv_file)
            }

    def test_interactive_viewer_uses_class_and_global_frequency_maxima(self):
        input_csv = self.temp_path / "class_scaling.csv"
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

        loaded_map = viewer.LoadedMap(
            {
                "csvPath": input_csv.as_posix(),
                "metric": "fic_ngram_total_freq",
                "scale": "linear",
            }
        )

        _values, class_colors = loaded_map._values_and_colors(True)
        _values, global_colors = loaded_map._values_and_colors(False)
        self.assertEqual(
            class_colors,
            [(255, 255, 255), (128, 128, 128), (255, 255, 255), (128, 128, 128)],
        )
        self.assertEqual(
            global_colors,
            [(159, 159, 159), (80, 80, 80), (255, 255, 255), (128, 128, 128)],
        )

    def test_interactive_viewport_applies_gaussian_smoothing_before_coloring(self):
        input_csv = self.temp_path / "smoothing.csv"
        with input_csv.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "word",
                    "normalized_word",
                    "word_class",
                    "paragraph_number",
                    "book_avg_dev",
                ],
            )
            writer.writeheader()
            for index, value in enumerate([-1.0] * 10 + [1.0] * 10):
                writer.writerow(
                    {
                        "word": f"word{index}",
                        "normalized_word": f"word{index}",
                        "word_class": "semantic",
                        "paragraph_number": 1,
                        "book_avg_dev": value,
                    }
                )

        loaded_map = viewer.LoadedMap(
            {
                "csvPath": input_csv.as_posix(),
                "metric": "book_avg_dev",
                "scale": "linear",
            }
        )
        result = loaded_map.viewport(
            0,
            20,
            100,
            smoothing=SmoothingConfig(
                method="gaussian",
                bandwidth=2,
                domain="normalized",
            ),
        )

        self.assertEqual(result["smoothing"]["method"], "gaussian")
        self.assertEqual(result["mode"], "rows")
        self.assertIn("smoothedDisplayValue", result["samples"][9])
        self.assertGreater(result["samples"][9]["smoothedDisplayValue"], -1)
        self.assertLess(result["samples"][10]["smoothedDisplayValue"], 1)

    def test_discovers_book_only_and_available_ngram_corpora(self):
        self.write_ngram_file("eng_fiction_2019_all_ngram_frequencies.csv")
        self.write_ngram_file("eng_fiction_2019_recent_1999_2019_ngram_frequencies.csv")
        book_specific_dir = viewer.DATA_NGRAM_DIR / "beowulf"
        book_specific_dir.mkdir(parents=True)
        (book_specific_dir / "eng_fiction_2019_all_ngram_frequencies.csv").write_text(
            "word,ngram_f\nbeowulf,0.1\n",
            encoding="utf-8",
        )

        payload = viewer.generation_options_payload()
        corpora = {corpus["id"]: corpus for corpus in payload["corpora"]}

        self.assertIn("book_only", corpora)
        self.assertIn("eng_fiction_2019", corpora)
        self.assertNotIn("beowulf", corpora)
        self.assertIn("Total", corpora["eng_fiction_2019"]["sources"])
        self.assertIn("1999-2019", corpora["eng_fiction_2019"]["sources"])

    def test_marks_prepublication_as_dynamic_when_archive_is_available(self):
        self.write_ngram_file("eng_fiction_2019_all_ngram_frequencies.csv")
        self.write_ngram_file("eng_fiction_2019_recent_1999_2019_ngram_frequencies.csv")
        self.write_google_ngram_fixture()

        payload = viewer.generation_options_payload()
        corpora = {corpus["id"]: corpus for corpus in payload["corpora"]}

        self.assertIn("-10y", corpora["eng_fiction_2019"]["dynamicSources"])

    def test_generates_selected_book_maps_from_uploaded_text(self):
        result = viewer.generate_maps_from_payload(
            {
                "filename": "Unit Upload.txt",
                "content": "The house was quiet. The house returned.",
                "corpusId": "book_only",
                "metrics": ["book_freq", "book_avg_dev"],
                "width": 300,
                "scale": "linear",
            }
        )

        self.assertEqual(len(result["maps"]), 2)
        self.assertTrue((viewer.PROJECT_ROOT / result["occurrenceCsv"]).exists())
        self.assertTrue((viewer.PROJECT_ROOT / result["wordMetricsCsv"]).exists())
        self.assertTrue((viewer.PROJECT_ROOT / result["bookStats"]).exists())
        self.assertIn("output/test_viewer_generation_", result["wordMetricsCsv"])
        self.assertIn("/word_metrics/", result["wordMetricsCsv"])
        self.assertEqual({entry["book"] for entry in result["maps"]}, {"Unit Upload"})
        self.assertEqual({entry["metric"] for entry in result["maps"]}, {"book_freq", "book_avg_dev"})
        self.assertEqual({entry["scale"] for entry in result["maps"]}, {"linear"})
        self.assertTrue(all(str(entry["mapType"]).endswith("_linear") for entry in result["maps"]))
        self.assertTrue(all(str(entry["metadataPath"]).endswith("_linear.pyramid.ome.json") for entry in result["maps"]))
        self.assertTrue(result["firstMapId"])

    def test_map_management_renames_excludes_and_duplicates_maps(self):
        result = viewer.generate_maps_from_payload(
            {
                "filename": "Managed Upload.txt",
                "content": "The house was quiet. The house returned.",
                "corpusId": "book_only",
                "metrics": ["book_freq"],
                "width": 300,
                "scale": "linear",
            }
        )
        map_id = result["maps"][0]["id"]

        renamed = viewer.rename_map_entry(map_id, "Renamed Book", "Renamed Map")
        self.assertEqual(renamed["book"], "Renamed Book")
        self.assertEqual(renamed["mapType"], "Renamed Map_linear")

        excluded = viewer.set_map_excluded(map_id, True)
        self.assertTrue(excluded["excluded"])
        self.assertNotIn(map_id, {entry["id"] for entry in viewer.discover_maps()})
        self.assertIn(map_id, {entry["id"] for entry in viewer.manage_maps_payload()["maps"]})

        restored = viewer.set_map_excluded(map_id, False)
        self.assertFalse(restored["excluded"])
        duplicated = viewer.duplicate_map_entry(map_id)
        self.assertNotEqual(duplicated["id"], map_id)
        self.assertEqual(duplicated["book"], "Renamed Book")
        self.assertIn("Copy", duplicated["mapType"])
        self.assertTrue(duplicated["mapType"].endswith("_linear"))

    def test_log_generated_map_uses_log_suffix(self):
        result = viewer.generate_maps_from_payload(
            {
                "filename": "Log Upload.txt",
                "content": "The house was quiet. The house returned.",
                "corpusId": "book_only",
                "metrics": ["book_freq"],
                "width": 300,
                "scale": "log",
            }
        )

        self.assertEqual(result["maps"][0]["scale"], "log")
        self.assertTrue(result["maps"][0]["mapType"].endswith("_log"))
        self.assertTrue(result["maps"][0]["metadataPath"].endswith("_log.pyramid.ome.json"))

    def test_map_management_exports_tiff_png_and_pdf(self):
        result = viewer.generate_maps_from_payload(
            {
                "filename": "Export Upload.txt",
                "content": "The house was quiet. The house returned.",
                "corpusId": "book_only",
                "metrics": ["book_freq"],
                "width": 32,
                "scale": "linear",
            }
        )
        map_id = result["maps"][0]["id"]

        tiff_export = viewer.export_map_entry(map_id, "tiff")
        self.assertEqual(tiff_export.content_type, "image/tiff")
        self.assertTrue(tiff_export.path.exists())

        png_export = viewer.export_map_entry(map_id, "png")
        self.assertEqual(png_export.content_type, "image/png")
        self.assertTrue(png_export.data.startswith(b"\x89PNG"))

        pdf_export = viewer.export_map_entry(map_id, "pdf")
        self.assertEqual(pdf_export.content_type, "application/pdf")
        self.assertTrue(pdf_export.data.startswith(b"%PDF"))

    def test_backfills_missing_ngram_words_for_uploaded_text(self):
        total_path = self.write_ngram_file("eng_fiction_2019_all_ngram_frequencies.csv")
        recent_path = self.write_ngram_file("eng_fiction_2019_recent_1999_2019_ngram_frequencies.csv")
        self.write_google_ngram_fixture()

        result = viewer.generate_maps_from_payload(
            {
                "filename": "Unit Upload 2001.txt",
                "content": "The house was quiet.",
                "corpusId": "eng_fiction_2019",
                "metrics": ["fic_ngram_total_freq", "fic_ngram_99_19_freq"],
                "width": 300,
                "scale": "linear",
            }
        )

        self.assertEqual({entry["metric"] for entry in result["maps"]}, {"fic_ngram_total_freq", "fic_ngram_99_19_freq"})
        self.assertTrue(all(str(entry["metadataPath"]).endswith("_linear.pyramid.ome.json") for entry in result["maps"]))
        total_words = self.read_ngram_words(total_path)
        recent_words = self.read_ngram_words(recent_path)
        self.assertEqual(total_words["quiet"], "0.0166666666667")
        self.assertEqual(recent_words["quiet"], "0.025")
        self.assertEqual(total_words["was"], "0")
        added = {entry["source"]: entry["addedWords"] for entry in result["ngramBackfill"]}
        self.assertEqual(added["Total"], 2)
        self.assertEqual(added["1999-2019"], 2)

    def test_generates_dynamic_prepublication_source_for_uploaded_text(self):
        self.write_ngram_file("eng_fiction_2019_all_ngram_frequencies.csv")
        self.write_ngram_file("eng_fiction_2019_recent_1999_2019_ngram_frequencies.csv")
        self.write_google_ngram_fixture()

        result = viewer.generate_maps_from_payload(
            {
                "filename": "Unit Upload.txt",
                "content": "The house was quiet.",
                "corpusId": "eng_fiction_2019",
                "metrics": ["fic_ngram_prepub_10y_freq"],
                "publicationYear": 2001,
                "width": 300,
                "scale": "linear",
            }
        )

        self.assertEqual({entry["metric"] for entry in result["maps"]}, {"fic_ngram_prepub_10y_freq"})
        self.assertTrue(result["maps"][0]["mapType"].endswith("_linear"))
        prepub_entry = next(entry for entry in result["ngramBackfill"] if entry["source"] == "-10y")
        prepub_path = viewer.PROJECT_ROOT / str(prepub_entry["path"]).replace("/", "\\")
        prepub_words = self.read_ngram_words(prepub_path)
        self.assertEqual(prepub_words["house"], "0.15")
        self.assertEqual(prepub_words["quiet"], "0")

    def test_single_chapter_segment_is_not_valid_chapter_structure(self):
        self.assertFalse(viewer._has_valid_chapter_structure([viewer.Segment(0, 100, 1)]))
        self.assertTrue(
            viewer._has_valid_chapter_structure(
                [viewer.Segment(0, 50, 1), viewer.Segment(50, 100, 2)]
            )
        )


if __name__ == "__main__":
    unittest.main()
