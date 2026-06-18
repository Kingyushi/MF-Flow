"""mf28 Navi v9 - Fetch the WP REST API via Playwright page context."""
import json
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

    # Fetch the documents API from within the page context
    data = page.evaluate("""() => {
        return fetch('/wp-json/nv/v1/documents')
            .then(r => r.json())
            .catch(e => ({error: e.toString()}));
    }""")

    if data and data.get('success') and data.get('data'):
        items = data['data']
        print(f'Total items: {len(items)}')
        print()
        for i, item in enumerate(items[:50]):
            print(f"{i}: {item.get('title', '')} -> {item.get('url', '')[:120]}")

        # Check what fields each item has
        if items:
            print()
            print('Item keys:', list(items[0].keys()))
            print('Sample item:', json.dumps(items[0], indent=2)[:500])
    else:
        print('Error or empty:', json.dumps(data, indent=2)[:500])

    with open('tools/probe_out/mf28_api.json', 'w') as f:
        json.dump(data, f, indent=2)

    b.close()
