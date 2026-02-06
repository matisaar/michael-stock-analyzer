"""Analyze stock using yfinance - auto-resolves company names to tickers"""
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
from datetime import datetime
import yfinance as yf

def format_number(n):
    if n is None or n == 0:
        return '0'
    n = float(n)
    if abs(n) >= 1e12:
        return f'{n/1e12:.1f}T'
    if abs(n) >= 1e9:
        return f'{n/1e9:.1f}B'
    if abs(n) >= 1e6:
        return f'{n/1e6:.0f}M'
    if abs(n) >= 1e3:
        return f'{n/1e3:.0f}K'
    return f'{n:.0f}'

def resolve_symbol(query):
    """Search Yahoo Finance via yfinance to resolve a company name to a ticker.
    Returns (resolved_symbol, company_name) or (None, None) if not found."""
    try:
        search = yf.Search(query, max_results=5, news_count=0)
        quotes = search.quotes if hasattr(search, 'quotes') else []
        for q in quotes:
            qt = q.get('quoteType', '')
            if qt in ('EQUITY', 'ETF'):
                sym = q.get('symbol', '')
                name = q.get('shortname') or q.get('longname') or sym
                if sym:
                    return sym, name
    except Exception as e:
        print(f"resolve_symbol error: {e}")
    return None, None

def try_yfinance(symbol):
    """Try to get stock info via yfinance. Returns info dict or None."""
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        if info and (info.get('regularMarketPrice') or info.get('currentPrice')):
            return info
    except Exception:
        pass
    return None

def safe_get(info, key, default=0):
    """Safely get value from info dict"""
    val = info.get(key)
    if val is None:
        return default
    return val

