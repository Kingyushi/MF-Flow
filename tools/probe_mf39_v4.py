"""mf39 Sundaram v4 - Expand the accordion and find the portfolio links."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    api_responses = []

    def capture(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        if 'GetCategory' in url or '.xls' in url.lower() or '.pdf' in url.lower():
            try:
                body = response.text()
            except:
                body = '<binary>'
            api_responses.append({'url': url[:300], 'body': body[:5000]})

    page.on('response', capture)
    page.goto('https://www.sundarammutual.com/Monthly-Fortnightly-Adhoc-Portfolios', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    # Select Monthly and click View
    page.select_option('#Cbx_Category', 'Monthly')
    page.wait_for_timeout(1000)
    page.evaluate("""() => {
        const btns = [...document.querySelectorAll('input[type="button"], button, a')];
        const view = btns.find(b => (b.value||b.innerText||'').trim() === 'View');
        if (view) view.click();
    }""")
    page.wait_for_timeout(8000)

    # Check accordion structure
    out['accordion_structure'] = page.evaluate("""() => {
        const acc = document.querySelector('#MonthAdhoc');
        if (!acc) return null;
        const items = [...acc.querySelectorAll('.accordion-item')];
        return items.map(item => {
            const header = item.querySelector('.accordion-button');
            const body = item.querySelector('.accordion-collapse');
            return {
                header: header ? header.innerText.trim() : '',
                bodyId: body ? body.id : '',
                bodyClass: body ? body.className : '',
                bodyHTML: body ? body.innerHTML.substring(0, 2000) : '',
                expanded: body ? body.classList.contains('show') : false
            };
        }).slice(0, 5);
    }""")

    # Try expanding the first (latest) accordion
    page.evaluate("""() => {
        const acc = document.querySelector('#MonthAdhoc');
        if (!acc) return;
        const btn = acc.querySelector('.accordion-button');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(5000)

    # Check accordion body content after expansion
    out['accordion_after_expand'] = page.evaluate("""() => {
        const acc = document.querySelector('#MonthAdhoc');
        if (!acc) return null;
        const items = [...acc.querySelectorAll('.accordion-item')];
        return items.map(item => {
            const header = item.querySelector('.accordion-button');
            const body = item.querySelector('.accordion-collapse');
            return {
                header: header ? header.innerText.trim() : '',
                expanded: body ? body.classList.contains('show') : false,
                bodyText: body ? body.innerText.trim().substring(0, 1000) : '',
                links: body ? [...body.querySelectorAll('a')].map(a => ({text: (a.innerText||'').trim().substring(0,100), href: a.href.substring(0,200)})).slice(0, 20) : []
            };
        }).slice(0, 3);
    }""")

    # Check API calls
    out['api_calls'] = api_responses

    b.close()

with open('tools/probe_out/mf39_v4.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf39 v4')
print()
print('Accordion structure:', json.dumps(out.get('accordion_structure', []), indent=2)[:1500])
print()
print('Accordion after expand:', json.dumps(out.get('accordion_after_expand', []), indent=2)[:2000])
print()
print('API calls:', len(out.get('api_calls', [])))
for r in out.get('api_calls', [])[:5]:
    print(f"  URL: {r['url'][:120]}")
    print(f"  Body: {r['body'][:500]}")
    print()
