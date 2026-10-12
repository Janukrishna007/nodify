"""Local video-analysis API. Run: python -m uvicorn main:app --port 8000."""
import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
import time
from uuid import uuid4

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from config import DATA_DIR, DEFAULT_CONFIDENCE, DEFAULT_FRAME_SKIP, GRID_COLS, GRID_ROWS, MAX_FRAME_WIDTH, MAX_UPLOAD_BYTES
from ensemble import EnsembleDetector, MODEL_REGISTRY
from scoring import GridScorer, SUPPORTED_CLASSES, render_heatmap

log = logging.getLogger("disastervision")
app = FastAPI(title="DisasterVision Video Analysis")
DATA_DIR.mkdir(exist_ok=True)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
lock = threading.RLock()
active_id = None
sessions = {}
cancel_flags = {}
model_info = []


def now():
    return datetime.now(timezone.utc).isoformat()


def save_session(session):
    directory = DATA_DIR / session["id"]
    temp = directory / "session.tmp"
    temp.write_text(json.dumps(session, indent=2), encoding="utf-8")
    temp.replace(directory / "session.json")


for session_file in DATA_DIR.glob("*/session.json"):
    try:
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        if saved["status"] in ("queued", "loading", "processing"):
            saved.update(status="failed", error="Analysis was interrupted by a server restart. Upload the video again.")
            save_session(saved)
        sessions[saved["id"]] = saved
    except (OSError, ValueError, KeyError):
        log.exception("Could not load saved session %s", session_file)


def get_session(session_id):
    if session_id not in sessions:
        raise HTTPException(404, "Session not found")
    return sessions[session_id]


def update_session(session_id, **changes):
    with lock:
        session = get_session(session_id)
        session.update(changes, updatedAt=now())
        save_session(session)


def write_image(path, frame):
    if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85]):
        raise RuntimeError("Could not save analysis frame. Check available disk space.")


