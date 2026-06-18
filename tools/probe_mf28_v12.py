"""mf28 Navi v12 - Extract the API call logic from app.js."""
import json, re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://navi.com/mutual-fund/downloads/portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    # Fetch app.js content
    app_js = page.evaluate("""() => {
        return fetch('https://navi.com/wp-content/themes/hello-theme-child/assets/js/app.js?ver=1757510711')
            .then(r => r.text())
            .catch(e => '');
    }""")

    # Find the relevant section around financial_year and document fetching
    if app_js:
        # Find sections mentioning financial_year, nonce, wp-json, documents
        for keyword in ['financial_year', 'wp-json', 'documents', 'nonce', 'ajax', 'fetch']:
            indices = [m.start() for m in re.finditer(re.escape(keyword), app_js, re.I)]
            for idx in indices[:3]:
                start = max(0, idx - 200)
                end = min(len(app_js), idx + 300)
                excerpt = app_js[start:end]
                print(f'--- {keyword} at {idx} ---')
                print(excerpt)
                print()

    b.close()
