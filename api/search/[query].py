"""Search for stocks by company name or partial ticker using yfinance"""
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import traceback

def search_with_yfinance(query):
    """Use yfinance.Search to find stocks matching a query. US exchanges only."""
    import yfinance as yf
    results = []
    US_EXCHANGES = {'NMS', 'NYQ', 'NGM', 'NCM', 'ASE', 'PCX', 'BTS', 'NAS', 'NYSE', 'NASDAQ', 'AMEX', 'ARCA', 'BATS'}
    try:
        search = yf.Search(query, max_results=15, news_count=0)
        quotes = search.quotes if hasattr(search, 'quotes') else []
        for q in quotes:
            quote_type = q.get('quoteType', '')
            exchange = q.get('exchange', '')
            symbol = q.get('symbol', '')
            # Skip non-equity/ETF, foreign exchanges, and tickers with dots (e.g. 398.F)
            if quote_type not in ('EQUITY', 'ETF'):
                continue
            if exchange and exchange not in US_EXCHANGES:
                continue
            if '.' in symbol:
                continue
            results.append({
                'symbol': symbol,
                'name': q.get('shortname') or q.get('longname') or symbol,
                'exchange': exchange,
                'type': quote_type,
            })
    except Exception as e:
        print(f"yf.Search error: {e}")
        traceback.print_exc()
    return results

def search_with_ticker_validation(query):
    """Fallback: try the query as a direct ticker via yfinance.Ticker."""
    import yfinance as yf
    results = []
    try:
        t = yf.Ticker(query.upper())
        info = t.info
        if info and (info.get('regularMarketPrice') or info.get('currentPrice')):
            results.append({
                'symbol': info.get('symbol', query.upper()),
                'name': info.get('longName') or info.get('shortName') or query.upper(),
                'exchange': info.get('exchange', ''),
                'type': 'EQUITY',
            })
    except Exception:
        pass
    return results

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Extract query from path: /api/search/some%20query
        path_parts = self.path.split('/')
        raw_query = path_parts[-1].split('?')[0] if len(path_parts) > 0 else ''
        query = urllib.parse.unquote(raw_query).strip()

        if not query:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Query required'}).encode())
            return

        try:
            # Primary: use yfinance Search
            results = search_with_yfinance(query)

            # Fallback: if no results, try as a direct ticker
            if not results:
                results = search_with_ticker_validation(query)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'query': query,
                'results': results[:8],
            }).encode())

        except Exception as e:
            traceback.print_exc()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'query': query,
                'results': [],
                'debug_error': str(e),
            }).encode())
