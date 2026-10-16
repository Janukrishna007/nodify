"""Run against a real RTSP publisher (default: local validation feed)."""
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

from config import DATA_DIR


def wait_session(request, session_id, predicate, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = request.get(f"http://127.0.0.1:3000/api/sessions/{session_id}").json()
        if predicate(session):
            return session
        if session["status"] == "failed":
            raise AssertionError(session.get("error"))
        time.sleep(0.5)
    raise AssertionError("RTSP session did not reach expected state")


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_navigation_timeout(90000)
        page.set_default_timeout(60000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        session_id = None
        try:
            assert not page.request.get("http://127.0.0.1:3000/api/health").json()["activeSession"], "Another source is running"
            page.goto("http://127.0.0.1:3000", wait_until="domcontentloaded")
            page.wait_for_url("**/upload", wait_until="domcontentloaded")
            page.get_by_text("Analysis server connected", exact=True).wait_for()
            page.get_by_role("tab", name="Drone live stream", exact=True).click()
            page.get_by_label("Stream name", exact=True).fill("RTSP validation")
            page.get_by_label("RTSP stream address", exact=True).fill("rtsp://127.0.0.1:18554/drone?token=validation-private")
            page.get_by_label("Username (optional)", exact=True).fill("validation")
            page.get_by_label("Password (optional)", exact=True).fill("validation-secret")
            page.screenshot(path=str(DATA_DIR / "rtsp-setup-verified.png"), full_page=True)
            page.get_by_role("button", name="Connect & analyze", exact=True).click()
            page.wait_for_url("**/dashboard?session=*", wait_until="domcontentloaded")
            session_id = parse_qs(urlsplit(page.url).query)["session"][0]
            session = wait_session(page.request, session_id, lambda item: item["analyzedFrames"] >= 4)
            assert session["sourceType"] == "rtsp"
            assert session["connectionState"] == "connected"
            assert session["sourceAddress"] == "rtsp://127.0.0.1:18554"
            assert "validation-secret" not in json.dumps(session)
            assert "validation-private" not in json.dumps(session)
            frame = page.request.get(f"http://127.0.0.1:3000/api/sessions/{session_id}/frames/{session['latestIndex']}").json()
            assert len(frame["cells"]) == 48 and frame["width"] > 0
            assert frame["timestamp"] > 0
            assert all(box["type"] in ("fire", "smoke", "flood") for box in frame["detections"])
            for key in ("imageUrl", "annotatedUrl", "heatmapUrl", "cumulativeUrl"):
                response = page.request.get("http://127.0.0.1:3000" + frame[key])
                assert response.ok and response.body().startswith(b"\xff\xd8")
            page.get_by_text("Stream connected", exact=True).wait_for()
            page.get_by_alt_text(re.compile("Analyzed video frame")).wait_for()
            page.screenshot(path=str(DATA_DIR / "rtsp-dashboard-verified.png"), full_page=True)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_url("**/upload", wait_until="domcontentloaded")
            page.get_by_text("Analysis server connected", exact=True).wait_for()
            page.get_by_role("heading", name="Drop your video here", exact=True).wait_for()
            assert page.locator('input[type="file"]').input_value() == ""
            page.get_by_role("button", name="Stop current analysis", exact=True).click()
            page.get_by_text("An analysis is already running", exact=True).wait_for(state="detached", timeout=30000)
            ended = page.request.get(f"http://127.0.0.1:3000/api/sessions/{session_id}").json()
            assert ended["status"] == "cancelled" and ended["connectionState"] == "disconnected"
            assert not page.request.get("http://127.0.0.1:3000/api/health").json()["activeSession"]
            page.get_by_role("tab", name="Drone live stream", exact=True).click()
            assert page.get_by_label("RTSP stream address", exact=True).input_value() == ""
            assert page.get_by_label("Password (optional)", exact=True).input_value() == ""
            page.get_by_role("tab", name="Upload video", exact=True).click()
            page.locator('input[type="file"]').set_input_files(str(DATA_DIR / "validation-clip.mp4"))
            page.get_by_role("button", name="Start analysis", exact=True).click()
            page.wait_for_url("**/dashboard?session=*", wait_until="domcontentloaded")
            next_id = parse_qs(urlsplit(page.url).query)["session"][0]
            assert next_id != session_id
            next_session = wait_session(page.request, next_id, lambda item: item["status"] == "completed")
            assert next_session["analyzedFrames"] == 10
            page.reload(wait_until="domcontentloaded")
            page.wait_for_url("**/upload", wait_until="domcontentloaded")
            page.get_by_role("heading", name="Drop your video here", exact=True).wait_for()
            page.set_viewport_size({"width": 390, "height": 844})
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert not errors, errors
            print("PASS: real RTSP frames, model inference, four image views, clean refresh, stop, next video upload, credential privacy and mobile layout.", flush=True)
            print("RTSP session:", session_id, flush=True)
        finally:
            if session_id:
                page.request.post(f"http://127.0.0.1:3000/api/sessions/{session_id}/cancel")
            browser.close()


if __name__ == "__main__":
    main()
