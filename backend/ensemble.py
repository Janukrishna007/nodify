"""
DisasterVision — Multi-Model Ensemble Inference
=================================================
Runs all specialist .pt models on the same frame simultaneously,
merges their detections into a unified class space, and applies
NMS across the merged set.

Confirmed model contents (inspected 2026-03-28)
────────────────────────────────────────────────
  best_2.pt                  →  {0: smoke,  1: fire}          nc=2
  smoke_fire_roboflow.pt     →  {0: fire}                     nc=1
  best_flood.pt              →  {0: flood,  1: non_water,
                                  2: occlusion, 3: water}     nc=4
  not-that-best_flood.pt     →  {0: flood}                    nc=1  (disabled)

Unified output class space
──────────────────────────
  0  collapsed_building   (placeholder — add a collapse model later)
  1  fire                 ← best_2 + smoke_fire_roboflow
  2  smoke                ← best_2
  3  flood                ← best_flood (flood + water classes)
  4  heavy_damage         (placeholder)
  5  debris               (placeholder)

  non_water / occlusion   → IGNORED (not disaster-relevant)

Usage
─────
  from ensemble import EnsembleDetector

  detector = EnsembleDetector()
  detector.load()

  detections = detector.run(frame_bgr)
  for d in detections:
      print(d.class_name, d.confidence, d.box)
"""

import threading
import time
import logging
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import numpy as np

log = logging.getLogger("Ensemble")

# ─── Unified class map ────────────────────────────────────────────────────────
# Every model's raw class name gets mapped to one of these unified IDs.
# Add more mappings as you discover what's inside each .pt file.

UNIFIED_CLASSES = {
    0: "collapsed_building",
    1: "fire",
    2: "smoke",
    3: "flood",
    4: "heavy_damage",
    5: "debris",
}

# Raw class name → unified class ID
# Built from confirmed inspection output — exact spellings only.
CLASS_NAME_MAP = {
    # ── best_2.pt ──────────────────────────────────────────
    "fire":       1,
    "smoke":      2,

    # ── smoke_fire_roboflow.pt ─────────────────────────────
    # "fire" already mapped above

    # ── best_flood.pt ──────────────────────────────────────
    "flood":      3,    # class 0 — active flood water
    "water":      None, # Ordinary water is not evidence of a flood.
    "non_water":  None, # class 1 — negative/background, ignore
    "occlusion":  None, # class 2 — occlusion artefact, ignore

    # ── not-that-best_flood.pt (disabled but mapped for safety) ──
    # "flood" already mapped above
}

# Impact weight per unified class (used by GridScorer)
CLASS_WEIGHTS = {
    0: 1.0,   # collapsed_building
    1: 0.9,   # fire
    2: 0.6,   # smoke
    3: 0.7,   # flood
    4: 0.6,   # heavy_damage
    5: 0.3,   # debris
}

# ─── Model registry ───────────────────────────────────────────────────────────
MODEL_REGISTRY = [
    {
        # fire_and_smoke_3.pt — smoke + fire {0: smoke, 1: fire}
        "name":    "smoke_fire_v2",
        "path":    "models_light/fire_and_smoke_3.pt",
        "focus":   [1, 2],
        "enabled": True,
    },
    {
        # smoke_fire_roboflow.pt — fire only  {0: fire}
        "name":    "fire_roboflow",
        "path":    "models_light/smoke_fire_roboflow.pt",
        "focus":   [1],
        "enabled": True,
    },
    {
        # best_flood.pt: flood, non_water, occlusion, water.
        # Only the flood label contributes disaster evidence.
        "name":    "flood_best",
        "path":    "models_light/best_flood.pt",
        "focus":   [3],
        "enabled": True,
    },
    {
        # not-that-best_flood.pt — flood only  {0: flood}
        # Disabled: best_flood.pt already covers this better
        "name":    "flood_backup",
        "path":    "models_light/not-that-best_flood.pt",
        "focus":   [3],
        "enabled": False,
    },
]


