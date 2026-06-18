"""Axis MF - fetch and parse the statutory disclosure JSON manifest properly."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Fetch the manifest directly
    resp = page.goto('https://transact.axismf.com/assets/shared/statutory-disclosure/statutoryDisclosureList.json', timeout=15000)
    data = resp.json()

    # Print structure
    if isinstance(data, list):
        print(f'=== Array of {len(data)} items ===')
        for i, item in enumerate(data):
            print(f'\n--- Item {i} ---')
            print(json.dumps(item, indent=2, ensure_ascii=False)[:500])
    elif isinstance(data, dict):
        print(f'=== Dict with keys: {list(data.keys())} ===')
        for key in data:
            val = data[key]
            if isinstance(val, list) and val:
                print(f'\n--- {key}: list of {len(val)} items ---')
                for i, item in enumerate(val[:3]):
                    print(json.dumps(item, indent=2, ensure_ascii=False)[:500])
            elif isinstance(val, dict):
                print(f'\n--- {key}: dict ---')
                print(json.dumps(val, indent=2, ensure_ascii=False)[:500])
            else:
                print(f'\n--- {key}: {str(val)[:200]} ---')

    page.close()

    # Now go to the actual page and explore the SPA behavior in depth
    page = browser.new_page()

    responses = []
    def capture(r):
        ct = r.headers.get('content-type', '')
        url = r.url
        if 'json' in ct or 'xlsx' in url or 'download' in url or 'statutory' in url.lower() or 'portfolio' in url.lower():
            body = ''
            try:
                body = r.text()[:500]
            except:
                pass
            responses.append({
                'url': url[:300], 'status': r.status, 'ct': ct, 'body_preview': body[:300]
            })
    page.on('response', capture)

    page.goto('https://transact.axismf.com/statutory-disclosures', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass

    # Wait for spinner
    try:
        page.wait_for_selector('#spinner', state='hidden', timeout=15000)
    except:
        page.evaluate('() => { const s = document.getElementById("spinner"); if(s) s.style.display = "none"; }')

    page.wait_for_timeout(2000)

    # Find the ion-col element for "Monthly Scheme Portfolios" and get its structure
    monthly_html = page.evaluate("""() => {
        const all = [...document.querySelectorAll('ion-col, ion-row, div')];
        for (const el of all) {
            const text = (el.innerText||'').trim();
            if (text === '8 . Monthly Scheme Portfolios' || text === 'Monthly Scheme Portfolios') {
                // Navigate up to find the parent section
                let parent = el;
                for (let i = 0; i < 5; i++) {
                    parent = parent.parentElement;
                    if (!parent) break;
                }
                return {
                    element: {tag: el.tagName, cls: el.className, text: text},
                    parentTag: parent?.tagName,
                    parentCls: parent?.className?.substring(0, 200),
                    parentHTML: parent?.outerHTML?.substring(0, 3000),
                    nearbyClicks: [...(parent?.querySelectorAll('[click], [ng-click], (click)') || [])].map(e => ({tag: e.tagName, text: (e.innerText||'').trim().substring(0, 80)})).slice(0, 10),
                };
            }
        }
        return null;
    }""")
    print('\n=== Monthly Scheme Portfolios element structure:')
    print(json.dumps(monthly_html, indent=2, ensure_ascii=False)[:3000])

    # Click the section using JS
    page.evaluate("""() => {
        const all = [...document.querySelectorAll('ion-col, ion-row, div')];
        const el = all.find(e => (e.innerText||'').trim().includes('Monthly Scheme Portfolios'));
        if (el) el.click();
    }""")
    page.wait_for_timeout(5000)

    # Check XHR responses after click
    print('\n=== Responses captured:')
    for r in responses[-10:]:
        print(f'  {r["status"]} {r["url"][:200]}')
        if r['body_preview']:
            print(f'    Body: {r["body_preview"][:200]}')

    # Try to find what changed after click - look for expanded content
    expanded = page.evaluate("""() => {
        // Angular might use ng-if or *ngIf to show/hide content
        // Check for any new content that appeared
        const allText = document.body.innerText;
        const idx = allText.indexOf('Monthly Scheme Portfolios');
        if (idx < 0) return 'section not found';
        // Get text after the section heading
        return allText.substring(idx, idx + 3000);
    }""")
    print('\n=== Text after Monthly Scheme Portfolios:', expanded[:3000])

    browser.close()
