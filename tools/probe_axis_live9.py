"""Axis - find the actual monthly consolidated portfolio entries."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    resp = page.goto('https://transact.axismf.com/cms/api/statutory-disclosures-scheme?cat=Monthly%20Scheme%20Portfolios', timeout=30000)
    data = resp.json()

    # Filter consolidated + has month + name indicates monthly
    consolidated = [d for d in data if d.get('field_aboutus_scheme_code') == 'Consolidated']

    # Look for monthly entries - they should have field_months set and NOT be "Weekly" or "Daily"
    monthly = []
    for d in consolidated:
        name = d.get('field_pdf_name_statutory', '')
        if 'weekly' in name.lower() or 'daily' in name.lower():
            continue
        if d.get('field_months') and d.get('field_year'):
            monthly.append(d)

    print(f'=== Monthly consolidated entries: {len(monthly)} ===')
    for d in monthly[-10:]:
        print(f'  year={d["field_year"]}, month={d["field_months"]}, name={d["field_pdf_name_statutory"]!r}, file={d["field_related_file"][:120]}')

    # Also check: what names do 2026 consolidated entries have?
    print('\n=== 2026 consolidated entries:')
    c2026 = [d for d in consolidated if d.get('field_year') == '2026']
    for d in c2026:
        name = d.get('field_pdf_name_statutory', '')
        month = d.get('field_months', '')
        print(f'  month={month!r}, name={name!r}, file={d.get("field_related_file","")[:100]}')

    # Check which have "Monthly" or "IN_MF_MONTHLY" in name or file
    print('\n=== Entries with "monthly" in name or file:')
    for d in data:
        name = d.get('field_pdf_name_statutory', '')
        fpath = d.get('field_related_file', '')
        if 'monthly' in name.lower() or 'MONTHLY' in fpath:
            code = d.get('field_aboutus_scheme_code', '')
            year = d.get('field_year', '')
            month = d.get('field_months', '')
            if year in ('2025', '2026') and code == 'Consolidated':
                print(f'  year={year}, month={month}, code={code}, name={name!r}, file={fpath[:120]}')

    page.close()
    browser.close()
