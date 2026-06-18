"""Axis - find section IDs, click correct one, capture API calls."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    all_responses = []
    def capture(r):
        url = r.url
        ct = r.headers.get('content-type', '')
        if ('json' in ct or 'cms' in url or 'api' in url) and 'google' not in url and 'facebook' not in url and 'linkedin' not in url and 'bing' not in url and 'doubleclick' not in url and 'spotify' not in url and 'notifyvisitors' not in url:
            body = ''
            try:
                body = r.text()[:3000]
            except:
                pass
            all_responses.append({'url': url[:300], 'status': r.status, 'ct': ct, 'body': body[:1000]})
    page.on('response', capture)

    page.goto('https://transact.axismf.com/statutory-disclosures', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    try:
        page.wait_for_selector('div#spinner', state='hidden', timeout=15000)
    except:
        pass
    page.wait_for_timeout(3000)

    # Find section IDs
    section_ids = page.evaluate("""() => {
        const sections = [...document.querySelectorAll('.indv-section')];
        return sections.map((s, i) => ({
            index: i,
            id: s.id,
            text: (s.querySelector('.indv-first-column')?.innerText || '').trim().substring(0, 80),
            hasContent: s.querySelectorAll('.indv-header').length > 0
        }));
    }""")
    print('=== Section IDs:')
    for s in section_ids:
        print(f'  [{s["index"]}] id="{s["id"]}" text="{s["text"]}"')

    # Find Monthly Scheme Portfolios section
    monthly_idx = None
    for s in section_ids:
        if 'Monthly Scheme Portfolios' in s['text']:
            monthly_idx = s['index']
            break

    if monthly_idx is None:
        print('=== Monthly Scheme Portfolios section not found!')
        browser.close()
        exit(1)

    load_count = len(all_responses)

    # Click via index
    print(f'\n=== Clicking section index {monthly_idx} ===')
    page.evaluate(f"""() => {{
        const sections = [...document.querySelectorAll('.indv-section')];
        const header = sections[{monthly_idx}].querySelector('.indv-header');
        if (header) header.click();
    }}""")
    page.wait_for_timeout(5000)

    # Check API responses
    print(f'=== New API responses:')
    for r in all_responses[load_count:]:
        print(f'  {r["status"]} {r["url"][:200]}')
        if r['body']:
            print(f'    Body: {r["body"][:500]}')

    # Check section content after click
    section_html = page.evaluate(f"""() => {{
        const sections = [...document.querySelectorAll('.indv-section')];
        const sec = sections[{monthly_idx}];
        return sec ? sec.innerHTML.substring(0, 5000) : 'section not found';
    }}""")
    print(f'\n=== Section innerHTML (first 5000):')
    print(section_html[:5000])

    # Check if year/month buttons appeared
    buttons_in_section = page.evaluate(f"""() => {{
        const sections = [...document.querySelectorAll('.indv-section')];
        const sec = sections[{monthly_idx}];
        if (!sec) return [];
        const allEls = [...sec.querySelectorAll('*')];
        return allEls.filter(e => e.children.length === 0 && (e.innerText||'').trim().length > 0 && (e.innerText||'').trim().length < 30)
            .map(e => ({{tag: e.tagName, text: (e.innerText||'').trim(), cls: (e.className||'').substring(0, 80)}}))
            .slice(0, 40);
    }}""")
    print(f'\n=== Elements in section:')
    for b in buttons_in_section:
        print(f'  {b["tag"]} cls="{b["cls"]}" text="{b["text"]}"')

    browser.close()
