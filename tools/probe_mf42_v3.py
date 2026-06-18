"""mf42 Trust v3 - Intercept the API to find portfolio data."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    api_responses = []

    def capture_response(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        if 'GetData' in url or 'Trust' in url or 'api' in url.lower() or 'portfolio' in url.lower() or '.xlsx' in url.lower() or '.xls' in url.lower():
            try:
                body = response.text()
            except:
                body = '<binary>'
            api_responses.append({
                'url': url[:300], 'status': response.status, 'ct': ct,
                'body_preview': body[:5000] if isinstance(body, str) else ''
            })

    page.on('response', capture_response)
    page.goto('https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    # Check what the GetData API returns
    out['api_responses_initial'] = [r for r in api_responses]

    # Now click Monthly disclosure section
    page.evaluate("""() => {
        const all = [...document.querySelectorAll('button, a, div, span, li, h3, h4, p')];
        const monthly = all.find(b => {
            const t = (b.innerText || '').trim();
            return /^monthly\\s*(disclosure|portfolio)/i.test(t);
        });
        if (monthly) monthly.click();
    }""")
    page.wait_for_timeout(5000)

    out['api_responses_after_click'] = [r for r in api_responses if r not in out['api_responses_initial']]

    # Check if there's an xlsx download in the API data
    # Look through all API bodies for xlsx URLs
    xlsx_urls = []
    for r in api_responses:
        body = r.get('body_preview', '')
        if '.xlsx' in body.lower() or '.xls' in body.lower():
            # Extract URLs
            import re
            urls = re.findall(r'https?://[^\s"\'<>]+\.xlsx?[^\s"\'<>]*', body, re.I)
            xlsx_urls.extend(urls)
    out['xlsx_urls_in_api'] = xlsx_urls

    # Also check for "monthly" in the API data
    monthly_hits = []
    for r in api_responses:
        body = r.get('body_preview', '')
        if 'monthly' in body.lower() or 'Monthly' in body:
            monthly_hits.append(r['url'][:120])
    out['monthly_in_api'] = monthly_hits

    b.close()

with open('tools/probe_out/mf42_v3.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf42 v3')
print()
print('Initial API responses:', len(out['api_responses_initial']))
for r in out['api_responses_initial'][:5]:
    print(f"  URL: {r['url'][:120]}")
    print(f"  Status: {r['status']} CT: {r['ct']}")
    print(f"  Body preview (first 500): {r['body_preview'][:500]}")
    print()
print('After click API responses:', len(out.get('api_responses_after_click', [])))
for r in out.get('api_responses_after_click', [])[:5]:
    print(f"  URL: {r['url'][:120]}")
    print(f"  Body preview (first 500): {r['body_preview'][:500]}")
    print()
print('XLSX URLs in API:', out.get('xlsx_urls_in_api', []))
print('Monthly in API:', out.get('monthly_in_api', []))
