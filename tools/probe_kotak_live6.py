"""Kotak - select 'Consolidated & Fortnightly Portfolio' from the Portfolios dropdown,
then pick a year, and capture the resulting file links/API calls."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled']
    )
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        locale='en-IN',
        viewport={'width': 1366, 'height': 768},
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en-US', 'en']});
        window.chrome = { runtime: {} };
    """)

    page = ctx.new_page()

    responses = []
    def capture(r):
        url = r.url
        ct = r.headers.get('content-type', '')
        if 'json' in ct or '.xlsx' in url or 'download' in url.lower() or 'portfolio' in url.lower() or 'forms' in url.lower():
            body = ''
            try:
                body = r.text()[:5000]
            except:
                pass
            responses.append({'url': url[:300], 'status': r.status, 'ct': ct, 'body': body})
    page.on('response', capture)

    page.goto('https://www.kotakmf.com/Information/forms-and-downloads', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    if 'captcha' in page.title().lower():
        print('CAPTCHA - aborting')
        browser.close()
        exit(1)

    resp_before = len(responses)

    # The Portfolio section has a custom select dropdown.
    # Find the "Portfolios" section's select (not the Factsheet one, not Addendums)
    # The sections are: Forms, Factsheet, Portfolios, Addendums, ...
    # Each has its own select with class "selectcustom"

    # Strategy: find the select that has "Consolidated & Fortnightly Portfolio" as an option
    select_info = page.evaluate("""() => {
        const selects = [...document.querySelectorAll('select')];
        for (let i = 0; i < selects.length; i++) {
            const opts = [...selects[i].options];
            const hasConsolidated = opts.some(o => o.text.includes('Consolidated'));
            if (hasConsolidated) {
                return {
                    index: i,
                    options: opts.map(o => ({text: o.text.trim(), value: o.value}))
                };
            }
        }
        return null;
    }""")
    print('=== Portfolio select:', json.dumps(select_info, indent=2))

    if select_info:
        idx = select_info['index']
        # Select "Consolidated & Fortnightly Portfolio"
        cons_value = None
        for opt in select_info['options']:
            if 'Consolidated' in opt['text']:
                cons_value = opt['value']
                break

        if cons_value:
            print(f'\n=== Selecting Consolidated (value={cons_value}) on select index {idx} ===')
            # Use JS to select by index
            page.evaluate(f"""() => {{
                const sel = document.querySelectorAll('select')[{idx}];
                sel.value = '{cons_value}';
                sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}""")
            page.wait_for_timeout(5000)

            # Check new responses
            new_resps = responses[resp_before:]
            print(f'=== New responses after selecting Consolidated: {len(new_resps)}')
            for r in new_resps:
                print(f'  {r["status"]} {r["url"][:200]}')
                if r['body'] and 'json' in r['ct']:
                    print(f'    JSON body: {r["body"][:1000]}')

            # Check for file links that appeared
            file_links = page.evaluate("""() => {
                return [...document.querySelectorAll('a[href]')].map(a => ({
                    text: (a.innerText||'').trim().substring(0, 100),
                    href: a.href?.substring(0, 300)
                })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls') || e.href.includes('download'))).slice(0, 20);
            }""")
            print(f'\n=== File links after Consolidated select: {json.dumps(file_links, indent=2)}')

            # Check body text around the Portfolios section
            body_after = page.evaluate('() => document.body?.innerText || ""')
            idx2 = body_after.find('Portfolios')
            if idx2 >= 0:
                print(f'\n=== Body around Portfolios after select:')
                print(body_after[idx2:idx2+2000])

            # Check for month calendar/list that may have appeared
            month_elements = page.evaluate("""() => {
                const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
                const all = [...document.querySelectorAll('*')];
                return all.filter(e =>
                    e.children.length === 0 &&
                    months.includes((e.innerText||'').trim())
                ).map(e => ({
                    tag: e.tagName,
                    text: e.innerText.trim(),
                    cls: (e.className||'').substring(0, 100),
                    clickable: e.tagName === 'A' || e.tagName === 'BUTTON' || e.onclick != null || e.getAttribute('ng-click') != null,
                    parentCls: (e.parentElement?.className||'').substring(0, 100)
                })).slice(0, 30);
            }""")
            print(f'\n=== Month elements: {json.dumps(month_elements, indent=2)}')

    browser.close()
