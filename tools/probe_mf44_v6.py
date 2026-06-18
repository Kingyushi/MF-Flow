"""mf44 UTI v6 - Fetch the API directly and parse the response."""
import json
import requests

# Direct API call
url = 'https://www.utimf.com/api/get-consolidate-portfolio-disclosure'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Referer': 'https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure',
}

out = {}

# Try different year/month combos
for year in [2026, 2025]:
    for month in ['May', 'April', 'March']:
        params = {'year': year, 'month': month}
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
            data = r.json()
            key = f"{year}_{month}"
            out[key] = {
                'status': r.status_code,
                'data_preview': json.dumps(data)[:2000],
                'type': type(data).__name__
            }
            if data:
                print(f"{year} {month}: status={r.status_code} data_type={type(data).__name__}")
                print(f"  Preview: {json.dumps(data)[:500]}")
                print()
        except Exception as e:
            out[f"{year}_{month}"] = {'error': str(e)}

# Also try to get year/month list
try:
    r = requests.get('https://www.utimf.com/api/get-consolidate-portfolio-disclosure-years',
                     headers=headers, timeout=30)
    out['years_api'] = {'status': r.status_code, 'body': r.text[:1000]}
    print('Years API:', r.status_code, r.text[:500])
except Exception as e:
    out['years_api'] = {'error': str(e)}

with open('tools/probe_out/mf44_v6.json', 'w') as f:
    json.dump(out, f, indent=2)
print('DONE')
