"""Live probe for Axis MF - deeper: click Monthly Scheme Portfolios, explore form."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    responses = []
    page.on('response', lambda r: responses.append({
        'url': r.url[:300], 'status': r.status, 'ct': r.headers.get('content-type','')
    }))

    page.goto('https://transact.axismf.com/statutory-disclosures', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    # Click "Monthly Scheme Portfolios"
    monthly = page.locator('text=Monthly Scheme Portfolios').first
    monthly.click(timeout=10000)
    page.wait_for_timeout(5000)

    # Snapshot responses after click
    resp_count_after_click = len(responses)
    json_after = [r for r in responses if 'json' in r['ct'].lower()]
    print('=== JSON responses after clicking Monthly Scheme Portfolios:')
    for r in json_after[-5:]:
        print(f'  {r["status"]} {r["url"][:200]}')

    # Body text after click
    body = page.evaluate('() => document.body?.innerText?.substring(0, 8000) || ""')
    print('=== Body text after click (first 8000):')
    print(body[:8000])

    # Check for selects
    selects = page.evaluate("""() => {
        return [...document.querySelectorAll('select')].map(sel => ({
            name: sel.name, id: sel.id, cls: sel.className,
            options: [...sel.options].map(o => ({text: o.text.trim(), value: o.value}))
        }));
    }""")
    print('=== Select dropdowns:', json.dumps(selects, indent=2))

    # Check for year buttons/tabs
    year_elements = page.evaluate(r"""() => {
        const all = [...document.querySelectorAll('*')];
        return all.filter(e => /^20\d{2}$/.test((e.innerText||'').trim()) && e.children.length === 0)
            .map(e => ({tag: e.tagName, text: e.innerText.trim(), cls: (e.className||'').substring(0, 80)}))
            .slice(0, 20);
    }""")
    print('=== Year-like elements:', json.dumps(year_elements, indent=2))

    # Check for month elements
    month_elements = page.evaluate("""() => {
        const months = ['january','february','march','april','may','june','july','august','september','october','november','december'];
        const all = [...document.querySelectorAll('*')];
        return all.filter(e => months.includes((e.innerText||'').trim().toLowerCase()) && e.children.length === 0)
            .map(e => ({tag: e.tagName, text: e.innerText.trim(), cls: (e.className||'').substring(0, 80)}))
            .slice(0, 30);
    }""")
    print('=== Month-like elements:', json.dumps(month_elements, indent=2))

    # Check for radio buttons, chips, tabs
    ui_controls = page.evaluate("""() => {
        const els = document.querySelectorAll('input[type="radio"], .mat-radio-button, [role="radio"], .mat-chip, .mat-tab-label, .mat-button-toggle, .year-tab, .month-tab');
        return [...els].map(e => ({
            tag: e.tagName,
            text: (e.innerText || e.textContent || '').trim().substring(0, 100),
            cls: (e.className||'').substring(0, 100),
            checked: e.checked || false
        })).slice(0, 30);
    }""")
    print('=== UI controls (radio/chips/tabs):', json.dumps(ui_controls, indent=2))

    # Check for Angular material components
    mat_components = page.evaluate("""() => {
        const els = document.querySelectorAll('mat-radio-group, mat-radio-button, mat-select, mat-tab-group, mat-button-toggle-group');
        return [...els].map(e => ({
            tag: e.tagName,
            text: (e.innerText || '').trim().substring(0, 200),
            cls: (e.className||'').substring(0, 100)
        })).slice(0, 20);
    }""")
    print('=== Angular material components:', json.dumps(mat_components, indent=2))

    # Look for any download links / xlsx links
    xlsx_links = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].filter(a =>
            a.href.includes('.xlsx') || a.href.includes('.xls') || a.href.includes('download')
        ).map(a => ({text: (a.innerText||'').trim().substring(0, 100), href: a.href.substring(0, 300)})).slice(0, 20);
    }""")
    print('=== xlsx/download links:', json.dumps(xlsx_links, indent=2))

    # Fetch the statutory disclosure list JSON
    print('\n=== Fetching statutoryDisclosureList.json ===')
    try:
        page2 = browser.new_page()
        resp = page2.goto('https://transact.axismf.com/assets/shared/statutory-disclosure/statutoryDisclosureList.json', timeout=15000)
        if resp and resp.ok:
            data = resp.json()
            # Find section 8 about Monthly Scheme Portfolios
            for item in data if isinstance(data, list) else [data]:
                title = str(item.get('title', '') or item.get('name', '') or '')
                if 'monthly' in title.lower() or 'portfolio' in title.lower():
                    print(f'=== Monthly portfolio config: {json.dumps(item, indent=2)[:2000]}')
            # Print all section titles
            if isinstance(data, list):
                for i, item in enumerate(data):
                    print(f'  Section {i}: {item.get("title", item.get("name", "?"))}')
        page2.close()
    except Exception as e:
        print(f'  Failed: {e}')

    browser.close()
