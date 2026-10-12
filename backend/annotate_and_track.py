"""
One-Shot Annotator + ByteTrack — Browser UI
============================================
No Qt. No display. Runs in your browser.

Usage
─────
  python annotate_and_track.py --video path/to/video.mp4
  python annotate_and_track.py --video clip.mp4 --frame 30 --model best_flood.pt

Then open: http://localhost:5000
"""

import cv2
import numpy as np
import argparse
import sys
import os
import json
import threading
import base64
import time
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify

try:
    import supervision as sv
    HAS_SUPERVISION = True
except ImportError:
    HAS_SUPERVISION = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

app = Flask(__name__)

STATE = {
    "video_path":      None,
    "frame_idx":       0,
    "seed_frame":      None,
    "annotations":     [],
    "tracking":        False,
    "progress":        0,
    "total_frames":    0,
    "output_path":     None,
    "log":             [],
    "done":            False,
    "model_path":      None,
    "live_frame":      None,   # b64 jpeg of the most recent tracked frame
    "live_frame_idx":  0,
    "slowmo_delay":    0.0,    # seconds to sleep between frames (0 = full speed)
}

DISASTER_LABELS = ["fire", "smoke", "flood", "collapsed_building", "debris", "custom"]

LABEL_COLORS = {
    "fire":               (0,   128, 255),
    "smoke":              (160, 160, 160),
    "flood":              (200, 140, 0),
    "collapsed_building": (0,   0,   220),
    "debris":             (140, 140, 140),
    "custom":             (180, 0,   180),
}

def get_color(label):
    return LABEL_COLORS.get(label, (0, 200, 100))

def log(msg):
    print(msg)
    STATE["log"].append(msg)
    if len(STATE["log"]) > 200:
        STATE["log"] = STATE["log"][-200:]

def frame_to_jpeg_b64(frame):
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf).decode()

