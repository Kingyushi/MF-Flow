"""mf28 Navi v7 - Force-interact with hidden selects and check resulting content."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    api_responses = []

    def capture(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        status = response.status
        if 'navi.com' in url:
            try:
                body_preview = response.text()[:2000]
            except:
                body_preview = ''
            api_responses.append({'url': url[:300], 'status': status, 'ct': ct, 'body': body_preview})

    page.on('response', capture)
    page.goto('https://navi.com/mutual-fund/downloads/portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    # Force-interact with hidden selects via JS
    result = page.evaluate("""() => {
        // There are multiple sets of selects (for each sub-tab: Monthly, Fortnightly, etc.)
        // Find the one that's in the "Monthly" section
        const allSections = [...document.querySelectorAll('.elementor-section, .elementor-widget, div')];

        // Get all select pairs
        const selPairs = [];
        const allSelects = [...document.querySelectorAll('select')];
        for (let i = 0; i < allSelects.length; i += 2) {
            if (i + 1 < allSelects.length) {
                const fy = allSelects[i];
                const dur = allSelects[i + 1];
                if (fy.name === 'financial_year' && (dur.className === 'month' || dur.name === 'duration')) {
                    selPairs.push({
                        fyName: fy.name,
                        durName: dur.name,
                        durCls: dur.className,
                        fyOptions: [...fy.options].map(o => o.value).filter(v => v),
                        durOptions: [...dur.options].map(o => o.value).filter(v => v),
                        parent: fy.closest('[data-id]') ? fy.closest('[data-id]').getAttribute('data-id') : ''
                    });
                }
            }
        }
        return selPairs;
    }""")
    out['select_pairs'] = result

    # Now try setting the first "Monthly" select pair (cls=month)
    page.evaluate("""() => {
        const allSelects = [...document.querySelectorAll('select')];
        // Find select with className "month" (not "fortnight" etc.)
        for (let i = 0; i < allSelects.length; i++) {
            const s = allSelects[i];
            if (s.className === 'month') {
                // Found the monthly duration select. The FY select should be the previous one
                const fySelect = allSelects[i - 1];
                if (fySelect && fySelect.name === 'financial_year') {
                    // Set to latest FY
                    const fyOpts = [...fySelect.options].filter(o => o.value).sort((a,b) => b.value.localeCompare(a.value));
                    if (fyOpts.length > 0) {
                        fySelect.value = fyOpts[0].value;
                        fySelect.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                    // Set to latest month - but which months have data?
                    // Try April first
                    s.value = 'April';
                    s.dispatchEvent(new Event('change', {bubbles: true}));
                    return {fy: fySelect.value, month: s.value};
                }
            }
        }
        return null;
    }""")
    page.wait_for_timeout(3000)

    # Check if any new content appeared
    content_after = page.content()
    import re
    xlsx_urls = re.findall(r'https?://[^\s"\'<>]+\.xlsx?[^\s"\'<>]*', content_after, re.I)
    out['xlsx_after_select'] = xlsx_urls[:20]

    # Check for download links or scheme names
    out['navi_scheme_text'] = page.evaluate(r"""() => {
        const body = document.body.innerText;
        const lines = body.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /navi.*fund|flexi.*cap|large.*mid/i.test(l)).slice(0, 20);
    }""")

    # Check the response to the page itself for embedded data
    page_response = [r for r in api_responses if r['url'].startswith('https://navi.com/mutual-fund/downloads/portfolio') and r['status'] == 200]
    if page_response:
        body = page_response[0]['body']
        xlsx_in_body = re.findall(r'https?://[^\s"\'<>]+\.xlsx?[^\s"\'<>]*', body, re.I)
        out['xlsx_in_initial_response'] = xlsx_in_body[:10]

    # Check ALL responses for xlsx URLs
    all_xlsx_responses = []
    for r in api_responses:
        if '.xls' in r['body'].lower():
            all_xlsx_responses.append({'url': r['url'][:120], 'xlsx_found': True})
    out['responses_with_xlsx'] = all_xlsx_responses

    # The page might use WordPress REST API
    wp_api = [r for r in api_responses if 'wp-json' in r['url'] or 'wp-admin' in r['url'] or 'rest_route' in r['url']]
    out['wp_api'] = [{'url': r['url'][:200], 'body': r['body'][:500]} for r in wp_api]

    b.close()

with open('tools/probe_out/mf28_v7.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf28 v7')
print()
print('Select pairs:', json.dumps(out['select_pairs'], indent=2)[:1000])
print()
print('XLSX after select:', out.get('xlsx_after_select', []))
print('Navi scheme text:', out.get('navi_scheme_text', []))
print('Responses with xlsx:', out.get('responses_with_xlsx', []))
print('WP API:', json.dumps(out.get('wp_api', []), indent=2)[:500])
print('XLSX in initial response:', out.get('xlsx_in_initial_response', []))
print()
print('All navi.com responses:')
for r in api_responses:
    if 'navi.com' in r['url']:
        print(f"  [{r['status']}] {r['url'][:120]}")