def calculate_score(data):
    """Calculate investment score"""
    score = 0
    checks = []
    
    roa = data.get('roa', 0) or 0
    roe = data.get('roe', 0) or 0
    cash = data.get('cash', 0) or 0
    debt = data.get('debt', 0) or 0
    price = data.get('price', 0) or 0
    fair_value = data.get('fair_value', price) or price
    profit_margin = data.get('profit_margin', 0) or 0
    ps_ratio = data.get('ps_ratio', 0) or 0
    fcf = data.get('fcf', 0) or 0
    
    # ROA check (multiply by 100 if decimal)
    roa_pct = roa * 100 if abs(roa) < 1 else roa
    if roa_pct > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROA ({roa_pct:.1f}%) > 10%'})
    elif roa_pct > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROA ({roa_pct:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROA ({roa_pct:.1f}%) < 10%'})
    
    # ROE check
    roe_pct = roe * 100 if abs(roe) < 1 else roe
    if roe_pct > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROE ({roe_pct:.1f}%) > 10%'})
    elif roe_pct > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROE ({roe_pct:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROE ({roe_pct:.1f}%) < 10%'})
    
    # Cash vs Debt
    if cash > 0 and cash >= debt:
        score += 15
        checks.append({'pass': True, 'text': f'Cash (${format_number(cash)}) ≥ Debt'})
    elif debt > 0:
        checks.append({'pass': False, 'text': f'Debt (${format_number(debt)}) > Cash'})
    else:
        checks.append({'pass': 'warn', 'text': 'Cash/Debt data limited'})
    
    # Fair value
    if price > 0 and fair_value > 0:
        upside = ((fair_value - price) / price) * 100
        if upside > 30:
            score += 20
            checks.append({'pass': True, 'text': f'{upside:.0f}% undervalued'})
        elif upside > 10:
            score += 10
            checks.append({'pass': 'warn', 'text': f'{upside:.0f}% below fair value'})
        elif upside > 0:
            score += 5
            checks.append({'pass': 'warn', 'text': 'Near fair value'})
        else:
            checks.append({'pass': False, 'text': f'Overvalued by {abs(upside):.0f}%'})
    
    # Profit margin
    pm_pct = profit_margin * 100 if abs(profit_margin) < 1 else profit_margin
    if pm_pct > 15:
        score += 10
        checks.append({'pass': True, 'text': f'Strong margin ({pm_pct:.1f}%)'})
    elif pm_pct > 5:
        score += 5
        checks.append({'pass': 'warn', 'text': f'Margin ({pm_pct:.1f}%)'})
    elif pm_pct > 0:
        checks.append({'pass': 'warn', 'text': f'Low margin ({pm_pct:.1f}%)'})
    else:
        checks.append({'pass': False, 'text': 'Negative margin'})
    
    # P/S ratio
    if ps_ratio > 0 and ps_ratio < 2:
        score += 10
        checks.append({'pass': True, 'text': f'P/S ({ps_ratio:.2f}x) attractive'})
    elif ps_ratio > 0:
        checks.append({'pass': 'warn', 'text': f'P/S ({ps_ratio:.2f}x)'})
    
    # FCF
    if fcf > 0:
        score += 15
        checks.append({'pass': True, 'text': f'Positive FCF (${format_number(fcf)})'})
    else:
        checks.append({'pass': False, 'text': 'Negative/no FCF'})
    
    return score, checks

def get_recommendation(score, upside):
    if score >= 70 and upside > 30:
        return {'signal': 'STRONG BUY', 'color': '#00d374', 'reason': 'High score + undervalued'}
    elif score >= 60 and upside > 15:
        return {'signal': 'BUY', 'color': '#00d374', 'reason': 'Good fundamentals, undervalued'}
    elif score >= 50 and upside > 0:
        return {'signal': 'HOLD', 'color': '#ffb800', 'reason': 'Decent fundamentals'}
    elif score >= 40:
        return {'signal': 'WATCH', 'color': '#ffb800', 'reason': 'Some concerns'}
    else:
        return {'signal': 'AVOID', 'color': '#ff5252', 'reason': 'Does not meet criteria'}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        raw_input = self.path.split('/')[-1].split('?')[0]
        raw_input_decoded = urllib.parse.unquote(raw_input)
        symbol = raw_input_decoded.upper().strip()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            # Step 1: Try direct yfinance lookup with the input as-is
            info = try_yfinance(symbol)
            
            # Step 2: If that fails, search Yahoo Finance to resolve the name
            resolved_name = None
            if info is None:
                resolved_sym, resolved_name = resolve_symbol(raw_input_decoded)
                if resolved_sym:
                    symbol = resolved_sym.upper()
                    info = try_yfinance(symbol)
            
            # Step 3: If still nothing, give up with helpful error
            if info is None:
                self.wfile.write(json.dumps({
                    'error': f'Could not find "{raw_input_decoded}". Try a ticker symbol like AAPL, TSLA, or MSFT.',
                    'symbol': symbol
                }).encode())
                return
            
            # Extract data
            price = safe_get(info, 'currentPrice') or safe_get(info, 'regularMarketPrice', 0)
            
            data = {
                'price': price,
                'roa': safe_get(info, 'returnOnAssets', 0),
                'roe': safe_get(info, 'returnOnEquity', 0),
                'cash': safe_get(info, 'totalCash', 0),
                'debt': safe_get(info, 'totalDebt', 0),
                'profit_margin': safe_get(info, 'profitMargins', 0),
                'ps_ratio': safe_get(info, 'priceToSalesTrailing12Months', 0),
                'fcf': safe_get(info, 'freeCashflow', 0),
                'eps': safe_get(info, 'trailingEps', 0),
            }
            
            # Calculate fair value - smarter approach
            eps = data['eps']
            pe = safe_get(info, 'trailingPE', 0)
            forward_pe = safe_get(info, 'forwardPE', 0)
            target_price = safe_get(info, 'targetMeanPrice', 0)  # Analyst target
            
            fair_values = []
            
            # Method 1: Analyst target price (most reliable)
            if target_price and target_price > 0:
                fair_values.append(target_price)
            
            # Method 2: Forward PE based (if growth stock)
            if forward_pe and forward_pe > 0 and eps and eps > 0:
                # Use forward PE as indicator of expected growth
                growth_pe = min(forward_pe * 1.2, 30)  # Cap at 30x
                fair_values.append(eps * growth_pe)
            
            # Method 3: Current PE regression to mean (for value stocks)
            if pe and pe > 0 and pe < 25 and price > 0:
                # Stock already reasonably valued, small upside
                fair_values.append(price * 1.1)
            elif pe and pe > 25 and price > 0:
                # High PE stock - use current price as baseline
                fair_values.append(price * 0.95)
            
            # Method 4: Simple EPS * industry PE
            if eps and eps > 0 and not fair_values:
                sector = safe_get(info, 'sector', '')
                if 'Technology' in sector:
                    fair_values.append(eps * 25)
                elif 'Consumer' in sector:
                    fair_values.append(eps * 20)
                else:
                    fair_values.append(eps * 18)
            
            fair_value = sum(fair_values) / len(fair_values) if fair_values else price
            data['fair_value'] = fair_value
            
            # Calculate score
            score, checks = calculate_score(data)
            
            # Upside
            upside = ((fair_value - price) / price * 100) if price > 0 else 0
            
            result = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'quote': {
                    'name': safe_get(info, 'longName') or safe_get(info, 'shortName', symbol),
                    'price': price,
                    'change_percent': safe_get(info, 'regularMarketChangePercent', 0),
                    'market_cap': safe_get(info, 'marketCap', 0),
                    'week_52_high': safe_get(info, 'fiftyTwoWeekHigh', 0),
                    'week_52_low': safe_get(info, 'fiftyTwoWeekLow', 0),
                    'industry': safe_get(info, 'industry', 'N/A'),
                    'sector': safe_get(info, 'sector', 'N/A'),
                },
                'fundamentals': {
                    'pe_ratio': safe_get(info, 'trailingPE', 0),
                    'ps_ratio': data['ps_ratio'],
                    'pb_ratio': safe_get(info, 'priceToBook', 0),
                    'eps': data['eps'],
                    'roa': (data['roa'] * 100) if data['roa'] and abs(data['roa']) < 1 else data['roa'],
                    'roe': (data['roe'] * 100) if data['roe'] and abs(data['roe']) < 1 else data['roe'],
                    'profit_margin': (data['profit_margin'] * 100) if data['profit_margin'] and abs(data['profit_margin']) < 1 else data['profit_margin'],
                    'gross_margin': safe_get(info, 'grossMargins', 0) * 100 if safe_get(info, 'grossMargins', 0) else 0,
                    'cash': data['cash'],
                    'debt': data['debt'],
                    'fcf': data['fcf'],
                },
                'fair_value': round(fair_value, 2),
                'upside_percent': round(upside, 1),
                'investment_score': score,
                'checklist': checks,
                'recommendation': get_recommendation(score, upside),
            }
            
            self.wfile.write(json.dumps(result).encode())
            
        except Exception as e:
            self.wfile.write(json.dumps({
                'error': str(e),
                'symbol': symbol
            }).encode())
