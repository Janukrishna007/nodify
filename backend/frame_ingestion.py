"""

Reads a video source (file or RTSP), samples every k-th frame,
and places it into a thread-safe queue ready for inference workers.

Mirrors the diagram:
  Video Input
      ↓
  OpenCV Processing (every k-th frame)
      ↓
  Image Queue  ←──────────────────────────
      ↓                                   |
  Inference Workers (pull from queue)     |
      ↓                                   |
  Fire / Smoke / Heavy Damage / Flood     |
                                          |
  (queue feeds back into the loop)  ──────

"""

import cv2
import queue
import threading
import time
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("FrameIngestion")


# ─── Config ───────────────────────────────────────────────────────────────────
@dataclass
class IngestionConfig:
    """All tunable knobs in one place. Edit here, nowhere else."""

    # Video source — file path, RTSP URL, or webcam index (0)
    source: str = "disaster_footage.mp4"

    # Run inference on every k-th frame. k=1 → every frame, k=3 → every 3rd.
    frame_skip: int = 3

    # Maximum frames held in queue before the reader starts dropping.
    # Keeps memory bounded if inference is slower than the camera.
    queue_maxsize: int = 8

    # Loop the video file for demo purposes (ignored for RTSP/webcam).
    loop_video: bool = True

    # JPEG encode quality for frames put in the queue (0-100).
    # Encoding reduces memory per frame; set to None to queue raw numpy arrays.
    jpeg_quality: Optional[int] = None   # None = raw BGR numpy array

    # Resize frame before queuing. Tuple (width, height) or None = no resize.
    # YOLO11 internally resizes to 640×640 anyway — resize here saves bus bandwidth.
    resize_to: Optional[tuple] = (960, 540)

    # Frames-per-second cap on the reader.
    # Useful to avoid burning CPU reading a 120fps file faster than needed.
    reader_fps_cap: Optional[float] = 30.0

    # ── Frame Saving ──────────────────────────────────────────────────────────

    # Save frames to disk as JPEGs. False = disabled.
    save_frames: bool = True

    # Folder where saved frames go. Created automatically if it doesn't exist.
    save_dir: str = "saved_frames"

    # Save every n-th queued frame. 1 = save every queued frame,
    # 10 = save every 10th queued frame (after frame_skip already applied).
    # So with frame_skip=3 and save_every=10, you save 1 in every 30 raw frames.
    save_every: int = 10

    # JPEG quality for saved frames (0-100). 90 is a good balance.
    save_jpeg_quality: int = 90

    # Maximum number of frames to keep on disk per source.
    # Oldest files are deleted when the limit is exceeded. 0 = unlimited.
    save_max_frames: int = 500


# ─── Frame container ──────────────────────────────────────────────────────────
@dataclass
class QueuedFrame:
    """Everything an inference worker needs about a single frame."""

    frame_index: int          # absolute frame number in the video stream
    timestamp_ms: float       # wall-clock time the frame was captured (ms)
    frame_bgr: object         # numpy array, shape (H, W, 3), dtype uint8
    width: int
    height: int
    source_id: str = ""       # tag for multi-stream setups

    @property
    def shape(self):
        return self.frame_bgr.shape


