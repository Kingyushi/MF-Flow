"""Live probe for Kotak MF forms-and-downloads page."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    responses = []
    page.on('response', lambda r: responses.append({
        'url': r.url[:200], 'status': r.status, 'ct': r.headers.get('content-type','')
    }))

    print('=== Loading Kotak forms-and-downloads ===')
    page.goto('https://www.kotakmf.com/Information/forms-and-downloads', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    print('=== Page title:', page.title())

    json_xhrs = [r for r in responses if 'json' in r['ct'].lower()]
    print('=== JSON responses:', json.dumps(json_xhrs[:15], indent=2))

    body_text = page.evaluate('() => document.body?.innerText?.substring(0, 5000) || ""')
    print('=== Body text (first 5000):', body_text[:5000])

    links = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.innerText||'').trim().substring(0, 100),
            href: a.href?.substring(0, 200)
        })).filter(e => e.text.length > 0).slice(0, 50);
    }""")
    print('=== Links:', json.dumps(links[:30], indent=2))

    tabs = page.evaluate("""() => {
        const els = document.querySelectorAll('.tab, [role="tab"], .nav-link, .accordion-button, .panel-heading, .card-header, h3, h4, .nav-item, li a');
        return [...els].map(e => ({
            text: (e.innerText||'').trim().substring(0, 100),
            tag: e.tagName,
            cls: (e.className||'').substring(0, 80)
        })).filter(e => e.text.length > 0).slice(0, 40);
    }""")
    print('=== Tabs/headers:', json.dumps(tabs, indent=2))

    # Try clicking Portfolios
    portfolio_btns = page.locator('text=Portfolios').all()
    print('=== "Portfolios" elements:', len(portfolio_btns))

    if portfolio_btns:
        for i, btn in enumerate(portfolio_btns[:3]):
            txt = btn.inner_text()
            print(f'  Portfolios btn #{i}: text={txt!r}')

        # Click the first "Portfolios" match
        portfolio_btns[0].click(timeout=5000)
        page.wait_for_timeout(3000)

        # Check new JSON XHRs
        new_json_xhrs = [r for r in responses if 'json' in r['ct'].lower()]
        new_only = new_json_xhrs[len(json_xhrs):]
        print('=== New JSON XHRs after Portfolios click:', json.dumps(new_only[:10], indent=2))

        body_after = page.evaluate('() => document.body?.innerText?.substring(0, 6000) || ""')
        print('=== Body after Portfolios click (first 6000):', body_after[:6000])

        # Look for consolidated option
        consolidated = page.locator('text=Consolidated').all()
        print('=== "Consolidated" elements:', len(consolidated))

        links_after = page.evaluate("""() => {
            return [...document.querySelectorAll('a[href]')].map(a => ({
                text: (a.innerText||'').trim().substring(0, 100),
                href: a.href?.substring(0, 200)
            })).filter(e => e.href.includes('.xlsx') || e.href.includes('.xls')).slice(0, 30);
        }""")
        print('=== xlsx links after Portfolios click:', json.dumps(links_after, indent=2))

    browser.close()
