"""mf28 Navi v4 - Look at what content appears after selecting FY + month."""
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

    out = {}

    # Select FY 2025-2026 (April 2025 - March 2026)
    page.select_option('select[name="financial_year"]', '2025-2026')
    page.wait_for_timeout(2000)

    # Check month options
    out['month_options'] = page.evaluate("""() => {
        const sel = document.querySelector('select[name="duration"]');
        if (!sel) return [];
        return [...sel.options].map(o => ({value: o.value, text: o.text.trim()}));
    }""")

    # Select May (should have data for May 2025)
    page.select_option('select[name="duration"]', 'May')
    page.wait_for_timeout(3000)

    # Check full page HTML for xlsx references
    out['xlsx_in_html'] = page.evaluate("""() => {
        const html = document.body.innerHTML;
        const matches = [];
        const regex = /https?:\\/\\/[^"'\\s]+\\.xlsx?[^"'\\s]*/gi;
        let m;
        while ((m = regex.exec(html)) !== null) {
            matches.push(m[0]);
        }
        return matches.slice(0, 30);
    }""")

    # Check for ANY hidden divs that might contain download content
    out['hidden_content'] = page.evaluate("""() => {
        const divs = [...document.querySelectorAll('div[style*="display: none"], div[style*="display:none"], div.hidden, div[class*="hide"], [aria-hidden="true"]')];
        const withXlsx = divs.filter(d => d.innerHTML.toLowerCase().includes('.xls'));
        return withXlsx.map(d => d.innerHTML.substring(0, 500)).slice(0, 5);
    }""")

    # Check for ALL anchor tags in the page (visible AND hidden)
    out['all_anchors'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a'))
            .filter(a => {
                const href = (a.href || '').toLowerCase();
                return href.includes('.xls') || href.includes('xlsx') || href.includes('download');
            })
            .map(a => ({
                text: (a.innerText || '').trim().substring(0, 100),
                href: a.href.substring(0, 200),
                visible: a.offsetParent !== null,
                display: getComputedStyle(a).display,
                parentVisible: a.parentElement ? a.parentElement.offsetParent !== null : false
            }))
            .slice(0, 30)
    }""")

    # Check the portfolio section specifically
    out['portfolio_section'] = page.evaluate(r"""() => {
        const body = document.body.innerText;
        const lines = body.split('\n');
        // Find the area between "Monthly" and "Fortnightly"
        let start = -1, end = -1;
        for (let i = 0; i < lines.length; i++) {
            if (start === -1 && /^Monthly$/i.test(lines[i].trim())) start = i;
            else if (start > -1 && /^Fortnightly$/i.test(lines[i].trim())) { end = i; break; }
        }
        if (start > -1) return lines.slice(start, end > -1 ? end : start + 30).join('\n');
        return null;
    }""")

    # Now try 2025-2026 with April (which is likely to have data)
    page.select_option('select[name="financial_year"]', '2025-2026')
    page.wait_for_timeout(1000)
    page.select_option('select[name="duration"]', 'April')
    page.wait_for_timeout(3000)

    out['xlsx_after_april'] = page.evaluate("""() => {
        const html = document.body.innerHTML;
        const matches = [];
        const regex = /https?:\\/\\/[^"'\\s]+\\.xlsx?[^"'\\s]*/gi;
        let m;
        while ((m = regex.exec(html)) !== null) {
            matches.push(m[0]);
        }
        return matches.slice(0, 30);
    }""")

    out['portfolio_section_april'] = page.evaluate(r"""() => {
        const body = document.body.innerText;
        const lines = body.split('\n');
        let start = -1, end = -1;
        for (let i = 0; i < lines.length; i++) {
            if (start === -1 && /^Monthly$/i.test(lines[i].trim())) start = i;
            else if (start > -1 && /^Fortnightly$/i.test(lines[i].trim())) { end = i; break; }
        }
        if (start > -1) return lines.slice(start, end > -1 ? end : start + 50).join('\n');
        return null;
    }""")

    # Also check page.content() for xlsx patterns
    content = page.content()
    import re
    xlsx_urls = re.findall(r'https?://[^\s"\'<>]+\.xlsx?[^\s"\'<>]*', content, re.I)
    out['xlsx_urls_in_content'] = xlsx_urls[:30]

    b.close()

with open('tools/probe_out/mf28_v4.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf28 v4')
print('XLSX in HTML:', out.get('xlsx_in_html', []))
print('Hidden content with xlsx:', out.get('hidden_content', []))
print('All xlsx/download anchors:', json.dumps(out.get('all_anchors', []), indent=2)[:1000])
print()
print('Portfolio section (May):', (out.get('portfolio_section') or 'None')[:500])
print()
print('XLSX after April:', out.get('xlsx_after_april', []))
print('Portfolio section (April):', (out.get('portfolio_section_april') or 'None')[:500])
print()
print('XLSX URLs in page content:', out.get('xlsx_urls_in_content', [])[:10])
