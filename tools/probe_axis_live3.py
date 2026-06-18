"""Axis MF - wait for spinner, then click section, explore form."""
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

    # Wait for spinner to disappear
    print('=== Waiting for spinner to disappear ===')
    try:
        page.wait_for_selector('#spinner', state='hidden', timeout=15000)
        print('  Spinner hidden')
    except:
        print('  Spinner wait timed out, trying force approach')
        # Force hide the spinner
        page.evaluate('() => { const s = document.getElementById("spinner"); if(s) s.style.display = "none"; }')

    page.wait_for_timeout(2000)

    # Use JS click to bypass overlay
    print('=== Clicking Monthly Scheme Portfolios via JS ===')
    clicked = page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => (e.innerText||'').trim() === '8 . Monthly Scheme Portfolios' || (e.innerText||'').trim() === 'Monthly Scheme Portfolios');
        if (el) { el.click(); return el.tagName + ': ' + el.innerText.trim().substring(0, 100); }
        // Try broader
        const el2 = all.find(e => (e.innerText||'').includes('Monthly Scheme Portfolios') && e.children.length < 3);
        if (el2) { el2.click(); return 'broad: ' + el2.tagName + ': ' + el2.innerText.trim().substring(0, 100); }
        return 'NOT FOUND';
    }""")
    print(f'  Clicked: {clicked}')
    page.wait_for_timeout(5000)

    # Check for new JSON XHRs
    json_after = [r for r in responses if 'json' in r['ct'].lower() and 'statutory' in r['url'].lower()]
    print('=== Statutory JSON XHRs:', json.dumps(json_after[-5:], indent=2))

    # Fetch the statutory disclosure JSON manifest directly
    print('\n=== Fetching statutoryDisclosureList.json ===')
    page2 = browser.new_page()
    try:
        resp = page2.goto('https://transact.axismf.com/assets/shared/statutory-disclosure/statutoryDisclosureList.json', timeout=15000)
        if resp and resp.ok:
            data = resp.json()
            if isinstance(data, list):
                for i, item in enumerate(data):
                    title = item.get('title', item.get('name', '?'))
                    print(f'  [{i}] {title}')
                    if 'monthly' in str(title).lower() and 'portfolio' in str(title).lower():
                        print(f'  >>> MATCH: {json.dumps(item, indent=2)[:3000]}')
            elif isinstance(data, dict):
                print(f'  Dict keys: {list(data.keys())}')
                print(f'  Snippet: {json.dumps(data, indent=2)[:3000]}')
    except Exception as e:
        print(f'  Failed: {e}')
    page2.close()

    # Check body text after click
    body = page.evaluate('() => document.body?.innerText?.substring(0, 8000) || ""')
    # Find section around "Monthly Scheme Portfolios"
    idx = body.find('Monthly Scheme Portfolios')
    if idx >= 0:
        print(f'\n=== Text around Monthly Scheme Portfolios (pos {idx}):')
        print(body[max(0,idx-200):idx+2000])

    # Look for Angular components that appeared
    new_components = page.evaluate("""() => {
        const section = document.querySelector('.statutory-section-active, .selected-section, .content-area, .disclosure-content');
        if (section) return {found: true, html: section.innerHTML.substring(0, 2000)};
        // Try finding the active/expanded section
        const panels = document.querySelectorAll('.panel, .accordion-item, ion-item, .section-content');
        const results = [];
        for (const p of panels) {
            const text = (p.innerText||'').trim();
            if (text.includes('Monthly') && text.includes('Portfolio')) {
                results.push({html: p.innerHTML.substring(0, 2000), text: text.substring(0, 500)});
            }
        }
        return {found: false, panels: results};
    }""")
    print('\n=== Section components:', json.dumps(new_components, indent=2)[:3000])

    browser.close()
