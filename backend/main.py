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
from fastapi.responses import FileResponse, Response

from config import DATA_DIR, DEFAULT_CONFIDENCE, DEFAULT_FRAME_SKIP, GRID_COLS, GRID_ROWS, MAX_FRAME_WIDTH, MAX_UPLOAD_BYTES
from ensemble import EnsembleDetector, active_model_registry
from tracking import DisasterTracker
from alerts import AlertEngine, email_configured, intensity_level, send_email_alert
from scoring import GridScorer, SUPPORTED_CLASSES, render_heatmap
from live import LiveCapture, StreamRequest, LIVE_FRAME_LIMIT

log = logging.getLogger("disastervision")
app = FastAPI(title="DisasterVision Video Analysis")
DATA_DIR.mkdir(exist_ok=True)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
notification_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notification")
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
            saved.update(status="failed", connectionState="disconnected" if saved.get("sourceType") == "rtsp" else None,
                         error="Analysis was interrupted by a server restart. Start a new upload or reconnect the stream.")
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


def deliver_email(session_id, alert_id, filename):
    with lock:
        alert = next((item for item in get_session(session_id).get("alerts", []) if item["id"] == alert_id), None)
        if alert is None:
            return
        payload = dict(alert)
    try:
        status, error = send_email_alert(payload, filename), None
    except Exception as exc:
        log.exception("Email alert delivery failed for %s", alert_id)
        status, error = "failed", str(exc)
    with lock:
        session = get_session(session_id)
        for item in session.get("alerts", []):
            if item["id"] == alert_id:
                item["emailStatus"] = status
                if error:
                    item["emailError"] = error
                update_session(session_id, alerts=session["alerts"])
                break


def analyze(session_id, video_path):
    global active_id, model_info
    capture = None
    try:
        with lock:
            settings = dict(sessions[session_id])
        is_live = settings.get("sourceType") == "rtsp"
        update_session(session_id, status="loading")
        # Retain low-confidence boxes for ByteTrack's second association stage.
        detector = EnsembleDetector(conf_threshold=0.1, parallel=False)
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
        if is_live:
            capture = LiveCapture(str(video_path), settings["frameSkip"], cancel_flags[session_id],
                                  lambda state, retries: update_session(session_id, connectionState=state,
                                                                        reconnectAttempts=retries)).start()
            total, fps = 0, 25.0
        else:
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
        tracker = DisasterTracker(fps, settings["frameSkip"], settings["confidence"])
        alert_engine = AlertEngine()
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
            number = capture.number if is_live else frame_number
            frame_number = capture.frames_read if is_live else frame_number + 1
            if not is_live and number % settings["frameSkip"]:
                continue
            if frame.shape[1] > MAX_FRAME_WIDTH:
                scale = MAX_FRAME_WIDTH / frame.shape[1]
                frame = cv2.resize(frame, (MAX_FRAME_WIDTH, max(1, round(frame.shape[0] * scale))))
            height, width = frame.shape[:2]
            candidates = tracker.update(detector.run(frame), (height, width))
            detections = [d for d in candidates if d.confidence >= settings["confidence"]]
            cells = scorer.update(detections, width, height)
            for cell in cells:
                cell["intensity"] = intensity_level(cell["risk"])
            timestamp = round(capture.timestamp if is_live else number / fps, 3)
            new_alerts = alert_engine.update(detections, cells, timestamp, number, session_id)
            boxes = []
            for index, detection in enumerate(detections):
                counts[detection.class_name] += 1
                x1, y1, x2, y2 = detection.box
                boxes.append({
                    "id": f"{sample_index}-{index}", "type": detection.class_name,
                    "confidence": round(detection.confidence, 6), "weight": detection.weight,
                    "box": [max(0, min(1, value)) for value in [x1 / width, y1 / height, x2 / width, y2 / height]],
                    "sourceModel": detection.source_model,
                    "trackId": detection.track_id,
                })
            root_url = f"/api/sessions/{session_id}/frames/{sample_index}"
            classes = sorted({d.class_name for d in detections})
            current_risk = max(c["risk"] for c in cells)
            payload = {"index": sample_index, "frameNumber": number, "timestamp": timestamp,
                       "width": width, "height": height, "detections": boxes, "cells": cells,
                       "imageUrl": root_url + "/image", "heatmapUrl": root_url + "/heatmap",
                       "cumulativeUrl": root_url + "/cumulative", "inferenceMs": round(detector.last_inference_ms, 1),
                       "annotatedUrl": root_url + "/annotated", "disasterClasses": classes,
                       "intensity": {"level": intensity_level(current_risk) if classes else "none", "risk": current_risk},
                       "alerts": new_alerts}
            write_image(directory / f"{sample_index}.jpg", frame)
            write_image(directory / f"{sample_index}-annotated.jpg", detector.draw(frame, detections))
            write_image(directory / f"{sample_index}-heatmap.jpg", detector.draw(render_heatmap(frame, cells), detections))
            write_image(directory / f"{sample_index}-cumulative.jpg", render_heatmap(frame, cells, cumulative=True))
            (directory / f"{sample_index}.json").write_text(json.dumps(payload), encoding="utf-8")
            sample_index += 1
            peak_risk = max(peak_risk, max(s["risk"] for s in cells))
            with lock:
                oldest_index = max(0, sample_index - LIVE_FRAME_LIMIT) if is_live else 0
                if oldest_index:
                    expired = oldest_index - 1
                    for suffix in (".json", ".jpg", "-annotated.jpg", "-heatmap.jpg", "-cumulative.jpg"):
                        (directory / f"{expired}{suffix}").unlink(missing_ok=True)
                # Merge under the lock so a simultaneous acknowledgement cannot be lost.
                alerts = sessions[session_id].get("alerts", []) + new_alerts
                if is_live:
                    alerts = alerts[-500:]
                live_stats = {"fps": capture.fps, "droppedSamples": capture.dropped_frames} if is_live else {}
                update_session(session_id, alerts=alerts, uniqueTrackCounts=tracker.counts(), tracker="ByteTrack",
                           analyzedFrames=sample_index, latestIndex=sample_index - 1,
                           oldestFrameIndex=oldest_index,
                           framesRead=frame_number, progress=min(99.9, frame_number / total * 100) if total else 0,
                           detectionCounts=dict(counts), peakRisk=peak_risk,
                           cumulativeCells=cells, elapsedSeconds=round(time.perf_counter() - start, 2), **live_stats)
            for alert in new_alerts:
                if alert["emailStatus"] == "pending":
                    notification_executor.submit(deliver_email, session_id, alert["id"], settings["filename"])
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
        if sessions[session_id].get("sourceType") == "rtsp":
            update_session(session_id, connectionState="disconnected")
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
                                        for entry in active_model_registry() if entry.get("enabled", True)],
                "tracker": "ByteTrack", "notifications": {"dashboard": True, "browser": True,
                                                              "email": email_configured()},
                "grid": {"rows": GRID_ROWS, "cols": GRID_COLS}}


