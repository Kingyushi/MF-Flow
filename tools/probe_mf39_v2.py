"""Deeper probe for mf39 Sundaram - check what appears after View click."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    responses = []
    page.on('response', lambda r: responses.append({'url': r.url, 'status': r.status, 'ct': r.headers.get('content-type', '')}))
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
    page.click('text=View')
    page.wait_for_timeout(8000)

    # Get ALL links - not just xlsx
    out['all_links'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .slice(0, 300)
    }""")

    # Visible text with monthly/portfolio/equity
    out['vis'] = page.evaluate(r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /20[2-3][0-9]|monthly|portfolio|equity|fund|disclosure|download/i.test(l)).slice(0, 80);
    }""")

    # Check for file download links (pdf, xls, xlsx, zip)
    out['file_links'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .filter(([t,h]) => /\\.(xlsx?|pdf|zip|csv)(\\?|$|#)/i.test(h))
            .slice(0, 100)
    }""")

    # Check for iframes
    out['iframes'] = page.evaluate("""() => {
        return [...document.querySelectorAll('iframe')].map(f => ({src: f.src, id: f.id}))
    }""")

    # XHR responses - check for any content delivery
    out['all_responses'] = [{'url': r['url'], 'status': r['status'], 'ct': r['ct']} for r in responses
                            if r['status'] == 200 and ('xls' in r['url'].lower() or 'pdf' in r['url'].lower() or 'portfolio' in r['url'].lower() or 'monthly' in r['url'].lower())]

    # Check the HTML of the results section
    out['results_html'] = page.evaluate("""() => {
        // Look for the section that appeared after View click
        const sections = [...document.querySelectorAll('.accordion, .panel, .card, .result, [class*="result"], [class*="portfolio"], [class*="download"]')];
        return sections.map(s => ({cls: s.className.substring(0,100), html: s.outerHTML.substring(0,500)})).slice(0, 10);
    }""")

    b.close()

with open('tools/probe_out/mf39_v2.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf39 v2')
print('Total all links:', len(out['all_links']))
print('File links:', len(out['file_links']))
for l in out['file_links'][:20]:
    print('  ', l[0][:80], '|', l[1][:120])
print()
print('Visible text (first 30):')
for v in out['vis'][:30]:
    print(' ', v[:100])
print()
print('Responses with portfolio/monthly:', len(out['all_responses']))
for r in out['all_responses'][:10]:
    print(' ', r['url'][:120])
print()
print('Results HTML sections:', len(out.get('results_html', [])))
for s in out.get('results_html', [])[:5]:
    print(' cls:', s['cls'][:80])
    print(' html:', s['html'][:300])
    print()
