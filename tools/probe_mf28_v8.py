"""mf28 Navi v8 - Fetch the WP REST API to get document list."""
import json
import requests

url = 'https://navi.com/wp-json/nv/v1/documents'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Referer': 'https://navi.com/mutual-fund/downloads/portfolio',
}

r = requests.get(url, headers=headers, timeout=30)
data = r.json()
print(f'Status: {r.status_code}')
print(f'Success: {data.get("success")}')
print(f'Total items: {len(data.get("data", []))}')
print()

# Show all items
items = data.get('data', [])
for i, item in enumerate(items[:30]):
    print(f'{i}: {item.get("title", "")} -> {item.get("url", "")[:120]}')

with open('tools/probe_out/mf28_api.json', 'w') as f:
    json.dump(data, f, indent=2)
