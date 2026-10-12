import unittest
import numpy as np

from ensemble import Detection, multi_model_nms
from scoring import GridScorer, render_heatmap


def detection(box=(100, 100, 140, 140), confidence=0.8, name="fire"):
    ids = {"fire": 1, "smoke": 2, "flood": 3}
    return Detection(box, ids[name], name, confidence, name, "test", 0.9)


class ScoringTests(unittest.TestCase):
    def test_empty_video_frames_have_zero_risk_and_unchanged_overlay(self):
        scorer = GridScorer()
        cells = scorer.update([], 800, 600)
        self.assertTrue(all(cell["risk"] == cell["cumulativeRisk"] == 0 for cell in cells))
        frame = np.full((60, 80, 3), 127, dtype=np.uint8)
        np.testing.assert_array_equal(render_heatmap(frame, cells), frame)

    def test_detection_maps_to_correct_cell_and_risk_decays(self):
        scorer = GridScorer()
        cells = scorer.update([detection()], 800, 600)
        cell = cells[1 * 8 + 1]
        self.assertGreater(cell["risk"], 0)
        self.assertEqual(sum(value["risk"] > 0 for value in cells), 1)
        next_cell = scorer.update([], 800, 600)[9]
        self.assertLess(next_cell["risk"], cell["risk"])
        self.assertLess(next_cell["cumulativeRisk"], cell["cumulativeRisk"])
        self.assertEqual(scorer.persistence[0, 1, 1], 0)

    def test_persistence_counts_frames_not_boxes_and_boundaries_are_clamped(self):
        scorer = GridScorer()
        boxes = [detection((790, 590, 810, 610)), detection((790, 590, 810, 610))]
        cells = scorer.update(boxes, 800, 600)
        self.assertEqual(scorer.persistence[0, 5, 7], 1)
        self.assertAlmostEqual(cells[-1]["score"], 2 * 0.9 * 0.8 * 1.05)
        scorer.update(boxes, 800, 600)
        self.assertEqual(scorer.persistence[0, 5, 7], 2)

    def test_nms_removes_duplicate_models_without_merging_disaster_classes(self):
        results = multi_model_nms([detection(confidence=0.8), detection(confidence=0.5), detection(name="smoke")])
        self.assertEqual(len(results), 2)
        self.assertEqual({value.class_name for value in results}, {"fire", "smoke"})
        self.assertEqual(next(value.confidence for value in results if value.class_name == "fire"), 0.8)


if __name__ == "__main__":
    unittest.main()
