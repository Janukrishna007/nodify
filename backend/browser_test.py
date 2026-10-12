"""Browser smoke test against the running UI; uses an installed Edge browser."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

from config import DATA_DIR


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:3000/upload", wait_until="networkidle")
        page.get_by_text("Analysis server connected", exact=True).wait_for()
        page.locator('input[type="file"]').set_input_files(str(DATA_DIR / "validation-clip.mp4"))
        page.get_by_role("button", name="Start analysis", exact=True).click()
        page.wait_for_url("**/dashboard?session=*", timeout=60000)
        page.wait_for_function("document.body.innerText.includes('completed ·')", timeout=180000)
        page.locator('img[alt^="Analyzed video frame"]').wait_for()
        page.wait_for_function("Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)")
        assert page.get_by_text("Cumulative heatmap", exact=True).is_visible()
        page.get_by_role("button", name="Previous", exact=True).click()
        page.get_by_text("Reviewing saved frame", exact=True).wait_for()
        assert page.get_by_role("heading", name="Analyzed frame 24 · 0.96s", exact=True).is_visible()
        page.get_by_role("button", name="Hide heatmap", exact=True).click()
        page.get_by_role("button", name="Show heatmap", exact=True).wait_for()
        page.get_by_role("button", name="Show heatmap", exact=True).click()
        flood_filter = page.get_by_role("button", name="flood", exact=True)
        flood_filter.click()
        assert flood_filter.get_attribute("aria-pressed") == "false"
        flood_filter.click()
        page.get_by_role("button", name="Follow latest", exact=True).click()
        page.get_by_text("Following latest result", exact=True).wait_for()
        with page.expect_download() as download:
            page.get_by_role("link", name="Download report", exact=True).click()
        download.value.save_as(str(DATA_DIR / "browser-downloaded-report.json"))
        report = json.loads((DATA_DIR / "browser-downloaded-report.json").read_text())
        assert report["session"]["analyzedFrames"] == 10
        assert report["session"]["detectionCounts"].get("flood", 0) > 0
        assert page.locator('[aria-label="Cumulative risk grid"] > div').count() == 48
        page.screenshot(path=str(DATA_DIR / "dashboard-verified.png"), full_page=True)
        print("Browser session:", page.url, flush=True)
        page.reload(wait_until="networkidle")
        page.locator('img[alt^="Analyzed video frame"]').wait_for()
        page.get_by_text("Following latest result", exact=True).wait_for()
        assert not errors, errors
        browser.close()
    print("PASS: browser upload, inference, frame review, filters, heatmap toggle, report download and refresh.", flush=True)


if __name__ == "__main__":
    main()
