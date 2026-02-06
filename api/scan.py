"""Scan stocks using yfinance"""
from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime
from urllib.parse import parse_qs, urlparse
import yfinance as yf

def safe_get(info, key, default=0):
    val = info.get(key)
    return val if val is not None else default

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        # Parse params
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        symbols_param = params.get('symbols', [''])[0]
        
        if symbols_param:
            tickers = [s.strip().upper() for s in symbols_param.split(',')][:15]
        else:
            tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM', 'V', 'WMT']
        
        opportunities = []
        
        for symbol in tickers:
            try:
                stock = yf.Ticker(symbol)
                info = stock.info
                
                if not info:
                    continue
                
                price = safe_get(info, 'currentPrice') or safe_get(info, 'regularMarketPrice', 0)
                if price == 0:
                    continue
                
                # Quick score calculation
                score = 30
                pe = safe_get(info, 'trailingPE', 0)
                roa = safe_get(info, 'returnOnAssets', 0)
                roe = safe_get(info, 'returnOnEquity', 0)
                fcf = safe_get(info, 'freeCashflow', 0)
                
                if pe > 0 and pe < 20:
                    score += 15
                if roa and roa > 0.1:
                    score += 15
                if roe and roe > 0.1:
                    score += 15
                if fcf and fcf > 0:
                    score += 15
                
                # Upside estimate
                eps = safe_get(info, 'trailingEps', 0)
                if eps and eps > 0:
                    fair_value = eps * 15
                    upside = ((fair_value - price) / price) * 100
                elif pe and pe > 0 and pe < 15:
                    upside = ((15 - pe) / pe) * 100
                else:
                    upside = 10
                
                opportunities.append({
                    'symbol': symbol,
                    'name': safe_get(info, 'longName') or safe_get(info, 'shortName', symbol),
                    'price': round(price, 2),
                    'score': min(score, 100),
                    'upside': round(upside, 1),
                })
                
            except Exception as e:
                print(f"Error {symbol}: {e}")
        
        opportunities.sort(key=lambda x: x['score'], reverse=True)
        
        self.wfile.write(json.dumps({
            'opportunities': opportunities,
            'scanned': len(tickers),
            'timestamp': datetime.now().isoformat(),
        }).encode())
