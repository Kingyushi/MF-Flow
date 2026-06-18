"""Axis - try different API endpoints with year/month params, also try
fetching the SPA's internal API by capturing network after complete interaction."""
import json, re
from playwright.sync_api import sync_playwright

# First try the CMS API with various parameter combos
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    print('=== Probing CMS API endpoints ===')
    page = browser.new_page()
    api_urls = [
        'https://transact.axismf.com/cms/api/statutory-disclosure?category=Monthly Scheme Portfolios&year=2026',
        'https://transact.axismf.com/cms/api/statutory-disclosure?category=Monthly Scheme Portfolios&year=2026&month=May',
        'https://transact.axismf.com/cms/api/statutory-disclosure?category=Monthly Scheme Portfolios&year=2026&month=5',
        'https://transact.axismf.com/cms/api/statutory-disclosure?category=Monthly+Scheme+Portfolios&year=2026&month=5',
        'https://transact.axismf.com/cms/api/statutory-disclosure?category=Monthly+Scheme+Portfolios&year=2026&month=April',
        'https://transact.axismf.com/cms/api/statutory-disclosure?category=Monthly+Scheme+Portfolios&year=2025&month=December',
        'https://transact.axismf.com/cms/api/statutory-disclosure?category=Monthly+Scheme+Portfolios&year=2025&month=December&type=Consolidated',
    ]
    for url in api_urls:
        try:
            resp = page.goto(url, timeout=10000)
            body = page.evaluate('() => document.body?.innerText || ""')
            if body.strip() != '[]' and body.strip():
                print(f'  HIT: {url}')
                print(f'    Body: {body[:500]}')
            else:
                print(f'  EMPTY: {url}')
        except Exception as e:
            print(f'  FAIL: {url}: {e}')
    page.close()

    # Now try the full SPA interaction with all network capture
    print('\n=== Full SPA interaction ===')
    page = browser.new_page()

    all_responses = []
    def capture_all(r):
        url = r.url
        ct = r.headers.get('content-type', '')
        if ('json' in ct or 'cms' in url or 'api' in url) and 'google' not in url and 'facebook' not in url and 'linkedin' not in url and 'bing' not in url:
            body = ''
            try:
                body = r.text()[:2000]
            except:
                pass
            all_responses.append({'url': url[:300], 'status': r.status, 'ct': ct, 'body': body[:500], 'phase': 'load'})
    page.on('response', capture_all)

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

    # Mark phase
    for r in all_responses:
        r['phase'] = 'load'
    load_count = len(all_responses)

    # Click section 8 via JS
    page.evaluate("""() => {
        const el = document.querySelector('#8, [id="8"]');
        if (el) { el.click(); return; }
        // Fallback: click the header div inside section 8
        const all = [...document.querySelectorAll('.indv-section')];
        const sec = all.find(e => e.id === '8' || (e.innerText||'').includes('Monthly Scheme Portfolios'));
        if (sec) {
            const header = sec.querySelector('.indv-header');
            if (header) header.click();
            else sec.click();
        }
    }""")
    page.wait_for_timeout(5000)

    for r in all_responses[load_count:]:
        r['phase'] = 'click_section'
    click_count = len(all_responses)

    print(f'=== CMS/API responses after section click:')
    for r in all_responses[load_count:]:
        if 'cms' in r['url'] or 'api' in r['url']:
            print(f'  {r["status"]} {r["url"][:200]}')
            if r['body']:
                print(f'    Body: {r["body"][:400]}')

    # Look at the DOM now - the section should have expanded to show the form
    section_content = page.evaluate("""() => {
        // Find section with id="8" or containing "Monthly Scheme Portfolios"
        const sec = document.querySelector('.indv-section#8, [id="8"]') ||
                    [...document.querySelectorAll('.indv-section')].find(e => (e.innerText||'').includes('Monthly Scheme Portfolios'));
        if (!sec) return 'section not found';
        return sec.innerHTML.substring(0, 5000);
    }""")
    print(f'\n=== Section 8 innerHTML:')
    print(section_content[:5000] if isinstance(section_content, str) else json.dumps(section_content)[:5000])

    # Check the section numbering - we know "8 . Monthly Scheme Portfolios" but the id might not be "8"
    section_ids = page.evaluate("""() => {
        const sections = [...document.querySelectorAll('.indv-section')];
        return sections.map((s, i) => ({
            index: i,
            id: s.id,
            text: (s.querySelector('.indv-first-column')?.innerText || s.innerText || '').trim().substring(0, 80)
        })).slice(0, 15);
    }""")
    print(f'\n=== Section IDs:')
    print(json.dumps(section_ids, indent=2))

    browser.close()