def active_model_registry():
    """A published YOLO11 checkpoint takes precedence over the legacy ensemble."""
    checkpoint = Path(os.environ.get("DISASTER_MODEL_PATH", str(Path(__file__).parent / "models" / "disaster_yolo11.pt")))
    if checkpoint.is_file():
        return [{"name": "disaster_yolo11", "path": str(checkpoint.resolve()), "enabled": True}]
    if "DISASTER_MODEL_PATH" in os.environ:
        raise FileNotFoundError(f"Configured disaster checkpoint missing: {checkpoint}")
    return MODEL_REGISTRY


# ─── Detection dataclass ──────────────────────────────────────────────────────
@dataclass
class Detection:
    box:          tuple          # (x1, y1, x2, y2) in pixels
    unified_id:   int            # unified class ID
    class_name:   str            # human-readable unified name
    confidence:   float          # 0.0 – 1.0
    raw_class:    str            # original class name from the model
    source_model: str            # which model produced this detection
    weight:       float          # CLASS_WEIGHTS[unified_id]
    track_id:     Optional[str] = None


# ─── Single-model wrapper ─────────────────────────────────────────────────────
class SpecialistModel:
    """Wraps one YOLO .pt file. Handles loading and per-frame inference."""

    def __init__(self, name: str, path: str, conf_threshold: float = 0.40):
        self.name           = name
        self.path           = path
        self.conf_threshold = conf_threshold
        self.model          = None
        self.raw_names      = {}   # {int → str} as YOLO reports them
        self.loaded         = False

    def load(self):
        try:
            from ultralytics import YOLO
            model_path = Path(self.path)
            if not model_path.is_absolute():
                model_path = Path(__file__).resolve().parent / model_path
            if not model_path.is_file():
                raise FileNotFoundError(f"Model file missing: {model_path}")
            self.model     = YOLO(str(model_path))
            self.raw_names = self.model.names   # e.g. {0: 'fire', 1: 'smoke'}
            self.loaded    = True
            log.info(f"[{self.name}] Loaded — classes: {self.raw_names}")
        except Exception as e:
            log.error(f"[{self.name}] Failed to load: {e}")
            self.loaded = False

    def infer(self, frame_bgr) -> list[Detection]:
        """Run inference on one frame. Returns list of Detection objects."""
        if not self.loaded:
            return []

        try:
            results = self.model(
                frame_bgr,
                conf    = self.conf_threshold,
                verbose = False,
            )[0]
        except Exception as e:
            raise RuntimeError(f"[{self.name}] Inference failed: {e}") from e

        detections = []
        for box in results.boxes:
            raw_id   = int(box.cls)
            raw_name = self.raw_names.get(raw_id, f"class_{raw_id}")
            conf     = float(box.conf)

            # Map raw class name → unified class ID
            normalized_name = raw_name.strip().lower().replace(" ", "_")
            unified_id = CLASS_NAME_MAP.get(normalized_name)
            if unified_id is None and normalized_name in CLASS_NAME_MAP:
                # Explicitly mapped to None (e.g. non_water, occlusion) — skip
                continue
            if unified_id is None:
                log.debug(f"[{self.name}] Unmapped class '{raw_name}' — skipping")
                continue

            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]

            detections.append(Detection(
                box          = (x1, y1, x2, y2),
                unified_id   = unified_id,
                class_name   = UNIFIED_CLASSES[unified_id],
                confidence   = conf,
                raw_class    = raw_name,
                source_model = self.name,
                weight       = CLASS_WEIGHTS[unified_id],
            ))

        return detections


# ─── NMS across detections from multiple models ───────────────────────────────
def multi_model_nms(detections: list[Detection],
                    iou_threshold: float = 0.45) -> list[Detection]:
    """
    Suppress overlapping boxes across all models.

    Two boxes are considered duplicates if:
      - They have the same unified class ID
      - Their IoU exceeds iou_threshold

    Keep the higher-confidence one.
    """
    if not detections:
        return []

    # Group by unified class so we only compare same-class boxes
    by_class: dict[int, list[Detection]] = {}
    for d in detections:
        by_class.setdefault(d.unified_id, []).append(d)

    kept = []
    for cls_id, dets in by_class.items():
        # Sort descending by confidence
        dets = sorted(dets, key=lambda x: x.confidence, reverse=True)
        suppressed = [False] * len(dets)

        for i in range(len(dets)):
            if suppressed[i]:
                continue
            kept.append(dets[i])
            for j in range(i + 1, len(dets)):
                if suppressed[j]:
                    continue
                if _iou(dets[i].box, dets[j].box) > iou_threshold:
                    suppressed[j] = True

    return kept


