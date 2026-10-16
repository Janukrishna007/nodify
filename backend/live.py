"""RTSP ingestion with bounded I/O and a latest-frame buffer for slow inference."""
import os
import threading
import time
from urllib.parse import quote, urlsplit, urlunsplit

import cv2
from pydantic import BaseModel, Field, SecretStr, field_validator

# Use reliable TCP on the local drone/receiver network. Suppress native FFmpeg
# messages, which can include credentials embedded in a camera URL.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
LIVE_FRAME_LIMIT = 300
IO_TIMEOUT_MS = 8000
MAX_RETRIES = 3


class StreamRequest(BaseModel):
    url: SecretStr
    name: str = Field(default="Drone live stream", min_length=1, max_length=80)
    username: str = Field(default="", max_length=256)
    password: SecretStr = SecretStr("")
    frame_skip: int = Field(default=3, ge=1, le=60)
    confidence: float = Field(default=0.45, ge=0.1, le=0.95)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        raw = value.get_secret_value()
        try:
            parts = urlsplit(raw)
            valid = (parts.scheme in ("rtsp", "rtsps") and bool(parts.hostname)
                     and parts.port != 0 and not parts.fragment and len(raw) <= 2048
                     and not any(char.isspace() or ord(char) < 32 for char in raw))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Enter an RTSP address such as rtsp://192.168.1.10:554/live")
        return value

    def connection_url(self):
        parts = urlsplit(self.url.get_secret_value())
        if not self.username:
            return self.url.get_secret_value()
        host = parts.netloc.rsplit("@", 1)[-1]
        credentials = quote(self.username, safe="") + ":" + quote(self.password.get_secret_value(), safe="")
        return urlunsplit(parts._replace(netloc=credentials + "@" + host))

    def public_source(self):
        parts = urlsplit(self.url.get_secret_value())
        # Keep path/query tokens and camera credentials out of persisted metadata.
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], "", "", ""))


def open_stream(url):
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, IO_TIMEOUT_MS,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, IO_TIMEOUT_MS,
    ])


class LiveCapture:
    """Only retain the latest sampled frame; never build a stale video queue."""

    def __init__(self, url, frame_skip, stop, on_state):
        self._url = url
        self._skip = frame_skip
        self._stop = stop
        self._on_state = on_state
        self._condition = threading.Condition()
        self._latest = None
        self._consumed = -1
        self._done = False
        self._error = None
        self._start = time.monotonic()
        self._thread = threading.Thread(target=self._receive, daemon=True, name="rtsp-reader")
        self.fps = 25.0
        self.number = 0
        self.timestamp = 0.0
        self.frames_read = 0
        self.dropped_frames = 0

    def start(self):
        self._thread.start()
        return self

    def _receive(self):
        failures = 0
        try:
            while not self._stop.is_set():
                self._on_state("connecting" if failures == 0 else "reconnecting", failures)
                capture = None
                received = False
                try:
                    capture = open_stream(self._url)
                    if capture.isOpened():
                        fps = capture.get(cv2.CAP_PROP_FPS)
                        if 0 < fps < 1000:
                            self.fps = fps
                        while not self._stop.is_set():
                            ok, frame = capture.read()
                            if not ok:
                                break
                            if not received:
                                self._on_state("connected", failures)
                                received = True
                            number = self.frames_read
                            self.frames_read += 1
                            if number % self._skip == 0:
                                with self._condition:
                                    self._latest = (number, time.monotonic() - self._start, frame)
                                    self._condition.notify_all()
                except Exception:
                    # Native errors may contain URL secrets. Expose a safe explanation.
                    pass
                finally:
                    if capture is not None:
                        capture.release()
                if self._stop.is_set():
                    break
                # Retry short connections too; a flapping camera must eventually fail.
                failures += 1
                if failures > MAX_RETRIES:
                    self._error = "Drone stream disconnected or could not be opened after 3 retries. Check the RTSP address, credentials, network and camera output, then reconnect."
                    break
                self._on_state("reconnecting", failures)
                self._stop.wait(min(failures, 3))
        finally:
            self._url = ""
            with self._condition:
                self._done = True
                self._condition.notify_all()

    def read(self):
        with self._condition:
            while not self._stop.is_set():
                if self._latest is not None and self._latest[0] > self._consumed:
                    number, timestamp, frame = self._latest
                    self.dropped_frames += max(0, (number - self._consumed - 1) // self._skip) if self._consumed >= 0 else number // self._skip
                    self._consumed = self.number = number
                    self.timestamp = timestamp
                    return True, frame
                if self._done:
                    if self._error:
                        raise RuntimeError(self._error)
                    return False, None
                self._condition.wait(0.25)
        return False, None

    def release(self):
        self._stop.set()
        self._thread.join((IO_TIMEOUT_MS / 1000) + 2)
