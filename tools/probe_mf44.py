"""Live probe for mf44 UTI."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    responses = []
    page.on('response', lambda r: responses.append({'url': r.url, 'status': r.status, 'ct': r.headers.get('content-type', '')}))
    page.goto('https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure', wait_until='domcontentloaded', timeout=60000)
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
        return [...document.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn')]
            .map(b => ({tag: b.tagName, text: (b.innerText||b.value||'').trim().substring(0,100), id: b.id, cls: b.className.substring(0,100)}))
            .filter(b => b.text.length > 0).slice(0, 30)
    }"""
    out['buttons'] = page.evaluate(JS_BUTTONS)

    JS_VIS = r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /year|month|portfolio|download|consolidate|select|get/i.test(l)).slice(0, 50);
    }"""
    out['visible_text'] = page.evaluate(JS_VIS)

    JS_CUSTOM = """() => {
        const els = [...document.querySelectorAll('[class*="dropdown"], [class*="select"], [class*="Dropdown"], [class*="Select"], [role="listbox"], [role="combobox"]')];
        return els.map(e => ({
            tag: e.tagName, cls: e.className.substring(0,150), id: e.id,
            text: (e.innerText||'').trim().substring(0,200),
            role: e.getAttribute('role'),
            ariaExpanded: e.getAttribute('aria-expanded')
        })).slice(0, 30);
    }"""
    out['custom_dropdowns'] = page.evaluate(JS_CUSTOM)

    JS_FW = """() => {
        const hints = [];
        if (document.querySelector('[ng-model]')) hints.push('angular1');
        if (document.querySelector('[_nghost]') || document.querySelector('[_ngcontent]')) hints.push('angular2+');
        if (document.querySelector('[data-reactroot]') || document.querySelector('[data-reactid]')) hints.push('react');
        if (document.querySelector('[data-v-]')) hints.push('vue');
        if (document.querySelector('ng-select')) hints.push('ng-select');
        if (document.querySelector('mat-select')) hints.push('mat-select');
        if (document.querySelector('.ng-select')) hints.push('ng-select-class');
        if (document.querySelector('.p-dropdown')) hints.push('primeng-dropdown');
        return hints;
    }"""
    out['framework_hints'] = page.evaluate(JS_FW)

    JS_FORM = """() => {
        const forms = [...document.querySelectorAll('form')];
        if (forms.length > 0) return forms[0].outerHTML.substring(0, 5000);
        const divs = [...document.querySelectorAll('div, section')];
        const match = divs.find(d => /select.*year|select.*month|get.*portfolio/i.test(d.innerText) && d.innerText.length < 500);
        if (match) return match.outerHTML.substring(0, 5000);
        return null;
    }"""
    out['form_area_html'] = page.evaluate(JS_FORM)

    out['xhrs'] = [r for r in responses if 'json' in r.get('ct', '') or 'api' in r['url'].lower()][:20]

    b.close()

with open('tools/probe_out/mf44_postclick.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)
print('DONE mf44')
print('Title:', out['title'])
print('Selects:', json.dumps(out['selects'], indent=2)[:1000])
print('Custom dropdowns:', json.dumps(out['custom_dropdowns'], indent=2)[:1000])
print('Framework hints:', out['framework_hints'])
print('Buttons:', json.dumps(out['buttons'], indent=2)[:500])
print('Visible text:', json.dumps(out['visible_text'], indent=2)[:1000])
print('Form area HTML (first 2000):', (out.get('form_area_html') or 'None')[:2000])
