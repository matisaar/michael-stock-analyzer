"""
Shared utilities for Michael's Stock Analyzer
"""
import os
import requests
from datetime import datetime

# =============================================================================
# API CONFIGURATION
# =============================================================================

TRADIER_API_KEY = os.environ.get('TRADIER_API_KEY', '')
TRADIER_BASE_URL = 'https://sandbox.tradier.com/v1'

FMP_API_KEY = os.environ.get('FMP_API_KEY', '')
FMP_BASE_URL = 'https://financialmodelingprep.com/api/v3'

GITHUB_STOCKS_URL = 'https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main'

# =============================================================================
# API REQUEST HELPERS
# =============================================================================

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
# FORMATTING HELPERS
# =============================================================================

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

# =============================================================================
# ANALYSIS FUNCTIONS
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
    """Calculate fair value using multiple methods"""
    eps = data.get('eps', 0) or 0
    book_value = data.get('book_value_per_share', 0) or 0
    fcf = data.get('fcf', 0) or 0
    shares = data.get('shares_outstanding', 0) or 0
    growth_rate = data.get('growth_rate', 0.05)
    
    fair_values = []
    
    # Method 1: P/E based (industry avg ~ 15)
    if eps > 0:
        pe_fair_value = eps * 15
        fair_values.append(pe_fair_value)
    
    # Method 2: Graham Number = sqrt(22.5 * EPS * Book Value)
    if eps > 0 and book_value > 0:
        graham = (22.5 * eps * book_value) ** 0.5
        fair_values.append(graham)
    
    # Method 3: Simple DCF
    if fcf > 0 and shares > 0:
        discount_rate = 0.10
        terminal_multiple = 12
        fcf_per_share = fcf / shares
        
        dcf_value = 0
        for year in range(1, 6):
            future_fcf = fcf_per_share * ((1 + growth_rate) ** year)
            dcf_value += future_fcf / ((1 + discount_rate) ** year)
        
        terminal_value = (fcf_per_share * ((1 + growth_rate) ** 5) * terminal_multiple) / ((1 + discount_rate) ** 5)
        dcf_value += terminal_value
        fair_values.append(dcf_value)
    
    if fair_values:
        return sum(fair_values) / len(fair_values)
    
    return data.get('price', 0) * 1.3

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
