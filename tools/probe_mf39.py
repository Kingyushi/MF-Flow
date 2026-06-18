"""Live probe for mf39 Sundaram."""
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
    out['title'] = page.title()
    out['url'] = page.url

    JS_SELECTS = """() => {
        return [...document.querySelectorAll('select')].map(s => ({
            id: s.id, name: s.name, cls: s.className.substring(0,100),
            options: [...s.options].map(o => ({value: o.value, text: o.text.trim()})).slice(0, 30)
        }))
    }"""
    out['selects'] = page.evaluate(JS_SELECTS)

    JS_BUTTONS = """() => {
        return [...document.querySelectorAll('button, input[type="submit"], input[type="button"]')]
            .map(b => ({tag: b.tagName, text: (b.innerText||b.value||'').trim().substring(0,100), id: b.id, cls: b.className.substring(0,100)}))
            .filter(b => b.text.length > 0).slice(0, 30)
    }"""
    out['buttons'] = page.evaluate(JS_BUTTONS)

    # Try to select Monthly Portfolio and click View
    has_cbx = page.evaluate("() => !!document.querySelector('#Cbx_Category')")
    out['has_Cbx_Category'] = has_cbx
    if has_cbx:
        page.select_option('#Cbx_Category', 'Monthly')
        page.wait_for_timeout(1000)
        page.click('text=View')
        page.wait_for_timeout(5000)
        out['view_clicked'] = True
    else:
        out['all_select_ids'] = page.evaluate("() => [...document.querySelectorAll('select')].map(s => s.id)")
        # Try to find category dropdown by any means
        found = page.evaluate("""() => {
            const sel = document.querySelectorAll('select');
            for (const s of sel) {
                for (const o of s.options) {
                    if (o.text.toLowerCase().includes('monthly')) {
                        s.value = o.value;
                        s.dispatchEvent(new Event('change', {bubbles:true}));
                        return {id: s.id, val: o.value, text: o.text};
                    }
                }
            }
            return null;
        }""")
        out['monthly_option_found'] = found
        if found:
            page.wait_for_timeout(1000)
            try:
                page.click('text=View', timeout=5000)
                page.wait_for_timeout(5000)
                out['view_clicked'] = True
            except:
                out['view_clicked'] = False
        else:
            out['view_clicked'] = False

    JS_LINKS = """() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .filter(([t,h]) => t.length > 0).slice(0, 200)
    }"""
    out['links_after_view'] = page.evaluate(JS_LINKS)

    JS_VIS = r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /20[2-3][0-9]|monthly|portfolio|equity|fund.*fund|disclosure/i.test(l)).slice(0, 80);
    }"""
    out['visible_text'] = page.evaluate(JS_VIS)

    b.close()

with open('tools/probe_out/mf39_postclick.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)
print('DONE mf39')
print('Title:', out['title'])
print('View clicked:', out.get('view_clicked'))
print('Selects:', json.dumps(out['selects'], indent=2)[:500])
xlsx = [l for l in out.get('links_after_view', []) if '.xls' in (l[1] if len(l) > 1 else '').lower()]
print('XLSX links after view:', len(xlsx))
for l in xlsx[:15]:
    print('  ', l[0][:80], '|', l[1][:120])
