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


# ── Rule #1 Investing Functions (Phil Town) ──────────────────────────

def calculate_roic(info):
    """Calculate Return on Invested Capital.
    ROIC = Net Income / Invested Capital
    Invested Capital = Equity + Total Debt - Cash"""
    net_income = safe_get(info, 'netIncomeToCommon', 0)
    if not net_income:
        return None
    bv_ps = safe_get(info, 'bookValue', 0)
    shares = safe_get(info, 'sharesOutstanding', 0)
    total_debt = safe_get(info, 'totalDebt', 0)
    total_cash = safe_get(info, 'totalCash', 0)
    equity = bv_ps * shares if bv_ps and shares else 0
    invested_capital = equity + total_debt - total_cash
    if invested_capital <= 0:
        return None
    return (net_income / invested_capital) * 100


def calculate_sticker_price(info, price):
    """Phil Town's Rule #1 Sticker Price with 50% Margin of Safety.
    Sticker = EPS × (1+g)^10 × min(2×g%, 50) ÷ 1.15^10
    MOS Price = Sticker ÷ 2"""
    eps = safe_get(info, 'trailingEps', 0)
    if not eps or eps <= 0:
        return None
    growth_rate = None
    growth_source = None
    # Try analyst earnings growth
    eg = info.get('earningsGrowth')
    if eg is not None:
        eg_f = float(eg)
        if eg_f > 0:
            growth_rate = eg_f if eg_f < 1 else eg_f / 100
            growth_source = 'analyst earnings est.'
    # Try forward vs trailing EPS
    if growth_rate is None:
        fwd = safe_get(info, 'forwardEps', 0)
        if fwd and eps and fwd > eps:
            growth_rate = (fwd - eps) / eps
            growth_source = 'forward EPS growth'
    # Try revenue growth
    if growth_rate is None:
        rg = info.get('revenueGrowth')
        if rg is not None:
            rg_f = float(rg)
            if rg_f > 0:
                growth_rate = rg_f if rg_f < 1 else rg_f / 100
                growth_source = 'revenue growth'
    if growth_rate is None or growth_rate <= 0:
        return None
    # Cap at 30% for conservative estimate
    growth_rate = min(growth_rate, 0.30)
    future_eps = eps * (1 + growth_rate) ** 10
    future_pe = min(2 * growth_rate * 100, 50)
    future_price = future_eps * future_pe
    sticker_price = future_price / (1.15 ** 10)
    mos_price = sticker_price / 2
    if price <= mos_price:
        verdict, verdict_color = 'ON SALE', '#00d374'
    elif price <= sticker_price:
        verdict, verdict_color = 'FAIR VALUE', '#ffb800'
    else:
        verdict, verdict_color = 'OVERPRICED', '#ff5252'
    return {
        'eps': round(eps, 2),
        'growth_rate': round(growth_rate * 100, 1),
        'growth_source': growth_source,
        'future_eps': round(future_eps, 2),
        'future_pe': round(future_pe, 1),
        'future_price': round(future_price, 2),
        'sticker_price': round(sticker_price, 2),
        'mos_price': round(mos_price, 2),
        'current_price': round(price, 2),
        'verdict': verdict,
        'verdict_color': verdict_color,
    }


