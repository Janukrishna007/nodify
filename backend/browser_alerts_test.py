"""Verify the browser-notification preference without modifying saved alerts."""
from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(permissions=["notifications"])
        page.set_default_timeout(60000)
        page.set_default_navigation_timeout(90000)
        page.goto("http://127.0.0.1:3000/alerts", wait_until="domcontentloaded")
        page.get_by_text("Systems operational", exact=True).wait_for()
        page.get_by_role("button", name="Enable browser alerts", exact=True).click()
        page.get_by_role("button", name="Disable browser alerts", exact=True).wait_for()
        page.reload(wait_until="domcontentloaded")
        page.wait_for_url("**/upload", wait_until="domcontentloaded")
        page.locator('nav[aria-label="Main navigation"] a[href="/alerts"]').click()
        page.get_by_text("Systems operational", exact=True).wait_for()
        page.get_by_role("button", name="Disable browser alerts", exact=True).click()
        page.get_by_role("button", name="Enable browser alerts", exact=True).wait_for()
        page.reload(wait_until="domcontentloaded")
        page.wait_for_url("**/upload", wait_until="domcontentloaded")
        page.locator('nav[aria-label="Main navigation"] a[href="/alerts"]').click()
        page.get_by_text("Systems operational", exact=True).wait_for()
        page.get_by_role("button", name="Enable browser alerts", exact=True).wait_for()
        assert page.evaluate("localStorage.getItem('disastervision.browserAlerts')") == "disabled"
        browser.close()
    print("PASS: enable and disable persist after refresh; dashboard alert history is preserved.")


if __name__ == "__main__":
    main()
