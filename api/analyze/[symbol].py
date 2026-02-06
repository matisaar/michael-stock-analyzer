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

def to_pct(val):
    """Convert yfinance decimal ratio to percentage.
    yfinance ALWAYS returns ratios as decimals: 0.24 = 24%, 1.5 = 150%.
    Values > 10 are likely already percentages from a different source."""
    if val is None:
        return 0
    val = float(val)
    if abs(val) > 10:
        # Already looks like a percentage (e.g. 24.4 not 0.244)
        return val
    return val * 100

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
    
    # ROA check
    roa_pct = to_pct(roa)
    if roa_pct > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROA ({roa_pct:.1f}%) > 10%'})
    elif roa_pct > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROA ({roa_pct:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROA ({roa_pct:.1f}%) < 10%'})
    
    # ROE check
    roe_pct = to_pct(roe)
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
    pm_pct = to_pct(profit_margin)
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
            
            # Detect asset type
            quote_type = info.get('quoteType', 'EQUITY')
            is_etf = quote_type == 'ETF'
            
            # Extract price
            price = safe_get(info, 'currentPrice') or safe_get(info, 'regularMarketPrice') or safe_get(info, 'navPrice', 0)
            
            if is_etf:
                # === ETF-specific analysis ===
                result = build_etf_result(symbol, info, price)
            else:
                # === Stock analysis ===
                result = build_stock_result(symbol, info, price)
            
            self.wfile.write(json.dumps(result).encode())
            
        except Exception as e:
            self.wfile.write(json.dumps({
                'error': str(e),
                'symbol': symbol
            }).encode())

def build_etf_result(symbol, info, price):
    """Build analysis result for an ETF."""
    expense_ratio = safe_get(info, 'annualReportExpenseRatio', None)
    total_assets = safe_get(info, 'totalAssets', 0)
    ytd_return = safe_get(info, 'ytdReturn', None)
    three_yr_return = safe_get(info, 'threeYearAverageReturn', None)
    five_yr_return = safe_get(info, 'fiveYearAverageReturn', None)
    dividend_yield = safe_get(info, 'yield', None) or safe_get(info, 'dividendYield', None)
    beta = safe_get(info, 'beta3Year', None) or safe_get(info, 'beta', None)
    
    # ETF scoring
    score = 0
    checks = []
    
    # Expense ratio
    if expense_ratio is not None:
        er_pct = expense_ratio * 100 if expense_ratio < 1 else expense_ratio
        if er_pct < 0.1:
            score += 20
            checks.append({'pass': True, 'text': f'Very low expense ratio ({er_pct:.2f}%)'})
        elif er_pct < 0.5:
            score += 15
            checks.append({'pass': True, 'text': f'Low expense ratio ({er_pct:.2f}%)'})
        elif er_pct < 1.0:
            score += 5
            checks.append({'pass': 'warn', 'text': f'Moderate expense ratio ({er_pct:.2f}%)'})
        else:
            checks.append({'pass': False, 'text': f'High expense ratio ({er_pct:.2f}%)'})
    else:
        checks.append({'pass': 'warn', 'text': 'Expense ratio data unavailable'})
    
    # Dividend yield
    if dividend_yield is not None and dividend_yield > 0:
        dy_pct = dividend_yield * 100 if dividend_yield < 1 else dividend_yield
        if dy_pct > 3:
            score += 15
            checks.append({'pass': True, 'text': f'Strong yield ({dy_pct:.2f}%)'})
        elif dy_pct > 1:
            score += 10
            checks.append({'pass': True, 'text': f'Decent yield ({dy_pct:.2f}%)'})
        else:
            score += 5
            checks.append({'pass': 'warn', 'text': f'Low yield ({dy_pct:.2f}%)'})
    else:
        checks.append({'pass': 'warn', 'text': 'No dividend yield'})
    
    # 3-year return
    if three_yr_return is not None:
        ret_pct = three_yr_return * 100 if abs(three_yr_return) < 5 else three_yr_return
        if ret_pct > 10:
            score += 20
            checks.append({'pass': True, 'text': f'Strong 3yr avg return ({ret_pct:.1f}%)'})
        elif ret_pct > 5:
            score += 10
            checks.append({'pass': 'warn', 'text': f'Moderate 3yr avg return ({ret_pct:.1f}%)'})
        elif ret_pct > 0:
            score += 5
            checks.append({'pass': 'warn', 'text': f'Low 3yr avg return ({ret_pct:.1f}%)'})
        else:
            checks.append({'pass': False, 'text': f'Negative 3yr return ({ret_pct:.1f}%)'})
    else:
        checks.append({'pass': 'warn', 'text': '3yr return data unavailable'})
    
    # 5-year return
    if five_yr_return is not None:
        ret_pct = five_yr_return * 100 if abs(five_yr_return) < 5 else five_yr_return
        if ret_pct > 10:
            score += 15
            checks.append({'pass': True, 'text': f'Strong 5yr avg return ({ret_pct:.1f}%)'})
        elif ret_pct > 5:
            score += 10
            checks.append({'pass': 'warn', 'text': f'Moderate 5yr avg return ({ret_pct:.1f}%)'})
        else:
            checks.append({'pass': False, 'text': f'Weak 5yr avg return ({ret_pct:.1f}%)'})
    
    # Beta (risk)
    if beta is not None and beta > 0:
        if beta < 1.0:
            score += 10
            checks.append({'pass': True, 'text': f'Low volatility (beta {beta:.2f})'})
        elif beta < 1.3:
            score += 5
            checks.append({'pass': 'warn', 'text': f'Moderate volatility (beta {beta:.2f})'})
        else:
            checks.append({'pass': False, 'text': f'High volatility (beta {beta:.2f})'})
    
    # Total assets (liquidity)
    if total_assets and total_assets > 1e9:
        score += 10
        checks.append({'pass': True, 'text': f'Large fund (${format_number(total_assets)})'})
    elif total_assets and total_assets > 100e6:
        score += 5
        checks.append({'pass': 'warn', 'text': f'Mid-size fund (${format_number(total_assets)})'})
    elif total_assets:
        checks.append({'pass': False, 'text': f'Small fund (${format_number(total_assets)})'})

    # Cap score at 100
    score = min(score, 100)
    
    # Fair value for ETFs - use 52-week average or NAV
    week_52_high = safe_get(info, 'fiftyTwoWeekHigh', price)
    week_52_low = safe_get(info, 'fiftyTwoWeekLow', price)
    fair_value = (week_52_high + week_52_low) / 2 if week_52_high and week_52_low else price
    upside = ((fair_value - price) / price * 100) if price > 0 else 0
    
    return {
        'symbol': symbol,
        'is_etf': True,
        'timestamp': datetime.now().isoformat(),
        'quote': {
            'name': safe_get(info, 'longName') or safe_get(info, 'shortName', symbol),
            'price': price,
            'change_percent': safe_get(info, 'regularMarketChangePercent', 0),
            'market_cap': total_assets,
            'week_52_high': week_52_high,
            'week_52_low': week_52_low,
            'industry': info.get('category', 'ETF'),
            'sector': 'ETF',
        },
        'fundamentals': {
            'pe_ratio': safe_get(info, 'trailingPE', None),
            'expense_ratio': round(expense_ratio * 100, 3) if expense_ratio and expense_ratio < 1 else expense_ratio,
            'dividend_yield': round(dividend_yield * 100, 2) if dividend_yield and dividend_yield < 1 else dividend_yield,
            'ytd_return': round(ytd_return * 100, 1) if ytd_return and abs(ytd_return) < 5 else ytd_return,
            'three_yr_return': round(three_yr_return * 100, 1) if three_yr_return and abs(three_yr_return) < 5 else three_yr_return,
            'five_yr_return': round(five_yr_return * 100, 1) if five_yr_return and abs(five_yr_return) < 5 else five_yr_return,
            'beta': round(beta, 2) if beta else None,
            'total_assets': total_assets,
        },
        'fair_value': round(fair_value, 2),
        'upside_percent': round(upside, 1),
        'investment_score': score,
        'checklist': checks,
        'recommendation': get_recommendation(score, upside),
    }

def build_stock_result(symbol, info, price):
    """Build analysis result for a regular stock."""
    data = {
        'price': price,
        'roa': safe_get(info, 'returnOnAssets', None),
        'roe': safe_get(info, 'returnOnEquity', None),
        'cash': safe_get(info, 'totalCash', 0),
        'debt': safe_get(info, 'totalDebt', 0),
        'profit_margin': safe_get(info, 'profitMargins', None),
        'ps_ratio': safe_get(info, 'priceToSalesTrailing12Months', 0),
        'fcf': safe_get(info, 'freeCashflow', 0),
        'eps': safe_get(info, 'trailingEps', 0),
    }
    
    # Calculate fair value
    eps = data['eps']
    pe = safe_get(info, 'trailingPE', 0)
    forward_pe = safe_get(info, 'forwardPE', 0)
    target_price = safe_get(info, 'targetMeanPrice', 0)
    
    fair_values = []
    
    if target_price and target_price > 0:
        fair_values.append(target_price)
    
    if forward_pe and forward_pe > 0 and eps and eps > 0:
        growth_pe = min(forward_pe * 1.2, 30)
        fair_values.append(eps * growth_pe)
    
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
    
    fair_value = sum(fair_values) / len(fair_values) if fair_values else price
    data['fair_value'] = fair_value
    
    score, checks = calculate_score(data)
    upside = ((fair_value - price) / price * 100) if price > 0 else 0
    
    # Build fundamentals - use None for truly missing data so frontend shows N/A
    roa_val = to_pct(data['roa']) if data['roa'] is not None else None
    roe_val = to_pct(data['roe']) if data['roe'] is not None else None
    pm_val = to_pct(data['profit_margin']) if data['profit_margin'] is not None else None
    gm_raw = safe_get(info, 'grossMargins', None)
    gm_val = to_pct(gm_raw) if gm_raw is not None else None
    
    return {
        'symbol': symbol,
        'is_etf': False,
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
            'pe_ratio': safe_get(info, 'trailingPE', None),
            'ps_ratio': data['ps_ratio'] or None,
            'pb_ratio': safe_get(info, 'priceToBook', None),
            'eps': data['eps'] or None,
            'roa': roa_val,
            'roe': roe_val,
            'profit_margin': pm_val,
            'gross_margin': gm_val,
            'cash': data['cash'] or None,
            'debt': data['debt'] or None,
            'fcf': data['fcf'] or None,
            'dividend_yield': to_pct(safe_get(info, 'dividendYield', None)) if info.get('dividendYield') else None,
        },
        'fair_value': round(fair_value, 2),
        'upside_percent': round(upside, 1),
        'investment_score': score,
        'checklist': checks,
        'recommendation': get_recommendation(score, upside),
    }
