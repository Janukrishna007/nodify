"""Train and validate YOLO11, then atomically publish the checkpoint to the backend."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

BASE = Path(__file__).resolve().parent
WORKSPACE_CACHE = BASE.parent / ".cache"
os.environ.setdefault("TORCH_HOME", str(WORKSPACE_CACHE / "torch"))
os.environ.setdefault("YOLO_CONFIG_DIR", str(WORKSPACE_CACHE / "ultralytics"))
os.environ.setdefault("TMP", str(WORKSPACE_CACHE / "tmp"))
os.environ.setdefault("TEMP", str(WORKSPACE_CACHE / "tmp"))
os.environ.setdefault("MPLCONFIGDIR", str(WORKSPACE_CACHE / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(WORKSPACE_CACHE / "xdg"))
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(WORKSPACE_CACHE / "pycache"))
for directory in (WORKSPACE_CACHE / "tmp", WORKSPACE_CACHE / "ultralytics" / "Ultralytics"):
    directory.mkdir(parents=True, exist_ok=True)

import torch
from ultralytics import YOLO
import yaml


def train(args):
    config = yaml.safe_load(args.data.read_text(encoding="utf-8"))
    names = config.get("names")
    names = list(names.values()) if isinstance(names, dict) else names
    if names != ["fire", "smoke", "flood"]:
        raise ValueError("Prepare the dataset first; expected class order fire, smoke, flood.")
    if args.epochs < 1 or args.batch < 1 or args.imgsz < 128:
        raise ValueError("Use positive epochs/batch and image size >= 128.")
    torch.set_num_threads(4)
    model = YOLO(args.base)
    if "C3k2" not in str(model.model):
        raise ValueError("Base checkpoint must use YOLO11 architecture.")
    model.train(data=str(args.data.resolve()), epochs=args.epochs, imgsz=args.imgsz,
                batch=args.batch, device=args.device, workers=0, seed=42,
                deterministic=True, project=str(BASE / "runs"), name=args.name,
                patience=15, cache=False, plots=True)
    run = Path(model.trainer.save_dir)
    checkpoint = run / "weights" / "best.pt"
    trained = YOLO(str(checkpoint))
    metrics = trained.val(data=str(args.data.resolve()), imgsz=args.imgsz,
                          device=args.device, workers=0, plots=True,
                          project=str(BASE / "runs"), name=args.name + "-final-val")
    provenance_path = args.data.parent / "provenance.json"
    metadata = {"architecture": "YOLO11", "createdAt": datetime.now(timezone.utc).isoformat(),
                "classes": trained.names, "epochsRequested": args.epochs, "imageSize": args.imgsz,
                "device": args.device, "dataset": str(args.data.resolve()), "runDirectory": str(run),
                "metrics": {k: float(v) for k, v in metrics.results_dict.items()},
                "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                "provenance": json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else None,
                "releaseStatus": "bootstrap; requires human-labeled evaluation" if provenance_path.exists() and
                                 ("pseudo-labels" in provenance_path.read_text() or '"humanReviewed": false' in provenance_path.read_text())
                                 else "trained; evaluate for deployment"}
    args.publish.parent.mkdir(parents=True, exist_ok=True)
    temp = args.publish.with_suffix(".tmp")
    shutil.copy2(checkpoint, temp)
    temp.replace(args.publish)
    args.publish.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Published trained YOLO11: {args.publish}\nStatus: {metadata['releaseStatus']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--base", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--name", default="disaster-yolo11")
    parser.add_argument("--publish", type=Path, default=BASE / "models" / "disaster_yolo11.pt")
    train(parser.parse_args())
