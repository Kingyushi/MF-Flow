"""mf42 Trust v5 - Parse the GetData API response for monthly portfolio files."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    disclosure_data = None

    def capture(response):
        nonlocal disclosure_data
        url = response.url
        ct = response.headers.get('content-type', '')
        if 'GetData' in url and 'json' in ct:
            try:
                data = response.json()
                arr = data.get('resultSetArray', [])
                if arr and isinstance(arr[0], dict) and 'fileurl' in arr[0] and 'title' in arr[0]:
                    disclosure_data = arr
            except:
                pass

    page.on('response', capture)
    page.goto('https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    if disclosure_data:
        # Filter to monthly disclosure items
        monthly_items = [
            item for item in disclosure_data
            if 'monthly' in item.get('title', '').lower()
            and 'portfolio' in item.get('title', '').lower()
        ]
        out['monthly_items'] = monthly_items[:10]

        # Also check the matching_slugs field
        portfolio_monthly = [
            item for item in disclosure_data
            if 'portfolio-monthly-disclosure' in item.get('matching_slugs', '')
        ]
        out['portfolio_monthly_by_slug'] = portfolio_monthly[:10]

        # Get ALL unique matching_slugs
        slugs = set()
        for item in disclosure_data:
            for s in item.get('matching_slugs', '').split(','):
                if s.strip():
                    slugs.add(s.strip())
        out['unique_slugs'] = sorted(slugs)

        out['total_items'] = len(disclosure_data)
        out['sample_item'] = disclosure_data[0] if disclosure_data else None
    else:
        out['no_disclosure_data'] = True

    b.close()

with open('tools/probe_out/mf42_v5.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf42 v5')
print('Total items:', out.get('total_items'))
print('Unique slugs:', out.get('unique_slugs'))
print()
print('Monthly items by title:', json.dumps(out.get('monthly_items', []), indent=2)[:2000])
print()
print('Monthly items by slug:', json.dumps(out.get('portfolio_monthly_by_slug', []), indent=2)[:2000])
