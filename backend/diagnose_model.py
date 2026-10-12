"""
Model diagnostic — run this BEFORE the main tracker to see exactly
what the YOLO model detects on your video.

Usage:
  python diagnose_model.py --model models_light/best_flood.pt --video disaster_footage_fixed.mp4

It will:
  1. Print all class names the model knows
  2. Run inference on 10 evenly-spaced frames and print every detection
  3. Save annotated sample frames as diag_frame_*.jpg so you can see visually
"""

import cv2
import argparse
import sys
import os

try:
    from ultralytics import YOLO
except ImportError:
    print("[error] ultralytics not installed: pip install ultralytics")
    sys.exit(1)

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--video", required=True)
ap.add_argument("--conf",  type=float, default=0.01)   # very low to see everything
ap.add_argument("--frames", type=int, default=10)
args = ap.parse_args()

if not os.path.exists(args.model):
    print(f"[error] Model not found: {args.model}"); sys.exit(1)
if not os.path.exists(args.video):
    print(f"[error] Video not found: {args.video}"); sys.exit(1)

print(f"\n{'='*60}")
print(f"  Model : {args.model}")
print(f"  Video : {args.video}")
print(f"  Conf  : {args.conf}  (showing ALL detections above this)")
print(f"{'='*60}\n")

model = YOLO(args.model)

print("── Model classes ──────────────────────────────────────────")
for cid, name in model.names.items():
    print(f"  {cid:3d} : {name}")
print()

cap   = cv2.VideoCapture(args.video)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps   = cap.get(cv2.CAP_PROP_FPS)
w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"── Video info ─────────────────────────────────────────────")
print(f"  Frames : {total}   FPS : {fps:.1f}   Size : {w}x{h}\n")

sample_indices = [int(i * total / args.frames) for i in range(args.frames)]
total_dets = 0

print("── Per-frame detections ───────────────────────────────────")
for fidx in sample_indices:
    cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
    ret, frame = cap.read()
    if not ret:
        print(f"  frame {fidx:5d} : [could not read]")
        continue

    results = model(frame, conf=args.conf, verbose=False)[0]
    boxes   = results.boxes

    if len(boxes) == 0:
        print(f"  frame {fidx:5d} : NO DETECTIONS")
    else:
        for b in boxes:
            cls   = int(b.cls)
            name  = model.names[cls]
            conf  = float(b.conf)
            x1,y1,x2,y2 = [int(v) for v in b.xyxy[0]]
            print(f"  frame {fidx:5d} : {name:25s}  conf={conf:.3f}  box=[{x1},{y1},{x2},{y2}]")
            total_dets += 1

            # Draw box on frame for visual check
            color = (0, 200, 255)
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
            tag = f"{name} {conf:.2f}"
            (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(frame, (x1, max(0,y1-th-8)), (x1+tw+8, y1), color, -1)
            cv2.putText(frame, tag, (x1+4, max(12,y1-4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 1)

    out_name = f"diag_frame_{fidx:05d}.jpg"
    cv2.imwrite(out_name, frame)

cap.release()

print(f"\n── Summary ────────────────────────────────────────────────")
print(f"  Total detections across {args.frames} frames: {total_dets}")
if total_dets == 0:
    print("\n  ⚠  ZERO detections at conf={:.2f}!".format(args.conf))
    print("  Possible causes:")
    print("   1. Model was trained on different image size — try --imgsz 640")
    print("   2. Model class names don't match video content")
    print("   3. Model needs different input (e.g. BGR vs RGB)")
    print("   4. Model file is corrupt or wrong format")
    print("\n  Try running with even lower conf:")
    print(f"    python diagnose_model.py --model {args.model} --video {args.video} --conf 0.001")
else:
    print(f"\n  ✓ Model IS detecting things. Check diag_frame_*.jpg files.")
    print(f"  If conf is too low for tracker, use --conf 0.1 or 0.15 in main script.")

print(f"\n  Saved annotated frames: diag_frame_*.jpg\n")
