"""mf44 UTI v4 - Full interaction with custom dropdowns + capture API."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    api_responses = []

    def capture(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        if '.zip' in url.lower() or 'portfolio' in url.lower() or 'consolidate' in url.lower() or 'download' in url.lower():
            try:
                body = response.text()[:3000]
            except:
                body = ''
            api_responses.append({'url': url[:300], 'status': response.status, 'ct': ct, 'body': body})

    page.on('response', capture)
    page.goto('https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    # Click year dropdown and select 2026
    page.click('input[placeholder="Select Year"]')
    page.wait_for_timeout(2000)
    page.evaluate("""() => {
        const items = [...document.querySelectorAll('div.option-select')];
        const y2026 = items.find(i => i.innerText.trim() === '2026');
        if (y2026) y2026.click();
    }""")
    page.wait_for_timeout(3000)

    # Click month dropdown and check which months are available
    month_input = page.locator('input[placeholder="select "]')
    if month_input.count() == 0:
        # Try other selectors
        month_input = page.locator('input.input-box').nth(2)  # third input box

    month_input.click()
    page.wait_for_timeout(2000)

    out['month_options'] = page.evaluate("""() => {
        const items = [...document.querySelectorAll('div.option-select')];
        return items.filter(i => i.offsetParent !== null)
            .map(i => i.innerText.trim())
            .slice(0, 15);
    }""")

    # Select April (most likely to have data) from the latest available
    months_avail = out.get('month_options', [])
    print('Available months:', months_avail)

    # Try to select the latest month
    target_month = months_avail[-1] if months_avail else 'April'
    page.evaluate(f"""() => {{
        const items = [...document.querySelectorAll('div.option-select')];
        const target = items.find(i => i.innerText.trim() === '{target_month}' && i.offsetParent !== null);
        if (target) target.click();
    }}""")
    page.wait_for_timeout(2000)

    # Click "Get Portfolio"
    page.click('button:has-text("Get Portfolio")')
    page.wait_for_timeout(8000)

    # Check for download link or new content
    out['links_after_submit'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .slice(0, 100)
    }""")

    # Check specifically for zip links
    out['zip_links'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .filter(a => a.href.toLowerCase().includes('.zip'))
            .map(a => [(a.innerText || '').trim().substring(0,200), a.href])
            .slice(0, 10)
    }""")

    # Check for any new visible content
    out['vis_after'] = page.evaluate(r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /download|click|here|zip|portfolio|april|may|consolidate/i.test(l)).slice(0, 20);
    }""")

    # Check for dynamically added content
    out['new_content'] = page.evaluate("""() => {
        const html = document.body.innerHTML;
        const matches = [];
        const regex = /https?:\\/\\/[^"'\\s<>]+\\.zip[^"'\\s<>]*/gi;
        let m;
        while ((m = regex.exec(html)) !== null) {
            matches.push(m[0]);
        }
        return matches.slice(0, 10);
    }""")

    # Check API responses
    out['api_responses'] = api_responses

    # Also try fetching common UTI download patterns
    out['cloudfront_urls'] = page.evaluate("""() => {
        const html = document.body.innerHTML;
        const matches = [];
        const regex = /https?:\\/\\/d3ce1o48hc5oli\\.cloudfront\\.net[^"'\\s<>]*/gi;
        let m;
        while ((m = regex.exec(html)) !== null) {
            if (m[0].toLowerCase().includes('portfolio') || m[0].toLowerCase().includes('.zip'))
                matches.push(m[0]);
        }
        return matches.slice(0, 10);
    }""")

    b.close()

with open('tools/probe_out/mf44_v4.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf44 v4')
print('Month options:', out.get('month_options', []))
print('Zip links:', out.get('zip_links', []))
print('New content (zip URLs):', out.get('new_content', []))
print('Cloudfront URLs:', out.get('cloudfront_urls', []))
print()
print('Visible after submit:', out.get('vis_after', []))
print()
print('API responses:', len(out.get('api_responses', [])))
for r in out.get('api_responses', [])[:5]:
    print(f"  URL: {r['url'][:120]}")
    print(f"  Status: {r['status']} Body: {r['body'][:200]}")
