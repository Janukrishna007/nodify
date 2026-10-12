"""Exercise the running upload API with a short clip and the real checkpoints."""
import argparse
import json
from pathlib import Path
import time

import cv2
import numpy as np
import requests

from config import BASE_DIR, DATA_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", default=str(BASE_DIR / "disaster_footage_fixed.mp4"))
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    cap = cv2.VideoCapture(args.video)
    ok, first = cap.read()
    if not ok:
        raise RuntimeError("Validation video could not be decoded")
    DATA_DIR.mkdir(exist_ok=True)
    clip = DATA_DIR / "validation-clip.mp4"
    height, width = first.shape[:2]
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 25, (width, height))
    if not writer.isOpened():
        raise RuntimeError("Could not create validation video")
    frames = 0
    frame = first
    while frames < 30:
        writer.write(frame)
        frames += 1
        ok, frame = cap.read()
        if not ok:
            break
    writer.release()
    cap.release()
    invalid = requests.post(args.url + "/api/analysis", files={"file": ("broken.mp4", b"not a video", "video/mp4")}, timeout=60)
    assert invalid.status_code == 422, invalid.text
    with clip.open("rb") as file:
        response = requests.post(args.url + "/api/analysis", files={"file": ("validation-clip.mp4", file, "video/mp4")},
                                 data={"frame_skip": "3", "confidence": "0.45"}, timeout=120)
    assert response.status_code == 202, response.text
    session_id = response.json()["id"]
    print("Validation session:", session_id, flush=True)
    deadline = time.monotonic() + 300
    previous = None
    while time.monotonic() < deadline:
        session = requests.get(args.url + f"/api/sessions/{session_id}", timeout=60).json()
        progress = (session["status"], session["analyzedFrames"])
        if progress != previous:
            print(progress, session.get("detectionCounts"), flush=True)
            previous = progress
        if session["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(1)
    assert session["status"] == "completed", session
    assert session["analyzedFrames"] == (frames + 2) // 3, session
    report = requests.get(args.url + f"/api/sessions/{session_id}/report", timeout=60).json()
    assert [frame["frameNumber"] for frame in report["frames"]] == list(range(0, frames, 3))
    assert all(len(frame["cells"]) == 48 for frame in report["frames"])
    sample = report["frames"][-1]
    assert all(0 <= cell["risk"] < 1 for cell in sample["cells"])
    images = {}
    for key in ("imageUrl", "heatmapUrl", "cumulativeUrl"):
        response = requests.get(args.url + sample[key], timeout=60)
        assert response.status_code == 200
        image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)
        assert image is not None
        images[key] = image
    if sum(session["detectionCounts"].values()):
        assert any(cell["cumulativeRisk"] > 0 for cell in sample["cells"])
        assert not np.array_equal(images["imageUrl"], images["heatmapUrl"])
    (DATA_DIR / "validation-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS: {frames} input frames, {session['analyzedFrames']} analyzed frames; real model results, report and heatmap images verified.", flush=True)
    print(f"Dashboard: {args.url}/dashboard?session={session_id}", flush=True)


if __name__ == "__main__":
    main()
