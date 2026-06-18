"""Live probe for mf42 Trust MF."""
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
    out['title'] = page.title()
    out['url'] = page.url

    JS_ALL_ELEMENTS = """() => {
        return [...document.querySelectorAll('button, [role="tab"], a, div[role="tab"], span, li')]
            .map(b => ({tag: b.tagName, text: (b.innerText||'').trim().substring(0,100), cls: (b.className||'').toString().substring(0,100), id: b.id}))
            .filter(b => b.text.length > 0 && b.text.length < 80)
            .slice(0, 80)
    }"""
    out['buttons'] = page.evaluate(JS_ALL_ELEMENTS)

    JS_LINKS = """() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .filter(([t,h]) => t.length > 0 || h.includes('.xls')).slice(0, 100)
    }"""
    out['links_before'] = page.evaluate(JS_LINKS)

    JS_VIS = r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /monthly|portfolio|disclosure|fortnightly|download/i.test(l)).slice(0, 50);
    }"""
    out['visible_text'] = page.evaluate(JS_VIS)

    # Find all elements with 'monthly' in text
    JS_MONTHLY = """() => {
        const all = [...document.querySelectorAll('button, a, div, span, li, p')];
        const monthly = all.filter(b => /monthly/i.test((b.innerText || '').trim()));
        return monthly.map(m => ({tag: m.tagName, text: (m.innerText||'').trim().substring(0,100), cls: (m.className||'').toString().substring(0,100)})).slice(0, 20);
    }"""
    out['monthly_elements'] = page.evaluate(JS_MONTHLY)

    # Try clicking Monthly Disclosure
    clicked = page.evaluate("""() => {
        const all = [...document.querySelectorAll('button, a, div, span, li')];
        const monthly = all.find(b => {
            const t = (b.innerText || '').trim();
            return /monthly\\s*(disclosure|portfolio)/i.test(t) && t.length < 50;
        });
        if (monthly) { monthly.click(); return monthly.innerText.trim(); }
        return null;
    }""")
    out['monthly_clicked_text'] = clicked
    page.wait_for_timeout(5000)

    out['links_after'] = page.evaluate(JS_LINKS)

    JS_VIS2 = r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /monthly|portfolio|disclosure|fortnightly|download|20[2-3][0-9]/i.test(l)).slice(0, 50);
    }"""
    out['visible_text_after'] = page.evaluate(JS_VIS2)

    # Get full HTML of the disclosure section for deeper inspection
    out['disclosure_section_html'] = page.evaluate("""() => {
        const container = document.querySelector('[class*="disclosure"], [class*="portfolio"], [id*="disclosure"]');
        if (container) return container.outerHTML.substring(0, 5000);
        return null;
    }""")

    out['xhrs'] = [r for r in responses if 'json' in r.get('ct', '') or 'api' in r['url'].lower() or 'xlsx' in r['url'].lower()][:20]

    b.close()

with open('tools/probe_out/mf42_postclick.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)
print('DONE mf42')
print('Title:', out['title'])
print('Monthly clicked:', out.get('monthly_clicked_text'))
xlsx = [l for l in out.get('links_after', []) if '.xls' in (l[1] if len(l) > 1 else '').lower()]
print('XLSX links after click:', len(xlsx))
for l in xlsx[:10]:
    print('  ', l[0][:80], '|', l[1][:120])
print('All links after:', len(out.get('links_after', [])))
for l in out.get('links_after', [])[:20]:
    print('  ', l[0][:60], '|', l[1][:100])
print()
print('Monthly elements:', json.dumps(out.get('monthly_elements', []), indent=2)[:600])
print()
print('Visible text:', json.dumps(out.get('visible_text', []), indent=2)[:600])