def calculate_rule1(info, price):
    """Full Rule #1 analysis: Big 5 Numbers + Sticker Price + Moat."""
    big5 = []
    # 1. ROIC
    roic = calculate_roic(info)
    big5.append({
        'name': 'ROIC', 'value': round(roic, 1) if roic is not None else None,
        'unit': '%', 'pass': roic is not None and roic >= 10, 'target': '≥ 10%',
    })
    # 2. Revenue Growth
    rg = info.get('revenueGrowth')
    rg_pct = to_pct(rg) if rg is not None else None
    big5.append({
        'name': 'Revenue Growth', 'value': round(rg_pct, 1) if rg_pct is not None else None,
        'unit': '%', 'pass': rg_pct is not None and rg_pct >= 10, 'target': '≥ 10%',
    })
    # 3. EPS Growth
    eg = info.get('earningsGrowth')
    eg_pct = to_pct(eg) if eg is not None else None
    big5.append({
        'name': 'EPS Growth', 'value': round(eg_pct, 1) if eg_pct is not None else None,
        'unit': '%', 'pass': eg_pct is not None and eg_pct >= 10, 'target': '≥ 10%',
    })
    # 4. Equity Growth (quarterly earnings growth as proxy)
    eq_g = info.get('earningsQuarterlyGrowth')
    eq_pct = to_pct(eq_g) if eq_g is not None else None
    big5.append({
        'name': 'Equity Growth', 'value': round(eq_pct, 1) if eq_pct is not None else None,
        'unit': '%', 'pass': eq_pct is not None and eq_pct >= 10, 'target': '≥ 10%',
        'note': 'quarterly earnings proxy',
    })
    # 5. FCF Margin (proxy for FCF health)
    fcf = safe_get(info, 'freeCashflow', 0)
    revenue = safe_get(info, 'totalRevenue', 0)
    fcf_margin = (fcf / revenue * 100) if revenue and fcf else None
    big5.append({
        'name': 'FCF Margin', 'value': round(fcf_margin, 1) if fcf_margin is not None else None,
        'unit': '%', 'pass': fcf_margin is not None and fcf_margin >= 10, 'target': '≥ 10%',
        'note': 'FCF as % of revenue',
    })
    passing = sum(1 for m in big5 if m['pass'])
    # Sticker Price
    sticker = calculate_sticker_price(info, price)
    # Moat assessment
    roe = info.get('returnOnEquity')
    roe_pct = to_pct(roe) if roe is not None else 0
    has_moat = roic is not None and roic >= 10 and roe_pct >= 15
    return {
        'big5': big5,
        'big5_passing': passing,
        'big5_total': 5,
        'sticker': sticker,
        'has_moat': has_moat,
        'moat_text': 'Strong moat indicators (ROIC ≥10%, ROE ≥15%)' if has_moat else 'Moat uncertain — needs deeper analysis',
    }


