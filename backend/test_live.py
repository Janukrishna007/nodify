"""RTSP input validation, latest-frame backpressure, retry and stop behaviour."""
import threading
import unittest
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError

from live import LiveCapture, StreamRequest


class StreamTests(unittest.TestCase):
    def test_only_camera_urls_and_no_saved_secrets(self):
        for url in ("file:///private.mp4", "http://camera/live", "rtsp:///live", "rtsp://camera:bad/live", "rtsp://camera/live\n"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                StreamRequest(url=url)
        request = StreamRequest(url="rtsp://old:secret@camera:554/path-token?token=private",
                                username="pilot@example.com", password="p@ss:/word")
        self.assertEqual(request.public_source(), "rtsp://camera:554")
        self.assertIn("pilot%40example.com:p%40ss%3A%2Fword@camera", request.connection_url())
        self.assertNotIn("private", repr(request))
        self.assertNotIn("p@ss:/word", repr(request))

    def test_consumer_gets_latest_sample_and_stop_releases_reader(self):
        produced = threading.Event()
        stop = threading.Event()

        class Capture:
            released = False
            count = 0
            def isOpened(self): return True
            def get(self, _): return 30
            def read(self):
                if self.count < 20:
                    self.count += 1
                    return True, np.full((2, 2, 3), self.count, dtype=np.uint8)
                produced.set()
                stop.wait(2)
                return False, None
            def release(self): self.released = True

        source = Capture()
        states = []
        with patch("live.open_stream", return_value=source):
            reader = LiveCapture("rtsp://camera/live", 3, stop, lambda state, _: states.append(state)).start()
            try:
                self.assertTrue(produced.wait(2))
                ok, frame = reader.read()
                self.assertTrue(ok)
                self.assertEqual(reader.number, 18)
                self.assertEqual(int(frame[0, 0, 0]), 19)
                self.assertEqual(reader.dropped_frames, 6)
                self.assertEqual(reader.frames_read, 20)
                self.assertEqual(states, ["connecting", "connected"])
            finally:
                reader.release()
            self.assertTrue(source.released)
            self.assertFalse(reader._thread.is_alive())

    def test_dead_endpoint_fails_safely_after_bounded_retries(self):
        stop = threading.Event()
        stop.wait = lambda _: stop.is_set()
        with patch("live.open_stream", side_effect=RuntimeError("rtsp://user:secret@camera/token")) as opened:
            reader = LiveCapture("rtsp://user:secret@camera/token", 3, stop, lambda *_: None).start()
            try:
                with self.assertRaisesRegex(RuntimeError, "after 3 retries") as error:
                    reader.read()
                self.assertNotIn("secret", str(error.exception))
                self.assertEqual(opened.call_count, 4)
            finally:
                reader.release()


if __name__ == "__main__":
    unittest.main()
