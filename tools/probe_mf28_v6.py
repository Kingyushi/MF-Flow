"""mf28 Navi v6 - Check if the content is loaded via AJAX or if selects need JS trigger."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    api_responses = []

    def capture(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        if 'navi.com' in url and ('json' in ct or 'xlsx' in url.lower() or 'api' in url.lower() or 'portfolio' in url.lower()):
            try:
                body = response.text()[:3000]
            except:
                body = ''
            api_responses.append({'url': url[:300], 'status': response.status, 'ct': ct, 'body': body})

    page.on('response', capture)
    page.goto('https://navi.com/mutual-fund/downloads/portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    # Use JavaScript to change the select values and trigger the change event properly
    result = page.evaluate("""() => {
        // Find ALL selects (visible and hidden)
        const selects = [...document.querySelectorAll('select')];
        const info = selects.map(s => ({
            name: s.name,
            cls: s.className,
            visible: s.offsetParent !== null,
            display: getComputedStyle(s).display,
            parentDisplay: s.parentElement ? getComputedStyle(s.parentElement).display : '',
            computedVisibility: getComputedStyle(s).visibility,
            options: [...s.options].map(o => o.value).slice(0, 5)
        }));
        return info;
    }""")
    out['select_visibility'] = result

    # Look at the page structure more carefully - maybe the data is in Elementor widgets
    out['elementor_widgets'] = page.evaluate("""() => {
        const widgets = [...document.querySelectorAll('[data-widget_type]')];
        return widgets.map(w => ({
            type: w.getAttribute('data-widget_type'),
            id: w.getAttribute('data-id'),
            textPreview: (w.innerText || '').trim().substring(0, 100)
        })).filter(w => w.textPreview.length > 0).slice(0, 30);
    }""")

    # Check for shortcode or dynamic content containers
    out['dynamic_content'] = page.evaluate("""() => {
        const els = [...document.querySelectorAll('[data-settings], .jet-listing-grid, .elementor-shortcode')];
        return els.map(e => ({
            tag: e.tagName,
            cls: (e.className||'').toString().substring(0, 100),
            settings: (e.getAttribute('data-settings') || '').substring(0, 300),
            textPreview: (e.innerText || '').trim().substring(0, 200)
        })).slice(0, 20);
    }""")

    # The real test: look in the HTML source for any href containing file downloads
    # that are conditionally shown via CSS classes
    out['hidden_download_divs'] = page.evaluate("""() => {
        const all = [...document.querySelectorAll('div, section, article')];
        const withDownloads = all.filter(d => {
            const html = d.innerHTML.toLowerCase();
            return (html.includes('.xlsx') || html.includes('.xls')) && d.children.length < 50;
        });
        return withDownloads.map(d => ({
            cls: (d.className||'').toString().substring(0, 100),
            visible: d.offsetParent !== null,
            html: d.innerHTML.substring(0, 500)
        })).slice(0, 10);
    }""")

    out['api_responses'] = api_responses

    b.close()

with open('tools/probe_out/mf28_v6.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf28 v6')
print()
print('Select visibility:', json.dumps(out['select_visibility'], indent=2)[:1000])
print()
print('Hidden download divs:', json.dumps(out.get('hidden_download_divs', []), indent=2)[:2000])
print()
print('API responses:', len(out.get('api_responses', [])))
for r in out.get('api_responses', [])[:5]:
    print(f"  {r['url'][:120]} [{r['status']}]")
    print(f"  {r['body'][:200]}")
print()
print('Elementor widgets:', json.dumps(out.get('elementor_widgets', []), indent=2)[:500])
