"""mf28 Navi v3 - Use the real select names to navigate."""
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

    # Get all select details
    out['selects'] = page.evaluate("""() => {
        return [...document.querySelectorAll('select')].map(s => ({
            name: s.name, cls: s.className, id: s.id,
            parent_cls: s.parentElement ? s.parentElement.className : '',
            options: [...s.options].map(o => ({value: o.value, text: o.text.trim()}))
        }))
    }""")

    # Click "Portfolio" tab first
    page.evaluate("""() => {
        const tabs = [...document.querySelectorAll('a, button, [role="tab"]')];
        const port = tabs.find(t => (t.innerText||'').trim() === 'Portfolio');
        if (port) port.click();
    }""")
    page.wait_for_timeout(2000)

    # Click "Monthly" sub-tab
    page.evaluate("""() => {
        const tabs = [...document.querySelectorAll('a, button, [role="tab"], li, span')];
        const monthly = tabs.find(t => (t.innerText||'').trim() === 'Monthly');
        if (monthly) monthly.click();
    }""")
    page.wait_for_timeout(2000)

    # Now select the latest financial year (2025-2026)
    fy_selected = page.evaluate("""() => {
        const sel = document.querySelector('select[name="financial_year"]');
        if (!sel) return null;
        const opts = [...sel.options].filter(o => o.value.trim() !== '');
        if (!opts.length) return null;
        // Sort by year descending
        opts.sort((a,b) => b.value.localeCompare(a.value));
        const latest = opts[0];
        sel.value = latest.value;
        sel.dispatchEvent(new Event('change', {bubbles: true}));
        return latest.value;
    }""")
    out['fy_selected'] = fy_selected
    page.wait_for_timeout(3000)

    # Check month select options
    out['month_select_after'] = page.evaluate("""() => {
        const sel = document.querySelector('select[name="duration"]');
        if (!sel) return null;
        return {
            name: sel.name, cls: sel.className,
            options: [...sel.options].map(o => ({value: o.value, text: o.text.trim()}))
        };
    }""")

    # Select the latest month
    month_selected = page.evaluate("""() => {
        const sel = document.querySelector('select[name="duration"]');
        if (!sel) return null;
        const opts = [...sel.options].filter(o => o.value.trim() !== '');
        if (!opts.length) return null;
        // Take the last option (most recent)
        const latest = opts[opts.length - 1];
        sel.value = latest.value;
        sel.dispatchEvent(new Event('change', {bubbles: true}));
        return {value: latest.value, text: latest.text};
    }""")
    out['month_selected'] = month_selected
    page.wait_for_timeout(3000)

    # Now collect ALL links
    out['all_links'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .filter(([t,h]) => h.toLowerCase().includes('.xls') || h.toLowerCase().includes('download'))
            .slice(0, 100)
    }""")

    # Also get the full visible text in the portfolio section
    out['vis'] = page.evaluate(r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /navi|fund|download|xlsx|april|may|june|portfolio/i.test(l)).slice(0, 30);
    }""")

    # Check all links, not just xls ones
    out['sample_all_links'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .filter(([t,h]) => t.length > 0)
            .slice(0, 50)
    }""")

    # Check the download section HTML
    out['download_section'] = page.evaluate("""() => {
        // Look for divs with download/portfolio content
        const divs = [...document.querySelectorAll('div, section')];
        const match = divs.find(d => {
            const t = (d.innerText || '').trim();
            return t.includes('Navi') && (t.includes('Download') || t.includes('.xlsx')) && t.length < 3000;
        });
        if (match) return match.outerHTML.substring(0, 3000);
        return null;
    }""")

    b.close()

with open('tools/probe_out/mf28_v3.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf28 v3')
print('FY selected:', out.get('fy_selected'))
print('Month select after:', json.dumps(out.get('month_select_after'), indent=2)[:600])
print('Month selected:', out.get('month_selected'))
print()
print('Download/xlsx links:', len(out.get('all_links', [])))
for l in out.get('all_links', [])[:20]:
    print('  ', l[0][:80], '|', l[1][:120])
print()
print('Visible text:')
for v in out.get('vis', [])[:20]:
    print(' ', v[:100])
print()
print('Download section HTML (first 1500):')
print((out.get('download_section') or 'None')[:1500])
