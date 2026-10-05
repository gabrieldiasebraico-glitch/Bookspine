from __future__ import annotations

import math
import unittest

from vocab_mapper.smoothing import SmoothingConfig, config_from_query, smooth_values


class SmoothingTests(unittest.TestCase):
    def test_every_analytical_method_returns_finite_values(self):
        values = [0.0, 0.2, 1.0, -0.5, 0.3, 0.8, -0.2, 0.0, 0.4]
        methods = (
            "moving_average",
            "gaussian",
            "median",
            "savitzky_golay",
            "exponential",
            "adaptive_gaussian",
            "structure_gaussian",
        )
        structures = {
            "sentence": [1, 1, 1, 2, 2, 2, 3, 3, 3],
            "paragraph": [1, 1, 1, 1, 1, 2, 2, 2, 2],
            "chapter": [1] * len(values),
        }
        for method in methods:
            with self.subTest(method=method):
                result = smooth_values(
                    values,
                    SmoothingConfig(method=method, bandwidth=2, window=5),
                    structures,
                )
                self.assertEqual(len(result), len(values))
                self.assertTrue(all(math.isfinite(value) for value in result))

    def test_gaussian_preserves_a_constant_signal(self):
        result = smooth_values(
            [0.35] * 31,
            SmoothingConfig(method="gaussian", bandwidth=4, boundary="reflect"),
        )
        self.assertTrue(all(abs(value - 0.35) < 1e-12 for value in result))

    def test_median_removes_an_isolated_spike(self):
        result = smooth_values(
            [0, 0, 0, 10, 0, 0, 0],
            SmoothingConfig(method="median", window=3),
        )
        self.assertEqual(result[3], 0)

    def test_structure_gaussian_does_not_cross_paragraph_boundaries(self):
        values = [0.0] * 8 + [1.0] * 8
        result = smooth_values(
            values,
            SmoothingConfig(
                method="structure_gaussian",
                bandwidth=10,
                structure="paragraph",
            ),
            {"paragraph": [1] * 8 + [2] * 8},
        )
        self.assertTrue(all(abs(value) < 1e-12 for value in result[:8]))
        self.assertTrue(all(abs(value - 1.0) < 1e-12 for value in result[8:]))

    def test_query_configuration_is_validated_and_zoom_resolved(self):
        config = config_from_query(
            {
                "smoothingMethod": ["gaussian"],
                "smoothingBandwidth": ["12.5"],
                "smoothingWindow": ["20"],
                "smoothingDomain": ["normalized"],
                "smoothingZoomAdaptive": ["1"],
            }
        )
        self.assertEqual(config.bandwidth, 12.5)
        self.assertEqual(config.window % 2, 1)
        resolved = config.resolved_for_zoom(0.01)
        self.assertGreaterEqual(resolved.bandwidth, 100)
        self.assertFalse(resolved.zoom_adaptive)

    def test_unknown_method_is_rejected(self):
        with self.assertRaises(ValueError):
            SmoothingConfig(method="unknown").validated()


if __name__ == "__main__":
    unittest.main()
