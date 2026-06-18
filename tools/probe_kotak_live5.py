"""Kotak MF - use Playwright with stealth to interact with the SPA,
select Portfolios > Consolidated, and capture the API call."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled']
    )
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        locale='en-IN',
        viewport={'width': 1366, 'height': 768},
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en-US', 'en']});
        window.chrome = { runtime: {} };
    """)

    page = ctx.new_page()

    # Since the page loaded OK with stealth earlier, let's interact with the SPA.
    # The page uses Angular and has sections: Forms, Factsheet, Portfolios, Addendums, etc.
    # We need to:
    # 1. Click "Portfolios" section
    # 2. Select "Consolidated & Fortnightly Portfolio" from the dropdown
    # 3. Capture the XHR that fetches the file list

    responses = []
    def capture(r):
        url = r.url
        ct = r.headers.get('content-type', '')
        if 'json' in ct or 'download' in url.lower() or 'portfolio' in url.lower() or '.xlsx' in url.lower():
            body = ''
            try:
                body = r.text()[:3000]
            except:
                pass
            responses.append({'url': url[:300], 'status': r.status, 'ct': ct, 'body': body})
    page.on('response', capture)

    print('=== Loading Kotak ===')
    page.goto('https://www.kotakmf.com/Information/forms-and-downloads', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    title = page.title()
    print(f'=== Title: {title}')

    if 'captcha' in title.lower() or 'Radware' in title:
        print('=== CAPTCHA detected, aborting ===')
        browser.close()
        exit(1)

    # Find the "Portfolios" clickable heading
    portfolios_items = page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        return all.filter(e =>
            e.children.length < 3 &&
            (e.innerText||'').trim() === 'Portfolios'
        ).map(e => ({
            tag: e.tagName,
            cls: (e.className||'').substring(0, 100),
            id: e.id,
            parentTag: e.parentElement?.tagName,
            parentCls: (e.parentElement?.className||'').substring(0, 100),
        })).slice(0, 10);
    }""")
    print(f'\n=== "Portfolios" elements: {json.dumps(portfolios_items, indent=2)}')

    # Click on the Portfolios section
    page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => e.children.length < 3 && (e.innerText||'').trim() === 'Portfolios');
        if (el) el.click();
    }""")
    page.wait_for_timeout(3000)

    # Check what appeared
    body_after = page.evaluate('() => document.body?.innerText?.substring(0, 6000) || ""')
    # Find Portfolios section
    idx = body_after.find('Portfolios')
    if idx >= 0:
        print(f'\n=== Text around "Portfolios" (pos {idx}):')
        print(body_after[idx:idx+2000])

    # Look for select/dropdown with Consolidated option
    selects = page.evaluate("""() => {
        return [...document.querySelectorAll('select')].map(sel => ({
            name: sel.name, id: sel.id, cls: sel.className,
            options: [...sel.options].map(o => ({text: o.text.trim(), value: o.value})).slice(0, 20)
        }));
    }""")
    print(f'\n=== Selects: {json.dumps(selects, indent=2)}')

    # Look for dropdown trigger elements (Angular custom dropdowns)
    dropdowns = page.evaluate("""() => {
        const els = document.querySelectorAll('.dropdown, .ng-select, [role="listbox"], [role="combobox"], .custom-select, .form-select, .mat-select, ngb-dropdown, [ngbDropdown]');
        return [...els].map(e => ({
            tag: e.tagName,
            text: (e.innerText||'').trim().substring(0, 200),
            cls: (e.className||'').substring(0, 100),
        })).slice(0, 10);
    }""")
    print(f'\n=== Dropdown elements: {json.dumps(dropdowns, indent=2)}')

    # Check captured responses
    print(f'\n=== Captured responses after Portfolios click:')
    for r in responses:
        print(f'  {r["status"]} {r["url"][:200]}')
        if r['body']:
            print(f'    Body: {r["body"][:500]}')

    # Try to click "Consolidated & Fortnightly Portfolio" or "Please Select"
    please_select = page.locator('text=Please Select').all()
    print(f'\n=== "Please Select" elements: {len(please_select)}')
    if please_select:
        for i, ps in enumerate(please_select[:3]):
            try:
                t = ps.inner_text()
                print(f'  #{i}: {t[:80]}')
            except:
                pass

    browser.close()
