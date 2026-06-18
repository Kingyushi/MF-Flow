"""mf44 UTI v3 - Click the custom input-box dropdowns."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    api_responses = []

    def capture_response(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        if 'portfolio' in url.lower() or 'download' in url.lower() or 'api' in url.lower() or '.zip' in url.lower() or 'consolidate' in url.lower():
            try:
                body = response.text()
            except:
                body = '<binary>'
            api_responses.append({
                'url': url[:300], 'status': response.status, 'ct': ct,
                'body_preview': body[:3000] if isinstance(body, str) else ''
            })

    page.on('response', capture_response)
    page.goto('https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    # Get the input-box elements
    out['input_boxes'] = page.evaluate("""() => {
        const inputs = [...document.querySelectorAll('input.input-box')];
        return inputs.map(i => ({
            placeholder: i.placeholder,
            value: i.value,
            cls: i.className,
            parentHTML: i.parentElement ? i.parentElement.outerHTML.substring(0, 500) : ''
        }));
    }""")

    # Click the "Select Year" input box
    try:
        page.click('input[placeholder="Select Year"]', timeout=5000)
        page.wait_for_timeout(2000)

        # Check what appeared
        out['year_dropdown_items'] = page.evaluate(r"""() => {
            // Look for dropdown items, list items, options that appeared
            const items = [...document.querySelectorAll('.dropdown-item, .option, [class*="option"], [class*="item"], li.ng-star-inserted')];
            const visible = items.filter(i => i.offsetParent !== null);
            return visible.map(i => ({
                tag: i.tagName,
                text: (i.innerText||'').trim().substring(0, 50),
                cls: i.className.substring(0, 100)
            })).filter(i => /^20\d{2}$/.test(i.text)).slice(0, 20);
        }""")

        # Also get any element with year text that just appeared
        out['all_year_elements'] = page.evaluate(r"""() => {
            const all = [...document.querySelectorAll('*')];
            return all.filter(e => {
                const t = (e.innerText||'').trim();
                return /^20\d{2}$/.test(t) && e.children.length === 0 && e.offsetParent !== null;
            }).map(e => ({
                tag: e.tagName,
                text: e.innerText.trim(),
                cls: e.className.substring(0, 100),
                parentCls: e.parentElement ? e.parentElement.className.substring(0, 100) : ''
            })).slice(0, 20);
        }""")
    except Exception as e:
        out['year_click_error'] = str(e)

    # If we found years, click the latest one
    year_items = out.get('all_year_elements', [])
    if year_items:
        years = sorted([int(y['text']) for y in year_items if y['text'].isdigit()], reverse=True)
        out['available_years'] = years
        if years:
            latest_year = years[0]
            out['clicking_year'] = latest_year
            # Click the latest year
            page.evaluate(f"""() => {{
                const all = [...document.querySelectorAll('*')];
                const el = all.find(e => (e.innerText||'').trim() === '{latest_year}' && e.children.length === 0 && e.offsetParent !== null);
                if (el) el.click();
            }}""")
            page.wait_for_timeout(3000)

            # Now click the month dropdown
            try:
                # Find the month input
                page.click('input[placeholder="select "]', timeout=5000)
                page.wait_for_timeout(2000)

                out['month_dropdown_items'] = page.evaluate(r"""() => {
                    const months = ['january','february','march','april','may','june','july','august','september','october','november','december'];
                    const all = [...document.querySelectorAll('*')];
                    return all.filter(e => {
                        const t = (e.innerText||'').trim().toLowerCase();
                        return months.includes(t) && e.children.length === 0 && e.offsetParent !== null;
                    }).map(e => ({
                        tag: e.tagName,
                        text: e.innerText.trim(),
                        cls: e.className.substring(0, 100)
                    })).slice(0, 15);
                }""")
            except Exception as e:
                out['month_click_error'] = str(e)

            # If months found, click the latest
            month_items = out.get('month_dropdown_items', [])
            if month_items:
                month_order = {'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,'july':7,'august':8,'september':9,'october':10,'november':11,'december':12}
                months_available = [(month_order.get(m['text'].lower(), 0), m['text']) for m in month_items]
                months_available.sort(reverse=True)
                if months_available:
                    latest_month = months_available[0][1]
                    out['clicking_month'] = latest_month
                    page.evaluate(f"""() => {{
                        const all = [...document.querySelectorAll('*')];
                        const el = all.find(e => (e.innerText||'').trim().toLowerCase() === '{latest_month.lower()}' && e.children.length === 0 && e.offsetParent !== null);
                        if (el) el.click();
                    }}""")
                    page.wait_for_timeout(2000)

                    # Click "Get Portfolio"
                    page.evaluate("""() => {
                        const btns = [...document.querySelectorAll('button')];
                        const get = btns.find(b => /get\\s*portfolio/i.test((b.innerText||'').trim()));
                        if (get) get.click();
                    }""")
                    page.wait_for_timeout(5000)

                    # Check for download links
                    out['links_after_submit'] = page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('a[href]'))
                            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
                            .filter(([t,h]) => h.toLowerCase().includes('.zip') || h.toLowerCase().includes('download') || h.toLowerCase().includes('portfolio'))
                            .slice(0, 20)
                    }""")

                    # Check all visible text for download indicators
                    out['vis_after_submit'] = page.evaluate(r"""() => {
                        const all = document.body.innerText;
                        const lines = all.split('\n').filter(l => l.trim().length > 0);
                        return lines.filter(l => /download|zip|portfolio|click|here/i.test(l)).slice(0, 20);
                    }""")

    out['api_responses'] = api_responses

    b.close()

with open('tools/probe_out/mf44_v3.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf44 v3')
print()
print('Input boxes:', json.dumps(out.get('input_boxes', []), indent=2)[:600])
print()
print('Year dropdown items:', json.dumps(out.get('year_dropdown_items', []), indent=2)[:600])
print('All year elements:', json.dumps(out.get('all_year_elements', []), indent=2)[:600])
print('Available years:', out.get('available_years', []))
print()
print('Month dropdown items:', json.dumps(out.get('month_dropdown_items', []), indent=2)[:600])
print('Clicking month:', out.get('clicking_month'))
print()
print('Links after submit:', json.dumps(out.get('links_after_submit', []), indent=2)[:500])
print('Visible after submit:', json.dumps(out.get('vis_after_submit', []), indent=2)[:500])
print()
print('API responses:', len(out.get('api_responses', [])))
for r in out.get('api_responses', [])[:5]:
    print(f"  URL: {r['url'][:120]}")
    print(f"  Body preview: {r['body_preview'][:300]}")
