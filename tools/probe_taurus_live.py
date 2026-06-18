"""Live probe for Taurus MF monthly-portfolio page."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    responses = []
    page.on('response', lambda r: responses.append({
        'url': r.url[:200], 'status': r.status, 'ct': r.headers.get('content-type','')
    }))

    print('=== Loading Taurus monthly-portfolio ===')
    page.goto('https://taurusmutualfund.com/monthly-portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(3000)

    print('=== Page title:', page.title())

    body_text = page.evaluate('() => document.body?.innerText?.substring(0, 3000) || ""')
    print('=== Body text (first 3000):', body_text[:3000])

    selects = page.evaluate("""() => {
        return [...document.querySelectorAll('select')].map(sel => ({
            name: sel.name, id: sel.id, cls: sel.className,
            options: [...sel.options].map(o => ({text: o.text.trim(), value: o.value}))
        }));
    }""")
    print('=== Selects:', json.dumps(selects, indent=2))

    links_before = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.innerText||'').trim().substring(0, 100),
            href: a.href?.substring(0, 200)
        })).filter(e => e.text.length > 0 && (e.href.includes('.xlsx') || e.href.includes('.xls') || e.href.includes('.pdf'))).slice(0, 30);
    }""")
    print('=== File links before year select:', json.dumps(links_before, indent=2))

    # Select latest year
    year_result = page.evaluate(r"""() => {
        const sel = document.querySelector('select');
        if (!sel) return {error: 'no select found'};
        const opts = [...sel.options].filter(o => /^\d{4}$/.test(o.value.trim()));
        if (!opts.length) return {error: 'no year options', all_opts: [...sel.options].map(o => ({text: o.text, value: o.value}))};
        opts.sort((a, b) => parseInt(b.value) - parseInt(a.value));
        const latest = opts[0].value;
        sel.value = latest;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        return {selected: latest};
    }""")
    print('=== Year selection result:', json.dumps(year_result))

    page.wait_for_timeout(5000)

    links_after = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.innerText||'').trim().substring(0, 100),
            href: a.href?.substring(0, 200)
        })).filter(e => e.text.length > 0).slice(0, 60);
    }""")
    print('=== All links after year select:', json.dumps(links_after, indent=2))

    file_links_after = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.innerText||'').trim().substring(0, 100),
            href: a.href?.substring(0, 200)
        })).filter(e => e.text.length > 0 && (e.href.includes('.xlsx') || e.href.includes('.xls') || e.href.includes('.pdf'))).slice(0, 30);
    }""")
    print('=== File links after year select:', json.dumps(file_links_after, indent=2))

    ajax_xhrs = [r for r in responses if 'views/ajax' in r['url'] or 'json' in r['ct'].lower()]
    print('=== AJAX responses:', json.dumps(ajax_xhrs[:10], indent=2))

    # Check body text after
    body_after = page.evaluate('() => document.body?.innerText?.substring(0, 5000) || ""')
    print('=== Body after year select (first 5000):', body_after[:5000])

    browser.close()