def calculate_score(data):
    """Calculate investment score with proportional scaling.
    Instead of all-or-nothing, metrics earn points based on how well they perform."""
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
    
    # ROA check (max 15) - proportional scale
    # Target: 15%+ = full points, scales down linearly to 0 at -5%
    roa_pct = to_pct(roa)
    roa_pts = max(0, min(15, int((roa_pct + 5) * 15 / 20)))  # -5% -> 0pts, 15% -> 15pts
    score += roa_pts
    if roa_pct >= 10:
        checks.append({'pass': True, 'text': f'ROA ({roa_pct:.1f}%) excellent', 'points': roa_pts, 'max': 15})
    elif roa_pct >= 5:
        checks.append({'pass': 'warn', 'text': f'ROA ({roa_pct:.1f}%) decent', 'points': roa_pts, 'max': 15})
    else:
        checks.append({'pass': False, 'text': f'ROA ({roa_pct:.1f}%) weak', 'points': roa_pts, 'max': 15})
    
    # ROE check (max 15) - proportional scale
    # Target: 15%+ = full points, scales down to 0 at -5%
    roe_pct = to_pct(roe)
    roe_pts = max(0, min(15, int((roe_pct + 5) * 15 / 20)))
    score += roe_pts
    if roe_pct >= 10:
        checks.append({'pass': True, 'text': f'ROE ({roe_pct:.1f}%) excellent', 'points': roe_pts, 'max': 15})
    elif roe_pct >= 5:
        checks.append({'pass': 'warn', 'text': f'ROE ({roe_pct:.1f}%) decent', 'points': roe_pts, 'max': 15})
    else:
        checks.append({'pass': False, 'text': f'ROE ({roe_pct:.1f}%) weak', 'points': roe_pts, 'max': 15})
    
    # Cash vs Debt (max 15) - proportional based on coverage ratio
    if debt > 0:
        coverage = cash / debt if debt > 0 else 10  # cash/debt ratio
        # 2x coverage = full points, 0x = 0 points
        debt_pts = max(0, min(15, int(coverage * 7.5)))
        score += debt_pts
        if coverage >= 1:
            checks.append({'pass': True, 'text': f'Cash covers {coverage:.1f}x debt', 'points': debt_pts, 'max': 15})
        elif coverage >= 0.5:
            checks.append({'pass': 'warn', 'text': f'Cash covers {coverage:.1f}x debt', 'points': debt_pts, 'max': 15})
        else:
            checks.append({'pass': False, 'text': f'Cash only {coverage:.1f}x debt', 'points': debt_pts, 'max': 15})
    elif cash > 0:
        score += 15
        checks.append({'pass': True, 'text': f'Cash (${format_number(cash)}) & minimal debt', 'points': 15, 'max': 15})
    else:
        checks.append({'pass': 'warn', 'text': 'Cash/Debt data limited', 'points': 0, 'max': 15})
    
    # Fair value (max 20) - proportional based on upside
    if price > 0 and fair_value > 0:
        upside = ((fair_value - price) / price) * 100
        # 50%+ upside = full 20pts, 0% = 0pts, negative = 0
        value_pts = max(0, min(20, int(upside * 0.4)))
        score += value_pts
        if upside > 30:
            checks.append({'pass': True, 'text': f'{upside:.0f}% undervalued', 'points': value_pts, 'max': 20})
        elif upside > 10:
            checks.append({'pass': 'warn', 'text': f'{upside:.0f}% below fair value', 'points': value_pts, 'max': 20})
        elif upside > 0:
            checks.append({'pass': 'warn', 'text': f'{upside:.0f}% near fair value', 'points': value_pts, 'max': 20})
        else:
            checks.append({'pass': False, 'text': f'Overvalued by {abs(upside):.0f}%', 'points': 0, 'max': 20})
    
    # Profit margin (max 10) - proportional scale
    # 20%+ = full points, scales to 0 at -5%
    pm_pct = to_pct(profit_margin)
    pm_pts = max(0, min(10, int((pm_pct + 5) * 10 / 25)))
    score += pm_pts
    if pm_pct >= 15:
        checks.append({'pass': True, 'text': f'Strong margin ({pm_pct:.1f}%)', 'points': pm_pts, 'max': 10})
    elif pm_pct >= 5:
        checks.append({'pass': 'warn', 'text': f'Margin ({pm_pct:.1f}%)', 'points': pm_pts, 'max': 10})
    elif pm_pct > 0:
        checks.append({'pass': 'warn', 'text': f'Thin margin ({pm_pct:.1f}%)', 'points': pm_pts, 'max': 10})
    else:
        checks.append({'pass': False, 'text': f'Negative margin ({pm_pct:.1f}%)', 'points': 0, 'max': 10})
    
    # P/S ratio (max 10) - proportional (lower is better)
    # P/S < 1 = full 10pts, P/S 5+ = 0pts
    if ps_ratio > 0:
        ps_pts = max(0, min(10, int((5 - ps_ratio) * 2.5)))
        score += ps_pts
        if ps_ratio < 1:
            checks.append({'pass': True, 'text': f'P/S ({ps_ratio:.2f}x) very attractive', 'points': ps_pts, 'max': 10})
        elif ps_ratio < 2:
            checks.append({'pass': True, 'text': f'P/S ({ps_ratio:.2f}x) attractive', 'points': ps_pts, 'max': 10})
        elif ps_ratio < 4:
            checks.append({'pass': 'warn', 'text': f'P/S ({ps_ratio:.2f}x) moderate', 'points': ps_pts, 'max': 10})
        else:
            checks.append({'pass': False, 'text': f'P/S ({ps_ratio:.2f}x) expensive', 'points': ps_pts, 'max': 10})
    
    # FCF (max 15) - proportional based on FCF yield (FCF / market cap)
    market_cap = data.get('market_cap', 0) or 0
    if fcf > 0 and market_cap > 0:
        fcf_yield = (fcf / market_cap) * 100
        # 10%+ yield = full points, 0% = 0 points
        fcf_pts = max(0, min(15, int(fcf_yield * 1.5)))
        score += fcf_pts
        if fcf_yield >= 5:
            checks.append({'pass': True, 'text': f'Strong FCF yield ({fcf_yield:.1f}%)', 'points': fcf_pts, 'max': 15})
        elif fcf_yield >= 2:
            checks.append({'pass': True, 'text': f'Positive FCF yield ({fcf_yield:.1f}%)', 'points': fcf_pts, 'max': 15})
        else:
            checks.append({'pass': 'warn', 'text': f'Low FCF yield ({fcf_yield:.1f}%)', 'points': fcf_pts, 'max': 15})
    elif fcf > 0:
        score += 10
        checks.append({'pass': True, 'text': f'Positive FCF (${format_number(fcf)})', 'points': 10, 'max': 15})
    else:
        checks.append({'pass': False, 'text': 'Negative/no FCF', 'points': 0, 'max': 15})
    
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
        'market_cap': safe_get(info, 'marketCap', 0),
    }
    
    # Calculate fair value with component tracking
    eps = data['eps']
    pe = safe_get(info, 'trailingPE', 0)
    forward_pe = safe_get(info, 'forwardPE', 0)
    target_price = safe_get(info, 'targetMeanPrice', 0)
    earnings_growth = info.get('earningsGrowth')
    
    fair_values = []
    fair_value_components = []
    
    if target_price and target_price > 0:
        fair_values.append(target_price)
        fair_value_components.append({'label': 'Analyst Consensus Target', 'value': round(target_price, 2)})
    
    if forward_pe and forward_pe > 0 and eps and eps > 0:
        growth_pe = min(forward_pe * 1.2, 30)
        fv = eps * growth_pe
        fair_values.append(fv)
        fair_value_components.append({'label': f'Forward PE Model (EPS \u00d7 {growth_pe:.1f})', 'value': round(fv, 2)})
    
    # Growth-adjusted PE fair value (PEG-based)
    if earnings_growth and float(earnings_growth) > 0 and eps and eps > 0:
        eg = float(earnings_growth)
        growth_pct = eg * 100 if eg < 1 else eg
        fair_pe_from_growth = min(growth_pct * 1.0, 40)
        fv = eps * fair_pe_from_growth
        if fv > 0:
            fair_values.append(fv)
            fair_value_components.append({'label': f'PEG Model (EPS \u00d7 {fair_pe_from_growth:.0f} growth-PE)', 'value': round(fv, 2)})
    
    if pe and pe > 0 and pe < 25 and price > 0:
        fv = price * 1.1
        fair_values.append(fv)
        fair_value_components.append({'label': 'Low PE Premium (+10%)', 'value': round(fv, 2)})
    elif pe and pe > 25 and price > 0:
        fv = price * 0.95
        fair_values.append(fv)
        fair_value_components.append({'label': 'High PE Discount (-5%)', 'value': round(fv, 2)})
    
    if eps and eps > 0 and not fair_values:
        sector = safe_get(info, 'sector', '')
        if 'Technology' in str(sector):
            mult = 25
        elif 'Consumer' in str(sector):
            mult = 20
        else:
            mult = 18
        fv = eps * mult
        fair_values.append(fv)
        fair_value_components.append({'label': f'Sector PE Model (EPS \u00d7 {mult})', 'value': round(fv, 2)})
    
    fair_value = sum(fair_values) / len(fair_values) if fair_values else price
    data['fair_value'] = fair_value
    
    score, checks = calculate_score(data)
    upside = ((fair_value - price) / price * 100) if price > 0 else 0
    
    # Growth & Trend data
    rev_growth = info.get('revenueGrowth')
    earn_growth = info.get('earningsGrowth')
    quarterly_growth = info.get('earningsQuarterlyGrowth')
    rev_growth_pct = to_pct(rev_growth) if rev_growth is not None else None
    earn_growth_pct = to_pct(earn_growth) if earn_growth is not None else None
    quarterly_growth_pct = to_pct(quarterly_growth) if quarterly_growth is not None else None
    
    # Rule #1 Analysis
    rule1 = calculate_rule1(info, price)
    
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
            'forward_pe': forward_pe or None,
            'ps_ratio': data['ps_ratio'] or None,
            'pb_ratio': safe_get(info, 'priceToBook', None),
            'peg_ratio': safe_get(info, 'pegRatio', None),
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
        'growth': {
            'revenue': round(rev_growth_pct, 1) if rev_growth_pct is not None else None,
            'earnings': round(earn_growth_pct, 1) if earn_growth_pct is not None else None,
            'quarterly_earnings': round(quarterly_growth_pct, 1) if quarterly_growth_pct is not None else None,
            'revenue_trend': 'up' if rev_growth_pct and rev_growth_pct > 0 else ('down' if rev_growth_pct and rev_growth_pct < 0 else None),
            'earnings_trend': 'up' if earn_growth_pct and earn_growth_pct > 0 else ('down' if earn_growth_pct and earn_growth_pct < 0 else None),
        },
        'fair_value': round(fair_value, 2),
        'fair_value_components': fair_value_components,
        'upside_percent': round(upside, 1),
        'investment_score': score,
        'checklist': checks,
        'recommendation': get_recommendation(score, upside),
        'rule1': rule1,
    }
