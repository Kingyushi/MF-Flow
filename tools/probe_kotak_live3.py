"""Kotak MF - use curl_cffi to get the SPA HTML, extract inline JSON config for Portfolios."""
import json
import re

try:
    from curl_cffi import requests as creq
except ImportError:
    print('curl_cffi not available')
    exit(1)

s = creq.Session(impersonate='chrome131')
s.headers.update({
    'Accept-Language': 'en-IN,en;q=0.9',
})

# Get the main page first to warm cookies
print('=== Warming up ===')
r = s.get('https://www.kotakmf.com/', timeout=30)
print(f'  Main page: HTTP {r.status_code}')

# Now get the downloads page
print('\n=== Fetching forms-and-downloads ===')
r = s.get('https://www.kotakmf.com/Information/forms-and-downloads', timeout=30)
print(f'  Status: {r.status_code}')
print(f'  Content-Type: {r.headers.get("content-type")}')

html = r.text

# Look for inline JSON data in script tags
# Angular apps often embed state in script tags
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
print(f'\n=== Found {len(scripts)} script blocks ===')

# Look for the JSON data about portfolios
for i, script in enumerate(scripts):
    if 'Portfolio' in script or 'portfolio' in script or 'Consolidated' in script:
        # Find JSON-like structures
        print(f'\n=== Script block {i} contains portfolio data (len={len(script)}):')
        # Try to find the state transfer data
        if 'transferState' in script or 'window.__' in script or 'JSON.parse' in script:
            print(f'  Has transfer state/window global')

        # Find the relevant portion
        idx = script.find('Consolidated')
        if idx > 0:
            snippet = script[max(0, idx-300):idx+500]
            print(f'  Around "Consolidated": ...{snippet}...')

        idx = script.find('Portfolio')
        if idx > 0:
            snippet = script[max(0, idx-200):idx+400]
            print(f'  Around first "Portfolio": ...{snippet}...')

# Look for Angular transfer state
transfer_match = re.search(r'<script[^>]*id="serverApp-state"[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
if not transfer_match:
    transfer_match = re.search(r'<script[^>]*type="application/json"[^>]*id="serverApp-state"[^>]*>(.*?)</script>', html, re.DOTALL)

if transfer_match:
    print('\n=== Found Angular transfer state ===')
    state_json = transfer_match.group(1)
    print(f'  Length: {len(state_json)}')
    # Decode HTML entities
    state_json = state_json.replace('&q;', '"').replace('&a;', '&').replace('&l;', '<').replace('&g;', '>')
    try:
        state = json.loads(state_json)
        # Find portfolio-related keys
        for key in state:
            val = str(state[key])
            if 'portfolio' in val.lower() or 'consolidated' in val.lower():
                print(f'\n  Key: {key[:200]}')
                if isinstance(state[key], dict):
                    print(f'  Value snippet: {json.dumps(state[key], indent=2)[:2000]}')
                elif isinstance(state[key], str):
                    try:
                        inner = json.loads(state[key])
                        print(f'  Parsed inner JSON: {json.dumps(inner, indent=2)[:2000]}')
                    except:
                        print(f'  Value: {state[key][:500]}')
                else:
                    print(f'  Value: {str(state[key])[:500]}')
    except json.JSONDecodeError as e:
        print(f'  JSON parse failed: {e}')
        # Try finding portfolio data directly in the raw state
        idx = state_json.find('Consolidated')
        if idx > 0:
            print(f'  Raw around "Consolidated": {state_json[max(0,idx-200):idx+500]}')
else:
    print('\n=== No Angular transfer state found ===')
    # Look for any JSON-like data in page
    json_matches = re.findall(r'\{["\'](?:portfolio|Portfolio|Consolidated)[^}]{100,2000}\}', html)
    print(f'  Found {len(json_matches)} portfolio JSON matches')
    for m in json_matches[:3]:
        print(f'  Match: {m[:500]}')