@app.post("/api/streams", status_code=202)
def start_stream(source: StreamRequest):
    global active_id
    session_id = uuid4().hex
    with lock:
        if active_id is not None:
            raise HTTPException(409, "An analysis is already running. Stop it before connecting a drone stream.")
        active_id = session_id
        try:
            (DATA_DIR / session_id).mkdir()
            session = {"id": session_id, "filename": source.name.strip() or "Drone live stream",
                       "sourceType": "rtsp", "sourceAddress": source.public_source(), "isLive": True,
                       "connectionState": "connecting", "reconnectAttempts": 0,
                       "retainedFrameLimit": LIVE_FRAME_LIMIT, "oldestFrameIndex": 0,
                       "status": "queued", "createdAt": now(), "updatedAt": now(),
                       "frameSkip": source.frame_skip, "confidence": source.confidence,
                       "analyzedFrames": 0, "latestIndex": None, "progress": 0,
                       "detectionCounts": {}, "uniqueTrackCounts": {}, "alerts": [], "tracker": "ByteTrack",
                       "error": None, "grid": {"rows": GRID_ROWS, "cols": GRID_COLS}}
            sessions[session_id] = session
            cancel_flags[session_id] = threading.Event()
            save_session(session)
            # The credential-bearing URL lives only in this worker invocation.
            executor.submit(analyze, session_id, source.connection_url())
            return dict(session)
        except Exception:
            active_id = None
            sessions.pop(session_id, None)
            cancel_flags.pop(session_id, None)
            raise


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
                   "sourceType": "upload", "status": "queued", "createdAt": now(), "updatedAt": now(), "frameSkip": frame_skip,
                   "confidence": confidence, "analyzedFrames": 0, "latestIndex": None, "progress": 0,
                   "detectionCounts": {}, "uniqueTrackCounts": {}, "alerts": [], "tracker": "ByteTrack",
                   "error": None, "grid": {"rows": GRID_ROWS, "cols": GRID_COLS}}
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


@app.get("/api/sessions/{session_id}/alerts")
def session_alerts(session_id: str):
    with lock:
        return list(get_session(session_id).get("alerts", []))


@app.post("/api/sessions/{session_id}/alerts/{alert_id}/acknowledge")
def acknowledge_alert(session_id: str, alert_id: str):
    with lock:
        session = get_session(session_id)
        for alert in session.get("alerts", []):
            if alert["id"] == alert_id:
                alert["acknowledgedAt"] = alert["acknowledgedAt"] or now()
                update_session(session_id, alerts=session["alerts"])
                return dict(alert)
        raise HTTPException(404, "Alert not found")


def frame_path(session_id, index):
    with lock:
        session = get_session(session_id)
        if index < session.get("oldestFrameIndex", 0) or index >= session["analyzedFrames"]:
            raise HTTPException(404, "Frame is not available. Older live frames expire; select a recent frame.")
    return DATA_DIR / session_id / str(index)


@app.get("/api/sessions/{session_id}/frames/{index}")
def frame_detail(session_id: str, index: int):
    with lock:
        path = frame_path(session_id, index).with_suffix(".json")
        return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/sessions/{session_id}/frames/{index}/{view}")
def frame_image(session_id: str, index: int, view: str):
    suffix = {"image": ".jpg", "annotated": "-annotated.jpg", "heatmap": "-heatmap.jpg", "cumulative": "-cumulative.jpg"}.get(view)
    if suffix is None:
        raise HTTPException(404, "Unknown frame view")
    with lock:
        path = frame_path(session_id, index)
        if get_session(session_id).get("isLive"):
            # Read while holding the retention lock: an expiring frame cannot
            # disappear between validation and FileResponse opening the file.
            return Response(Path(str(path) + suffix).read_bytes(), media_type="image/jpeg")
    return FileResponse(str(path) + suffix, media_type="image/jpeg")


@app.get("/api/sessions/{session_id}/report")
def report(session_id: str):
    with lock:
        session = dict(get_session(session_id))
        frames = [frame_detail(session_id, index) for index in range(session.get("oldestFrameIndex", 0), session["analyzedFrames"])]
    return {"session": session, "frames": frames,
            "retention": "Live streams retain the latest 300 analyzed frames and 500 alerts; aggregate detection counts and cumulative heatmaps cover the entire session. Uploaded videos retain all sampled frames.",
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
