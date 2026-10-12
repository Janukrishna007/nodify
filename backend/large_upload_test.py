"""Regression check: a large video must reach inference intact via the browser."""
import argparse
import hashlib
from pathlib import Path
import time

from playwright.sync_api import sync_playwright
import requests

from config import DATA_DIR


def checksum(path):
    with path.open("rb") as file:
        result = hashlib.sha256()
        while chunk := file.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--keep-running", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    assert args.video.stat().st_size > 10 * 1024 * 1024, "Use a video larger than the old 10 MB proxy limit."
    assert requests.get(args.url + "/api/health", timeout=30).json()["activeSession"] is None, "An analysis is already running."
    session_id = None
    succeeded = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(args.url + "/upload", wait_until="networkidle")
            page.get_by_text("Analysis server connected", exact=True).wait_for()
            page.locator('input[type="file"]').set_input_files(str(args.video.resolve()))
            with page.expect_response(lambda response: response.url.endswith("/api/analysis"), timeout=180000) as upload:
                page.get_by_role("button", name="Start analysis", exact=True).click()
            response = upload.value
            assert response.status == 202, f"HTTP {response.status}: {response.text()[:1000]}"
            session_id = response.json()["id"]
            print(f"Upload accepted: {args.video.stat().st_size} bytes; session {session_id}", flush=True)
            saved = DATA_DIR / session_id / ("source" + args.video.suffix.lower())
            assert saved.stat().st_size == args.video.stat().st_size, "Uploaded video was truncated."
            assert checksum(saved) == checksum(args.video), "Uploaded video bytes differ from the original."
            page.wait_for_url("**/dashboard?session=*", timeout=60000)
            page.locator('img[alt^="Analyzed video frame"]').wait_for(timeout=180000)
            page.wait_for_function("Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)")
            # Next.js includes an empty alert for route announcements.
            alerts = [text.strip() for text in page.get_by_role("alert").all_text_contents() if text.strip()]
            assert not alerts, alerts
            session = requests.get(args.url + f"/api/sessions/{session_id}", timeout=30).json()
            assert session["analyzedFrames"] > 0, session
            print("Inference active:", {key: session.get(key) for key in ("status", "totalFrames", "analyzedFrames", "detectionCounts")}, flush=True)
            page.screenshot(path=str(DATA_DIR / "large-upload-verified.png"), full_page=True)
            print("Dashboard:", page.url, flush=True)
            browser.close()
        succeeded = True
        print("PASS: large browser upload, identical saved video, dashboard navigation and actual analyzed frames.", flush=True)
    finally:
        if session_id and (not args.keep_running or not succeeded):
            requests.post(args.url + f"/api/sessions/{session_id}/cancel", timeout=30).raise_for_status()
            for _ in range(120):
                session = requests.get(args.url + f"/api/sessions/{session_id}", timeout=30).json()
                if session["status"] in ("completed", "failed", "cancelled"):
                    break
                time.sleep(0.5)


if __name__ == "__main__":
    main()
