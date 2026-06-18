"""Kotak MF - decode the SPA inline data and find the portfolio download API."""
import json
import re

from curl_cffi import requests as creq

s = creq.Session(impersonate='chrome131')
s.headers.update({
    'Accept-Language': 'en-IN,en;q=0.9',
    'Referer': 'https://www.kotakmf.com/',
})

r = s.get('https://www.kotakmf.com/Information/forms-and-downloads', timeout=30)
html = r.text

# Find the large script block with portfolio data
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
biggest = max(scripts, key=len)
print(f'=== Biggest script block: {len(biggest)} chars ===')

# Decode &q; -> " and &a; -> & in the script content
decoded = biggest.replace('&q;', '"').replace('&a;', '&').replace('&l;', '<').replace('&g;', '>').replace('&s;', "'")

# Find the portfolio section JSON
# Look for the "Portfolios" header section
portfolio_idx = decoded.find('"headerTitle":"Portfolios"')
if portfolio_idx < 0:
    portfolio_idx = decoded.find('Portfolios')
    print(f'  "Portfolios" found at idx {portfolio_idx}')

# Try to extract the portfolio section config
# The structure seems to be: headers with optionList, yearList, and Items
# Let's find the section from headerTitle:"Portfolios" backward to find the start
if portfolio_idx > 0:
    # Search backward for the opening brace of this object
    # and forward for its end
    snippet = decoded[max(0, portfolio_idx-500):portfolio_idx+5000]
    print(f'\n=== Snippet around Portfolios (5500 chars):')
    print(snippet[:5500])

# Also look for the optionId:51 (Consolidated & Fortnightly) file data
cons_idx = decoded.find('"optionId":51')
if cons_idx > 0:
    # Get context around this
    snippet = decoded[max(0, cons_idx-200):cons_idx+3000]
    print(f'\n=== Context around optionId:51 (Consolidated):')
    print(snippet[:3000])

# Try to find file URLs
file_urls = re.findall(r'"file":"([^"]+\.xlsx[^"]*)"', decoded)
if not file_urls:
    file_urls = re.findall(r'"file":"([^"]+)"', decoded)
    file_urls = [u for u in file_urls if u]  # filter empty

print(f'\n=== File URLs found: {len(file_urls)} ===')
for u in file_urls[:20]:
    print(f'  {u}')

# Also search for any XHR endpoint patterns
api_patterns = re.findall(r'"(https?://[^"]*api[^"]*)"', decoded, re.IGNORECASE)
print(f'\n=== API URL patterns: {len(api_patterns)} ===')
for u in set(api_patterns)[:10]:
    print(f'  {u}')

# Search for download URL patterns
download_patterns = re.findall(r'"(https?://[^"]*(?:download|portfolio|consolidated)[^"]*)"', decoded, re.IGNORECASE)
print(f'\n=== Download URL patterns: {len(download_patterns)} ===')
for u in set(download_patterns)[:10]:
    print(f'  {u}')
