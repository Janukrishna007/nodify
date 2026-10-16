"""End-to-end check for the redesigned workspace using real local inference."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from config import DATA_DIR


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_navigation_timeout(90000)
        page.set_default_timeout(60000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:3000/dashboard", wait_until="domcontentloaded")
        page.get_by_role("heading", name="Intelligence overview", exact=True).wait_for()
        page.goto("http://127.0.0.1:3000/upload", wait_until="domcontentloaded")
        page.get_by_text("Analysis server connected", exact=True).wait_for()
        page.locator('input[type="file"]').set_input_files(str(DATA_DIR / "validation-clip.mp4"))
        page.get_by_label("Selected video preview").wait_for()
        page.get_by_role("button", name="Start analysis", exact=True).click()
        page.wait_for_url("**/dashboard?session=*", wait_until="domcontentloaded", timeout=90000)
        page.locator('[data-slot="badge"][data-status="completed"]').wait_for(timeout=180000)
        page.get_by_alt_text("Analyzed video frame 27", exact=True).wait_for()
        page.wait_for_function("Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)")
        assert page.get_by_text("Cumulative heatmap", exact=True).is_visible()
        page.get_by_role("button", name="Previous", exact=True).click()
        page.get_by_alt_text("Analyzed video frame 24", exact=True).wait_for()
        page.get_by_text("Reviewing saved frame", exact=True).wait_for()
        page.get_by_role("button", name="Hide heatmap", exact=True).click()
        page.get_by_role("button", name="Show heatmap", exact=True).wait_for()
        page.get_by_role("button", name="Show heatmap", exact=True).click()
        flood_filter = page.get_by_role("button", name="flood", exact=True)
        flood_filter.click()
        assert flood_filter.get_attribute("aria-pressed") == "false"
        flood_filter.click()
        page.get_by_role("tab", name="Session details", exact=True).click()
        page.get_by_text("Confidence threshold", exact=True).wait_for()
        page.get_by_role("button", name="Follow latest", exact=True).click()
        page.get_by_text("Following latest result", exact=True).wait_for()
        page.get_by_role("button", name="Play analyzed frames", exact=True).click()
        page.get_by_role("button", name="Pause frame playback", exact=True).wait_for()
        page.wait_for_function("document.querySelector('img[alt^=\"Analyzed video frame\"]').alt !== 'Analyzed video frame 27'")
        page.get_by_role("button", name="Pause frame playback", exact=True).click()
        page.get_by_role("button", name="Follow latest", exact=True).click()
        with page.expect_download() as download:
            page.get_by_role("link", name="Download report", exact=True).click()
        download.value.save_as(str(DATA_DIR / "browser-downloaded-report.json"))
        report = json.loads((DATA_DIR / "browser-downloaded-report.json").read_text())
        assert report["session"]["analyzedFrames"] == 10
        assert page.locator('[aria-label="Cumulative risk grid"] > div').count() == 48
        page.screenshot(path=str(DATA_DIR / "dashboard-verified.png"), full_page=True)
        print("Browser session:", page.url, flush=True)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_url("**/upload", wait_until="domcontentloaded")
        page.get_by_text("Analysis server connected", exact=True).wait_for()
        page.get_by_role("heading", name="Drop your video here", exact=True).wait_for()
        assert page.locator('input[type="file"]').input_value() == ""
        # The reload flag must be consumed once: opening saved results still works.
        page.get_by_role("link", name="Video analysis", exact=True).click()
        page.get_by_alt_text("Analyzed video frame 27", exact=True).wait_for()
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("button", name="Open navigation", exact=True).click()
        page.get_by_role("dialog").get_by_role("link", name="Session history", exact=True).click()
        page.get_by_role("heading", name="Session history", exact=True).wait_for(timeout=60000)
        assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        assert not errors, errors
        browser.close()
    print("PASS: upload, real inference, frame review/playback, filters, heatmap, report, refresh and mobile navigation.", flush=True)


if __name__ == "__main__":
    main()
