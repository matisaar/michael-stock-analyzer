from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Extract query from path
        path_parts = self.path.split('/')
        query = path_parts[-1].split('?')[0] if len(path_parts) > 0 else ''
        query = urllib.parse.unquote(query)
        
        if not query or len(query) < 1:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Query required'}).encode())
            return
        
        try:
            results = search_yahoo(query)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'query': query,
                'results': results
            }).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

def search_yahoo(query):
    """Search Yahoo Finance for tickers matching the query"""
    results = []
    
    # Yahoo Finance search API
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(query)}&quotesCount=10&newsCount=0&enableFuzzyQuery=true&quotesQueryId=tss_match_phrase_query"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            quotes = data.get('quotes', [])
            
            for quote in quotes:
                # Only include stocks (not crypto, futures, etc.)
                quote_type = quote.get('quoteType', '')
                if quote_type in ['EQUITY', 'ETF']:
                    symbol = quote.get('symbol', '')
                    name = quote.get('shortname') or quote.get('longname') or symbol
                    exchange = quote.get('exchange', '')
                    
                    # Skip non-US exchanges for simplicity (user can still type full symbol)
                    # But include major ones
                    if symbol and not '.' in symbol:  # US stocks don't have dots
                        results.append({
                            'symbol': symbol,
                            'name': name,
                            'exchange': exchange,
                            'type': quote_type
                        })
                    elif symbol:
                        # Include international but mark them
                        results.append({
                            'symbol': symbol,
                            'name': name,
                            'exchange': exchange,
                            'type': quote_type
                        })
    except Exception as e:
        # If Yahoo search fails, return empty
        print(f"Search error: {e}")
    
    return results[:8]  # Limit to 8 results
