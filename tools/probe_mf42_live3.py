"""Get the full POST body of request 4."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()

    def on_request(request):
        if "GetData" in request.url and request.post_data and "GetDisclosureByType" in (request.post_data or ""):
            print("FULL POST BODY:")
            print(request.post_data)

    page.on("request", on_request)
    page.goto("https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures", timeout=30000)
    page.wait_for_timeout(8000)
    browser.close()
