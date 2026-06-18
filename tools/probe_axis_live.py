"""Live probe for Axis MF statutory disclosures page."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    responses = []
    page.on('response', lambda r: responses.append({
        'url': r.url[:200], 'status': r.status, 'ct': r.headers.get('content-type','')
    }))

    print('=== Loading Axis statutory-disclosures ===')
    page.goto('https://transact.axismf.com/statutory-disclosures', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    print('=== Page title:', page.title())

    json_xhrs = [r for r in responses if 'json' in r['ct'].lower() or r['url'].endswith('.json')]
    print('=== JSON responses:', json.dumps(json_xhrs[:10], indent=2))

    body_text = page.evaluate('() => document.body?.innerText?.substring(0, 3000) || ""')
    print('=== Body text (first 3000):', body_text[:3000])

    monthly_el = page.locator('text=Monthly Scheme Portfolios').all()
    print('=== Monthly Scheme Portfolios elements:', len(monthly_el))

    headings = page.evaluate("""() => {
        const els = document.querySelectorAll('h1,h2,h3,h4,h5,h6,.section-heading,.accordion-header,[role="tab"],[role="heading"],.mat-expansion-panel-header');
        return [...els].map(e => e.innerText?.trim()).filter(Boolean).slice(0, 30);
    }""")
    print('=== Headings:', json.dumps(headings, indent=2))

    clickables = page.evaluate("""() => {
        const all = document.querySelectorAll('a, button, [role="button"], [role="tab"], [onclick]');
        return [...all].map(e => ({
            text: (e.innerText||'').trim()[:100],
            tag: e.tagName,
            cls: (e.className if isinstance(e.className, str) else '')[:80]
        })).filter(e => e.text.length > 0).slice(0, 50);
    }""")
    print('=== Clickable elements:', json.dumps(clickables[:30], indent=2))

    # Try clicking "Monthly Scheme Portfolios" if found
    if monthly_el:
        print('=== Clicking Monthly Scheme Portfolios ===')
        monthly_el[0].click(timeout=5000)
        page.wait_for_timeout(3000)

        # Check for year/month selects after click
        selects_after = page.evaluate("""() => {
            return [...document.querySelectorAll('select')].map(sel => ({
                name: sel.name, id: sel.id, cls: sel.className,
                options: [...sel.options].map(o => ({text: o.text.trim(), value: o.value}))
            }));
        }""")
        print('=== Selects after click:', json.dumps(selects_after, indent=2))

        # Check for radio/tab buttons (Consolidated etc)
        radios = page.evaluate("""() => {
            const els = document.querySelectorAll('input[type="radio"], .mat-radio-button, [role="radio"]');
            return [...els].map(e => ({
                text: (e.labels?.[0]?.innerText || e.parentElement?.innerText || '').trim()[:100],
                value: e.value, checked: e.checked, id: e.id
            }));
        }""")
        print('=== Radio buttons:', json.dumps(radios, indent=2))

        body_after = page.evaluate('() => document.body?.innerText?.substring(0, 5000) || ""')
        print('=== Body text after click (first 5000):', body_after[:5000])

    browser.close()
