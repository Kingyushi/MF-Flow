"""mf28 Navi v13 - Call the API directly using the page's nonce."""
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

    # Get the navi_property object
    navi_prop = page.evaluate("""() => {
        if (typeof navi_property !== 'undefined') {
            return {
                rest_url: navi_property.rest_url,
                nonce: navi_property.nonce,
                ajaxurl: navi_property.ajaxurl
            };
        }
        return null;
    }""")
    print('navi_property:', json.dumps(navi_prop, indent=2))

    # Get data-attributes from the select container to find category/type/order
    container_data = page.evaluate("""() => {
        // Find the container with the Monthly portfolio select
        const containers = [...document.querySelectorAll('[data-category]')];
        return containers.map(c => ({
            category: c.getAttribute('data-category'),
            type: c.getAttribute('data-type'),
            order: c.getAttribute('data-order'),
            cls: c.className.substring(0, 100),
            textPreview: (c.innerText || '').trim().substring(0, 200)
        })).slice(0, 10);
    }""")
    print('Containers:', json.dumps(container_data, indent=2)[:1000])

    # Now call the API for Monthly portfolio with FY 2025-2026, May
    if navi_prop:
        data = page.evaluate("""([restUrl, nonce]) => {
            return new Promise((resolve) => {
                jQuery.ajax({
                    url: restUrl + 'nv/v1/documents',
                    type: 'POST',
                    dataType: 'json',
                    data: {
                        financial_year: '2025-2026',
                        value: 'May',
                        category: 'Monthly',
                        type: 'Monthly',
                        order: '1'
                    },
                    beforeSend: function(xhr) {
                        xhr.setRequestHeader('WP-NONCE', nonce);
                    },
                    success: function(response) { resolve(response); },
                    error: function(xhr, status, error) { resolve({error: error, status: xhr.status}); }
                });
            });
        }""", [navi_prop['rest_url'], navi_prop['nonce']])
        print()
        print('API response for Monthly 2025-2026 May:')
        print(json.dumps(data, indent=2)[:2000])

        # Try different category names
        for cat in ['Portfolio', 'portfolio', 'Monthly Portfolio', 'Monthly', 'monthly']:
            data2 = page.evaluate("""([restUrl, nonce, cat]) => {
                return new Promise((resolve) => {
                    jQuery.ajax({
                        url: restUrl + 'nv/v1/documents',
                        type: 'POST',
                        dataType: 'json',
                        data: {
                            financial_year: '2025-2026',
                            value: 'May',
                            category: cat,
                            type: 'Monthly',
                            order: '1'
                        },
                        beforeSend: function(xhr) {
                            xhr.setRequestHeader('WP-NONCE', nonce);
                        },
                        success: function(response) { resolve(response); },
                        error: function(xhr, status, error) { resolve({error: error}); }
                    });
                });
            }""", [navi_prop['rest_url'], navi_prop['nonce'], cat])
            items = data2.get('data', []) if isinstance(data2, dict) else []
            print(f'  category={cat}: {len(items)} items')
            if items:
                for item in items[:3]:
                    print(f'    {item.get("title", "")} -> {item.get("url", "")[:100]}')

    b.close()
