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
    """Proportional scoring - points scale with how well each metric performs"""
    score = 0
    roa = to_pct(safe_get(info, 'returnOnAssets', 0))
    roe = to_pct(safe_get(info, 'returnOnEquity', 0))
    cash = safe_get(info, 'totalCash', 0)
    debt = safe_get(info, 'totalDebt', 0)
    fcf = safe_get(info, 'freeCashflow', 0)
    pm = to_pct(safe_get(info, 'profitMargins', 0))
    ps = safe_get(info, 'priceToSalesTrailing12Months', 0)
    market_cap = safe_get(info, 'marketCap', 0)
    
    # ROA (max 15) - proportional: -5% -> 0pts, 15% -> 15pts
    score += max(0, min(15, int((roa + 5) * 15 / 20)))
    
    # ROE (max 15) - proportional
    score += max(0, min(15, int((roe + 5) * 15 / 20)))
    
    # Cash vs Debt (max 15) - proportional based on coverage
    if debt > 0:
        coverage = cash / debt
        score += max(0, min(15, int(coverage * 7.5)))
    elif cash > 0:
        score += 15
    
    # Fair value upside (max 20) - proportional
    if price > 0 and fair_value > 0:
        upside = ((fair_value - price) / price) * 100
        score += max(0, min(20, int(upside * 0.4)))
    
    # Profit margin (max 10) - proportional: -5% -> 0pts, 20% -> 10pts
    score += max(0, min(10, int((pm + 5) * 10 / 25)))
    
    # P/S ratio (max 10) - lower is better: <1 = 10pts, 5+ = 0pts
    if ps > 0:
        score += max(0, min(10, int((5 - ps) * 2.5)))
    
    # FCF (max 15) - proportional based on FCF yield
    if fcf > 0 and market_cap > 0:
        fcf_yield = (fcf / market_cap) * 100
        score += max(0, min(15, int(fcf_yield * 1.5)))
    elif fcf > 0:
        score += 10
    
    return min(score, 100)


def calculate_score_value(info, price, fair_value):
    """Deep Value scoring - emphasizes low multiples and dividends"""
    score = 0
    pe = safe_get(info, 'trailingPE', 0)
    pb = safe_get(info, 'priceToBook', 0)
    div_yield = to_pct(safe_get(info, 'dividendYield', 0))
    debt_equity = safe_get(info, 'debtToEquity', 0)
    fcf = safe_get(info, 'freeCashflow', 0)
    market_cap = safe_get(info, 'marketCap', 0)
    
    # P/E (max 25) - lower is better: PE < 10 = 25pts, PE > 30 = 0
    if pe > 0: score += max(0, min(25, int((30 - pe) * 1.25)))
    else: score += 10  # No PE data = middle score
    
    # P/B (max 20) - lower is better: PB < 1 = 20pts, PB > 3 = 0
    if pb > 0: score += max(0, min(20, int((3 - pb) * 10)))
    
    # Dividend yield (max 20)
    score += max(0, min(20, int(div_yield * 5)))
    
    # Low debt (max 15) - D/E < 0.5 = 15pts, D/E > 2 = 0
    if debt_equity >= 0: score += max(0, min(15, int((2 - debt_equity) * 10)))
    else: score += 10
    
    # FCF yield (max 20)
    if fcf > 0 and market_cap > 0:
        fcf_yield = (fcf / market_cap) * 100
        score += max(0, min(20, int(fcf_yield * 2)))
    
    return min(score, 100)


