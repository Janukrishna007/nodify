"""Class-separated ByteTrack association for merged specialist or YOLO11 boxes."""
from types import SimpleNamespace

import numpy as np
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker

from scoring import SUPPORTED_CLASSES


class DisasterTracker:
    def __init__(self, fps=25, frame_skip=1, confidence=0.45):
        args = SimpleNamespace(track_high_thresh=confidence, track_low_thresh=0.1,
                               new_track_thresh=confidence, track_buffer=30,
                               match_thresh=0.8, fuse_score=True)
        # track_buffer is expressed in analyzed frames, so scale it to preserve
        # roughly the same one-second occlusion window when frames are skipped.
        args.track_buffer = max(1, round(fps / frame_skip))
        self.trackers = {name: BYTETracker(args) for name in SUPPORTED_CLASSES}
        self.seen = {name: set() for name in SUPPORTED_CLASSES}

    def update(self, detections, shape):
        for name, tracker in self.trackers.items():
            selected = [d for d in detections if d.class_name == name]
            data = np.asarray([(*d.box, d.confidence, d.unified_id) for d in selected],
                              dtype=np.float32).reshape(-1, 6)
            tracks = tracker.update(Boxes(data, shape))
            for track in tracks:
                index = int(track[-1])
                if 0 <= index < len(selected):
                    identity = f"{name}:{int(track[4])}"
                    selected[index].track_id = identity
                    self.seen[name].add(identity)
        return detections

    def counts(self):
        return {name: len(ids) for name, ids in self.seen.items()}
