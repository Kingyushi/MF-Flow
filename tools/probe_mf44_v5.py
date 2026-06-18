"""mf44 UTI v5 - Capture ALL network requests after Get Portfolio."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    all_responses = []

    def capture(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        all_responses.append({'url': url[:300], 'status': response.status, 'ct': ct})

    page.on('response', capture)
    page.goto('https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}
    initial_count = len(all_responses)

    # Click year dropdown and select 2026
    page.click('input[placeholder="Select Year"]')
    page.wait_for_timeout(2000)
    page.evaluate("""() => {
        const items = [...document.querySelectorAll('div.option-select')];
        const y2026 = items.find(i => i.innerText.trim() === '2026');
        if (y2026) y2026.click();
    }""")
    page.wait_for_timeout(3000)

    after_year_count = len(all_responses)
    out['responses_after_year'] = [r for r in all_responses[initial_count:after_year_count]
                                    if not r['url'].startswith('data:')]

    # Click month dropdown
    page.click('input[placeholder="select "]')
    page.wait_for_timeout(2000)

    # Select April
    page.evaluate("""() => {
        const items = [...document.querySelectorAll('div.option-select')];
        const apr = items.find(i => i.innerText.trim() === 'April' && i.offsetParent !== null);
        if (apr) apr.click();
    }""")
    page.wait_for_timeout(2000)

    before_submit = len(all_responses)

    # Click "Get Portfolio" and capture the download
    try:
        with page.expect_download(timeout=15000) as download_info:
            page.click('button:has-text("Get Portfolio")')
        download = download_info.value
        out['download'] = {
            'url': download.url,
            'suggested_filename': download.suggested_filename,
        }
    except Exception as e:
        out['download_error'] = str(e)
        # Still wait for responses
        page.wait_for_timeout(8000)

    after_submit = len(all_responses)
    out['responses_after_submit'] = [r for r in all_responses[before_submit:]
                                      if not r['url'].startswith('data:')]

    # Also check for zip/portfolio responses
    out['zip_responses'] = [r for r in all_responses if '.zip' in r['url'].lower()]
    out['portfolio_api_responses'] = [r for r in all_responses
                                       if 'api' in r['url'].lower()
                                       and r['status'] == 200
                                       and 'json' in r.get('ct', '')]

    b.close()

with open('tools/probe_out/mf44_v5.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf44 v5')
print()
if 'download' in out:
    print('DOWNLOAD CAPTURED!')
    print('URL:', out['download']['url'])
    print('Filename:', out['download']['suggested_filename'])
else:
    print('Download error:', out.get('download_error', 'unknown'))
print()
print('Responses after year select:', len(out.get('responses_after_year', [])))
for r in out.get('responses_after_year', [])[:5]:
    print(f"  {r['url'][:120]} [{r['status']}] {r['ct'][:40]}")
print()
print('Responses after submit:', len(out.get('responses_after_submit', [])))
for r in out.get('responses_after_submit', [])[:10]:
    print(f"  {r['url'][:120]} [{r['status']}] {r['ct'][:40]}")
print()
print('Zip responses:', out.get('zip_responses', []))
print('Portfolio API responses:', len(out.get('portfolio_api_responses', [])))
for r in out.get('portfolio_api_responses', [])[:5]:
    print(f"  {r['url'][:120]}")
