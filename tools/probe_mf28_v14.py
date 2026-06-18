"""mf28 Navi v14 - Call API with numeric category 884."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto('https://navi.com/mutual-fund/downloads/portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    navi_prop = page.evaluate("""() => {
        return {
            rest_url: navi_property.rest_url,
            nonce: navi_property.nonce
        };
    }""")

    # Try with category=884 (Monthly) and various months
    for fy, month in [('2025-2026', 'May'), ('2025-2026', 'April'), ('2025-2026', 'March'), ('2026-2027', 'April')]:
        data = page.evaluate("""([restUrl, nonce, fy, month]) => {
            return new Promise((resolve) => {
                jQuery.ajax({
                    url: restUrl + 'nv/v1/documents',
                    type: 'POST',
                    dataType: 'json',
                    data: {
                        financial_year: fy,
                        value: month,
                        category: '884',
                        type: 'Monthly',
                        order: 'DESC'
                    },
                    beforeSend: function(xhr) {
                        xhr.setRequestHeader('WP-NONCE', nonce);
                    },
                    success: function(response) { resolve(response); },
                    error: function(xhr, status, error) { resolve({error: error, status: xhr.status}); }
                });
            });
        }""", [navi_prop['rest_url'], navi_prop['nonce'], fy, month])
        items = data.get('data', []) if isinstance(data, dict) else []
        print(f'FY={fy} Month={month}: {len(items)} items, success={data.get("success")}')
        for item in items[:5]:
            title = item.get('title', '')
            url = item.get('url', '')
            if isinstance(url, list):
                url = url[0] if url else ''
            print(f'  {title} -> {str(url)[:120]}')

    b.close()
