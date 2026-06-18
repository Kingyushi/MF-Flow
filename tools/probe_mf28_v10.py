"""mf28 Navi v10 - Intercept the API response from page load."""
import json
from playwright.sync_api import sync_playwright

api_bodies = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()

    def capture(response):
        if 'wp-json/nv/v1/documents' in response.url and response.status == 200:
            try:
                api_bodies.append(response.json())
            except:
                pass

    page.on('response', capture)
    page.goto('https://navi.com/mutual-fund/downloads/portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    if api_bodies:
        data = api_bodies[0]
        if data.get('success') and data.get('data'):
            items = data['data']
            print(f'Total items: {len(items)}')
            for i, item in enumerate(items[:50]):
                print(f"  {i}: {item.get('title', '')} -> {item.get('url', '')[:120]}")
            if items:
                print()
                print('Keys:', list(items[0].keys()))
        else:
            print('API returned error:', json.dumps(data, indent=2)[:500])
    else:
        print('No API response captured')

    with open('tools/probe_out/mf28_api.json', 'w') as f:
        json.dump(api_bodies, f, indent=2, default=str)

    b.close()