def draw_annotations(frame, annotations):
    out = frame.copy()
    for ann in annotations:
        x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
        label = ann.get("label", "fire")
        col = get_color(label)
        cv2.rectangle(out, (x1, y1), (x2, y2), col, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(out, (x1, max(0, y1-th-8)), (x1+tw+8, y1), col, -1)
        cv2.putText(out, label, (x1+4, max(12, y1-4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
    return out


def _iou(a, b):
    ax1,ay1,ax2,ay2 = a
    bx1,by1,bx2,by2 = b
    ix1,iy1 = max(ax1,bx1), max(ay1,by1)
    ix2,iy2 = min(ax2,bx2), min(ay2,by2)
    inter = max(0,ix2-ix1)*max(0,iy2-iy1)
    if not inter: return 0.0
    union = (ax2-ax1)*(ay2-ay1)+(bx2-bx1)*(by2-by1)-inter
    return inter/union if union else 0.0


class SimpleIoUTracker:
    def __init__(self):
        self.tracks  = {}
        self.next_id = 0
        self.max_lost = 30

    def update(self, detections):
        if not detections:
            for tid in list(self.tracks):
                self.tracks[tid]["lost"] += 1
                if self.tracks[tid]["lost"] > self.max_lost:
                    del self.tracks[tid]
            return []
        matched_t, matched_d = set(), set()
        for tid, track in self.tracks.items():
            best_iou, best_d = 0.3, -1
            for didx, det in enumerate(detections):
                if didx in matched_d: continue
                iou = _iou(track["box"], det[:4])
                if iou > best_iou:
                    best_iou, best_d = iou, didx
            if best_d >= 0:
                self.tracks[tid]["box"]   = detections[best_d][:4]
                self.tracks[tid]["lost"]  = 0
                self.tracks[tid]["label"] = detections[best_d][5]
                matched_t.add(tid); matched_d.add(best_d)
        for didx, det in enumerate(detections):
            if didx not in matched_d:
                self.tracks[self.next_id] = {"box": det[:4], "lost": 0, "label": det[5]}
                self.next_id += 1
        for tid in list(self.tracks):
            if tid not in matched_t:
                self.tracks[tid]["lost"] += 1
                if self.tracks[tid]["lost"] > self.max_lost:
                    del self.tracks[tid]
        results = []
        for tid, track in self.tracks.items():
            if track["lost"] == 0:
                x1,y1,x2,y2 = track["box"]
                results.append((int(x1),int(y1),int(x2),int(y2),tid,track["label"]))
        return results


def run_tracking():
    STATE["tracking"]      = True
    STATE["done"]          = False
    STATE["progress"]      = 0
    STATE["live_frame"]    = None
    STATE["live_frame_idx"] = 0

    video_path  = STATE["video_path"]
    annotations = STATE["annotations"]
    out_path    = STATE["output_path"]
    seed_fidx   = STATE["frame_idx"]

    cap    = cv2.VideoCapture(video_path)
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    STATE["total_frames"] = total

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    if HAS_SUPERVISION:
        tracker = sv.ByteTrack(
            track_activation_threshold=0.25,
            lost_track_buffer=30,
            minimum_matching_threshold=0.8,
            minimum_consecutive_frames=1,
        )
    else:
        tracker = SimpleIoUTracker()

    yolo_model = None
    if STATE["model_path"] and HAS_YOLO:
        try:
            yolo_model = YOLO(STATE["model_path"])
            log(f"[tracker] YOLO loaded: {STATE['model_path']}")
        except Exception as e:
            log(f"[tracker] YOLO load failed: {e}")

    all_tracks = {}
    frame_idx  = 0
    log(f"[tracker] Starting — {total} frames, seed at frame {seed_fidx}")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx == seed_fidx:
            boxes  = [[a["x1"],a["y1"],a["x2"],a["y2"]] for a in annotations]
            labels = [a["label"] for a in annotations]
            if HAS_SUPERVISION and boxes:
                dets = sv.Detections(
                    xyxy       = np.array(boxes, dtype=np.float32),
                    confidence = np.ones(len(boxes), dtype=np.float32),
                    class_id   = np.array([DISASTER_LABELS.index(l)
                                           if l in DISASTER_LABELS else 0
                                           for l in labels], dtype=int),
                )
                tracked = tracker.update_with_detections(dets)
                # Map tracker_id → label using IoU with seed boxes
                t_labels = {}
                if len(tracked) and tracked.tracker_id is not None:
                    for ti in range(len(tracked)):
                        t_box = tracked.xyxy[ti]
                        best_iou, best_label = 0, labels[0] if labels else "unknown"
                        for di, box in enumerate(boxes):
                            iou = _iou(t_box, box)
                            if iou > best_iou:
                                best_iou = iou
                                best_label = labels[di]
                        t_labels[int(tracked.tracker_id[ti])] = best_label
                log(f"[seed] frame {seed_fidx}: {len(boxes)} boxes → "
                    f"{len(tracked)} tracked, ids={list(t_labels.keys())}")
            elif boxes:
                raw      = [(b[0],b[1],b[2],b[3],1.0,l) for b,l in zip(boxes,labels)]
                tracked  = tracker.update(raw)
                t_labels = {}
            else:
                tracked = []; t_labels = {}
        else:
            if yolo_model:
                results = yolo_model(frame, conf=0.15, verbose=False)[0]
                if HAS_SUPERVISION:
                    dets = sv.Detections.from_ultralytics(results)
                    # Build a dict: detection index → label, BEFORE tracker reorders
                    det_labels = {i: results.names[int(results.boxes.cls[i])]
                                  for i in range(len(results.boxes))}
                    if frame_idx % 30 == 0:
                        log(f"[yolo] frame {frame_idx}: {len(dets)} detections — "
                            + ", ".join(f"{det_labels[i]}({results.boxes.conf[i]:.2f})"
                                        for i in range(len(dets))))
                    tracked = tracker.update_with_detections(dets)

                    # Map tracker_id back to label via xyxy overlap with original dets
                    t_label_map = {}
                    if len(tracked) and tracked.tracker_id is not None:
                        for ti in range(len(tracked)):
                            t_box = tracked.xyxy[ti]
                            best_iou, best_label = 0, "unknown"
                            for di in range(len(dets)):
                                iou = _iou(t_box, dets.xyxy[di])
                                if iou > best_iou:
                                    best_iou = iou
                                    best_label = det_labels.get(di, "unknown")
                            t_label_map[int(tracked.tracker_id[ti])] = best_label
                    t_labels = t_label_map
                else:
                    raw = [(float(b.xyxy[0][0]),float(b.xyxy[0][1]),
                            float(b.xyxy[0][2]),float(b.xyxy[0][3]),
                            float(b.conf), results.names[int(b.cls)])
                           for b in results.boxes]
                    tracked  = tracker.update(raw)
                    t_labels = {}
            else:
                if HAS_SUPERVISION:
                    tracked = tracker.update_with_detections(sv.Detections.empty())
                    t_labels = {}
                else:
                    tracked  = tracker.update([])
                    t_labels = {}

        out_frame = frame.copy()

        if HAS_SUPERVISION and hasattr(tracked, "xyxy") and len(tracked):
            for i in range(len(tracked)):
                x1,y1,x2,y2 = [int(v) for v in tracked.xyxy[i]]
                tid   = int(tracked.tracker_id[i]) if tracked.tracker_id is not None else i
                # Look up label by tracker_id (dict) or index (list fallback)
                if isinstance(t_labels, dict):
                    label = t_labels.get(tid, "unknown")
                else:
                    label = t_labels[i] if i < len(t_labels) else "unknown"
                col   = get_color(label)
                cv2.rectangle(out_frame,(x1,y1),(x2,y2),col,2)
                tag = f"#{tid} {label}"
                (tw,th),_ = cv2.getTextSize(tag,cv2.FONT_HERSHEY_SIMPLEX,0.55,1)
                cv2.rectangle(out_frame,(x1,y1-th-8),(x1+tw+6,y1),col,-1)
                cv2.putText(out_frame,tag,(x1+3,y1-4),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1)
                all_tracks.setdefault(frame_idx,[]).append(
                    {"track_id":tid,"label":label,"box":[x1,y1,x2,y2]})
        elif isinstance(tracked, list):
            for item in tracked:
                x1,y1,x2,y2,tid,label = item
                col = get_color(label)
                cv2.rectangle(out_frame,(x1,y1),(x2,y2),col,2)
                tag = f"#{tid} {label}"
                (tw,th),_ = cv2.getTextSize(tag,cv2.FONT_HERSHEY_SIMPLEX,0.55,1)
                cv2.rectangle(out_frame,(x1,y1-th-8),(x1+tw+6,y1),col,-1)
                cv2.putText(out_frame,tag,(x1+3,y1-4),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1)
                all_tracks.setdefault(frame_idx,[]).append(
                    {"track_id":tid,"label":label,"box":[x1,y1,x2,y2]})

        cv2.putText(out_frame, f"Frame {frame_idx}/{total}",
                    (10, out_frame.shape[0]-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
        writer.write(out_frame)

        # Push live preview — encode a smaller version so polling stays fast
        preview = out_frame
        if width > 960:
            scale = 960 / width
            preview = cv2.resize(out_frame, (960, int(height * scale)))
        STATE["live_frame"]     = frame_to_jpeg_b64(preview)
        STATE["live_frame_idx"] = frame_idx

        STATE["progress"] = int(frame_idx/total*100) if total else 0
        frame_idx += 1
        if frame_idx % 60 == 0:
            log(f"[tracker] {STATE['progress']}% — frame {frame_idx}/{total}")

        delay = STATE.get("slowmo_delay", 0.0)
        if delay > 0:
            time.sleep(delay)

    cap.release()
    writer.release()

    csv_path = Path(out_path).stem + "_tracks.csv"
    with open(csv_path, "w") as f:
        f.write("frame,track_id,label,x1,y1,x2,y2\n")
        for fidx in sorted(all_tracks):
            for t in all_tracks[fidx]:
                b = t["box"]
                f.write(f"{fidx},{t['track_id']},{t['label']},{b[0]},{b[1]},{b[2]},{b[3]}\n")

    log(f"[done] Video → {out_path}")
    log(f"[done] CSV   → {csv_path}")
    STATE["tracking"] = False
    STATE["done"]     = True


@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/frame")
def get_frame():
    if STATE["seed_frame"] is None:
        return jsonify({"error": "no frame"}), 404
    frame = draw_annotations(STATE["seed_frame"], STATE["annotations"])
    b64   = frame_to_jpeg_b64(frame)
    h, w  = frame.shape[:2]
    return jsonify({"image": b64, "width": w, "height": h,
                    "frame_idx": STATE["frame_idx"],
                    "total_frames": STATE["total_frames"]})

@app.route("/seek", methods=["POST"])
def seek():
    """Jump to an arbitrary frame and set it as the new seed."""
    data      = request.json or {}
    target    = int(data.get("frame", 0))
    total     = STATE["total_frames"]
    target    = max(0, min(target, total - 1))
    cap       = cv2.VideoCapture(STATE["video_path"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return jsonify({"error": f"Could not read frame {target}"}), 400
    STATE["frame_idx"]  = target
    STATE["seed_frame"] = frame
    STATE["annotations"] = []          # clear boxes when jumping
    b64 = frame_to_jpeg_b64(frame)
    h, w = frame.shape[:2]
    return jsonify({"image": b64, "width": w, "height": h,
                    "frame_idx": target, "total_frames": total})

@app.route("/annotations", methods=["GET","POST"])
def annotations():
    if request.method == "POST":
        STATE["annotations"] = request.json.get("annotations", [])
        return jsonify({"ok": True, "count": len(STATE["annotations"])})
    return jsonify({"annotations": STATE["annotations"]})

@app.route("/start_tracking", methods=["POST"])
def start_tracking():
    if not STATE["annotations"]:
        return jsonify({"error": "No annotations"}), 400
    if STATE["tracking"]:
        return jsonify({"error": "Already tracking"}), 400
    threading.Thread(target=run_tracking, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/status")
def status():
    return jsonify({
        "tracking":       STATE["tracking"],
        "progress":       STATE["progress"],
        "total":          STATE["total_frames"],
        "done":           STATE["done"],
        "log":            STATE["log"][-20:],
        "output":         STATE["output_path"],
        "live_frame":     STATE["live_frame"],
        "live_frame_idx": STATE["live_frame_idx"],
    })

@app.route("/set_speed", methods=["POST"])
def set_speed():
    """Set slowmo delay. delay=0 → full speed, delay=0.1 → ~10fps preview, etc."""
    delay = float((request.json or {}).get("delay", 0.0))
    STATE["slowmo_delay"] = max(0.0, min(delay, 2.0))
    return jsonify({"ok": True, "delay": STATE["slowmo_delay"]})

@app.route("/info")
def info():
    return jsonify({
        "video":        STATE["video_path"],
        "frame_idx":    STATE["frame_idx"],
        "total_frames": STATE["total_frames"],
        "labels":       DISASTER_LABELS,
        "has_model":    bool(STATE["model_path"]),
        "tracker":      "ByteTrack" if HAS_SUPERVISION else "SimpleIoU",
    })


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ByteTrack Annotator</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Syne:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:       #0c0c0f;
  --surface:  #13131a;
  --panel:    #1a1a24;
  --border:   #252535;
  --accent:   #e8ff47;
  --accent2:  #47b8ff;
  --danger:   #ff4747;
  --text:     #e0e0f0;
  --muted:    #555570;
  --mono:     'IBM Plex Mono', monospace;
  --sans:     'Syne', sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{font-family:var(--sans);background:var(--bg);color:var(--text);display:flex;flex-direction:column}

/* ── HEADER ── */
header{
  display:flex;align-items:center;gap:16px;
  padding:10px 20px;
  background:var(--surface);
  border-bottom:1px solid var(--border);
  flex-shrink:0;z-index:10;
}
.logo{font-size:15px;font-weight:700;letter-spacing:.04em;color:var(--accent);white-space:nowrap}
.logo span{color:var(--text);opacity:.5}
.badges{display:flex;gap:8px;margin-left:auto}
.badge{
  font-family:var(--mono);font-size:10px;padding:3px 10px;
  border-radius:3px;border:1px solid var(--border);
  background:var(--panel);color:var(--muted);letter-spacing:.05em;
}
.badge.ok{border-color:#2a4a1a;background:#141f0e;color:#8eff80}
.badge.model{border-color:#1a3a4a;background:#0e161f;color:#80d8ff}

/* ── LAYOUT ── */
.workspace{display:flex;flex:1;overflow:hidden}

/* ── VIDEO AREA ── */
.viewer{
  flex:1;display:flex;flex-direction:column;
  background:#070709;overflow:hidden;
}
#canvas-wrap{
  flex:1;display:flex;align-items:center;justify-content:center;
  overflow:hidden;cursor:crosshair;position:relative;
}
canvas{display:block;max-width:100%;max-height:100%}

/* seed marker overlay */
#seed-marker{
  position:absolute;bottom:12px;left:12px;
  font-family:var(--mono);font-size:10px;
  background:rgba(232,255,71,.12);border:1px solid rgba(232,255,71,.3);
  color:var(--accent);padding:3px 9px;border-radius:3px;
  pointer-events:none;opacity:0;transition:opacity .3s;
}
#seed-marker.show{opacity:1}

/* ── TRANSPORT ── */
.transport{
  flex-shrink:0;background:var(--surface);border-top:1px solid var(--border);
  padding:10px 16px 12px;display:flex;flex-direction:column;gap:8px;
}

/* scrubber */
.scrub-row{display:flex;align-items:center;gap:10px}
#frame-label{font-family:var(--mono);font-size:11px;color:var(--muted);white-space:nowrap;min-width:100px}
.scrub-track{
  flex:1;height:20px;position:relative;cursor:pointer;
  display:flex;align-items:center;
}
.scrub-rail{
  position:absolute;left:0;right:0;height:4px;
  background:var(--border);border-radius:2px;overflow:hidden;
}
.scrub-fill{
  height:100%;background:var(--accent);border-radius:2px;
  transition:width .05s linear;
}
.scrub-track:hover .scrub-rail{height:6px}
.scrub-thumb{
  position:absolute;width:14px;height:14px;border-radius:50%;
  background:var(--accent);border:2px solid #fff;
  transform:translateX(-50%);
  box-shadow:0 0 6px rgba(232,255,71,.5);
  transition:left .05s linear;pointer-events:none;
  opacity:0;
}
.scrub-track:hover .scrub-thumb{opacity:1}

/* step buttons */
.controls-row{display:flex;align-items:center;gap:8px}
.ctrl-btn{
  background:var(--panel);border:1px solid var(--border);color:var(--text);
  border-radius:5px;padding:5px 12px;font-family:var(--mono);font-size:12px;
  cursor:pointer;display:flex;align-items:center;gap:5px;transition:all .15s;
}
.ctrl-btn:hover{background:var(--border);border-color:var(--accent);color:var(--accent)}
.ctrl-btn svg{width:13px;height:13px;fill:currentColor;flex-shrink:0}
.ctrl-btn.set-seed{
  margin-left:auto;
  background:rgba(232,255,71,.08);border-color:rgba(232,255,71,.3);
  color:var(--accent);font-weight:600;
}
.ctrl-btn.set-seed:hover{background:rgba(232,255,71,.18)}

/* frame jump input */
.jump-wrap{display:flex;align-items:center;gap:6px}
.jump-wrap label{font-family:var(--mono);font-size:10px;color:var(--muted)}
#jump-input{
  width:72px;background:var(--panel);border:1px solid var(--border);
  color:var(--text);font-family:var(--mono);font-size:12px;
  padding:4px 8px;border-radius:4px;
}
#jump-input:focus{outline:none;border-color:var(--accent2)}
.jump-go{
  background:var(--panel);border:1px solid var(--border);color:var(--accent2);
  border-radius:4px;padding:4px 10px;font-family:var(--mono);font-size:12px;cursor:pointer;
}
.jump-go:hover{background:rgba(71,184,255,.1)}

/* tracking progress bar */
.track-bar-wrap{display:none;align-items:center;gap:10px}
.track-bar-wrap.show{display:flex}
.track-rail{flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden}
.track-fill{height:100%;background:var(--accent2);border-radius:2px;transition:width .3s}
.track-pct{font-family:var(--mono);font-size:10px;color:var(--accent2);white-space:nowrap;min-width:60px}

/* ── SIDEBAR ── */
aside{
  width:280px;flex-shrink:0;
  background:var(--surface);border-left:1px solid var(--border);
  display:flex;flex-direction:column;overflow:hidden;
}
.panel-title{
  font-size:9px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
  color:var(--muted);margin-bottom:10px;
}
.s-panel{padding:14px 16px;border-bottom:1px solid var(--border)}

/* label select */
#lsel{
  width:100%;padding:7px 10px;border-radius:5px;
  border:1px solid var(--border);background:var(--panel);
  color:var(--text);font-family:var(--sans);font-size:13px;
  cursor:pointer;appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23555570'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center;
  padding-right:28px;
}
#lsel:focus{outline:none;border-color:var(--accent2)}

.hint-text{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:8px;line-height:1.6}

/* annotation list */
#ann-list{font-size:12px;max-height:160px;overflow-y:auto;margin-top:4px}
#ann-list::-webkit-scrollbar{width:3px}
#ann-list::-webkit-scrollbar-thumb{background:var(--border)}
.ann-item{
  display:flex;align-items:center;gap:8px;
  padding:5px 8px;border-radius:4px;margin-bottom:3px;
  background:var(--panel);border:1px solid var(--border);
}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.ann-label{flex:1;color:var(--text);font-family:var(--mono);font-size:11px}
.ann-dim{color:var(--muted);font-size:10px}
.del-btn{
  background:none;border:none;color:var(--muted);cursor:pointer;
  width:auto;padding:0 2px;margin:0;font-size:15px;line-height:1;
  transition:color .15s;
}
.del-btn:hover{color:var(--danger)}
.count-badge{
  display:inline-block;background:var(--panel);border:1px solid var(--border);
  color:var(--muted);font-family:var(--mono);font-size:10px;
  padding:1px 7px;border-radius:3px;margin-left:6px;vertical-align:middle;
}
.btn-row{display:flex;gap:6px;margin-top:8px}
.s-btn{
  flex:1;padding:7px 10px;border-radius:5px;font-family:var(--sans);
  font-size:12px;font-weight:600;cursor:pointer;border:1px solid;
  transition:all .15s;letter-spacing:.03em;
}
.s-btn.track{
  background:rgba(232,255,71,.1);border-color:var(--accent);
  color:var(--accent);
}
.s-btn.track:hover:not(:disabled){background:rgba(232,255,71,.2)}
.s-btn.track:disabled{opacity:.3;cursor:not-allowed}
.s-btn.clear{
  background:rgba(255,71,71,.06);border-color:rgba(255,71,71,.3);
  color:#ff7070;flex:0 0 auto;padding:7px 14px;
}
.s-btn.clear:hover{background:rgba(255,71,71,.14)}

/* speed slider */
.speed-wrap{display:flex;align-items:center;gap:6px;margin-left:10px}
.speed-label{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:.08em}
.speed-val{font-family:var(--mono);font-size:10px;color:var(--accent2);min-width:34px}
#speed-slider{
  width:80px;accent-color:var(--accent2);cursor:pointer;
}

/* log */
#log-wrap{
  flex:1;overflow-y:auto;background:#080810;padding:10px 12px;
}
#log-wrap::-webkit-scrollbar{width:3px}
#log-wrap::-webkit-scrollbar-thumb{background:var(--border)}
#log{font-family:var(--mono);font-size:10px;color:#4caf8c;line-height:1.7}
.log-info{color:#4caf8c}
.log-err{color:#ff7070}
.log-done{color:var(--accent)}
</style>
</head>
<body>
<header>
  <div class="logo">ByteTrack <span>Annotator</span></div>
  <div class="badges">
    <span class="badge" id="tbadge">loading…</span>
    <span class="badge" id="mbadge">no model</span>
    <span class="badge" id="vbadge">—</span>
  </div>
</header>

<div class="workspace">
  <!-- VIDEO VIEWER -->
  <div class="viewer">
    <div id="canvas-wrap">
      <canvas id="c"></canvas>
      <div id="seed-marker">● SEED FRAME</div>
    </div>

    <!-- TRANSPORT CONTROLS -->
    <div class="transport">
      <!-- scrubber -->
      <div class="scrub-row">
        <span id="frame-label">0 / 0</span>
        <div class="scrub-track" id="scrub">
          <div class="scrub-rail"><div class="scrub-fill" id="sfill" style="width:0%"></div></div>
          <div class="scrub-thumb" id="sthumb" style="left:0%"></div>
        </div>
      </div>

      <!-- step controls + seed setter + jump -->
      <div class="controls-row">
        <button class="ctrl-btn" onclick="step(-100)" title="−100 frames">
          <svg viewBox="0 0 16 16"><path d="M2 8l6-6v4h6v4H8v4z"/></svg>−100
        </button>
        <button class="ctrl-btn" onclick="step(-10)" title="−10 frames">
          <svg viewBox="0 0 16 16"><path d="M3 8l5-5v3.5h5v3H8V13z"/></svg>−10
        </button>
        <button class="ctrl-btn" onclick="step(-1)" title="−1 frame">
          <svg viewBox="0 0 16 16"><path d="M5 8l5-5v10z"/></svg>−1
        </button>
        <button class="ctrl-btn" onclick="step(1)" title="+1 frame">
          <svg viewBox="0 0 16 16"><path d="M11 8L6 3v10z"/></svg>+1
        </button>
        <button class="ctrl-btn" onclick="step(10)" title="+10 frames">
          +10<svg viewBox="0 0 16 16"><path d="M13 8L8 3v3.5H3v3h5V13z"/></svg>
        </button>
        <button class="ctrl-btn" onclick="step(100)" title="+100 frames">
          +100<svg viewBox="0 0 16 16"><path d="M14 8L8 2v4H2v4h6v4z"/></svg>
        </button>

        <div class="jump-wrap" style="margin-left:8px">
          <label>GO TO</label>
          <input id="jump-input" type="number" min="0" placeholder="frame #"
            onkeydown="if(event.key==='Enter')jumpTo()">
          <button class="jump-go" onclick="jumpTo()">→</button>
        </div>

        <button class="ctrl-btn set-seed" onclick="setSeedHere()" id="seed-btn">
          ◆ Set seed here
        </button>
      </div>

      <!-- tracking progress (hidden until tracking starts) -->
      <div class="track-bar-wrap" id="track-bar">
        <span class="track-pct" id="tpct">0%</span>
        <div class="track-rail"><div class="track-fill" id="tfill" style="width:0%"></div></div>
        <span style="font-family:var(--mono);font-size:10px;color:var(--muted)" id="tstat">tracking…</span>
        <div class="speed-wrap">
          <label class="speed-label">SPEED</label>
          <input type="range" id="speed-slider" min="0" max="5" step="1" value="0"
            oninput="setSpeed(this.value)" title="0=full speed, 5=slowest">
          <span class="speed-val" id="speed-val">full</span>
        </div>
      </div>
    </div>
  </div>

  <!-- SIDEBAR -->
  <aside>
    <div class="s-panel">
      <div class="panel-title">Label</div>
      <select id="lsel"></select>
      <p class="hint-text">Drag on the frame to draw a box.<br>Seek to any frame, then set it as seed.</p>
    </div>

    <div class="s-panel">
      <div class="panel-title">
        Annotations <span class="count-badge" id="acount">0</span>
      </div>
      <div id="ann-list"></div>
      <div class="btn-row">
        <button class="s-btn track" id="tbtn" onclick="startTracking()">▶ Track from seed</button>
        <button class="s-btn clear" onclick="clearAll()">✕</button>
      </div>
    </div>

    <div id="log-wrap"><div id="log"></div></div>
  </aside>
</div>

<script>
const canvas = document.getElementById("c");
const ctx    = canvas.getContext("2d");
let img = new Image(), anns = [], drawing = false;
let sx, sy, cx, cy, scX = 1, scY = 1, nW = 1280, nH = 720;
let totalFrames = 1, currentFrame = 0, seedFrame = 0;
let scrubDragging = false;
let seekInFlight = false, pendingSeek = null, seekDebounceTimer = null;

const COLS = {
  fire:"#ff8000", smoke:"#a8a8a8", flood:"#d4a800",
  collapsed_building:"#5555ff", debris:"#888", custom:"#cc00cc"
};
const col = l => COLS[l] || "#00c8aa";

/* ── INIT ── */
async function init() {
  const info = await fetch("/info").then(r => r.json());
  totalFrames = info.total_frames || 1;
  currentFrame = info.frame_idx || 0;
  seedFrame    = currentFrame;

  const sel = document.getElementById("lsel");
  info.labels.forEach(l => {
    const o = document.createElement("option");
    o.value = o.textContent = l; sel.appendChild(o);
  });
  document.getElementById("tbadge").textContent = info.tracker;
  document.getElementById("tbadge").className   = "badge ok";
  document.getElementById("vbadge").textContent =
    (info.video || "").split("/").pop().split("\\").pop();
  if (info.has_model) {
    document.getElementById("mbadge").textContent = "YOLO ✓";
    document.getElementById("mbadge").className   = "badge model";
  }
  await loadFrame();
  setupScrubber();
  setInterval(poll, 1000);
}

/* ── FRAME LOAD ── */
async function loadFrame() {
  const d = await fetch("/frame").then(r => r.json());
  if (d.error) { addLog(d.error, "err"); return; }
  nW = d.width; nH = d.height;
  currentFrame = d.frame_idx ?? currentFrame;
  totalFrames  = d.total_frames ?? totalFrames;
  anns = [];
  img.src = "data:image/jpeg;base64," + d.image;
  img.onload = () => { resize(); redraw(); };
  updateScrubUI();
  renderList();
}

/* ── SEEK ── */
// Queue at most one pending seek; if a request is in-flight, wait for it
// then fire the latest queued position. This prevents oscillation from
// overlapping responses arriving out of order.
function seekTo(frameNum) {
  frameNum = Math.max(0, Math.min(Math.round(frameNum), totalFrames - 1));
  // Update scrubber position immediately (optimistic UI)
  currentFrame = frameNum;
  updateScrubUI();
  if (seekInFlight) {
    pendingSeek = frameNum;   // overwrite — only the latest position matters
    return;
  }
  _doSeek(frameNum);
}

async function _doSeek(frameNum) {
  seekInFlight = true;
  try {
    const d = await fetch("/seek", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({frame: frameNum})
    }).then(r => r.json());
    if (!d.error) {
      nW = d.width; nH = d.height;
      currentFrame = d.frame_idx;
      totalFrames  = d.total_frames;
      anns = [];
      const newImg = new Image();
      newImg.onload = () => {
        img = newImg;
        resize(); redraw();
      };
      newImg.src = "data:image/jpeg;base64," + d.image;
      updateScrubUI();
      renderList();
      document.getElementById("seed-marker").classList.remove("show");
    }
  } finally {
    seekInFlight = false;
    if (pendingSeek !== null) {
      const next = pendingSeek;
      pendingSeek = null;
      _doSeek(next);
    }
  }
}

function step(delta) { seekTo(currentFrame + delta); }

function jumpTo() {
  const v = parseInt(document.getElementById("jump-input").value);
  if (!isNaN(v)) seekTo(v);
}

function setSeedHere() {
  seedFrame = currentFrame;
  // POST to backend so tracking uses this frame
  fetch("/seek", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({frame: currentFrame})
  });
  document.getElementById("seed-marker").classList.add("show");
  addLog(`Seed set at frame ${currentFrame}`, "info");
}

/* ── SCRUBBER ── */
function setupScrubber() {
  const track = document.getElementById("scrub");
  function scrubFrom(e) {
    const r = track.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    seekTo(Math.round(pct * (totalFrames - 1)));
  }
  track.addEventListener("mousedown", e => { scrubDragging = true; scrubFrom(e); });
  document.addEventListener("mousemove", e => { if (scrubDragging) scrubFrom(e); });
  document.addEventListener("mouseup",   () => { scrubDragging = false; });
  // touch
  track.addEventListener("touchstart", e => {
    scrubDragging = true; scrubFrom(e.touches[0]); e.preventDefault();
  },{passive:false});
  document.addEventListener("touchmove", e => {
    if (scrubDragging) scrubFrom(e.touches[0]);
  },{passive:false});
  document.addEventListener("touchend", () => { scrubDragging = false; });
}

function updateScrubUI() {
  const pct = totalFrames > 1 ? currentFrame / (totalFrames - 1) * 100 : 0;
  document.getElementById("sfill").style.width  = pct + "%";
  document.getElementById("sthumb").style.left  = pct + "%";
  document.getElementById("frame-label").textContent =
    `${currentFrame.toLocaleString()} / ${(totalFrames-1).toLocaleString()}`;
  const ji = document.getElementById("jump-input");
  if (document.activeElement !== ji) ji.value = currentFrame;
}

/* ── CANVAS ── */
function resize() {
  const wrap = document.getElementById("canvas-wrap");
  const r = Math.min(wrap.clientWidth / nW, wrap.clientHeight / nH, 1);
  canvas.width  = Math.round(nW * r);
  canvas.height = Math.round(nH * r);
  scX = canvas.width / nW;
  scY = canvas.height / nH;
}

function redraw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (img.complete && img.naturalWidth)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  anns.forEach((a, i) => drawBox(a, i));
  if (drawing) {
    ctx.strokeStyle = "#fff";
    ctx.lineWidth   = 1.5;
    ctx.setLineDash([5, 3]);
    ctx.strokeRect(
      Math.min(sx,cx)*scX, Math.min(sy,cy)*scY,
      Math.abs(cx-sx)*scX, Math.abs(cy-sy)*scY
    );
    ctx.setLineDash([]);
  }
}

function drawBox(a, i) {
  const c = col(a.label);
  ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.setLineDash([]);
  ctx.strokeRect(a.x1*scX, a.y1*scY, (a.x2-a.x1)*scX, (a.y2-a.y1)*scY);
  const tag = `${a.label}`;
  ctx.font = "bold 11px 'IBM Plex Mono'";
  const tw = ctx.measureText(tag).width;
  ctx.fillStyle = c;
  ctx.fillRect(a.x1*scX, Math.max(0, a.y1*scY-20), tw+8, 20);
  ctx.fillStyle = "#000";
  ctx.fillText(tag, a.x1*scX+4, Math.max(14, a.y1*scY-5));
}

function xy(e) {
  const r = canvas.getBoundingClientRect();
  return [(e.clientX - r.left) / scX, (e.clientY - r.top) / scY];
}
canvas.addEventListener("mousedown", e => { [sx,sy] = xy(e); drawing = true; });
canvas.addEventListener("mousemove", e => { if (!drawing) return; [cx,cy] = xy(e); redraw(); });
canvas.addEventListener("mouseup",   e => {
  if (!drawing) return; drawing = false; [cx,cy] = xy(e);
  const x1=Math.round(Math.min(sx,cx)), y1=Math.round(Math.min(sy,cy));
  const x2=Math.round(Math.max(sx,cx)), y2=Math.round(Math.max(sy,cy));
  if ((x2-x1)*(y2-y1) < 100) { redraw(); return; }
  anns.push({x1,y1,x2,y2, label: document.getElementById("lsel").value});
  sync(); redraw(); renderList();
});

/* ── ANNOTATIONS ── */
function clearAll()   { anns=[]; sync(); redraw(); renderList(); }
function delAnn(i)    { anns.splice(i,1); sync(); redraw(); renderList(); }
function renderList() {
  document.getElementById("acount").textContent = anns.length;
  document.getElementById("ann-list").innerHTML = anns.map((a,i) =>
    `<div class="ann-item">
      <span class="dot" style="background:${col(a.label)}"></span>
      <span class="ann-label">${a.label}
        <span class="ann-dim">${a.x2-a.x1}×${a.y2-a.y1}</span>
      </span>
      <button class="del-btn" onclick="delAnn(${i})">×</button>
    </div>`
  ).join("");
}

async function sync() {
  await fetch("/annotations", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({annotations: anns})
  });
}

/* ── TRACKING ── */
const SPEED_DELAYS = [0, 0.04, 0.1, 0.2, 0.5, 1.0];
const SPEED_LABELS = ["full", "0.5×", "0.2×", "0.1×", "slow", "crawl"];

function setSpeed(val) {
  const delay = SPEED_DELAYS[parseInt(val)] || 0;
  document.getElementById("speed-val").textContent = SPEED_LABELS[parseInt(val)] || "full";
  fetch("/set_speed", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({delay})
  });
}

async function startTracking() {
  if (!anns.length) { addLog("Draw at least one box first.", "err"); return; }
  await sync();
  const r = await fetch("/start_tracking", {method:"POST"}).then(x => x.json());
  if (r.error) { addLog(r.error, "err"); return; }
  document.getElementById("tbtn").disabled = true;
  document.getElementById("track-bar").classList.add("show");
  doneReported = false;
  addLog(`Tracking from frame ${seedFrame}…`, "info");
}

/* ── POLL ── */
const seen = new Set();
let doneReported = false;
async function poll() {
  const s = await fetch("/status").then(r=>r.json()).catch(()=>null);
  if (!s) return;
  if (s.tracking || s.done) {
    document.getElementById("track-bar").classList.add("show");
    document.getElementById("tfill").style.width = s.progress + "%";
    document.getElementById("tpct").textContent  = s.progress + "%";
    document.getElementById("tstat").textContent = s.done ? "✓ done" : "tracking…";
    // feed live frame into canvas while tracking
    if (s.live_frame) {
      const newImg = new Image();
      newImg.onload = () => { img = newImg; redraw(); };
      newImg.src = "data:image/jpeg;base64," + s.live_frame;
      currentFrame = s.live_frame_idx ?? currentFrame;
      updateScrubUI();
    }
  }
  (s.log || []).forEach(l => {
    if (!seen.has(l)) { seen.add(l); addLog(l); }
  });
  if (s.done && !doneReported) {
    doneReported = true;
    document.getElementById("tbtn").disabled = false;
    addLog(`✓ Output → ${s.output}`, "done");
  }
}

/* ── LOG ── */
function addLog(m, type="info") {
  const d = document.createElement("div");
  d.className = "log-" + type;
  d.textContent = m;
  document.getElementById("log").appendChild(d);
  document.getElementById("log-wrap").scrollTop = 99999;
}

window.addEventListener("resize", () => { resize(); redraw(); });
init();
</script>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video",  required=True)
    ap.add_argument("--frame",  type=int, default=0)
    ap.add_argument("--out",    default="tracked_output.mp4")
    ap.add_argument("--model",  default=None)
    ap.add_argument("--port",   type=int, default=5000)
    args = ap.parse_args()

    if not os.path.exists(args.video):
        print(f"[error] Video not found: {args.video}"); sys.exit(1)

    cap = cv2.VideoCapture(args.video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print(f"[error] Could not read frame {args.frame}"); sys.exit(1)

    STATE["video_path"]    = args.video
    STATE["frame_idx"]     = args.frame
    STATE["seed_frame"]    = frame
    STATE["output_path"]   = args.out
    STATE["model_path"]    = args.model
    STATE["total_frames"]  = int(cv2.VideoCapture(args.video).get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"\n  Tracker : {'ByteTrack (supervision)' if HAS_SUPERVISION else 'SimpleIoU (fallback)'}")
    print(f"  YOLO    : {'yes — ' + args.model if args.model else 'none (pure propagation)'}")
    print(f"  Video   : {args.video}  |  seed frame: {args.frame}")
    print(f"  Output  : {args.out}")
    print(f"\n  Open http://localhost:{args.port} in your browser\n")

    app.run(host="0.0.0.0", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
