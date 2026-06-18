"""Axis - parse the full scheme list API response to understand the data shape."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    resp = page.goto('https://transact.axismf.com/cms/api/statutory-disclosures-scheme?cat=Monthly%20Scheme%20Portfolios', timeout=30000)
    data = resp.json()
    print(f'=== Total entries: {len(data)} ===')

    # Show first entry structure
    if data:
        print(f'\n=== First entry:')
        print(json.dumps(data[0], indent=2, ensure_ascii=False))

    # Filter consolidated entries
    consolidated = [d for d in data if d.get('field_aboutus_scheme_code') == 'Consolidated']
    print(f'\n=== Consolidated entries: {len(consolidated)} ===')

    # Group by year
    by_year = {}
    for d in consolidated:
        year = d.get('field_year', 'unknown')
        by_year.setdefault(year, []).append(d)

    for year in sorted(by_year.keys(), reverse=True)[:5]:
        entries = by_year[year]
        print(f'\n--- Year {year}: {len(entries)} entries ---')
        for e in entries[:3]:
            print(f'  name={e.get("field_pdf_name_statutory")!r}, file={e.get("field_related_file", "")[:100]}, month={e.get("field_month", "")}, class={e.get("field_pdf_asset_class", "")}')

    # Get the latest entry
    latest = consolidated[-1] if consolidated else None
    if latest:
        print(f'\n=== Latest consolidated entry:')
        print(json.dumps(latest, indent=2, ensure_ascii=False))

    # Sort by year desc to find truly latest
    for d in consolidated:
        try:
            d['_year_int'] = int(d.get('field_year', '0'))
        except:
            d['_year_int'] = 0
    consolidated.sort(key=lambda d: (d['_year_int'], d.get('field_pdf_name_statutory', '')), reverse=True)
    if consolidated:
        print(f'\n=== Latest by year sort:')
        for d in consolidated[:5]:
            print(f'  year={d.get("field_year")}, name={d.get("field_pdf_name_statutory")!r}, file={d.get("field_related_file","")[:120]}')

    page.close()
    browser.close()
