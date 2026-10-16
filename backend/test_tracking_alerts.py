import os
import unittest
from unittest.mock import patch

import numpy as np

from alerts import AlertEngine, email_configured, intensity_level
from ensemble import Detection
from scoring import GridScorer
from tracking import DisasterTracker


def detection(name="fire", confidence=0.9, box=(10, 10, 50, 50)):
    ids = {"fire": 1, "smoke": 2, "flood": 3}
    weights = {"fire": 0.9, "smoke": 0.6, "flood": 0.7}
    return Detection(box, ids[name], name, confidence, name, "test", weights[name])


class TrackingAndAlertTests(unittest.TestCase):
    def test_bytetrack_assigns_stable_identity(self):
        tracker = DisasterTracker(fps=25, confidence=0.4)
        first = detection()
        tracker.update([first], (100, 100))
        second = detection(box=(11, 10, 51, 50))
        tracker.update([second], (100, 100))
        self.assertIsNotNone(second.track_id)
        self.assertEqual(tracker.counts()["fire"], 1)

    def test_alert_requires_persistent_evidence_and_cooldown(self):
        engine = AlertEngine(min_risk=0.1, persistence=3, cooldown=60)
        scorer = GridScorer()
        detections = [detection()]
        self.assertEqual(engine.update(detections, scorer.update(detections, 100, 100), 0, 0, "s"), [])
        self.assertEqual(engine.update(detections, scorer.update(detections, 100, 100), 1, 1, "s"), [])
        events = engine.update(detections, scorer.update(detections, 100, 100), 2, 2, "s")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "fire")
        self.assertEqual(engine.update(detections, scorer.update(detections, 100, 100), 3, 3, "s"), [])

    def test_intensity_thresholds_and_email_configuration(self):
        self.assertEqual([intensity_level(x) for x in (0, .35, .65, .85)], ["low", "moderate", "high", "critical"])
        with patch.dict(os.environ, {"ALERT_SMTP_HOST": "host", "ALERT_EMAIL_FROM": "a@b", "ALERT_EMAIL_TO": "c@d"}, clear=True):
            self.assertTrue(email_configured())


if __name__ == "__main__":
    unittest.main()
