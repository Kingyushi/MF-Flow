"""Taurus - after year AJAX, select month using dynamic ID, check results."""
import json, re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.goto('https://taurusmutualfund.com/monthly-portfolio', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(3000)

    # Select year 2026
    print('=== Selecting year 2026 ===')
    page.select_option('select[name="field_monthly_portfolio_target_id"]', label='2026')
    page.wait_for_timeout(5000)

    # After AJAX, the select IDs change. Use name-based selector instead.
    print('=== Selecting month May ===')
    page.select_option('select[name="field_month_target_id"]', label='May')
    page.wait_for_timeout(5000)

    # Check for xlsx links
    file_links = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.innerText||'').trim().substring(0, 100),
            href: a.href?.substring(0, 250)
        })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls'))).slice(0, 30);
    }""")
    print('=== xlsx links after May:', json.dumps(file_links, indent=2))

    # Check body text
    body = page.evaluate('() => document.body?.innerText || ""')
    idx = body.find('Monthly')
    if idx >= 0:
        print('=== Content:', body[idx:idx+2000])

    # If no xlsx, maybe May has no data yet. Try April.
    if not file_links:
        print('\n=== Trying April ===')
        page.select_option('select[name="field_month_target_id"]', label='April')
        page.wait_for_timeout(5000)

        file_links2 = page.evaluate("""() => {
            return [...document.querySelectorAll('a[href]')].map(a => ({
                text: (a.innerText||'').trim().substring(0, 100),
                href: a.href?.substring(0, 250)
            })).filter(e => e.href && (e.href.includes('.xlsx') || e.href.includes('.xls'))).slice(0, 30);
        }""")
        print('=== xlsx links after April:', json.dumps(file_links2, indent=2))

        body2 = page.evaluate('() => document.body?.innerText || ""')
        idx2 = body2.find('Select')
        if idx2 >= 0:
            print('=== Content after April:', body2[idx2:idx2+3000])

    # If still no links, try checking ALL links (maybe not .xlsx extension)
    all_links = page.evaluate("""() => {
        return [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.innerText||'').trim().substring(0, 100),
            href: a.href?.substring(0, 250)
        })).filter(e => e.text.length > 0 && !e.href.includes('#') && e.href.startsWith('http')).slice(0, 40);
    }""")
    print('\n=== All visible links:', json.dumps(all_links, indent=2))

    browser.close()
