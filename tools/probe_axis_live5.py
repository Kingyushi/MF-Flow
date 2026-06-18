"""Axis MF - find the API endpoint for statutory disclosure documents."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    responses = []
    def capture(r):
        url = r.url
        ct = r.headers.get('content-type', '')
        if 'json' in ct or 'statutory' in url.lower() or 'cms' in url.lower():
            body = ''
            try:
                body = r.text()[:2000]
            except:
                pass
            responses.append({'url': url[:300], 'status': r.status, 'ct': ct, 'body': body})
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
        pass
    page.wait_for_timeout(3000)

    print('=== Initial responses:')
    for r in responses:
        print(f'  {r["status"]} {r["url"][:150]}')
        if r['body'] and len(r['body']) < 500:
            print(f'    Body: {r["body"][:300]}')

    # Clear responses for next phase
    initial_count = len(responses)

    # JS-click the Monthly Scheme Portfolios section
    page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => (e.innerText||'').trim() === '8 . Monthly Scheme Portfolios' && e.children.length < 3);
        if (el) el.click();
    }""")
    page.wait_for_timeout(5000)

    print(f'\n=== Responses after clicking Monthly Scheme Portfolios:')
    for r in responses[initial_count:]:
        print(f'  {r["status"]} {r["url"][:200]}')
        if r['body']:
            print(f'    Body ({len(r["body"])} chars): {r["body"][:500]}')

    # Check what appeared in the DOM now
    # The section type is "yearMonthFilters" with showSchemeList=true
    # So after clicking, we should see year pills/tabs
    year_content = page.evaluate("""() => {
        // Find all visible year-like numbers in the content area
        const allEls = [...document.querySelectorAll('*')];
        const yearEls = allEls.filter(e =>
            e.children.length === 0 &&
            /^20\\d{2}$/.test((e.innerText||'').trim())
        );
        return yearEls.map(e => ({
            tag: e.tagName,
            text: e.innerText.trim(),
            cls: (e.className||'').substring(0, 100),
            id: e.id,
            parentTag: e.parentElement?.tagName,
            parentCls: (e.parentElement?.className||'').substring(0, 100),
        })).slice(0, 20);
    }""")
    print(f'\n=== Year elements visible: {json.dumps(year_content, indent=2)}')

    # Check the expanded section HTML
    section_html = page.evaluate("""() => {
        // Look for newly appeared content after the section 8 heading
        const all = [...document.querySelectorAll('ion-col, ion-row')];
        const heading = all.find(e => (e.innerText||'').includes('Monthly Scheme Portfolios'));
        if (!heading) return 'heading not found';

        // Walk the DOM to find the sibling content section
        let parent = heading.parentElement;
        let sibling = parent?.nextElementSibling;
        if (sibling) return sibling.outerHTML.substring(0, 3000);

        // Try going further up
        parent = parent?.parentElement;
        sibling = parent?.nextElementSibling;
        if (sibling) return sibling.outerHTML.substring(0, 3000);

        // Return the parent's full content
        return parent?.outerHTML?.substring(0, 5000) || 'no parent';
    }""")
    print(f'\n=== Section HTML after click:')
    print(section_html[:3000] if isinstance(section_html, str) else json.dumps(section_html)[:3000])

    # Try to find API endpoints by looking at Angular service calls
    # The SPA probably calls something like /cms/api/statutory-disclosure-docs
    print('\n=== Trying direct API calls ===')
    api_candidates = [
        'https://transact.axismf.com/cms/api/statutory-disclosure?category=Monthly%20Scheme%20Portfolios',
        'https://transact.axismf.com/cms/api/statutory-disclosures?category=Monthly%20Scheme%20Portfolios',
        'https://transact.axismf.com/cms/api/documents?category=Monthly%20Scheme%20Portfolios',
        'https://transact.axismf.com/cms/api/document-list?category=Monthly+Scheme+Portfolios',
        'https://transact.axismf.com/cms/api/statutory-disclosure-list',
    ]
    page2 = browser.new_page()
    for url in api_candidates:
        try:
            resp = page2.goto(url, timeout=10000)
            if resp:
                print(f'  {resp.status} {url}')
                if resp.ok:
                    body = page2.evaluate('() => document.body?.innerText || ""')
                    print(f'    Body: {body[:500]}')
        except Exception as e:
            print(f'  FAIL {url}: {e}')
    page2.close()

    browser.close()
