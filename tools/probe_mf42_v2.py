"""Deeper probe for mf42 Trust MF - find the actual download mechanism."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    responses = []
    page.on('response', lambda r: responses.append({'url': r.url, 'status': r.status, 'ct': r.headers.get('content-type', '')}))
    page.goto('https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    # Get the full HTML around disclosure section
    out['disclosure_html'] = page.evaluate("""() => {
        const body = document.body.innerHTML;
        // Find the area around "Monthly" text
        const idx = body.indexOf('Monthly');
        if (idx > -1) return body.substring(Math.max(0, idx - 500), idx + 3000);
        return body.substring(0, 5000);
    }""")

    # Find ALL elements with download-like attributes
    out['download_elements'] = page.evaluate("""() => {
        const els = [...document.querySelectorAll('a[href*="download"], a[href*=".pdf"], a[href*=".xls"], button[class*="download"], [download], a[href*="amazonaws"], a[href*="blob"], a[href*="cdn"]')];
        return els.map(e => ({
            tag: e.tagName,
            text: (e.innerText||'').trim().substring(0,100),
            href: (e.href||'').substring(0,300),
            download: e.getAttribute('download'),
            cls: (e.className||'').toString().substring(0,100)
        })).slice(0, 30);
    }""")

    # Check visible text specifically in the portfolio section
    out['portfolio_section_text'] = page.evaluate(r"""() => {
        const sections = document.querySelectorAll('div, section');
        for (const s of sections) {
            const t = (s.innerText || '').trim();
            if (t.includes('Portfolio Disclosures') && t.length < 5000) {
                return t.substring(0, 3000);
            }
        }
        return null;
    }""")

    # Click "Monthly" text to reveal the section
    page.evaluate("""() => {
        const all = [...document.querySelectorAll('button, a, div, span, li, h3, h4, p')];
        const monthly = all.find(b => {
            const t = (b.innerText || '').trim();
            return /^monthly\\s*(disclosure|portfolio)/i.test(t);
        });
        if (monthly) monthly.click();
    }""")
    page.wait_for_timeout(5000)

    # After clicking, check for new elements
    out['download_elements_after'] = page.evaluate("""() => {
        const els = [...document.querySelectorAll('a[href*="download"], a[href*=".pdf"], a[href*=".xls"], a[href*=".xlsx"], button[class*="download"], [download], a[href*="amazonaws"], a[href*="blob"], a[href*="cdn"], a[href*="trustmf"]')];
        return els.map(e => ({
            tag: e.tagName,
            text: (e.innerText||'').trim().substring(0,100),
            href: (e.href||'').substring(0,300),
            cls: (e.className||'').toString().substring(0,100),
            visible: e.offsetParent !== null
        })).slice(0, 50);
    }""")

    # Check for XHR/fetch responses
    out['all_responses'] = [{'url': r['url'][:200], 'status': r['status'], 'ct': r['ct']}
                            for r in responses if r['status'] == 200]

    # Also check the DOM for hidden xlsx URLs in data attributes
    out['data_attrs'] = page.evaluate("""() => {
        const els = [...document.querySelectorAll('[data-url], [data-href], [data-file], [data-download], [data-src]')];
        return els.map(e => ({
            tag: e.tagName,
            text: (e.innerText||'').trim().substring(0,100),
            dataUrl: e.getAttribute('data-url'),
            dataHref: e.getAttribute('data-href'),
            dataFile: e.getAttribute('data-file'),
            dataDownload: e.getAttribute('data-download'),
            dataSrc: e.getAttribute('data-src')
        })).slice(0, 20);
    }""")

    # Check XHR responses for any JSON/API calls
    out['api_responses'] = [{'url': r['url'][:200], 'status': r['status'], 'ct': r['ct']}
                            for r in responses if 'json' in r.get('ct', '') or 'api' in r['url'].lower()]

    b.close()

with open('tools/probe_out/mf42_v2.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf42 v2')
print()
print('Download elements after click:', len(out.get('download_elements_after', [])))
for e in out.get('download_elements_after', [])[:20]:
    print(f"  {e['tag']} text={e['text'][:60]} href={e['href'][:100]} visible={e.get('visible')}")
print()
print('Data attrs:', json.dumps(out.get('data_attrs', []), indent=2)[:500])
print()
print('API responses:', len(out.get('api_responses', [])))
for r in out.get('api_responses', [])[:10]:
    print(f"  {r['url'][:120]}")
print()
print('Portfolio section text (first 1000):')
print((out.get('portfolio_section_text') or 'None')[:1000])
