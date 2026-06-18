"""mf42 Trust v4 - Fetch the GetData API to find monthly portfolio links."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    api_data = []

    def capture(response):
        url = response.url
        ct = response.headers.get('content-type', '')
        if 'GetData' in url:
            try:
                body = response.json()
            except:
                body = None
            api_data.append({'url': url[:300], 'data': body})

    page.on('response', capture)
    page.goto('https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    out = {}

    # Analyze all GetData responses
    for i, resp in enumerate(api_data):
        data = resp.get('data', {})
        if data and isinstance(data, dict):
            arr = data.get('resultSetArray', [])
            if arr:
                # Check for monthly portfolio entries
                for item in arr:
                    if isinstance(item, dict):
                        text = json.dumps(item)
                        if 'monthly' in text.lower() or 'portfolio' in text.lower():
                            if 'monthly_responses' not in out:
                                out['monthly_responses'] = []
                            out['monthly_responses'].append({'api_idx': i, 'item': item})

    # Save all API data for inspection
    out['all_api_data'] = []
    for resp in api_data:
        data = resp.get('data', {})
        if data and isinstance(data, dict):
            arr = data.get('resultSetArray', [])
            out['all_api_data'].append({
                'url': resp['url'],
                'count': len(arr) if arr else 0,
                'sample_keys': list(arr[0].keys()) if arr and isinstance(arr[0], dict) else [],
                'sample_items': [json.dumps(item)[:200] for item in arr[:3]] if arr else []
            })

    # Now click on "Monthly Portfolio Disclosure" section to trigger more API calls
    page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => {
            const t = (e.innerText || '').trim();
            return t === 'Monthly Portfolio Disclosure' || t === 'Monthly Disclosure';
        });
        if (el) el.click();
    }""")
    page.wait_for_timeout(3000)

    # Also try clicking the actual list items
    page.evaluate("""() => {
        const all = [...document.querySelectorAll('*')];
        const el = all.find(e => {
            const t = (e.innerText || '').trim();
            return /TRUSTMF Monthly Portfolio Report/i.test(t) && t.length < 100;
        });
        if (el) el.click();
    }""")
    page.wait_for_timeout(3000)

    # Check for new API data after clicks
    new_api = []
    for resp in api_data[len(out.get('all_api_data', [])):]:
        data = resp.get('data', {})
        if data:
            new_api.append({'url': resp['url'], 'data_preview': json.dumps(data)[:1000]})
    out['new_api_after_click'] = new_api

    # Check ALL links now including hidden ones
    out['all_links_now'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a'))
            .filter(a => {
                const href = (a.href || '').toLowerCase();
                return href.includes('.xls') || href.includes('trustmf.com/content');
            })
            .map(a => ({text: (a.innerText||'').trim().substring(0, 100), href: a.href.substring(0, 300), visible: a.offsetParent !== null}))
            .slice(0, 30)
    }""")

    # Check the full DOM for all content/uploads URLs
    out['content_urls'] = page.evaluate("""() => {
        const html = document.body.innerHTML;
        const matches = [];
        const regex = /https?:\\/\\/[^"'\\s]*trustmf[^"'\\s]*\\.xls[x]?[^"'\\s]*/gi;
        let m;
        while ((m = regex.exec(html)) !== null) {
            matches.push(m[0]);
        }
        return matches.slice(0, 30);
    }""")

    # Also try fetching the API directly
    api_direct = page.evaluate("""() => {
        return fetch('/api/api/Trust/GetData', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({slug: 'monthly-portfolio-disclosure', parentslug: 'portfolio-disclosures'})
        }).then(r => r.json()).catch(e => ({error: e.toString()}));
    }""")
    out['api_direct'] = api_direct

    b.close()

with open('tools/probe_out/mf42_v4.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf42 v4')
print()
print('Monthly responses:', json.dumps(out.get('monthly_responses', [])[:5], indent=2)[:2000])
print()
print('All API data summary:')
for d in out.get('all_api_data', []):
    print(f"  URL: {d['url'][:80]}, count={d['count']}, keys={d['sample_keys']}")
    for s in d['sample_items'][:2]:
        print(f"    {s}")
print()
print('Content URLs in DOM:', out.get('content_urls', []))
print()
print('API direct call result:', json.dumps(out.get('api_direct', {}), indent=2)[:2000])
print()
print('All links now:', json.dumps(out.get('all_links_now', []), indent=2)[:500])
