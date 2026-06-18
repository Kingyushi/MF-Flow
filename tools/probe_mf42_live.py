"""Probe Trust MF API to see what it returns."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()

    # Intercept network requests to see what APIs fire
    responses_captured = []

    def on_response(response):
        url = response.url
        if "GetData" in url or "getdata" in url.lower() or "api" in url.lower():
            try:
                body = response.text()
                responses_captured.append({
                    "url": url,
                    "status": response.status,
                    "body_length": len(body),
                    "body_preview": body[:500] if len(body) < 2000 else body[:500] + "..."
                })
            except:
                responses_captured.append({"url": url, "status": response.status, "error": "could not read body"})

    page.on("response", on_response)

    print("Navigating to Trust MF...")
    page.goto("https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures", timeout=30000)
    page.wait_for_timeout(5000)

    print(f"\nCaptured {len(responses_captured)} API responses:")
    for r in responses_captured:
        print(f"  {r['url']} -> {r['status']} ({r.get('body_length', '?')} bytes)")

    # Now try the direct API call
    print("\n--- Direct API call ---")
    result = page.evaluate("""() => {
        return fetch('/api/api/Trust/GetData', {
            method: 'GET',
            headers: {'Accept': 'application/json'}
        })
        .then(r => r.text())
        .catch(e => 'ERROR: ' + e.message);
    }""")

    print(f"Direct API response length: {len(result)}")
    print(f"First 500 chars: {result[:500]}")

    # Try to parse it
    try:
        data = json.loads(result)
        print(f"\nParsed JSON type: {type(data)}")
        if isinstance(data, dict):
            print(f"Keys: {list(data.keys())}")
            for k, v in data.items():
                if isinstance(v, list):
                    print(f"  {k}: list of {len(v)} items")
                    if v:
                        print(f"    First item keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0])}")
                else:
                    print(f"  {k}: {type(v).__name__} = {str(v)[:100]}")
        elif isinstance(data, list):
            print(f"Array of {len(data)} items")
            if data:
                print(f"First item: {json.dumps(data[0], indent=2)[:500]}")
    except json.JSONDecodeError as e:
        print(f"Not valid JSON: {e}")

    # Also try the page content for links
    print("\n--- DOM links with 'monthly' or 'portfolio' ---")
    links = page.evaluate("""() => Array.from(document.querySelectorAll('a[href]'))
        .map(a => [(a.innerText || a.textContent || '').trim(), a.href])
        .filter(([t, h]) => {
            const combined = (t + ' ' + h).toLowerCase();
            return combined.includes('monthly') || combined.includes('portfolio');
        })
    """)
    for text, href in (links or [])[:20]:
        print(f"  [{text[:60]}] -> {href[:80]}")

    browser.close()