# ─── Frame Saver ──────────────────────────────────────────────────────────────
class FrameSaver:
    """
    Writes QueuedFrame objects to disk as JPEGs in a background thread.
    Runs independently so disk I/O never blocks the reader or inference.

    Saved filenames:
        saved_frames/cam0/cam0_f000120_20260328_143055_123.jpg
                          │         │              └─ wall-clock timestamp
                          │         └─ frame index (zero-padded)
                          └─ source id

    If save_max_frames > 0, the oldest files in the folder are pruned
    whenever the count exceeds the limit.
    """

    def __init__(self, cfg: IngestionConfig, source_id: str = "cam0"):
        self.cfg       = cfg
        self.source_id = source_id
        self._queue    = queue.Queue(maxsize=64)
        self._thread   = threading.Thread(target=self._run, daemon=True,
                                          name=f"FrameSaver-{source_id}")
        self._stop_evt = threading.Event()
        self.saved     = 0
        self.pruned    = 0

        # Create output directory: save_dir / source_id /
        self.out_dir = os.path.join(cfg.save_dir, source_id)
        os.makedirs(self.out_dir, exist_ok=True)
        log.info(f"[Saver-{source_id}] Saving frames → {self.out_dir}")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_evt.set()

    def enqueue(self, qf: "QueuedFrame"):
        """Non-blocking — drops frame silently if saver is backed up."""
        try:
            self._queue.put_nowait(qf)
        except queue.Full:
            pass   # disk too slow; skip this save

    def _run(self):
        while not self._stop_evt.is_set():
            try:
                qf: QueuedFrame = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Build filename with timestamp for easy sorting / review
            ts  = datetime.fromtimestamp(qf.timestamp_ms / 1000).strftime(
                    "%Y%m%d_%H%M%S_%f"
            )[:21]   # trim microseconds to milliseconds
            fname = f"{self.source_id}_f{qf.frame_index:06d}_{ts}.jpg"
            fpath = os.path.join(self.out_dir, fname)

            cv2.imwrite(
                fpath,
                qf.frame_bgr,
                [cv2.IMWRITE_JPEG_QUALITY, self.cfg.save_jpeg_quality],
            )
            self.saved += 1
            log.debug(f"[Saver-{self.source_id}] Saved {fname}")

            # Prune oldest files if over limit
            if self.cfg.save_max_frames > 0:
                self._prune()

            self._queue.task_done()

    def _prune(self):
        """Delete the oldest JPEG files if count exceeds save_max_frames."""
        files = sorted(
            [f for f in os.listdir(self.out_dir) if f.endswith(".jpg")],
            # lexicographic sort works because filenames embed timestamp
        )
        excess = len(files) - self.cfg.save_max_frames
        if excess > 0:
            for fname in files[:excess]:
                try:
                    os.remove(os.path.join(self.out_dir, fname))
                    self.pruned += 1
                except OSError:
                    pass


