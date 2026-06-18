"""Live probe for Taurus MF - use Playwright select_option instead of JS change event."""
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

    # The year select has name="field_monthly_portfolio_target_id"
    # Values are Drupal taxonomy IDs, not years. 2026 = "567"
    year_sel = page.locator('select#edit-field-monthly-portfolio-target-id')
    month_sel = page.locator('select#edit-field-month-target-id')

    # Select year 2026 (value="567") using Playwright select_option
    print('=== Selecting year 2026 via select_option ===')
    year_sel.select_option(value='567')
    page.wait_for_timeout(5000)

    # Check if AJAX fired
    ajax = [r for r in responses if 'views/ajax' in r['url'] or 'monthly-portfolio' in r['url']]
    print('=== AJAX/monthly-portfolio responses:', json.dumps(ajax[:10], indent=2))

    body = page.evaluate('() => document.body?.innerText?.substring(0, 5000) || ""')
    print('=== Body after year select:', body[:5000])

    # Check file links
    file_links = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.innerText||'').trim().substring(0, 100),
            href: a.href?.substring(0, 250)
        })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls'))).slice(0, 30);
    }""")
    print('=== xlsx links after year:', json.dumps(file_links, indent=2))

    # Try selecting month too - let's try May (value="285")
    print('\n=== Selecting month May via select_option ===')
    month_sel.select_option(value='285')
    page.wait_for_timeout(5000)

    ajax2 = [r for r in responses if 'views/ajax' in r['url'] or 'monthly-portfolio' in r['url']]
    print('=== AJAX after month select:', json.dumps(ajax2[-5:], indent=2))

    file_links2 = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.innerText||'').trim().substring(0, 100),
            href: a.href?.substring(0, 250)
        })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls'))).slice(0, 30);
    }""")
    print('=== xlsx links after year+month:', json.dumps(file_links2, indent=2))

    body2 = page.evaluate('() => document.body?.innerText?.substring(0, 5000) || ""')
    print('=== Body after year+month:', body2[:5000])

    # Maybe the form needs submit? Check for a submit button
    submit = page.evaluate("""() => {
        const btns = document.querySelectorAll('input[type="submit"], button[type="submit"], .form-submit');
        return [...btns].map(b => ({tag: b.tagName, text: (b.value || b.innerText || '').trim(), cls: (b.className||'').substring(0, 80), id: b.id}));
    }""")
    print('=== Submit buttons:', json.dumps(submit, indent=2))

    # Try clicking submit if found
    if submit:
        print('=== Clicking submit button ===')
        page.locator('.form-submit, input[type="submit"]').first.click()
        page.wait_for_timeout(5000)

        file_links3 = page.evaluate("""() => {
            return [...document.querySelectorAll('a[href]')].map(a => ({
                text: (a.innerText||'').trim().substring(0, 100),
                href: a.href?.substring(0, 250)
            })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls'))).slice(0, 30);
        }""")
        print('=== xlsx links after submit:', json.dumps(file_links3, indent=2))

        body3 = page.evaluate('() => document.body?.innerText?.substring(0, 5000) || ""')
        print('=== Body after submit:', body3[:5000])

        all_ajax = [r for r in responses if 'views' in r['url'] or 'monthly' in r['url']]
        print('=== All views/monthly responses:', json.dumps(all_ajax[-10:], indent=2))

    browser.close()
