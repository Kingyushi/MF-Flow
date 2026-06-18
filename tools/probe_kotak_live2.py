"""Live probe for Kotak MF - try different approaches to bypass Radware captcha."""
import json
from playwright.sync_api import sync_playwright

# Try with stealth and different user agent
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled']
    )
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        locale='en-IN',
        viewport={'width': 1366, 'height': 768},
    )
    # Stealth init script
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en-US', 'en']});
        window.chrome = { runtime: {} };
    """)

    page = ctx.new_page()

    responses = []
    page.on('response', lambda r: responses.append({
        'url': r.url[:300], 'status': r.status, 'ct': r.headers.get('content-type','')
    }))

    print('=== Loading Kotak with stealth ===')
    page.goto('https://www.kotakmf.com/Information/forms-and-downloads', wait_until='domcontentloaded', timeout=60000)
    try:
        page.wait_for_load_state('networkidle', timeout=20000)
    except:
        pass
    page.wait_for_timeout(5000)

    print('=== Page title:', page.title())
    body = page.evaluate('() => document.body?.innerText?.substring(0, 2000) || ""')
    print('=== Body (2000):', body[:2000])

    # If captcha, try the direct API approach
    is_captcha = 'captcha' in body.lower() or 'bot' in body.lower()
    print('=== Is captcha page:', is_captcha)

    if is_captcha:
        print('\n=== Trying direct API exploration ===')
        # Try to find API endpoints from the SPA
        # Kotak may have a documented/undocumented API
        page2 = ctx.new_page()
        try:
            # Try the main site first to get cookies
            page2.goto('https://www.kotakmf.com/', wait_until='domcontentloaded', timeout=30000)
            page2.wait_for_timeout(3000)
            title2 = page2.title()
            print(f'=== Main page title: {title2}')
            is_captcha2 = 'captcha' in page2.evaluate('() => document.body?.innerText?.substring(0, 500) || ""').lower()
            print(f'=== Main page captcha: {is_captcha2}')
        except Exception as e:
            print(f'  Main page failed: {e}')
        page2.close()

    # Try using requests directly to see if the API is accessible
    print('\n=== Trying requests library for API ===')
    import requests as req
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-IN,en;q=0.9',
    }
    # Try a few potential API URLs
    api_urls = [
        'https://www.kotakmf.com/api/downloads',
        'https://www.kotakmf.com/api/portfolio',
        'https://www.kotakmf.com/api/Information/forms-and-downloads',
        'https://api.kotakmf.com/downloads',
    ]
    for url in api_urls:
        try:
            r = req.get(url, headers=headers, timeout=10, allow_redirects=True)
            print(f'  {url}: HTTP {r.status_code} ct={r.headers.get("content-type","")} len={len(r.text)}')
            if r.ok and len(r.text) < 2000:
                print(f'    Body: {r.text[:500]}')
        except Exception as e:
            print(f'  {url}: {type(e).__name__}')

    # Check if curl_cffi can bypass
    try:
        from curl_cffi import requests as creq
        print('\n=== Trying curl_cffi with chrome131 ===')
        s = creq.Session(impersonate='chrome131')
        r = s.get('https://www.kotakmf.com/Information/forms-and-downloads', timeout=30)
        print(f'  Status: {r.status_code}')
        print(f'  Title match:', 'captcha' not in r.text[:2000].lower())
        if 'captcha' not in r.text[:2000].lower() and r.ok:
            # Extract links from the HTML
            import re
            xlsx_links = re.findall(r'href=["\']([^"\']*\.xlsx[^"\']*)["\']', r.text, re.IGNORECASE)
            print(f'  xlsx links in HTML: {xlsx_links[:10]}')
            # Check for portfolio-related content
            portfolio_matches = re.findall(r'(?i)(portfoli[^\s<"\']{0,100})', r.text)
            print(f'  Portfolio mentions: {portfolio_matches[:10]}')
            # Look for any JSON data or API calls referenced
            api_refs = re.findall(r'(?i)(?:api|endpoint|fetch|ajax)[^\n]{0,200}', r.text)
            print(f'  API references: {api_refs[:5]}')
            print(f'  Body snippet: {r.text[500:2000]}')
    except ImportError:
        print('  curl_cffi not available')

    browser.close()