# ─── FrameReader ──────────────────────────────────────────────────────────────
class FrameReader:
    """
    Runs in its own daemon thread.

    Reads frames from `source`, drops to every k-th frame, optional-resizes,
    and places QueuedFrame objects into `out_queue`.

    Usage
    -----
        cfg   = IngestionConfig(source="rtsp://...", frame_skip=4)
        q     = queue.Queue(maxsize=cfg.queue_maxsize)
        reader= FrameReader(cfg, q)
        reader.start()
        ...
        reader.stop()
    """

    def __init__(self, cfg: IngestionConfig, out_queue: queue.Queue,
                 source_id: str = "cam0"):
        self.cfg        = cfg
        self.out_queue  = out_queue
        self.source_id  = source_id

        self._thread    = threading.Thread(target=self._run, daemon=True,
                                           name=f"FrameReader-{source_id}")
        self._stop_evt  = threading.Event()

        # Public diagnostics (read from any thread, no lock needed for floats)
        self.fps_actual : float = 0.0
        self.total_read : int   = 0
        self.total_queued: int  = 0
        self.total_dropped: int = 0

        # Frame saver — only created if saving is enabled
        self._saver = (
            FrameSaver(cfg, source_id) if cfg.save_frames else None
        )
        self._save_counter = 0   # counts queued frames, triggers saves

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        log.info(f"[{self.source_id}] Starting reader → source: {self.cfg.source}")
        if self._saver:
            self._saver.start()
        self._thread.start()

    def stop(self):
        log.info(f"[{self.source_id}] Stop requested.")
        self._stop_evt.set()
        if self._saver:
            self._saver.stop()

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _open_capture(self) -> cv2.VideoCapture:
        """Open the video capture and verify it's readable."""
        src = self.cfg.source

        # Integer string → webcam index
        try:
            src = int(src)
        except (ValueError, TypeError):
            pass

        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            raise RuntimeError(
                f"[{self.source_id}] Cannot open source: {self.cfg.source}\n"
                f"  • File path — check the path is correct and the file exists\n"
                f"  • RTSP     — check the camera IP and stream URL\n"
                f"  • Webcam   — use integer index (0, 1, ...)"
            )

        native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        log.info(
            f"[{self.source_id}] Opened — "
            f"{width}×{height} @ {native_fps:.1f} fps  "
            f"({total if total > 0 else '∞'} frames)"
        )
        return cap

    def _run(self):
        try:
            cap = self._open_capture()
        except RuntimeError as e:
            log.error(str(e))
            return

        frame_index   = 0
        fps_counter   = 0
        fps_t0        = time.perf_counter()
        min_interval  = (1.0 / self.cfg.reader_fps_cap
                         if self.cfg.reader_fps_cap else 0.0)
        last_read_t   = 0.0

        while not self._stop_evt.is_set():

            # ── FPS cap ───────────────────────────────────────────────────
            now = time.perf_counter()
            if min_interval and (now - last_read_t) < min_interval:
                time.sleep(min_interval - (now - last_read_t))
            last_read_t = time.perf_counter()

            # ── Read frame ────────────────────────────────────────────────
            ret, frame = cap.read()

            if not ret:
                # End of file
                if self.cfg.loop_video:
                    log.info(f"[{self.source_id}] End of file — looping.")
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    frame_index = 0
                    continue
                else:
                    log.info(f"[{self.source_id}] End of file — stopping.")
                    break

            self.total_read += 1
            frame_index     += 1

            # ── Frame skip — only process every k-th frame ─────────────
            if frame_index % self.cfg.frame_skip != 0:
                continue

            # ── Optional resize ───────────────────────────────────────────
            if self.cfg.resize_to:
                frame = cv2.resize(frame, self.cfg.resize_to,
                                   interpolation=cv2.INTER_LINEAR)

            h, w = frame.shape[:2]

            qf = QueuedFrame(
                frame_index  = frame_index,
                timestamp_ms = time.time() * 1000,
                frame_bgr    = frame,
                width        = w,
                height       = h,
                source_id    = self.source_id,
            )

            # ── Enqueue — non-blocking, drop if queue is full ─────────
            try:
                self.out_queue.put_nowait(qf)
                self.total_queued += 1

                # ── Frame saving ──────────────────────────────────────
                if self._saver:
                    self._save_counter += 1
                    if self._save_counter % self.cfg.save_every == 0:
                        self._saver.enqueue(qf)

            except queue.Full:
                self.total_dropped += 1
                # Log a warning every 30 dropped frames so we don't spam
                if self.total_dropped % 30 == 0:
                    log.warning(
                        f"[{self.source_id}] Queue full — "
                        f"dropped {self.total_dropped} frames total. "
                        f"Inference may be too slow."
                    )

            # ── FPS tracker ───────────────────────────────────────────────
            fps_counter += 1
            elapsed = time.perf_counter() - fps_t0
            if elapsed >= 2.0:
                self.fps_actual = fps_counter / elapsed
                log.info(
                    f"[{self.source_id}] "
                    f"Reader {self.fps_actual:.1f} fps  |  "
                    f"Queue {self.out_queue.qsize()}/{self.cfg.queue_maxsize}  |  "
                    f"Dropped {self.total_dropped}"
                )
                fps_counter = 0
                fps_t0      = time.perf_counter()

        cap.release()
        log.info(f"[{self.source_id}] Reader exited. "
                 f"Read {self.total_read}, queued {self.total_queued}, "
                 f"dropped {self.total_dropped}.")
        if self._saver:
            log.info(f"[{self.source_id}] Saver: "
                     f"{self._saver.saved} saved, {self._saver.pruned} pruned → "
                     f"{self._saver.out_dir}")


# ─── Multi-Source Ingestion Manager ───────────────────────────────────────────
class IngestionManager:
    """
    Manages multiple FrameReader instances feeding into a SINGLE shared queue.

    This matches the diagram: all streams → one Image Queue → inference workers.

    Usage
    -----
        mgr = IngestionManager(
            sources=["stream1.mp4", "rtsp://192.168.1.10/stream"],
            cfg_overrides={"frame_skip": 4},
        )
        mgr.start()

        # In inference worker thread:
        while True:
            qf = mgr.queue.get()   # blocks until a frame is ready
            run_yolo(qf.frame_bgr)
    """

    def __init__(self, sources: list[str], cfg_overrides: dict = None):
        base_cfg = IngestionConfig(**(cfg_overrides or {}))

        # One shared queue for all sources
        self.queue: queue.Queue[QueuedFrame] = queue.Queue(
            maxsize=base_cfg.queue_maxsize * len(sources)
        )

        self.readers = []
        for i, src in enumerate(sources):
            cfg         = IngestionConfig(**(cfg_overrides or {}))
            cfg.source  = src
            reader      = FrameReader(cfg, self.queue, source_id=f"cam{i}")
            self.readers.append(reader)

    def start(self):
        for r in self.readers:
            r.start()
        log.info(f"IngestionManager started — {len(self.readers)} source(s)")

    def stop(self):
        for r in self.readers:
            r.stop()

    def diagnostics(self) -> list[dict]:
        return [
            {
                "source_id":     r.source_id,
                "fps":           round(r.fps_actual, 1),
                "total_read":    r.total_read,
                "total_queued":  r.total_queued,
                "total_dropped": r.total_dropped,
                "alive":         r.is_alive(),
            }
            for r in self.readers
        ]


