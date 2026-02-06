"""Get all US stock tickers from GitHub"""
from http.server import BaseHTTPRequestHandler
import json
import requests

GITHUB_STOCKS_URL = 'https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main'

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            tickers = set()
            
            for exchange in ['nasdaq', 'nyse', 'amex']:
                url = f'{GITHUB_STOCKS_URL}/{exchange}/{exchange}_tickers.json'
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    tickers.update(response.json())
            
            result = {
                'tickers': sorted(list(tickers)),
                'count': len(tickers),
                'source': 'github/rreichel3/US-Stock-Symbols'
            }
            
            self.wfile.write(json.dumps(result).encode())
        except Exception as e:
            self.wfile.write(json.dumps({'error': str(e), 'tickers': []}).encode())
        
        return
