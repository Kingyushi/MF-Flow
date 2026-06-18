"""mf28 Navi v11 - Look at app.js to understand how the page fetches documents."""
import json
from playwright.sync_api import sync_playwright

api_bodies = []

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()

    def capture(response):
        url = response.url
        if 'documents' in url.lower() or 'portfolio' in url.lower():
            try:
                ct = response.headers.get('content-type', '')
                if 'json' in ct:
                    api_bodies.append({'url': url, 'data': response.json()})
                elif 'javascript' in ct and 'app.js' in url:
                    api_bodies.append({'url': url, 'data': response.text()[:5000]})
            except:
                pass
        if 'app.js' in url:
            try:
                api_bodies.append({'url': url, 'data': response.text()[:10000]})
            except:
                pass

    page.on('response', capture)
    page.goto('https://navi.com/mutual-fund/downloads/portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=30000)
    except:
        pass
    page.wait_for_timeout(8000)

    # Check if maybe the API was called but with different timing
    print(f'Captured responses: {len(api_bodies)}')
    for r in api_bodies:
        print(f"  URL: {r['url'][:120]}")
        data = r['data']
        if isinstance(data, str):
            print(f"  JS preview: {data[:300]}")
        else:
            print(f"  JSON: {json.dumps(data)[:300]}")
        print()

    # Check the page's app.js content to find how it fetches documents
    app_js_url = page.evaluate("""() => {
        const scripts = [...document.querySelectorAll('script[src]')];
        return scripts.map(s => s.src).filter(s => s.includes('app.js') || s.includes('theme-child'));
    }""")
    print('App JS URLs:', app_js_url)

    # Inspect the app.js
    for url in app_js_url[:2]:
        content = page.evaluate(f"""() => {{
            return fetch('{url}').then(r => r.text()).catch(e => '');
        }}""")
        if content:
            # Look for document/portfolio/API related code
            import re
            # Find fetch or ajax calls related to documents
            matches = re.findall(r'.{0,100}(document|portfolio|wp-json|nv/v1|financial_year|duration|month).{0,100}', content, re.I)
            print(f'\nRelevant code from {url}:')
            for m in matches[:20]:
                print(f'  {m.strip()}')

    b.close()
