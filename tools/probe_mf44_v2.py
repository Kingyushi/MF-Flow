"""Deeper probe for mf44 UTI - find the actual dropdown mechanism."""
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

    # Get the main content area HTML
    out['main_html'] = page.evaluate("""() => {
        // Find the download form area
        const divs = [...document.querySelectorAll('div, section')];
        const match = divs.find(d => {
            const t = (d.innerText || '').trim();
            return t.includes('Select Year') && t.includes('Select Month') && t.length < 2000;
        });
        if (match) return match.outerHTML.substring(0, 5000);
        return document.body.innerHTML.substring(0, 8000);
    }""")

    # Look for Angular ng-select or custom dropdown components
    out['ng_selects'] = page.evaluate("""() => {
        const els = [...document.querySelectorAll('ng-select, .ng-select, .ng-dropdown-panel, [class*="ng-select"], mat-select, .mat-select')];
        return els.map(e => ({
            tag: e.tagName,
            cls: e.className.substring(0, 200),
            text: (e.innerText || '').trim().substring(0, 200),
            id: e.id,
            placeholder: e.getAttribute('placeholder'),
            bindLabel: e.getAttribute('bindlabel'),
            formControlName: e.getAttribute('formcontrolname')
        })).slice(0, 20);
    }""")

    # Look for all input/form elements
    out['inputs'] = page.evaluate("""() => {
        const els = [...document.querySelectorAll('input, textarea, select, ng-select')];
        return els.map(e => ({
            tag: e.tagName,
            type: e.type,
            name: e.name,
            id: e.id,
            cls: e.className.substring(0, 150),
            placeholder: e.getAttribute('placeholder'),
            value: (e.value || '').substring(0, 100),
            formControlName: e.getAttribute('formcontrolname')
        })).slice(0, 30);
    }""")

    # Check for the "Consolidate Portfolio Disclosure All Scheme" text
    out['page_text_excerpt'] = page.evaluate(r"""() => {
        const text = document.body.innerText;
        const lines = text.split('\n').filter(l => l.trim().length > 0);
        // Get all lines in the download section area
        const start = lines.findIndex(l => /consolidate|portfolio.*disclosure|select.*from/i.test(l));
        if (start > -1) return lines.slice(start, start + 30);
        return lines.slice(0, 30);
    }""")

    # Try to find and click the year dropdown
    year_dropdown = page.evaluate("""() => {
        // Look for elements containing "Select Year"
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => {
            const t = (e.innerText || '').trim();
            return t === 'Select Year' || t === 'select year';
        });
        if (el) {
            return {
                tag: el.tagName,
                cls: el.className.substring(0, 200),
                parentTag: el.parentElement ? el.parentElement.tagName : null,
                parentCls: el.parentElement ? el.parentElement.className.substring(0, 200) : null,
                grandparentTag: el.parentElement && el.parentElement.parentElement ? el.parentElement.parentElement.tagName : null,
                grandparentCls: el.parentElement && el.parentElement.parentElement ? el.parentElement.parentElement.className.substring(0, 200) : null,
                siblings: el.parentElement ? [...el.parentElement.children].map(c => ({tag: c.tagName, cls: c.className.substring(0, 100), text: (c.innerText||'').trim().substring(0, 50)})) : []
            };
        }
        return null;
    }""")
    out['year_dropdown_element'] = year_dropdown

    # Try clicking "Select Year" text to open a dropdown
    try:
        page.click('text=Select Year', timeout=5000)
        page.wait_for_timeout(2000)

        # Check what appeared (dropdown options)
        out['year_options_after_click'] = page.evaluate("""() => {
            const panels = [...document.querySelectorAll('.ng-dropdown-panel, .dropdown-menu, [class*="dropdown-panel"], [class*="option"], [class*="listbox"], [role="option"], [role="listbox"]')];
            return panels.map(p => ({
                tag: p.tagName,
                cls: p.className.substring(0, 200),
                text: (p.innerText || '').trim().substring(0, 500),
                role: p.getAttribute('role')
            })).slice(0, 20);
        }""")

        # Also get any visible option-like elements
        out['visible_options'] = page.evaluate(r"""() => {
            const all = [...document.querySelectorAll('*')];
            return all.filter(e => /^20\d{2}$/.test((e.innerText||'').trim()) && e.offsetParent !== null && e.innerText.trim().length === 4)
                .map(e => ({tag: e.tagName, cls: e.className.substring(0, 100), text: e.innerText.trim()}))
                .slice(0, 20);
        }""")
    except Exception as e:
        out['year_click_error'] = str(e)

    b.close()

with open('tools/probe_out/mf44_v2.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf44 v2')
print()
print('ng-selects:', json.dumps(out.get('ng_selects', []), indent=2)[:1000])
print()
print('inputs:', json.dumps(out.get('inputs', []), indent=2)[:1000])
print()
print('Year dropdown element:', json.dumps(out.get('year_dropdown_element'), indent=2)[:800])
print()
print('Year options after click:', json.dumps(out.get('year_options_after_click', []), indent=2)[:800])
print()
print('Visible options:', json.dumps(out.get('visible_options', []), indent=2)[:500])
print()
print('Page text excerpt:', json.dumps(out.get('page_text_excerpt', []), indent=2)[:500])
print()
print('Main HTML (first 2000):', (out.get('main_html') or '')[:2000])
