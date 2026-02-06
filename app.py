"""
Michael's Stock Analyzer - Python Backend
=========================================
A Flask API that provides stock analysis based on Michael's investment criteria:
- ROA > 10%
- ROE > 10%
- Cash > Debt
- Trading below fair value (DCF)
- Strong profit margins

Data Sources:
- Tradier API (free sandbox for quotes)
- GitHub rreichel3/US-Stock-Symbols (ticker lists)
- Financial Modeling Prep (fundamentals)
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import os
from datetime import datetime
import time

app = Flask(__name__, static_folder='.')
CORS(app)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Tradier API (Free Sandbox - get key at https://developer.tradier.com/)
TRADIER_API_KEY = os.environ.get('TRADIER_API_KEY', '')
TRADIER_BASE_URL = 'https://sandbox.tradier.com/v1'  # Use sandbox for free tier

# Financial Modeling Prep API (backup/fundamentals)
FMP_API_KEY = os.environ.get('FMP_API_KEY', '')
FMP_BASE_URL = 'https://financialmodelingprep.com/api/v3'

# GitHub stock symbols
GITHUB_STOCKS_URL = 'https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main'

# Cache for stock data (5 min TTL)
CACHE_TTL = 300
_cache = {}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_cached(key, ttl=CACHE_TTL):
    """Simple cache with TTL"""
    if key in _cache:
        data, timestamp = _cache[key]
        if time.time() - timestamp < ttl:
            return data
    return None

def set_cached(key, data):
    """Set cache value"""
    _cache[key] = (data, time.time())

def tradier_request(endpoint, params=None):
    """Make request to Tradier API"""
    if not TRADIER_API_KEY:
        return None
    
    headers = {
        'Authorization': f'Bearer {TRADIER_API_KEY}',
        'Accept': 'application/json'
    }
    
    try:
        url = f'{TRADIER_BASE_URL}{endpoint}'
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Tradier API error: {e}")
    return None

def fmp_request(endpoint, params=None):
    """Make request to Financial Modeling Prep API"""
    if not FMP_API_KEY:
        return None
    
    try:
        url = f'{FMP_BASE_URL}{endpoint}'
        params = params or {}
        params['apikey'] = FMP_API_KEY
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"FMP API error: {e}")
    return None

# =============================================================================
# MICHAEL'S ANALYSIS ENGINE
# =============================================================================

def calculate_investment_score(data):
    """
    Calculate investment score based on Michael's criteria:
    - ROA > 10% (+15 points)
    - ROE > 10% (+15 points)  
    - Cash > Debt (+15 points)
    - Below fair value (+20 points)
    - Positive profit margin (+10 points)
    - Low P/S ratio (+10 points)
    - Positive FCF (+15 points)
    
    Returns score (0-100) and checklist items
    """
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
    if roa > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROA ({roa:.1f}%) > 10%'})
    elif roa > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROA ({roa:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROA ({roa:.1f}%) < 10%'})
    
    # ROE check
    if roe > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROE ({roe:.1f}%) > 10%'})
    elif roe > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROE ({roe:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROE ({roe:.1f}%) < 10%'})
    
    # Cash vs Debt
    if cash >= debt:
        score += 15
        checks.append({'pass': True, 'text': f'Cash (${format_number(cash)}) covers debt'})
    else:
        checks.append({'pass': False, 'text': f'Debt exceeds cash'})
    
    # Fair value check
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
            checks.append({'pass': 'warn', 'text': f'Near fair value'})
        else:
            checks.append({'pass': False, 'text': f'Overvalued by {abs(upside):.0f}%'})
    
    # Profit margin
    if profit_margin > 15:
        score += 10
        checks.append({'pass': True, 'text': f'Strong margin ({profit_margin:.1f}%)'})
    elif profit_margin > 5:
        score += 5
        checks.append({'pass': 'warn', 'text': f'Margin ({profit_margin:.1f}%)'})
    elif profit_margin > 0:
        checks.append({'pass': 'warn', 'text': f'Low margin ({profit_margin:.1f}%)'})
    else:
        checks.append({'pass': False, 'text': 'Negative margin'})
    
    # P/S ratio
    if 0 < ps_ratio < 2:
        score += 10
        checks.append({'pass': True, 'text': f'P/S ({ps_ratio:.2f}x) attractive'})
    elif ps_ratio > 0:
        checks.append({'pass': 'warn', 'text': f'P/S ({ps_ratio:.2f}x)'})
    
    # FCF
    if fcf > 0:
        score += 15
        checks.append({'pass': True, 'text': f'Positive FCF (${format_number(fcf)})'})
    else:
        checks.append({'pass': False, 'text': 'Negative FCF'})
    
    return score, checks

def calculate_fair_value(data):
    """
    Calculate fair value using multiple methods:
    1. DCF (if we have cash flow data)
    2. P/E based (using industry avg PE)
    3. Graham number
    """
    eps = data.get('eps', 0) or 0
    book_value = data.get('book_value_per_share', 0) or 0
    fcf = data.get('fcf', 0) or 0
    shares = data.get('shares_outstanding', 0) or 0
    growth_rate = data.get('growth_rate', 0.05)  # Default 5%
    
    fair_values = []
    
    # Method 1: P/E based (industry avg ~ 15)
    if eps > 0:
        pe_fair_value = eps * 15
        fair_values.append(pe_fair_value)
    
    # Method 2: Graham Number = sqrt(22.5 * EPS * Book Value)
    if eps > 0 and book_value > 0:
        graham = (22.5 * eps * book_value) ** 0.5
        fair_values.append(graham)
    
    # Method 3: Simple DCF (5 years of FCF growth discounted at 10%)
    if fcf > 0 and shares > 0:
        discount_rate = 0.10
        terminal_multiple = 12
        fcf_per_share = fcf / shares
        
        dcf_value = 0
        for year in range(1, 6):
            future_fcf = fcf_per_share * ((1 + growth_rate) ** year)
            dcf_value += future_fcf / ((1 + discount_rate) ** year)
        
        # Terminal value
        terminal_value = (fcf_per_share * ((1 + growth_rate) ** 5) * terminal_multiple) / ((1 + discount_rate) ** 5)
        dcf_value += terminal_value
        fair_values.append(dcf_value)
    
    # Return average of methods
    if fair_values:
        return sum(fair_values) / len(fair_values)
    
    # Fallback: 1.3x current price
    return data.get('price', 0) * 1.3

def format_number(n):
    """Format large numbers with B/M/K suffix"""
    if n is None:
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

def get_recommendation(score, upside):
    """Get buy/hold/sell recommendation"""
    if score >= 70 and upside > 30:
        return {'signal': 'STRONG BUY', 'color': '#00d374', 'reason': 'High score with significant undervaluation'}
    elif score >= 60 and upside > 15:
        return {'signal': 'BUY', 'color': '#00d374', 'reason': 'Good fundamentals and undervalued'}
    elif score >= 50 and upside > 0:
        return {'signal': 'HOLD', 'color': '#ffb800', 'reason': 'Decent fundamentals, fair price'}
    elif score >= 40:
        return {'signal': 'WATCH', 'color': '#ffb800', 'reason': 'Some concerns, monitor closely'}
    else:
        return {'signal': 'AVOID', 'color': '#ff5252', 'reason': 'Does not meet investment criteria'}

# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/')
def index():
    """Serve the main HTML file"""
    return send_from_directory('.', 'index.html')

@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'tradier_configured': bool(TRADIER_API_KEY),
        'fmp_configured': bool(FMP_API_KEY)
    })

@app.route('/api/config', methods=['POST'])
def set_config():
    """Set API keys dynamically"""
    global TRADIER_API_KEY, FMP_API_KEY
    data = request.json or {}
    
    if 'tradier_key' in data:
        TRADIER_API_KEY = data['tradier_key']
    if 'fmp_key' in data:
        FMP_API_KEY = data['fmp_key']
    
    return jsonify({
        'status': 'ok',
        'tradier_configured': bool(TRADIER_API_KEY),
        'fmp_configured': bool(FMP_API_KEY)
    })

@app.route('/api/tickers')
def get_tickers():
    """Get all US stock tickers from GitHub"""
    cache_key = 'all_tickers'
    cached = get_cached(cache_key, ttl=3600)  # 1 hour cache
    if cached:
        return jsonify(cached)
    
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
        set_cached(cache_key, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e), 'tickers': []})

@app.route('/api/quote/<symbol>')
def get_quote(symbol):
    """Get stock quote from Tradier or FMP"""
    symbol = symbol.upper()
    cache_key = f'quote_{symbol}'
    cached = get_cached(cache_key, ttl=60)  # 1 min cache for quotes
    if cached:
        return jsonify(cached)
    
    result = {'symbol': symbol}
    
    # Try Tradier first
    if TRADIER_API_KEY:
        data = tradier_request('/markets/quotes', {'symbols': symbol})
        if data and 'quotes' in data and 'quote' in data['quotes']:
            q = data['quotes']['quote']
            result.update({
                'price': q.get('last', 0),
                'change': q.get('change', 0),
                'change_percent': q.get('change_percentage', 0),
                'volume': q.get('volume', 0),
                'high': q.get('high', 0),
                'low': q.get('low', 0),
                'open': q.get('open', 0),
                'prev_close': q.get('prevclose', 0),
                'week_52_high': q.get('week_52_high', 0),
                'week_52_low': q.get('week_52_low', 0),
                'name': q.get('description', symbol),
                'source': 'tradier'
            })
            set_cached(cache_key, result)
            return jsonify(result)
    
    # Fallback to FMP
    if FMP_API_KEY:
        data = fmp_request(f'/quote/{symbol}')
        if data and len(data) > 0:
            q = data[0]
            result.update({
                'price': q.get('price', 0),
                'change': q.get('change', 0),
                'change_percent': q.get('changesPercentage', 0),
                'volume': q.get('volume', 0),
                'high': q.get('dayHigh', 0),
                'low': q.get('dayLow', 0),
                'open': q.get('open', 0),
                'prev_close': q.get('previousClose', 0),
                'week_52_high': q.get('yearHigh', 0),
                'week_52_low': q.get('yearLow', 0),
                'name': q.get('name', symbol),
                'market_cap': q.get('marketCap', 0),
                'pe': q.get('pe', 0),
                'eps': q.get('eps', 0),
                'source': 'fmp'
            })
            set_cached(cache_key, result)
            return jsonify(result)
    
    return jsonify({'error': 'No API key configured', 'symbol': symbol})

@app.route('/api/analyze/<symbol>')
def analyze_stock(symbol):
    """
    Full stock analysis with Michael's criteria
    Returns fundamentals, fair value, and investment score
    """
    symbol = symbol.upper()
    cache_key = f'analysis_{symbol}'
    cached = get_cached(cache_key, ttl=300)  # 5 min cache
    if cached:
        return jsonify(cached)
    
    result = {
        'symbol': symbol,
        'timestamp': datetime.now().isoformat(),
    }
    
    # Get quote data
    quote = {'price': 0, 'name': symbol}
    
    if TRADIER_API_KEY:
        data = tradier_request('/markets/quotes', {'symbols': symbol})
        if data and 'quotes' in data and 'quote' in data['quotes']:
            q = data['quotes']['quote']
            quote = {
                'price': q.get('last', 0),
                'change_percent': q.get('change_percentage', 0),
                'week_52_high': q.get('week_52_high', 0),
                'week_52_low': q.get('week_52_low', 0),
                'name': q.get('description', symbol),
                'volume': q.get('volume', 0)
            }
    
    # Get fundamentals from FMP (required for deep analysis)
    fundamentals = {}
    if FMP_API_KEY:
        # Get quote if we don't have it from Tradier
        if quote['price'] == 0:
            fmp_quote = fmp_request(f'/quote/{symbol}')
            if fmp_quote and len(fmp_quote) > 0:
                q = fmp_quote[0]
                quote = {
                    'price': q.get('price', 0),
                    'change_percent': q.get('changesPercentage', 0),
                    'week_52_high': q.get('yearHigh', 0),
                    'week_52_low': q.get('yearLow', 0),
                    'name': q.get('name', symbol),
                    'volume': q.get('volume', 0),
                    'market_cap': q.get('marketCap', 0)
                }
        
        # Get ratios
        ratios = fmp_request(f'/ratios-ttm/{symbol}')
        if ratios and len(ratios) > 0:
            r = ratios[0]
            fundamentals['roa'] = (r.get('returnOnAssetsTTM') or 0) * 100
            fundamentals['roe'] = (r.get('returnOnEquityTTM') or 0) * 100
            fundamentals['profit_margin'] = (r.get('netProfitMarginTTM') or 0) * 100
            fundamentals['gross_margin'] = (r.get('grossProfitMarginTTM') or 0) * 100
            fundamentals['operating_margin'] = (r.get('operatingProfitMarginTTM') or 0) * 100
            fundamentals['ps_ratio'] = r.get('priceToSalesRatioTTM') or 0
            fundamentals['pb_ratio'] = r.get('priceBookValueRatioTTM') or 0
            fundamentals['pe_ratio'] = r.get('peRatioTTM') or 0
        
        # Get balance sheet
        balance = fmp_request(f'/balance-sheet-statement/{symbol}', {'limit': 1})
        if balance and len(balance) > 0:
            b = balance[0]
            fundamentals['cash'] = b.get('cashAndCashEquivalents') or 0
            fundamentals['debt'] = b.get('totalDebt') or 0
            fundamentals['total_assets'] = b.get('totalAssets') or 0
            fundamentals['total_equity'] = b.get('totalStockholdersEquity') or 0
        
        # Get cash flow
        cashflow = fmp_request(f'/cash-flow-statement/{symbol}', {'limit': 1})
        if cashflow and len(cashflow) > 0:
            c = cashflow[0]
            fundamentals['fcf'] = c.get('freeCashFlow') or 0
            fundamentals['operating_cf'] = c.get('operatingCashFlow') or 0
        
        # Get profile
        profile = fmp_request(f'/profile/{symbol}')
        if profile and len(profile) > 0:
            p = profile[0]
            quote['name'] = p.get('companyName') or quote.get('name', symbol)
            quote['industry'] = p.get('industry') or 'N/A'
            quote['sector'] = p.get('sector') or 'N/A'
            quote['market_cap'] = p.get('mktCap') or 0
            quote['website'] = p.get('website') or ''
            quote['description'] = p.get('description') or ''
            fundamentals['eps'] = p.get('eps') or 0
            if quote.get('price', 0) > 0 and quote.get('market_cap', 0) > 0:
                fundamentals['shares_outstanding'] = quote['market_cap'] / quote['price']
        
        # Get DCF value
        dcf = fmp_request(f'/discounted-cash-flow/{symbol}')
        if dcf and len(dcf) > 0:
            fundamentals['dcf_value'] = dcf[0].get('dcf') or 0
    
    # Combine data for analysis
    analysis_data = {
        'price': quote.get('price', 0),
        'roa': fundamentals.get('roa', 0),
        'roe': fundamentals.get('roe', 0),
        'cash': fundamentals.get('cash', 0),
        'debt': fundamentals.get('debt', 0),
        'profit_margin': fundamentals.get('profit_margin', 0),
        'ps_ratio': fundamentals.get('ps_ratio', 0),
        'fcf': fundamentals.get('fcf', 0),
        'eps': fundamentals.get('eps', 0),
        'shares_outstanding': fundamentals.get('shares_outstanding', 0)
    }
    
    # Calculate fair value
    fair_value = fundamentals.get('dcf_value') or calculate_fair_value(analysis_data)
    analysis_data['fair_value'] = fair_value
    
    # Calculate investment score using Michael's criteria
    score, checks = calculate_investment_score(analysis_data)
    
    # Calculate upside
    price = quote.get('price', 0)
    upside = ((fair_value - price) / price * 100) if price > 0 else 0
    
    result.update({
        'quote': quote,
        'fundamentals': fundamentals,
        'fair_value': round(fair_value, 2),
        'upside_percent': round(upside, 1),
        'investment_score': score,
        'checklist': checks,
        'recommendation': get_recommendation(score, upside)
    })
    
    set_cached(cache_key, result)
    return jsonify(result)

@app.route('/api/scan')
def scan_opportunities():
    """
    Scan multiple stocks and find opportunities
    Returns top stocks meeting Michael's criteria
    """
    # Get list of stocks to scan
    symbols = request.args.get('symbols', '')
    if symbols:
        tickers = [s.strip().upper() for s in symbols.split(',')][:30]  # Limit to 30
    else:
        # Default popular stocks
        tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 
                   'JPM', 'V', 'WMT', 'CRCT', 'ETSY', 'PINS', 'DIS', 'NFLX']
    
    opportunities = []
    
    for symbol in tickers:
        try:
            # Get analysis
            resp = analyze_stock(symbol)
            analysis = resp.get_json()
            if analysis and 'error' not in analysis:
                opportunities.append({
                    'symbol': symbol,
                    'name': analysis.get('quote', {}).get('name', symbol),
                    'price': analysis.get('quote', {}).get('price', 0),
                    'score': analysis.get('investment_score', 0),
                    'upside': analysis.get('upside_percent', 0),
                    'recommendation': analysis.get('recommendation', {}),
                    'roa': analysis.get('fundamentals', {}).get('roa', 0),
                    'roe': analysis.get('fundamentals', {}).get('roe', 0),
                })
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
    
    # Sort by score
    opportunities.sort(key=lambda x: x['score'], reverse=True)
    
    return jsonify({
        'opportunities': opportunities,
        'scanned': len(tickers),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/batch-quotes')
def batch_quotes():
    """Get quotes for multiple symbols at once"""
    symbols = request.args.get('symbols', '').upper()
    if not symbols:
        return jsonify({'error': 'No symbols provided'})
    
    result = {'quotes': []}
    
    if TRADIER_API_KEY:
        data = tradier_request('/markets/quotes', {'symbols': symbols})
        if data and 'quotes' in data:
            quotes = data['quotes'].get('quote', [])
            if isinstance(quotes, dict):
                quotes = [quotes]
            
            for q in quotes:
                result['quotes'].append({
                    'symbol': q.get('symbol'),
                    'name': q.get('description'),
                    'price': q.get('last', 0),
                    'change_percent': q.get('change_percentage', 0)
                })
    elif FMP_API_KEY:
        data = fmp_request(f'/quote/{symbols}')
        if data:
            for q in data:
                result['quotes'].append({
                    'symbol': q.get('symbol'),
                    'name': q.get('name'),
                    'price': q.get('price', 0),
                    'change_percent': q.get('changesPercentage', 0)
                })
    
    return jsonify(result)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║        Michael's Stock Analyzer - Backend Server          ║
    ╠═══════════════════════════════════════════════════════════╣
    ║  API Endpoints:                                           ║
    ║  • GET  /                - Web UI                         ║
    ║  • GET  /api/health      - Server health check            ║
    ║  • GET  /api/tickers     - All US stock symbols           ║
    ║  • GET  /api/quote/AAPL  - Get stock quote                ║
    ║  • GET  /api/analyze/AAPL - Full analysis                 ║
    ║  • GET  /api/scan        - Find opportunities             ║
    ║  • POST /api/config      - Set API keys                   ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Check API keys
    if not TRADIER_API_KEY and not FMP_API_KEY:
        print("⚠️  No API keys configured!")
        print("   Set TRADIER_API_KEY or FMP_API_KEY environment variable")
        print("   Or POST to /api/config with your keys")
        print("")
    else:
        if TRADIER_API_KEY:
            print("✅ Tradier API configured")
        if FMP_API_KEY:
            print("✅ FMP API configured")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
