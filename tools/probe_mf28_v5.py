"""mf28 Navi v5 - The selects are hidden, check what's visible and how the content toggles."""
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

    # Get the full page HTML section with portfolio content
    out['portfolio_html'] = page.evaluate("""() => {
        const html = document.body.innerHTML;
        // Find the section with "Monthly" / "Fortnightly" tabs
        const idx = html.indexOf('Monthly');
        if (idx > -1) return html.substring(Math.max(0, idx - 2000), idx + 10000);
        return html.substring(0, 10000);
    }""")

    # Find all WordPress/Elementor section IDs that contain portfolio data
    out['elementor_sections'] = page.evaluate("""() => {
        const sections = [...document.querySelectorAll('[data-id], [id]')];
        return sections.filter(s => {
            const t = (s.innerText || '').trim().toLowerCase();
            return t.includes('navi') && (t.includes('fund') || t.includes('download') || t.includes('.xlsx'));
        }).map(s => ({
            tag: s.tagName,
            id: s.id,
            dataId: s.getAttribute('data-id'),
            cls: (s.className || '').toString().substring(0, 100),
            textPreview: (s.innerText || '').trim().substring(0, 200)
        })).slice(0, 10);
    }""")

    # Check page source for xlsx URLs
    content = page.content()
    import re
    xlsx_urls = re.findall(r'https?://[^\s"\'<>]+\.xlsx?[^\s"\'<>]*', content, re.I)
    out['xlsx_in_page_source'] = xlsx_urls[:20]

    # Check for links with data attributes
    out['data_links'] = page.evaluate("""() => {
        const els = [...document.querySelectorAll('[data-url], [data-link], [data-file], [data-download], [data-href]')];
        return els.map(e => ({
            tag: e.tagName,
            text: (e.innerText||'').trim().substring(0, 50),
            dataUrl: e.getAttribute('data-url'),
            dataLink: e.getAttribute('data-link'),
            dataFile: e.getAttribute('data-file'),
        })).slice(0, 20);
    }""")

    # The key question: find the actual content that shows the download links
    # Check what visible content appears under the Monthly section
    out['full_body_text'] = page.evaluate(r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        // Find lines between "Monthly" and "Fortnightly"
        let inMonthly = false;
        const result = [];
        for (const line of lines) {
            const t = line.trim();
            if (t === 'Monthly') { inMonthly = true; result.push(t); continue; }
            if (inMonthly && (t === 'Fortnightly' || t === 'Half Yearly')) break;
            if (inMonthly) result.push(t);
        }
        return result.slice(0, 30);
    }""")

    b.close()

with open('tools/probe_out/mf28_v5.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf28 v5')
print()
print('XLSX in page source:', out.get('xlsx_in_page_source', [])[:10])
print()
print('Full body text under Monthly section:')
for l in out.get('full_body_text', []):
    print(' ', l[:100])
print()
print('Elementor sections:', json.dumps(out.get('elementor_sections', []), indent=2)[:500])
print()
print('Data links:', json.dumps(out.get('data_links', []), indent=2)[:500])
