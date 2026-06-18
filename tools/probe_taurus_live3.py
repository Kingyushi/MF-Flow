"""Taurus MF - select year 2026, then re-locate month, then try April."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    responses = []
    page.on('response', lambda r: responses.append({
        'url': r.url[:300], 'status': r.status, 'ct': r.headers.get('content-type','')
    }))

    page.goto('https://taurusmutualfund.com/monthly-portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(3000)

    # Year select: select by label text "2026"
    print('=== Selecting year 2026 by label ===')
    page.select_option('select#edit-field-monthly-portfolio-target-id', label='2026')
    page.wait_for_timeout(5000)

    # Check if month select still exists after AJAX
    month_exists = page.evaluate("""() => {
        const sel = document.querySelector('select#edit-field-month-target-id');
        if (!sel) return {exists: false};
        return {exists: true, options: [...sel.options].map(o => ({text: o.text.trim(), value: o.value}))};
    }""")
    print('=== Month select after year AJAX:', json.dumps(month_exists, indent=2))

    # Select month - try May first, then April
    if month_exists.get('exists'):
        print('\n=== Selecting month May ===')
        page.select_option('select#edit-field-month-target-id', label='May')
        page.wait_for_timeout(5000)

        # Check for file links
        file_links = page.evaluate("""() => {
            return [...document.querySelectorAll('a[href]')].map(a => ({
                text: (a.innerText||'').trim().substring(0, 100),
                href: a.href?.substring(0, 250)
            })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls'))).slice(0, 30);
        }""")
        print('=== xlsx links after May:', json.dumps(file_links, indent=2))

        body = page.evaluate('() => document.body?.innerText?.substring(0, 5000) || ""')
        # Find the content area
        idx = body.find('Monthly')
        if idx >= 0:
            print('=== Content around Monthly:', body[idx:idx+2000])

        # If no xlsx links, maybe need submit button?
        if not file_links:
            submit = page.evaluate("""() => {
                const btns = document.querySelectorAll('input[type="submit"], button[type="submit"], .form-submit, .views-submit-button input');
                return [...btns].map(b => ({tag: b.tagName, text: (b.value || b.innerText || '').trim(), id: b.id, name: b.name}));
            }""")
            print('=== Submit buttons:', json.dumps(submit, indent=2))

            if submit:
                print('=== Clicking submit ===')
                try:
                    page.click('input[type="submit"], .form-submit', timeout=5000)
                    page.wait_for_timeout(5000)
                except:
                    page.evaluate("""() => {
                        const btn = document.querySelector('input[type="submit"], .form-submit');
                        if (btn) btn.click();
                    }""")
                    page.wait_for_timeout(5000)

                file_links2 = page.evaluate("""() => {
                    return [...document.querySelectorAll('a[href]')].map(a => ({
                        text: (a.innerText||'').trim().substring(0, 100),
                        href: a.href?.substring(0, 250)
                    })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls'))).slice(0, 30);
                }""")
                print('=== xlsx links after submit:', json.dumps(file_links2, indent=2))

                body2 = page.evaluate('() => document.body?.innerText?.substring(0, 5000) || ""')
                print('=== Body after submit:', body2[:5000])

        # Try April
        if not file_links:
            print('\n=== Trying April instead ===')
            # Re-select year in case page was reloaded
            page.select_option('select#edit-field-monthly-portfolio-target-id', label='2026')
            page.wait_for_timeout(3000)
            page.select_option('select#edit-field-month-target-id', label='April')
            page.wait_for_timeout(5000)

            file_links3 = page.evaluate("""() => {
                return [...document.querySelectorAll('a[href]')].map(a => ({
                    text: (a.innerText||'').trim().substring(0, 100),
                    href: a.href?.substring(0, 250)
                })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls'))).slice(0, 30);
            }""")
            print('=== xlsx links after April:', json.dumps(file_links3, indent=2))

    # Check all AJAX responses
    ajax = [r for r in responses if 'views/ajax' in r['url']]
    print('\n=== All views/ajax responses:', len(ajax))
    for r in ajax:
        print(f'  {r["status"]} {r["url"][:200]}')

    browser.close()