def analyze(session_id, video_path):
    global active_id, model_info
    capture = None
    try:
        with lock:
            settings = dict(sessions[session_id])
        update_session(session_id, status="loading")
        detector = EnsembleDetector(conf_threshold=settings["confidence"], parallel=False)
        detector.load()
        import torch
        torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
        with lock:
            model_info = [{"name": m.name, "file": Path(m.path).name, "classes": list(m.raw_names.values())} for m in detector.models]
        # Confirm actual checkpoint labels; never claim unsupported damage classes.
        supported = sorted({d for m in detector.models for n in m.raw_names.values()
                            for d in SUPPORTED_CLASSES if n.strip().lower() == d})
        if set(supported) != set(SUPPORTED_CLASSES):
            raise RuntimeError(f"Bundled checkpoints do not cover the expected classes. Found: {supported}")
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError("Video could not be decoded. Upload a valid MP4, MOV, AVI or WebM file.")
        total = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not 0 < fps < 1000:
            fps = 25.0
        expected = (total + settings["frameSkip"] - 1) // settings["frameSkip"] if total else 0
        update_session(session_id, status="processing", totalFrames=total, fps=fps, expectedSamples=expected,
                       supportedClasses=supported, models=model_info)
        scorer = GridScorer()
        counts = Counter()
        peak_risk = 0.0
        frame_number = 0
        sample_index = 0
        start = time.perf_counter()
        directory = DATA_DIR / session_id
        while not cancel_flags[session_id].is_set():
            ok, frame = capture.read()
            if not ok:
                break
            number = frame_number
            frame_number += 1
            if number % settings["frameSkip"]:
                continue
            if frame.shape[1] > MAX_FRAME_WIDTH:
                scale = MAX_FRAME_WIDTH / frame.shape[1]
                frame = cv2.resize(frame, (MAX_FRAME_WIDTH, max(1, round(frame.shape[0] * scale))))
            height, width = frame.shape[:2]
            detections = detector.run(frame)
            cells = scorer.update(detections, width, height)
            boxes = []
            for index, detection in enumerate(detections):
                counts[detection.class_name] += 1
                x1, y1, x2, y2 = detection.box
                boxes.append({
                    "id": f"{sample_index}-{index}", "type": detection.class_name,
                    "confidence": round(detection.confidence, 6), "weight": detection.weight,
                    "box": [max(0, min(1, value)) for value in [x1 / width, y1 / height, x2 / width, y2 / height]],
                    "sourceModel": detection.source_model,
                })
            root_url = f"/api/sessions/{session_id}/frames/{sample_index}"
            payload = {"index": sample_index, "frameNumber": number, "timestamp": round(number / fps, 3),
                       "width": width, "height": height, "detections": boxes, "cells": cells,
                       "imageUrl": root_url + "/image", "heatmapUrl": root_url + "/heatmap",
                       "cumulativeUrl": root_url + "/cumulative", "inferenceMs": round(detector.last_inference_ms, 1)}
            write_image(directory / f"{sample_index}.jpg", frame)
            write_image(directory / f"{sample_index}-heatmap.jpg", detector.draw(render_heatmap(frame, cells), detections))
            write_image(directory / f"{sample_index}-cumulative.jpg", render_heatmap(frame, cells, cumulative=True))
            (directory / f"{sample_index}.json").write_text(json.dumps(payload), encoding="utf-8")
            sample_index += 1
            peak_risk = max(peak_risk, max(s["risk"] for s in cells))
            update_session(session_id, analyzedFrames=sample_index, latestIndex=sample_index - 1,
                           framesRead=frame_number, progress=min(99.9, frame_number / total * 100) if total else 0,
                           detectionCounts=dict(counts), peakRisk=peak_risk,
                           cumulativeCells=cells, elapsedSeconds=round(time.perf_counter() - start, 2))
        cancelled = cancel_flags[session_id].is_set()
        if not sample_index and not cancelled:
            raise RuntimeError("This video contains no readable frames.")
        if total and frame_number < total - max(2, int(fps)) and not cancelled:
            raise RuntimeError(f"Video decoding stopped early ({frame_number} of {total} frames). Partial results are available.")
        update_session(session_id, status="cancelled" if cancelled else "completed", framesRead=frame_number,
                       progress=(frame_number / total * 100 if total else 0) if cancelled else 100,
                       completedAt=now())
    except Exception as exc:
        log.exception("Analysis failed for %s", session_id)
        update_session(session_id, status="failed", error=str(exc))
    finally:
        if capture is not None:
            capture.release()
        with lock:
            if active_id == session_id:
                active_id = None
            cancel_flags.pop(session_id, None)


@app.get("/api/health")
def health():
    with lock:
        return {"ok": True, "activeSession": active_id, "supportedClasses": list(SUPPORTED_CLASSES),
                "models": model_info or [{"name": entry["name"], "file": Path(entry["path"]).name,
                                         "available": (Path(__file__).parent / entry["path"]).is_file()}
                                        for entry in MODEL_REGISTRY if entry.get("enabled", True)],
                "grid": {"rows": GRID_ROWS, "cols": GRID_COLS}}


