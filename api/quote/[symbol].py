"""Get stock quote for a specific symbol"""
from http.server import BaseHTTPRequestHandler
import json
import os
import requests

TRADIER_API_KEY = os.environ.get('TRADIER_API_KEY', '')
TRADIER_BASE_URL = 'https://sandbox.tradier.com/v1'

FMP_API_KEY = os.environ.get('FMP_API_KEY', '')
FMP_BASE_URL = 'https://financialmodelingprep.com/api/v3'

def tradier_request(endpoint, params=None):
    if not TRADIER_API_KEY:
        return None
    headers = {
        'Authorization': f'Bearer {TRADIER_API_KEY}',
        'Accept': 'application/json'
    }
    try:
        url = f'{TRADIER_BASE_URL}{endpoint}'
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Tradier API error: {e}")
    return None

def fmp_request(endpoint, params=None):
    if not FMP_API_KEY:
        return None
    try:
        url = f'{FMP_BASE_URL}{endpoint}'
        params = params or {}
        params['apikey'] = FMP_API_KEY
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"FMP API error: {e}")
    return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Extract symbol from path: /api/quote/AAPL -> AAPL
        symbol = self.path.split('/')[-1].split('?')[0].upper()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        result = {'symbol': symbol}
        
        # Try Tradier first
        if TRADIER_API_KEY:
            data = tradier_request('/markets/quotes', {'symbols': symbol})
            if data and 'quotes' in data and 'quote' in data['quotes']:
                q = data['quotes']['quote']
                result.update({
                    'price': q.get('last', 0),
                    'change': q.get('change', 0),
                    'change_percent': q.get('change_percentage', 0),
                    'volume': q.get('volume', 0),
                    'high': q.get('high', 0),
                    'low': q.get('low', 0),
                    'open': q.get('open', 0),
                    'prev_close': q.get('prevclose', 0),
                    'week_52_high': q.get('week_52_high', 0),
                    'week_52_low': q.get('week_52_low', 0),
                    'name': q.get('description', symbol),
                    'source': 'tradier'
                })
                self.wfile.write(json.dumps(result).encode())
                return
        
        # Fallback to FMP
        if FMP_API_KEY:
            data = fmp_request(f'/quote/{symbol}')
            if data and len(data) > 0:
                q = data[0]
                result.update({
                    'price': q.get('price', 0),
                    'change': q.get('change', 0),
                    'change_percent': q.get('changesPercentage', 0),
                    'volume': q.get('volume', 0),
                    'high': q.get('dayHigh', 0),
                    'low': q.get('dayLow', 0),
                    'open': q.get('open', 0),
                    'prev_close': q.get('previousClose', 0),
                    'week_52_high': q.get('yearHigh', 0),
                    'week_52_low': q.get('yearLow', 0),
                    'name': q.get('name', symbol),
                    'market_cap': q.get('marketCap', 0),
                    'pe': q.get('pe', 0),
                    'eps': q.get('eps', 0),
                    'source': 'fmp'
                })
                self.wfile.write(json.dumps(result).encode())
                return
        
        result['error'] = 'No API key configured'
        self.wfile.write(json.dumps(result).encode())
        return
