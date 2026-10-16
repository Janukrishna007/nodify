"""Inventory assets, merge labeled YOLO datasets, or bootstrap from teacher predictions."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil

import cv2
import numpy as np
import yaml

WORKSPACE_CACHE = Path(__file__).resolve().parents[1] / ".cache"
os.environ.setdefault("TORCH_HOME", str(WORKSPACE_CACHE / "torch"))
os.environ.setdefault("YOLO_CONFIG_DIR", str(WORKSPACE_CACHE / "ultralytics"))
os.environ.setdefault("TMP", str(WORKSPACE_CACHE / "tmp"))
os.environ.setdefault("TEMP", str(WORKSPACE_CACHE / "tmp"))
os.environ.setdefault("MPLCONFIGDIR", str(WORKSPACE_CACHE / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(WORKSPACE_CACHE / "xdg"))
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(WORKSPACE_CACHE / "pycache"))
for directory in (WORKSPACE_CACHE / "tmp", WORKSPACE_CACHE / "ultralytics" / "Ultralytics"):
    directory.mkdir(parents=True, exist_ok=True)

from ensemble import EnsembleDetector, MODEL_REGISTRY

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ["fire", "smoke", "flood"]
REFERENCES = [
    {"source": "Kaggle", "id": "sayedgamal99/smoke-fire-detection-yolo", "notebook": "TEMPLATE/kaggle.ipynb"},
    {"source": "Roboflow", "workspace": "ai-yolo-detection", "project": "drone-flood-detection-abdic-o5a73", "version": 1,
     "notebook": "TEMPLATE/roboflow_flood.ipynb"},
    {"source": "Roboflow", "workspace": "long-nguyen-hoang-9ecmq", "project": "flood-4oe1x", "version": 1,
     "notebook": "TEMPLATE/roboflow_flood1.ipynb"},
]


def inventory(output):
    import os
    assets = {"datasetReferences": REFERENCES, "datasetConfigs": [], "checkpoints": [], "videos": []}
    for directory, children, files in os.walk(ROOT):
        children[:] = [c for c in children if c not in {".git", ".venv", "node_modules", ".next", "__pycache__", "data", "runs"}]
        for name in files:
            path = Path(directory) / name
            item = {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size}
            if name in {"data.yaml", "data.yml"}:
                assets["datasetConfigs"].append(item)
            elif path.suffix == ".pt":
                assets["checkpoints"].append(item)
            elif path.suffix in {".mp4", ".webm", ".avi", ".mov", ".mkv"}:
                capture = cv2.VideoCapture(str(path))
                ok, _ = capture.read()
                item.update(decodable=ok, frames=int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), fps=capture.get(cv2.CAP_PROP_FPS))
                capture.release()
                assets["videos"].append(item)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(assets, indent=2), encoding="utf-8")
    print(f"Inventory: {output}; {len(assets['datasetConfigs'])} local labeled dataset configs.")


def initialize(output):
    if (output / "data.yaml").exists() or (output / "provenance.json").exists():
        raise ValueError(f"Output must be empty to avoid mixing dataset versions: {output}")
    for split in ("train", "val", "test"):
        for kind in ("images", "labels"):
            (output / split / kind).mkdir(parents=True, exist_ok=True)


def finish(output, provenance, counts):
    if not counts["train"] or not counts["val"]:
        raise ValueError("Both train and validation splits must contain images.")
    config = {"path": str(output.resolve()), "train": "train/images", "val": "val/images", "names": CLASSES}
    if counts["test"]:
        config["test"] = "test/images"
    (output / "data.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    provenance["imageCounts"] = dict(counts)
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(json.dumps(provenance, indent=2))


def bootstrap(videos, output, samples, confidence):
    """Weak supervision only. Validation uses later time blocks separated by an embargo."""
    if not output.exists() or not any(output.iterdir()):
        initialize(output)
    teacher = EnsembleDetector(conf_threshold=confidence, parallel=False)
    teacher.load(MODEL_REGISTRY)
    import torch
    torch.set_num_threads(4)
    counts, labels, sources = Counter(), Counter(), []
    for split in ("train", "val", "test"):
        existing = list((output / split / "images").glob("*"))
        counts[split] = len(existing)
        for annotation in (output / split / "labels").glob("*.txt"):
            for line in annotation.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    labels[f"{split}:{CLASSES[int(line.split()[0])]}" ] += 1
    for source_index, video in enumerate(videos):
        cap = cv2.VideoCapture(str(video))
        total, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
        if total < 30 or fps <= 0:
            raise ValueError(f"Video cannot be decoded: {video}")
        # Do not randomly split neighboring frames. Exclude the middle 20% of each clip.
        indexes = {"train": np.linspace(0, int(total * 0.6) - 1, samples, dtype=int),
                   "val": np.linspace(int(total * 0.8), total - 1, max(4, samples // 4), dtype=int)}
        sources.append({"video": str(video.resolve()), "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                        "frames": total, "fps": fps, "trainRange": [0, 0.6], "valRange": [0.8, 1],
                        "embargoSeconds": round(total * 0.2 / fps, 3)})
        for split, numbers in indexes.items():
            for number in sorted(set(numbers.tolist())):
                name = f"video{source_index}_frame{number}"
                if any((output / split / "images").glob(name + ".*")):
                    continue
                cap.set(cv2.CAP_PROP_POS_FRAMES, number)
                ok, frame = cap.read()
                if not ok:
                    for fallback in range(number - 1, max(-1, number - round(fps) - 1), -1):
                        cap.set(cv2.CAP_PROP_POS_FRAMES, fallback)
                        ok, frame = cap.read()
                        if ok:
                            break
                if not ok:
                    print(f"Skipping unreadable tail frame {number} in {video.name}", flush=True)
                    continue
                if frame.shape[1] > 640:
                    frame = cv2.resize(frame, (640, round(frame.shape[0] * 640 / frame.shape[1])))
                height, width = frame.shape[:2]
                detections = teacher.run(frame)
                rows = []
                for d in detections:
                    x1, y1, x2, y2 = np.clip(d.box, [0, 0, 0, 0], [width, height, width, height])
                    if x2 <= x1 or y2 <= y1:
                        continue
                    cls = CLASSES.index(d.class_name)
                    rows.append(f"{cls} {(x1+x2)/2/width:.6f} {(y1+y2)/2/height:.6f} {(x2-x1)/width:.6f} {(y2-y1)/height:.6f}")
                    labels[f"{split}:{d.class_name}"] += 1
                if not cv2.imwrite(str(output / split / "images" / f"{name}.jpg"), frame):
                    raise IOError("Could not save training frame")
                (output / split / "labels" / f"{name}.txt").write_text("\n".join(rows), encoding="utf-8")
                counts[split] += 1
            print(f"Prepared {video.name}: {split} {len(numbers)} frames", flush=True)
        cap.release()
    missing = [c for c in CLASSES if not labels[f"train:{c}"]]
    if missing:
        raise ValueError(f"Teacher produced no training boxes for {missing}; supply labeled examples.")
    finish(output, {"labelSource": "pseudo-labels from bundled YOLOv8 ensemble", "humanReviewed": False,
                    "teacherConfidence": confidence, "sources": sources, "boxCounts": dict(labels),
                    "limitation": "Validation measures agreement with teachers on later footage, not human-verified accuracy. Same-scene leakage remains possible."}, counts)


def merge(configs, output, max_per_split=None):
    initialize(output)
    counts, labels, fingerprints, component_provenance = Counter(), Counter(), {}, []
    for source_index, config_path in enumerate(configs):
        provenance_path = config_path.parent / "provenance.json"
        if provenance_path.exists():
            component_provenance.append(json.loads(provenance_path.read_text(encoding="utf-8")))
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        names = cfg["names"]
        names = dict(enumerate(names)) if isinstance(names, list) else {int(k): v for k, v in names.items()}
        root = Path(cfg.get("path", config_path.parent))
        if not root.is_absolute():
            root = config_path.parent / root
        if not root.exists():
            # Exported dataset YAML commonly contains a Colab/Kaggle absolute path.
            root = config_path.parent
        for split, key in (("train", "train"), ("val", "val"), ("test", "test")):
            if not cfg.get(key):
                continue
            paths = cfg[key] if isinstance(cfg[key], list) else [cfg[key]]
            for entry in paths:
                folder = root / entry
                if not folder.is_dir():
                    raise ValueError(f"Expected image directory, not a missing path or image-list file: {folder}")
                images = [image for image in sorted(folder.rglob("*"))
                          if image.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}]
                if max_per_split and len(images) > max_per_split:
                    images = [images[index] for index in np.linspace(0, len(images) - 1, max_per_split, dtype=int)]
                for image in images:
                    digest = hashlib.sha256(image.read_bytes()).hexdigest()
                    if digest in fingerprints:
                        if fingerprints[digest] != split:
                            raise ValueError(f"Duplicate image appears across splits: {image}")
                        continue
                    fingerprints[digest] = split
                    parts = list(image.parts)
                    if "images" not in parts:
                        raise ValueError(f"Use YOLO images/labels directory layout: {image}")
                    parts[len(parts) - 1 - parts[::-1].index("images")] = "labels"
                    annotation = Path(*parts).with_suffix(".txt")
                    if not annotation.is_file():
                        raise ValueError(f"Missing annotation (use empty files for confirmed negatives): {annotation}")
                    rows = []
                    for line in annotation.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        fields = line.split()
                        if len(fields) != 5:
                            raise ValueError(f"Expected detection box labels, not polygons: {annotation}")
                        cls, *box = map(float, fields)
                        if not cls.is_integer() or int(cls) not in names or not all(np.isfinite(box)):
                            raise ValueError(f"Invalid label in {annotation}: {line}")
                        x, y, w, h = box
                        x1, y1, x2, y2 = max(0, x - w / 2), max(0, y - h / 2), min(1, x + w / 2), min(1, y + h / 2)
                        if x2 <= x1 or y2 <= y1:
                            raise ValueError(f"Box must overlap the normalized image: {annotation}")
                        x, y, w, h = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
                        name = str(names[int(cls)]).strip().lower().replace(" ", "_")
                        if name in {"water", "non_water", "occlusion"}:
                            continue
                        if name not in CLASSES:
                            raise ValueError(f"Unmapped class {name}; specify a curated mapping before merging.")
                        rows.append(f"{CLASSES.index(name)} {x:.8f} {y:.8f} {w:.8f} {h:.8f}")
                        labels[f"{split}:{name}"] += 1
                    name = f"source{source_index}_{digest[:20]}"
                    destination = output / split / "images" / (name + image.suffix.lower())
                    if not destination.exists():
                        try:
                            os.link(image, destination)
                        except OSError:
                            shutil.copy2(image, destination)
                    (output / split / "labels" / (name + ".txt")).write_text("\n".join(rows), encoding="utf-8")
                    counts[split] += 1
    if any(not labels[f"train:{c}"] for c in CLASSES):
        raise ValueError("Training requires boxes for each of fire, smoke, and flood.")
    human_reviewed = not any(item.get("humanReviewed") is False for item in component_provenance)
    finish(output, {"labelSource": "mixed YOLO annotations",
                    "humanReviewed": human_reviewed,
                    "sources": [str(c.resolve()) for c in configs], "boxCounts": dict(labels),
                    "componentProvenance": component_provenance,
                    "limitation": "Contains pseudo-labeled footage; validate against a human-labeled holdout before deployment."
                    if not human_reviewed else "Annotation review status depends on the supplied datasets."}, counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("inventory")
    scan.add_argument("--output", type=Path, default=ROOT / "docs" / "dataset_inventory.json")
    boot = sub.add_parser("bootstrap")
    boot.add_argument("--videos", type=Path, nargs="+", required=True)
    boot.add_argument("--output", type=Path, required=True)
    boot.add_argument("--samples", type=int, default=48)
    boot.add_argument("--confidence", type=float, default=0.55)
    combine = sub.add_parser("merge")
    combine.add_argument("--configs", type=Path, nargs="+", required=True)
    combine.add_argument("--output", type=Path, required=True)
    combine.add_argument("--max-per-split", type=int, help="Deterministic per-source cap for resource-limited training")
    args = parser.parse_args()
    if args.command == "inventory":
        inventory(args.output)
    elif args.command == "bootstrap":
        if args.samples < 8 or not 0.1 <= args.confidence <= 0.95:
            parser.error("Use at least 8 samples and confidence from 0.1 to 0.95")
        bootstrap(args.videos, args.output, args.samples, args.confidence)
    else:
        merge(args.configs, args.output, args.max_per_split)
