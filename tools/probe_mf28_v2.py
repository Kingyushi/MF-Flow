"""Deeper probe for mf28 Navi - check what selects & links look like."""
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

    # Check the selects - these are what we need for year/month selection
    out['selects'] = page.evaluate("""() => {
        return [...document.querySelectorAll('select')].map(s => ({
            id: s.id, name: s.name, cls: s.className.substring(0,200),
            label: s.closest('label') ? s.closest('label').innerText.trim() : '',
            parent_text: s.parentElement ? s.parentElement.innerText.trim().substring(0, 100) : '',
            options: [...s.options].map(o => ({value: o.value, text: o.text.trim()})).slice(0, 20)
        }))
    }""")

    # Check all links - first 10 with their hrefs
    out['sample_links'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .filter(([t,h]) => t.length > 0)
            .slice(0, 20)
    }""")

    # Find the visible text on the page related to portfolio tab
    out['vis'] = page.evaluate(r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /portfolio|monthly|fortnightly|half yearly|quarterly|overlap|download|year|month/i.test(l)).slice(0, 30);
    }""")

    # Try to find the "Portfolio" tab/link and click it
    portfolio_click = page.evaluate("""() => {
        const els = [...document.querySelectorAll('a, button, [role="tab"], div')];
        const port = els.find(e => {
            const t = (e.innerText || '').trim();
            return t === 'Portfolio' || t === 'portfolio';
        });
        if (port) { port.click(); return port.innerText.trim(); }
        return null;
    }""")
    out['portfolio_click'] = portfolio_click
    page.wait_for_timeout(3000)

    # Re-check selects and visible text
    out['selects_after_portfolio'] = page.evaluate("""() => {
        return [...document.querySelectorAll('select')].map(s => ({
            id: s.id, name: s.name,
            parent_text: s.parentElement ? s.parentElement.innerText.trim().substring(0, 100) : '',
            options: [...s.options].map(o => ({value: o.value, text: o.text.trim()})).slice(0, 20)
        }))
    }""")

    out['vis_after_portfolio'] = page.evaluate(r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').filter(l => l.trim().length > 0);
        return lines.filter(l => /portfolio|monthly|fortnightly|half yearly|quarterly|overlap|download|year|month/i.test(l)).slice(0, 30);
    }""")

    # Check for the select with year options - try to interact with it
    year_info = page.evaluate(r"""() => {
        const selects = [...document.querySelectorAll('select')];
        for (const s of selects) {
            const opts = [...s.options].map(o => o.text.trim());
            if (opts.some(o => /^20\d{2}$/.test(o))) {
                return {id: s.id, name: s.name, options: opts, parent: s.parentElement.innerText.trim().substring(0,200)};
            }
        }
        return null;
    }""")
    out['year_select'] = year_info

    # If found year select, try to select latest year
    if year_info:
        # Select the latest year
        page.evaluate("""(selId) => {
            const s = document.getElementById(selId) || document.querySelector('select[name="' + selId + '"]');
            if (!s) return;
            const opts = [...s.options].filter(o => /^20\\d{2}$/.test(o.value.trim()));
            const latest = opts.sort((a,b) => parseInt(b.value) - parseInt(a.value))[0];
            if (latest) {
                s.value = latest.value;
                s.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }""", year_info.get('id') or year_info.get('name'))
        page.wait_for_timeout(3000)

        # Check for month select now
        month_info = page.evaluate(r"""() => {
            const selects = [...document.querySelectorAll('select')];
            for (const s of selects) {
                const opts = [...s.options].map(o => o.text.trim().toLowerCase());
                if (opts.some(o => ['january','february','march','april','may','june','july','august','september','october','november','december'].includes(o))) {
                    return {id: s.id, name: s.name, options: [...s.options].map(o => ({val: o.value, text: o.text.trim()}))};
                }
            }
            return null;
        }""")
        out['month_select'] = month_info

        if month_info:
            # Select latest month
            page.evaluate("""(selId) => {
                const months = ['january','february','march','april','may','june','july','august','september','october','november','december'];
                const s = document.getElementById(selId) || document.querySelector('select[name="' + selId + '"]');
                if (!s) return;
                const opts = [...s.options].filter(o => {
                    const t = o.text.trim().toLowerCase();
                    return months.includes(t);
                });
                if (opts.length > 0) {
                    const last = opts[opts.length - 1];
                    s.value = last.value;
                    s.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }""", month_info.get('id') or month_info.get('name'))
            page.wait_for_timeout(3000)

    # Now check links again
    out['links_after_selects'] = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => [(a.innerText || a.textContent || '').trim().substring(0,200), a.href])
            .filter(([t,h]) => h.toLowerCase().includes('.xls') || h.toLowerCase().includes('.xlsx'))
            .slice(0, 50)
    }""")

    # Also check for download buttons
    out['download_buttons'] = page.evaluate("""() => {
        const els = [...document.querySelectorAll('a, button')];
        return els.filter(e => /download/i.test((e.innerText||'').trim()) || e.getAttribute('download') !== null)
            .map(e => ({tag: e.tagName, text: (e.innerText||'').trim().substring(0,100), href: (e.href||'').substring(0,200), download: e.getAttribute('download')}))
            .slice(0, 20);
    }""")

    b.close()

with open('tools/probe_out/mf28_v2.json', 'w') as f:
    json.dump(out, f, indent=2, default=str)

print('DONE mf28 v2')
print('Selects:', json.dumps(out['selects'], indent=2)[:2000])
print()
print('Year select:', json.dumps(out.get('year_select'), indent=2)[:500])
print('Month select:', json.dumps(out.get('month_select'), indent=2)[:500])
print()
print('XLSX links after selects:', len(out.get('links_after_selects', [])))
for l in out.get('links_after_selects', [])[:20]:
    print('  ', l[0][:80], '|', l[1][:120])
print()
print('Download buttons:', json.dumps(out.get('download_buttons', []), indent=2)[:500])
print()
print('Visible text:', json.dumps(out.get('vis', []), indent=2)[:500])
