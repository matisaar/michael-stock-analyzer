"""Scan stocks using yfinance"""
from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime
from urllib.parse import parse_qs, urlparse
import yfinance as yf

def safe_get(info, key, default=0):
    val = info.get(key)
    return val if val is not None else default

def to_pct(val):
    if val is None:
        return 0
    val = float(val)
    if abs(val) > 10:
        return val
    return val * 100

def calculate_fair_value(info, price):
    eps = safe_get(info, 'trailingEps', 0)
    pe = safe_get(info, 'trailingPE', 0)
    forward_pe = safe_get(info, 'forwardPE', 0)
    target_price = safe_get(info, 'targetMeanPrice', 0)
    earnings_growth = info.get('earningsGrowth')
    fair_values = []
    if target_price and target_price > 0:
        fair_values.append(target_price)
    if forward_pe and forward_pe > 0 and eps and eps > 0:
        fair_values.append(eps * min(forward_pe * 1.2, 30))
    if earnings_growth and float(earnings_growth) > 0 and eps and eps > 0:
        eg = float(earnings_growth)
        gp = eg * 100 if eg < 1 else eg
        fv = eps * min(gp, 40)
        if fv > 0:
            fair_values.append(fv)
    if pe and pe > 0 and pe < 25 and price > 0:
        fair_values.append(price * 1.1)
    elif pe and pe > 25 and price > 0:
        fair_values.append(price * 0.95)
    if eps and eps > 0 and not fair_values:
        sector = safe_get(info, 'sector', '')
        if 'Technology' in str(sector):
            fair_values.append(eps * 25)
        elif 'Consumer' in str(sector):
            fair_values.append(eps * 20)
        else:
            fair_values.append(eps * 18)
    return sum(fair_values) / len(fair_values) if fair_values else price

def calculate_score(info, price, fair_value):
    score = 0
    roa = to_pct(safe_get(info, 'returnOnAssets', 0))
    roe = to_pct(safe_get(info, 'returnOnEquity', 0))
    cash = safe_get(info, 'totalCash', 0)
    debt = safe_get(info, 'totalDebt', 0)
    fcf = safe_get(info, 'freeCashflow', 0)
    pm = to_pct(safe_get(info, 'profitMargins', 0))
    ps = safe_get(info, 'priceToSalesTrailing12Months', 0)
    if roa > 10: score += 15
    elif roa > 5: score += 7
    if roe > 10: score += 15
    elif roe > 5: score += 7
    if cash > 0 and cash >= debt: score += 15
    if price > 0 and fair_value > 0:
        upside = ((fair_value - price) / price) * 100
        if upside > 30: score += 20
        elif upside > 10: score += 10
        elif upside > 0: score += 5
    if pm > 15: score += 10
    elif pm > 5: score += 5
    if ps > 0 and ps < 2: score += 10
    if fcf and fcf > 0: score += 15
    return min(score, 100)

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
            # Financially strong companies: high ROA/ROE, strong cash, solid margins
            tickers = ['AAPL', 'MSFT', 'COST', 'BRK-B', 'JNJ', 'UNH', 'V', 'MA', 'LLY', 'GOOGL', 'AVGO', 'HD']
        
        opportunities = []
        
        for symbol in tickers:
            try:
                stock = yf.Ticker(symbol)
                info = stock.info
                
                if not info:
                    # Still try to get basic price from history
                    hist = stock.history(period='5d')
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
                        opportunities.append({
                            'symbol': symbol,
                            'name': symbol,
                            'price': round(price, 2),
                            'score': 50,  # Default score
                            'upside': 0,
                        })
                    continue
                
                price = safe_get(info, 'currentPrice') or safe_get(info, 'regularMarketPrice', 0)
                if price == 0:
                    # Try history as fallback
                    hist = stock.history(period='5d')
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
                
                if price == 0:
                    continue
                
                fair_value = calculate_fair_value(info, price)
                score = calculate_score(info, price, fair_value)
                upside = ((fair_value - price) / price * 100) if price > 0 else 0
                
                opportunities.append({
                    'symbol': symbol,
                    'name': safe_get(info, 'longName') or safe_get(info, 'shortName', symbol),
                    'price': round(price, 2),
                    'score': score,
                    'upside': round(upside, 1),
                })
                
            except Exception as e:
                print(f"Error {symbol}: {e}")
                # On error, still try to add with minimal data
                try:
                    stock = yf.Ticker(symbol)
                    hist = stock.history(period='5d')
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
                        opportunities.append({
                            'symbol': symbol,
                            'name': symbol,
                            'price': round(price, 2),
                            'score': 50,
                            'upside': 0,
                        })
                except:
                    pass
        
        opportunities.sort(key=lambda x: x['score'], reverse=True)
        
        self.wfile.write(json.dumps({
            'opportunities': opportunities,
            'scanned': len(tickers),
            'timestamp': datetime.now().isoformat(),
        }).encode())