# ─── Minimal stub inference worker (for testing without YOLO) ─────────────────
class StubInferenceWorker:
    """
    Pulls frames from the queue and prints diagnostics.
    Replace this with your real YOLO inference logic.
    """

    def __init__(self, frame_queue: queue.Queue, worker_id: int = 0):
        self.queue     = frame_queue
        self.worker_id = worker_id
        self._thread   = threading.Thread(target=self._run, daemon=True,
                                          name=f"InferenceWorker-{worker_id}")
        self._stop_evt = threading.Event()
        self.processed = 0

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_evt.set()

    def _run(self):
        log.info(f"[Worker-{self.worker_id}] Ready — waiting for frames.")
        t0 = time.perf_counter()

        while not self._stop_evt.is_set():
            try:
                qf: QueuedFrame = self.queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # ── Simulate YOLO inference time ──────────────────────────
            # A100: ~15ms, RTX 3090: ~25ms, RTX 3060: ~40ms
            time.sleep(0.025)

            self.processed += 1
            elapsed = time.perf_counter() - t0

            log.info(
                f"  [Worker-{self.worker_id}]  "
                f"frame #{qf.frame_index:>6}  "
                f"from {qf.source_id}  "
                f"shape {qf.width}×{qf.height}  "
                f"queue_remaining={self.queue.qsize()}  "
                f"processed={self.processed}  "
                f"throughput={self.processed / elapsed:.1f} fps"
            )

            self.queue.task_done()


# ─── Entry point — run a self-test ────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import os

    print("""
╔══════════════════════════════════════════════════════╗
║         DisasterVision — Frame Ingestion Test        ║
╚══════════════════════════════════════════════════════╝

This module tests the full pipeline:
  Video → FrameReader → Queue → StubInferenceWorker(s)

""")

    # ── Source selection ──────────────────────────────────────────────────────
    # Priority: CLI argument → environment variable → default test file
    source = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("VIDEO_SRC", "disaster_footage.mp4")
    )

    print(f"  Source      : {source}")
    print(f"  Frame skip  : every 3rd frame")
    print(f"  Queue size  : 8 slots")
    print(f"  Workers     : 2 parallel inference workers")
    print(f"  Saving      : every 10th queued frame → saved_frames/cam0/")
    print(f"  Max on disk : 500 frames (oldest pruned automatically)")
    print()

    # ── Build pipeline ────────────────────────────────────────────────────────
    cfg = IngestionConfig(
        source        = source,
        frame_skip    = 3,
        queue_maxsize = 8,
        loop_video    = True,
        resize_to     = (960, 540),
        reader_fps_cap= 30.0,
    )

    shared_queue = queue.Queue(maxsize=cfg.queue_maxsize)
    reader       = FrameReader(cfg, shared_queue, source_id="cam0")

    # Two parallel inference workers pulling from the same queue
    workers = [StubInferenceWorker(shared_queue, i) for i in range(2)]

    # ── Start everything ──────────────────────────────────────────────────────
    reader.start()
    for w in workers:
        w.start()

    print("  Pipeline running — press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(5)
            print(f"\n  ── Stats ──────────────────────────────────────────")
            print(f"  Reader fps    : {reader.fps_actual:.1f}")
            print(f"  Queue depth   : {shared_queue.qsize()}/{cfg.queue_maxsize}")
            print(f"  Total read    : {reader.total_read}")
            print(f"  Total queued  : {reader.total_queued}")
            print(f"  Total dropped : {reader.total_dropped}")
            if reader._saver:
                print(f"  Frames saved  : {reader._saver.saved}  "
                      f"(pruned: {reader._saver.pruned})")
            for w in workers:
                print(f"  Worker-{w.worker_id} done : {w.processed}")
            print()
    except KeyboardInterrupt:
        print("\n  Stopping...")
        reader.stop()
        for w in workers:
            w.stop()
        print("  Done.")
