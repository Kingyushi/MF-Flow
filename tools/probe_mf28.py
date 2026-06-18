"""Live probe for mf28 Navi."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    responses = []
    page.on('response', lambda r: responses.append({'url': r.url, 'status': r.status, 'ct': r.headers.get('content-type', '')}))
    page.goto('https://navi.com/mutual-fund/downloads/portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}
    out['title'] = page.title()
    out['url'] = page.url

    JS_BUTTONS = """() => {
        return [...document.querySelectorAll('button, [role="tab"], a.tab, .tab-item, .nav-link, .nav-item')]
            .map(b => ({tag: b.tagName, text: (b.innerText||'').trim().substring(0,100), cls: b.className.substring(0,100)}))
            .filter(b => b.text.length > 0).slice(0, 50)
    }"""
    out['buttons'] = page.evaluate(JS_BUTTONS)

    JS_LINKS = """() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .filter(([t,h]) => t.length > 0 || h.toLowerCase().includes('.xls'))
            .slice(0, 200)
    }"""
    out['links'] = page.evaluate(JS_LINKS)

    JS_SELECTS = """() => {
        return [...document.querySelectorAll('select')].map(s => ({
            id: s.id, name: s.name,
            options: [...s.options].map(o => ({value: o.value, text: o.text.trim()})).slice(0, 30)
        }))
    }"""
    out['selects'] = page.evaluate(JS_SELECTS)

    JS_VIS = r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /20[2-3][0-9]|january|february|march|april|may|june|july|august|september|october|november|december|monthly|portfolio|download/i.test(l)).slice(0, 50);
    }"""
    out['visible_text_hits'] = page.evaluate(JS_VIS)

    # Try clicking Monthly tab
    try:
        monthly_btn = page.locator('text=/^Monthly$/i').first
        if monthly_btn.is_visible(timeout=3000):
            monthly_btn.click(timeout=5000)
            page.wait_for_timeout(3000)
            out['after_monthly_click'] = True
        else:
            out['after_monthly_click'] = False
    except Exception as e:
        out['after_monthly_click'] = str(e)

    out['links_after_click'] = page.evaluate(JS_LINKS)
    out['buttons_after_click'] = page.evaluate(JS_BUTTONS)
    out['visible_text_after_click'] = page.evaluate(JS_VIS)
    out['xhrs'] = [r for r in responses if 'json' in r.get('ct', '') or 'api' in r['url'].lower()][:20]

    b.close()

with open('tools/probe_out/mf28_postclick.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)
print('DONE mf28')
print('Title:', out['title'])
print('Buttons:', len(out.get('buttons', [])))
print('Links:', len(out.get('links', [])))
print('Links after click:', len(out.get('links_after_click', [])))
print('Selects:', len(out.get('selects', [])))
xlsx = [l for l in out.get('links_after_click', []) if '.xls' in (l[1] if len(l) > 1 else '').lower()]
print('XLSX links:', len(xlsx))
for l in xlsx[:10]:
    print('  ', l[0][:80], '|', l[1][:120])