def _iou(box_a: tuple, box_b: tuple) -> float:
    """Intersection over Union for two (x1,y1,x2,y2) boxes."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0

    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union  = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


# ─── Ensemble Detector ────────────────────────────────────────────────────────
class EnsembleDetector:
    """
    Loads all enabled specialist models and runs them in parallel threads
    on each frame. Merges results with NMS.

    Usage
    ─────
        detector = EnsembleDetector(conf_threshold=0.40, iou_threshold=0.45)
        detector.load()

        # In your pipeline loop:
        detections = detector.run(frame_bgr)
        for d in detections:
            print(f"{d.class_name:20s}  conf={d.confidence:.2f}  "
                  f"box={d.box}  from={d.source_model}")
    """

    def __init__(self,
                 conf_threshold: float = 0.40,
                 iou_threshold:  float = 0.45,
                 parallel:       bool  = True):
        self.conf_threshold = conf_threshold
        self.iou_threshold  = iou_threshold
        self.parallel       = parallel   # False = sequential (easier debugging)
        self.models: list[SpecialistModel] = []

        # Diagnostics
        self.last_inference_ms: float = 0.0
        self.frame_count: int = 0

    def load(self, registry: list[dict] = None):
        """Load all enabled models from the registry."""
        registry = registry if registry is not None else active_model_registry()
        self.models = []

        for entry in registry:
            if not entry.get("enabled", True):
                log.info(f"Skipping disabled model: {entry['name']}")
                continue

            m = SpecialistModel(
                name           = entry["name"],
                path           = entry["path"],
                conf_threshold = self.conf_threshold,
            )
            m.load()
            if m.loaded:
                self.models.append(m)
            else:
                raise RuntimeError(f"Required model failed to load: {entry['path']}")

        log.info(f"Ensemble ready — {len(self.models)} models loaded.")
        self._print_class_summary()

    def run(self, frame_bgr) -> list[Detection]:
        """
        Run all models on one frame. Returns merged, NMS-filtered detections.
        """
        t0 = time.perf_counter()

        if self.parallel and len(self.models) > 1:
            all_detections = self._run_parallel(frame_bgr)
        else:
            all_detections = self._run_sequential(frame_bgr)

        merged = multi_model_nms(all_detections, self.iou_threshold)

        self.last_inference_ms = (time.perf_counter() - t0) * 1000
        self.frame_count += 1

        return merged

    def _run_sequential(self, frame_bgr) -> list[Detection]:
        results = []
        for m in self.models:
            results.extend(m.infer(frame_bgr))
        return results

    def _run_parallel(self, frame_bgr) -> list[Detection]:
        """Run each model in its own thread, collect results."""
        results    = [[] for _ in self.models]
        threads    = []

        def _worker(model, idx):
            results[idx] = model.infer(frame_bgr)

        for i, m in enumerate(self.models):
            t = threading.Thread(target=_worker, args=(m, i))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        merged = []
        for r in results:
            merged.extend(r)
        return merged

    def _print_class_summary(self):
        """Print a summary of what each model detects after loading."""
        print("\n" + "═" * 55)
        print("  ENSEMBLE MODEL SUMMARY")
        print("═" * 55)
        for m in self.models:
            raw = list(m.raw_names.values()) if m.raw_names else ["unknown"]
            mapped = []
            for rn in raw:
                uid = CLASS_NAME_MAP.get(rn.strip().lower().replace(" ", "_"))
                unified = UNIFIED_CLASSES.get(uid, "UNMAPPED") if uid is not None else "excluded"
                mapped.append(f"{rn} → {unified}")
            print(f"\n  [{m.name}]")
            print(f"    path   : {m.path}")
            print(f"    classes: {', '.join(mapped)}")
        print("\n" + "═" * 55 + "\n")

    def draw(self, frame_bgr, detections: list[Detection]):
        """
        Draw bounding boxes and labels on a frame.
        Returns the annotated frame (does not modify in place).
        """
        import cv2

        COLOR_MAP = {
            0: (0,   0,   255),   # collapsed — red
            1: (0,   128, 255),   # fire — orange
            2: (128, 128, 128),   # smoke — grey
            3: (255, 180, 0),     # flood — blue-ish
            4: (0,   255, 255),   # heavy_damage — yellow
            5: (180, 180, 180),   # debris — light grey
        }

        out = frame_bgr.copy()
        for d in detections:
            x1, y1, x2, y2 = [int(v) for v in d.box]
            color = COLOR_MAP.get(d.unified_id, (255, 255, 255))
            label = f"{d.class_name} {d.confidence:.2f}" + (f" #{d.track_id}" if d.track_id else "")

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            # Background for text
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(out, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)

        # Inference time overlay
        cv2.putText(out,
                    f"Ensemble {self.last_inference_ms:.0f}ms | "
                    f"{len(detections)} detections",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (255, 255, 255), 2)
        return out


# ─── Model inspector ─────────────────────────────────────────────────────────
def inspect_models(paths: list[str] = None):
    """Prints the raw class names inside each .pt file."""
    from ultralytics import YOLO

    if paths is None:
        paths = [e["path"] for e in MODEL_REGISTRY]

    print("\n" + "═" * 55)
    print("  MODEL INSPECTION")
    print("═" * 55)

    for path in paths:
        print(f"\n  File: {path}")
        try:
            m = YOLO(path)
            print(f"  Classes ({m.model.nc} total): {m.names}")
            # Warn only for truly unmapped — not intentional None skips
            unmapped = [
                name for name in m.names.values()
                if name not in CLASS_NAME_MAP
            ]
            if unmapped:
                print(f"  ⚠ UNMAPPED — add to CLASS_NAME_MAP: {unmapped}")
            else:
                print(f"  ✓ All classes handled")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "═" * 55 + "\n")


# ─── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, os

    # ── Step 1: inspect (uses MODEL_REGISTRY paths automatically) ─────────
    print("\nStep 1 — Inspecting model class names...\n")
    inspect_models()

    # ── Step 2: load ensemble ─────────────────────────────────────────────
    print("Step 2 — Loading ensemble...\n")
    detector = EnsembleDetector(conf_threshold=0.40, parallel=True)
    detector.load()

    # ── Step 3: run on test image ─────────────────────────────────────────
    test_image = sys.argv[1] if len(sys.argv) > 1 else None

    if not test_image or not os.path.exists(test_image):
        print("Step 3 — No test image provided.")
        print("  Usage: python ensemble.py path/to/frame.jpg\n")
        sys.exit(0)

    import cv2
    frame = cv2.imread(test_image)
    print(f"Step 3 — Running on {test_image}  "
          f"({frame.shape[1]}×{frame.shape[0]})\n")

    # ── Confidence sweep — find lowest threshold that gets detections ──
    print("  Confidence sweep (to diagnose 0-detection frames):")
    print(f"  {'threshold':>12}   detections")
    print(f"  {'─'*30}")
    for thresh in [0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10, 0.05]:
        sweep_detector = EnsembleDetector(conf_threshold=thresh, parallel=False)
        sweep_detector.models = detector.models   # reuse loaded models
        # temporarily override threshold on each model
        for m in sweep_detector.models:
            m.conf_threshold = thresh
        dets = sweep_detector._run_sequential(frame)
        raw_count = len(dets)
        merged    = multi_model_nms(dets)
        print(f"  {thresh:>12.2f}   {raw_count} raw  →  {len(merged)} after NMS")
    print()

    # Restore threshold and run final
    for m in detector.models:
        m.conf_threshold = detector.conf_threshold
    detections = detector.run(frame)

    print(f"  Final ({detector.conf_threshold} threshold): "
          f"{len(detections)} detections  ({detector.last_inference_ms:.0f}ms)\n")

    for d in detections:
        print(f"  {d.class_name:20s}  conf={d.confidence:.2f}  "
              f"box=({int(d.box[0])},{int(d.box[1])},"
              f"{int(d.box[2])},{int(d.box[3])})  "
              f"from={d.source_model}")

    out_frame = detector.draw(frame, detections)
    cv2.imwrite("ensemble_test_output.jpg", out_frame)
    print("\n  Saved → ensemble_test_output.jpg")
