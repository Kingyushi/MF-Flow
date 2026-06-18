"""Taurus MF - after year select, the AJAX replaces the view.
Need to look at the full page structure after AJAX, including month select location."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    responses_data = []
    def capture(r):
        url = r.url
        ct = r.headers.get('content-type', '')
        if 'views/ajax' in url:
            try:
                body = r.text()
            except:
                body = ''
            responses_data.append({'url': url, 'status': r.status, 'ct': ct, 'body': body})
    page.on('response', capture)

    page.goto('https://taurusmutualfund.com/monthly-portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(3000)

    # Select year 2026
    print('=== Selecting year 2026 ===')
    page.select_option('select#edit-field-monthly-portfolio-target-id', label='2026')
    page.wait_for_timeout(5000)

    # Check AJAX response
    print(f'\n=== AJAX responses: {len(responses_data)} ===')
    for rd in responses_data:
        print(f'  Status: {rd["status"]}, URL: {rd["url"][:200]}')
        body = rd['body']
        print(f'  Body length: {len(body)}')
        # Parse the Drupal AJAX response
        try:
            ajax_data = json.loads(body)
            if isinstance(ajax_data, list):
                for cmd in ajax_data:
                    command = cmd.get('command', '?')
                    method = cmd.get('method', '?')
                    selector = cmd.get('selector', '?')
                    data_html = cmd.get('data', '')
                    settings = cmd.get('settings', '')
                    print(f'    Command: {command}, method: {method}, selector: {selector}')
                    if isinstance(data_html, str) and data_html:
                        # Look for xlsx links in the HTML data
                        xlsx_links = re.findall(r'href=["\']([^"\']*\.xlsx[^"\']*)["\']', data_html, re.IGNORECASE)
                        print(f'    xlsx links in HTML: {xlsx_links[:10]}')
                        # Look for month-related content
                        if 'month' in data_html.lower() or 'select' in data_html.lower():
                            # Find select elements
                            import re
                            select_matches = re.findall(r'<select[^>]*>(.*?)</select>', data_html, re.DOTALL)
                            for sm in select_matches:
                                opts = re.findall(r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>', sm)
                                print(f'    Select options: {opts[:15]}')
                        # Print a snippet of the HTML
                        print(f'    HTML snippet: {data_html[:1000]}')
        except (json.JSONDecodeError, Exception) as e:
            print(f'    Parse error: {e}')
            print(f'    Raw body snippet: {body[:500]}')

    # Check page state after AJAX
    all_selects = page.evaluate("""() => {
        return [...document.querySelectorAll('select')].map(sel => ({
            name: sel.name, id: sel.id,
            options: [...sel.options].map(o => ({text: o.text.trim(), value: o.value, selected: o.selected}))
        }));
    }""")
    print(f'\n=== All selects after year AJAX:')
    print(json.dumps(all_selects, indent=2))

    # Full body text to see what's there
    body = page.evaluate('() => document.body?.innerText || ""')
    # Find the main content
    for marker in ['Monthly', 'portfolio', 'Scheme', 'Select']:
        idx = body.lower().find(marker.lower())
        if idx >= 0:
            print(f'\n=== Body around "{marker}" (pos {idx}):')
            print(body[max(0,idx-100):idx+500])
            break

    import re  # ensure imported at module scope
    browser.close()
