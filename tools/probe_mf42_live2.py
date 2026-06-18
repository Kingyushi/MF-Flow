"""Probe Trust MF API - capture actual request details and response bodies."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()

    api_calls = []

    def on_request(request):
        if "GetData" in request.url:
            api_calls.append({
                "url": request.url,
                "method": request.method,
                "post_data": request.post_data,
                "headers": {k: v for k, v in request.headers.items() if k.lower() in ('content-type', 'accept')},
            })

    responses_data = []

    def on_response(response):
        if "GetData" in response.url:
            try:
                body = response.json()
                responses_data.append({
                    "url": response.url,
                    "status": response.status,
                    "body": body
                })
            except:
                try:
                    responses_data.append({
                        "url": response.url,
                        "status": response.status,
                        "body_text": response.text()[:500]
                    })
                except:
                    pass

    page.on("request", on_request)
    page.on("response", on_response)

    page.goto("https://www.trustmf.com/disclosures?activeTab=portfolio-disclosures", timeout=30000)
    page.wait_for_timeout(8000)

    print(f"Captured {len(api_calls)} GetData requests:")
    for i, call in enumerate(api_calls):
        print(f"\n--- Request {i+1} ---")
        print(f"  Method: {call['method']}")
        print(f"  URL: {call['url']}")
        print(f"  Headers: {call['headers']}")
        if call['post_data']:
            print(f"  Post data: {call['post_data'][:300]}")

    print(f"\n\nCaptured {len(responses_data)} GetData responses:")
    for i, resp in enumerate(responses_data):
        print(f"\n--- Response {i+1} (status={resp['status']}) ---")
        body = resp.get('body')
        if body:
            if isinstance(body, dict):
                print(f"  Keys: {list(body.keys())}")
                for k, v in body.items():
                    if isinstance(v, list):
                        print(f"  {k}: list[{len(v)}]")
                        if v and isinstance(v[0], dict):
                            print(f"    First item keys: {sorted(v[0].keys())}")
                            # Check if any have "monthly" or "portfolio" in title
                            monthly = [x for x in v if 'monthly' in (x.get('title','') + x.get('matching_slugs','')).lower()]
                            print(f"    Items with 'monthly': {len(monthly)}")
                            if monthly:
                                print(f"    First monthly item: {json.dumps(monthly[0], indent=2)[:400]}")
                    else:
                        print(f"  {k}: {type(v).__name__} = {str(v)[:100]}")
            elif isinstance(body, list):
                print(f"  Array[{len(body)}]")
        else:
            print(f"  Text: {resp.get('body_text', '?')[:200]}")

    browser.close()
