"""Watchlist API - CRUD operations with Supabase"""
from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse

SUPABASE_URL = 'https://uhmoslyaavuswzlqeyml.supabase.co'
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

def supabase_request(method, path, body=None, params=None):
    """Make a request to Supabase REST API."""
    url = SUPABASE_URL + '/rest/v1/' + path
    if params:
        url += '?' + urllib.parse.urlencode(params, doseq=True)

    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': 'Bearer ' + SUPABASE_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"Supabase error: {e.code} - {error_body}")
        return {'error': error_body, 'status': e.code}
    except Exception as e:
        print(f"Supabase connection error: {e}")
        return {'error': str(e), 'status': 0}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """List all watchlist items."""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        result = supabase_request('GET', 'watchlist', params={
            'select': '*',
            'order': 'added_at.desc',
        })

        if isinstance(result, dict) and 'error' in result:
            self.wfile.write(json.dumps({'error': 'Failed to load watchlist', 'detail': result}).encode())
        else:
            self.wfile.write(json.dumps({'watchlist': result or []}).encode())

    def do_POST(self):
        """Add a stock to watchlist."""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except Exception:
            body = {}

        symbol = body.get('symbol', '').upper().strip()
        if not symbol:
            self.wfile.write(json.dumps({'error': 'Symbol required'}).encode())
            return

        row = {
            'symbol': symbol,
            'name': body.get('name', symbol),
            'sector': body.get('sector', ''),
            'industry': body.get('industry', ''),
            'score': body.get('score', 0),
            'price_at_save': body.get('price', 0),
        }

        result = supabase_request('POST', 'watchlist', body=row)

        if isinstance(result, list) and len(result) > 0:
            self.wfile.write(json.dumps({'success': True, 'item': result[0]}).encode())
        elif isinstance(result, dict) and 'error' in result:
            # Check if duplicate
            if '23505' in str(result.get('error', '')):
                self.wfile.write(json.dumps({'error': 'Already in watchlist'}).encode())
            else:
                self.wfile.write(json.dumps({'error': 'Failed to save', 'detail': result}).encode())
        else:
            self.wfile.write(json.dumps({'error': 'Unexpected response'}).encode())

    def do_DELETE(self):
        """Remove a stock from watchlist."""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # Get symbol from query params
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        symbol = params.get('symbol', [''])[0].upper().strip()

        if not symbol:
            self.wfile.write(json.dumps({'error': 'Symbol required'}).encode())
            return

        result = supabase_request('DELETE', 'watchlist', params={
            'symbol': 'eq.' + symbol,
        })

        self.wfile.write(json.dumps({'success': True, 'removed': symbol}).encode())