def calculate_score_growth(info, price, fair_value):
    """Growth scoring - emphasizes revenue/earnings growth"""
    score = 0
    rev_growth = to_pct(safe_get(info, 'revenueGrowth', 0))
    earn_growth = to_pct(safe_get(info, 'earningsGrowth', 0))
    eps_growth = to_pct(safe_get(info, 'earningsQuarterlyGrowth', 0))
    roe = to_pct(safe_get(info, 'returnOnEquity', 0))
    pm = to_pct(safe_get(info, 'profitMargins', 0))
    
    # Revenue growth (max 30)
    score += max(0, min(30, int(rev_growth * 1.5)))
    
    # Earnings growth (max 25)
    if earn_growth: score += max(0, min(25, int(earn_growth)))
    elif eps_growth: score += max(0, min(25, int(eps_growth)))
    
    # ROE (max 20) - high returns on equity
    score += max(0, min(20, int(roe)))
    
    # Profit margin (max 15) - ability to scale profitably
    score += max(0, min(15, int(pm * 0.75)))
    
    # Momentum bonus (max 10) - if price is up
    if fair_value > price: score += 10
    
    return min(score, 100)


def calculate_score_quality(info, price, fair_value):
    """Quality + Moat scoring - emphasizes competitive advantages"""
    score = 0
    roic = to_pct(safe_get(info, 'returnOnEquity', 0))  # Proxy for ROIC
    roa = to_pct(safe_get(info, 'returnOnAssets', 0))
    pm = to_pct(safe_get(info, 'profitMargins', 0))
    gm = to_pct(safe_get(info, 'grossMargins', 0))
    fcf = safe_get(info, 'freeCashflow', 0)
    market_cap = safe_get(info, 'marketCap', 0)
    
    # ROIC/ROE (max 25) - consistent high returns = moat
    score += max(0, min(25, int(roic * 1.25)))
    
    # ROA (max 15)
    score += max(0, min(15, int(roa)))
    
    # Gross margin (max 20) - pricing power
    score += max(0, min(20, int(gm * 0.4)))
    
    # Operating/profit margin (max 20) - efficiency moat
    score += max(0, min(20, int(pm)))
    
    # FCF consistency (max 20)
    if fcf > 0 and market_cap > 0:
        fcf_yield = (fcf / market_cap) * 100
        score += max(0, min(20, int(fcf_yield * 2)))
    
    return min(score, 100)


def calculate_score_dividend(info, price, fair_value):
    """Dividend Safety scoring - emphasizes sustainable dividends"""
    score = 0
    div_yield = to_pct(safe_get(info, 'dividendYield', 0))
    payout = to_pct(safe_get(info, 'payoutRatio', 0))
    fcf = safe_get(info, 'freeCashflow', 0)
    debt_equity = safe_get(info, 'debtToEquity', 0)
    pm = to_pct(safe_get(info, 'profitMargins', 0))
    
    # Dividend yield (max 25) - 5%+ = max, 0% = 0
    score += max(0, min(25, int(div_yield * 5)))
    
    # Payout ratio (max 25) - 30-60% ideal = max, <20% or >80% penalized
    if 30 <= payout <= 60:
        score += 25
    elif 20 <= payout < 30 or 60 < payout <= 75:
        score += 15
    elif payout > 0 and payout < 80:
        score += 10
    
    # FCF coverage (max 20) - can they afford dividends
    if fcf > 0:
        score += 20
    
    # Low debt (max 15) - safety buffer
    if debt_equity >= 0: score += max(0, min(15, int((2 - debt_equity) * 10)))
    else: score += 10
    
    # Profit margin (max 15) - stable earnings
    score += max(0, min(15, int(pm * 0.75)))
    
    return min(score, 100)


def get_score_for_algo(info, price, fair_value, algo):
    """Get score based on selected algorithm"""
    if algo == 'value':
        return calculate_score_value(info, price, fair_value)
    elif algo == 'growth':
        return calculate_score_growth(info, price, fair_value)
    elif algo == 'quality':
        return calculate_score_quality(info, price, fair_value)
    elif algo == 'dividend':
        return calculate_score_dividend(info, price, fair_value)
    else:
        return calculate_score(info, price, fair_value)


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
        algo = params.get('algo', ['default'])[0]
        
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
                score = get_score_for_algo(info, price, fair_value, algo)
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