@app.post("/api/analysis", status_code=202)
def upload_video(file: UploadFile = File(...), frame_skip: int = Form(DEFAULT_FRAME_SKIP),
                 confidence: float = Form(DEFAULT_CONFIDENCE)):
    global active_id
    if not 1 <= frame_skip <= 60 or not 0.1 <= confidence <= 0.95:
        raise HTTPException(422, "Frame interval must be 1–60 and confidence must be 0.10–0.95.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".mp4", ".mov", ".avi", ".webm", ".mkv", ".m4v"):
        raise HTTPException(422, "Choose an MP4, MOV, AVI, WebM, MKV or M4V video.")
    session_id = uuid4().hex
    with lock:
        if active_id is not None:
            raise HTTPException(409, f"Analysis is already running. Finish or stop session {active_id} first.")
        active_id = session_id
    directory = DATA_DIR / session_id
    directory.mkdir()
    video_path = directory / ("source" + suffix)
    try:
        size = 0
        with video_path.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Maximum upload size is 500 MB.")
                output.write(chunk)
        if not size:
            raise HTTPException(422, "The uploaded file is empty.")
        # Validate input before spending time loading the models.
        cap = cv2.VideoCapture(str(video_path))
        valid, _ = cap.read()
        cap.release()
        if not valid:
            raise HTTPException(422, "This file is not a decodable video. Try exporting it as MP4 (H.264).")
        session = {"id": session_id, "filename": Path(file.filename.replace("\\", "/")).name,
                   "status": "queued", "createdAt": now(), "updatedAt": now(), "frameSkip": frame_skip,
                   "confidence": confidence, "analyzedFrames": 0, "latestIndex": None, "progress": 0,
                   "detectionCounts": {}, "error": None, "grid": {"rows": GRID_ROWS, "cols": GRID_COLS}}
        with lock:
            sessions[session_id] = session
            cancel_flags[session_id] = threading.Event()
            save_session(session)
        executor.submit(analyze, session_id, video_path)
        return dict(session)
    except Exception:
        with lock:
            if active_id == session_id:
                active_id = None
        video_path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()


@app.get("/api/sessions")
def list_sessions():
    with lock:
        return [{key: value for key, value in session.items() if key != "cumulativeCells"}
                for session in sorted(sessions.values(), key=lambda item: item["createdAt"], reverse=True)]


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: str):
    with lock:
        return dict(get_session(session_id))


@app.post("/api/sessions/{session_id}/cancel")
def cancel_session(session_id: str):
    with lock:
        get_session(session_id)
        if flag := cancel_flags.get(session_id):
            flag.set()
    return {"ok": True}


def frame_path(session_id, index):
    with lock:
        session = get_session(session_id)
        if index < 0 or index >= session["analyzedFrames"]:
            raise HTTPException(404, "Frame not available yet")
    return DATA_DIR / session_id / str(index)


@app.get("/api/sessions/{session_id}/frames/{index}")
def frame_detail(session_id: str, index: int):
    path = frame_path(session_id, index).with_suffix(".json")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/sessions/{session_id}/frames/{index}/{view}")
def frame_image(session_id: str, index: int, view: str):
    path = frame_path(session_id, index)
    suffix = {"image": ".jpg", "heatmap": "-heatmap.jpg", "cumulative": "-cumulative.jpg"}.get(view)
    if suffix is None:
        raise HTTPException(404, "Unknown frame view")
    return FileResponse(str(path) + suffix, media_type="image/jpeg")


@app.get("/api/sessions/{session_id}/report")
def report(session_id: str):
    with lock:
        session = dict(get_session(session_id))
    frames = [frame_detail(session_id, index) for index in range(session["analyzedFrames"])]
    return {"session": session, "frames": frames,
            "interpretation": "Risk is a class-weighted model confidence index, not measured physical damage. "
                              "Counts are detections across sampled frames, not unique objects. "
                              "Heatmaps use camera-frame coordinates; drone motion is not georegistered. "
                              "Cumulative risk is mean weighted evidence across analyzed frames. "
                              "Normal water detections are excluded from flood results."}


@app.websocket("/ws/sessions/{session_id}")
async def stream_session(websocket: WebSocket, session_id: str):
    await websocket.accept()
    previous = None
    try:
        while True:
            with lock:
                snapshot = dict(get_session(session_id))
            if snapshot["updatedAt"] != previous:
                await websocket.send_json({"session": snapshot,
                                           "frame": frame_detail(session_id, snapshot["latestIndex"])
                                           if snapshot["latestIndex"] is not None else None})
                previous = snapshot["updatedAt"]
            if snapshot["status"] in ("completed", "failed", "cancelled"):
                await websocket.close()
                return
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except HTTPException:
        await websocket.close(code=1008)
