"""mf39 Sundaram v3 - Investigate the AJAX response for portfolio links."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    api_responses = []

    def capture_response(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        if 'Monthly' in url or 'Adhoc' in url or 'Disclosure' in url or 'ajax' in url.lower() or 'ashx' in url.lower():
            try:
                body = response.text()
            except:
                body = '<binary>'
            api_responses.append({
                'url': url, 'status': response.status, 'ct': ct,
                'body_preview': body[:3000] if isinstance(body, str) else str(body[:500])
            })

    page.on('response', capture_response)
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

    # Find and click View button
    page.evaluate("""() => {
        const btns = [...document.querySelectorAll('input[type="button"], button, a')];
        const view = btns.find(b => (b.value||b.innerText||'').trim() === 'View');
        if (view) view.click();
    }""")
    page.wait_for_timeout(8000)

    # Check the accordion HTML
    out['accordion_html'] = page.evaluate("""() => {
        const acc = document.querySelector('#MonthAdhoc');
        if (acc) return acc.outerHTML.substring(0, 5000);
        return null;
    }""")

    # Check if the content loads in a different way
    out['page_html_snippet'] = page.evaluate("""() => {
        const body = document.body.innerHTML;
        // Look for any xlsx references
        const idx = body.toLowerCase().indexOf('.xlsx');
        if (idx > -1) return body.substring(Math.max(0, idx - 500), idx + 500);
        // Look for monthly portfolio references
        const idx2 = body.toLowerCase().indexOf('monthly portfolio disclosure');
        if (idx2 > -1) return body.substring(Math.max(0, idx2 - 200), idx2 + 1000);
        return null;
    }""")

    # Get all visible text after View
    out['vis'] = page.evaluate(r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /monthly|portfolio|equity|fund.*fund|disclosure|download|20[2-3][0-9]/i.test(l)).slice(0, 50);
    }""")

    out['api_responses'] = api_responses

    b.close()

with open('tools/probe_out/mf39_v3.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf39 v3')
print()
print('Accordion HTML (first 500):', (out.get('accordion_html') or 'None')[:500])
print()
print('Page HTML snippet:', (out.get('page_html_snippet') or 'None')[:1000])
print()
print('API responses:', len(out.get('api_responses', [])))
for r in out.get('api_responses', [])[:5]:
    print(f"  URL: {r['url'][:120]}")
    print(f"  Status: {r['status']} CT: {r['ct']}")
    print(f"  Body: {r['body_preview'][:500]}")
    print()
print('Visible text:')
for v in out.get('vis', [])[:20]:
    print(' ', v[:100])
